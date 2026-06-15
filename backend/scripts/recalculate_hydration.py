"""
Backfill HydrationAnalysis for activities that predate the feature.

Usage (run from the backend directory):
    python scripts/recalculate_hydration.py [--all] [--user-id N] [--dry-run]

Options:
    --all        Recompute ALL existing analyses, not just missing ones
    --user-id N  Restrict to a single user
    --dry-run    Print what would be done without writing to the database
"""

from __future__ import annotations
import sys
import os
import argparse
import logging

# Allow running from the backend directory without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("DATABASE_URL", "sqlite:///./cycling.db")

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.orm import Session
from database import SessionLocal
import models
from utils.hydration import build_analysis, update_heat_adaptation

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _intensity_factor(activity: models.Activity, user: models.User) -> float:
    if activity.normalized_power_w and user.ftp and user.ftp > 0:
        return min(1.0, activity.normalized_power_w / user.ftp)
    if activity.avg_heart_rate_bpm and user.max_hr and user.max_hr > 0:
        lthr = 0.85 * user.max_hr
        return min(1.0, activity.avg_heart_rate_bpm / lthr)
    return 0.65


def process_activity(
    db: Session,
    activity: models.Activity,
    user: models.User,
    force: bool = False,
    dry_run: bool = False,
) -> bool:
    """Compute and upsert HydrationAnalysis for one activity. Returns True if written."""
    duration_h = (activity.elapsed_seconds or activity.duration_seconds or 0) / 3600
    if duration_h < 0.1:
        return False   # skip sub-6-min efforts

    existing = db.query(models.HydrationAnalysis).filter(
        models.HydrationAnalysis.activity_id == activity.id
    ).first()

    if existing and not force:
        return False

    temp_c = (
        activity.sensor_temp_avg_c
        if activity.sensor_temp_avg_c is not None
        else (activity.weather_temp_c if activity.weather_temp_c is not None else 20.0)
    )
    intensity = _intensity_factor(activity, user)

    is_indoor = activity.ride_environment == "indoor"

    data = build_analysis(
        temp_c=temp_c,
        humidity_pct=activity.weather_humidity_pct,
        wind_speed_kmh=activity.weather_wind_kmh,
        max_temp_c=activity.sensor_temp_max_c,
        duration_h=duration_h,
        intensity_factor=intensity,
        intake_ml=activity.hydration_ml,
        weight_kg=user.weight_kg,
        user_calibrated_ml_h=user.sweat_rate_ml_per_hour,
        heat_adaptation=user.heat_adaptation_level,
        is_indoor=is_indoor,
    )

    if dry_run:
        log.info(
            "  [DRY RUN] activity %d — sweat %.0f ml, risk=%s, quality=%s",
            activity.id, data["estimated_total_sweat_ml"], data["risk_level"], data["analysis_quality"],
        )
        return True

    if existing:
        for k, v in data.items():
            setattr(existing, k, v)
    else:
        db.add(models.HydrationAnalysis(activity_id=activity.id, **data))

    return True


def recalculate_heat_adaptation(db: Session, user: models.User, dry_run: bool = False) -> None:
    """Recompute heat_rides_last_14d and heat_adaptation_level from scratch.

    Counts activities in the last 14 days where weather_temp_c >= 27.
    """
    from datetime import datetime, timedelta
    from sqlalchemy import case, func as _func
    cutoff = datetime.utcnow() - timedelta(days=14)
    # Use sensor temp when available; fall back to weather API temp
    effective_temp = _func.coalesce(models.Activity.sensor_temp_avg_c, models.Activity.weather_temp_c)
    hot_rides = db.query(models.Activity).filter(
        models.Activity.user_id == user.id,
        models.Activity.date >= cutoff,
        effective_temp >= 27.0,
    ).count()

    _, level = update_heat_adaptation(hot_rides, False, 0.0)  # counter already accurate

    if not dry_run:
        user.heat_rides_last_14d = hot_rides
        user.heat_adaptation_level = level
    log.info(
        "  user %d: %d hot rides → adaptation=%s%s",
        user.id, hot_rides, level, " [DRY RUN]" if dry_run else "",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill hydration analyses")
    parser.add_argument("--all",     dest="force",   action="store_true", help="Recompute all, not just missing")
    parser.add_argument("--user-id", dest="user_id", type=int, default=None)
    parser.add_argument("--dry-run", dest="dry_run", action="store_true")
    args = parser.parse_args()

    db: Session = SessionLocal()
    try:
        user_query = db.query(models.User)
        if args.user_id:
            user_query = user_query.filter(models.User.id == args.user_id)
        users = user_query.all()

        if not users:
            log.warning("No users found (user_id=%s)", args.user_id)
            return

        total_written = 0
        total_skipped = 0

        for user in users:
            log.info("Processing user %d (%s)…", user.id, user.username)

            activity_query = db.query(models.Activity).filter(
                models.Activity.user_id == user.id
            ).order_by(models.Activity.date)
            activities = activity_query.all()

            written = 0
            skipped = 0
            for activity in activities:
                ok = process_activity(db, activity, user, force=args.force, dry_run=args.dry_run)
                if ok:
                    written += 1
                else:
                    skipped += 1

            if not args.dry_run and written > 0:
                db.flush()

            recalculate_heat_adaptation(db, user, dry_run=args.dry_run)

            log.info("  %d written, %d skipped (already had analysis)", written, skipped)
            total_written += written
            total_skipped += skipped

        if not args.dry_run:
            db.commit()
            log.info("Committed. Total: %d written, %d skipped.", total_written, total_skipped)
        else:
            log.info("Dry run complete. %d would be written, %d already exist.", total_written, total_skipped)

    except Exception as e:
        db.rollback()
        log.error("Error: %s", e)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
