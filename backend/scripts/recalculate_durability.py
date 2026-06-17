"""
Backfill durability analysis for all existing activities that lack it.

Usage (from the backend/ directory):
    python scripts/recalculate_durability.py [--user-id USER_ID] [--dry-run]

Options:
    --user-id USER_ID   Only process activities for this user (default: all users)
    --dry-run           Compute but do not write to the database
    --force             Re-compute even if a DurabilityAnalysis row already exists

The script mirrors the pipeline used at upload time in routes/activities.py,
including the TSB context fetch via the Banister EMA model.
"""

from __future__ import annotations

import argparse
import sys
import os
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import SessionLocal
import models
from utils.durability import validate_durability_calculation, calculate_durability

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── TSB helper (mirrors routes/activities.py) ─────────────────────────────────

def _get_tsb_at_date(db, user_id: int, target_date: datetime) -> float | None:
    """Banister EMA: CTL (42-day decay), ATL (7-day decay) → TSB = CTL − ATL."""
    from datetime import timedelta

    activities = (
        db.query(models.Activity)
        .filter(
            models.Activity.user_id == user_id,
            models.Activity.date < target_date,
        )
        .order_by(models.Activity.date)
        .all()
    )

    if not activities:
        return None

    daily_load: dict[str, float] = {}
    for a in activities:
        day = a.date.date().isoformat()
        tss = a.tss if a.tss is not None else (
            (a.duration_seconds / 3600) * 40 if a.duration_seconds else 0
        )
        daily_load[day] = daily_load.get(day, 0.0) + tss

    ctl, atl = 0.0, 0.0
    ctl_k, atl_k = 1 / 42, 1 / 7
    end_dt = target_date if isinstance(target_date, datetime) else \
        datetime.combine(target_date, datetime.min.time())
    cursor = datetime(
        activities[0].date.year,
        activities[0].date.month,
        activities[0].date.day,
    )

    while cursor < end_dt:
        day_str = cursor.date().isoformat()
        load = daily_load.get(day_str, 0.0)
        ctl = ctl + ctl_k * (load - ctl)
        atl = atl + atl_k * (load - atl)
        cursor += timedelta(days=1)

    return round(ctl - atl, 1)


# ── Main backfill logic ───────────────────────────────────────────────────────

def process_activity(db, activity: models.Activity, user: models.User,
                     dry_run: bool) -> str:
    """Return a status string: 'ok', 'skipped', 'ineligible', 'error'."""
    track_points = [
        {
            "timestamp":      tp.timestamp,
            "distance_m":     tp.distance_m,
            "elevation":      tp.elevation,
            "speed_kmh":      tp.speed_kmh,
            "heart_rate_bpm": tp.heart_rate_bpm,
            "power_w":        tp.power_w,
            "cadence_rpm":    tp.cadence_rpm,
        }
        for tp in activity.track_points
    ]

    can_calc, _, reason = validate_durability_calculation(
        activity.duration_seconds or 0,
        len(track_points),
        activity.notes,
        activity.avg_heart_rate_bpm,
        activity.max_heart_rate_bpm or user.max_hr,
    )
    if not can_calc:
        return f"ineligible ({reason[:60]})"

    try:
        tsb = _get_tsb_at_date(db, user.id, activity.date)
    except Exception:
        tsb = None

    try:
        result = calculate_durability(
            duration_seconds=activity.duration_seconds,
            track_points=track_points,
            climb_detections=[],
            max_hr=float(activity.max_heart_rate_bpm or user.max_hr or 0) or None,
            ftp=user.ftp,
            weight_kg=user.weight_kg,
            tsb_at_start=tsb,
            temperature_avg_c=activity.weather_temp_c,
            notes=activity.notes,
        )
    except Exception as exc:
        return f"error ({exc})"

    if result is None:
        return "ineligible (calculate_durability returned None)"

    if dry_run:
        return f"dry-run DI={result['durability_index']}"

    db_fields = {k: v for k, v in result.items() if k != "context"}

    existing = db.query(models.DurabilityAnalysis).filter(
        models.DurabilityAnalysis.activity_id == activity.id
    ).first()

    if existing:
        for k, v in db_fields.items():
            setattr(existing, k, v)
    else:
        row = models.DurabilityAnalysis(activity_id=activity.id, **db_fields)
        db.add(row)

    activity.durability_index = result["durability_index"]
    db.commit()
    return f"ok DI={result['durability_index']} ({result['durability_category']})"


def main():
    parser = argparse.ArgumentParser(description="Backfill durability analysis for all activities")
    parser.add_argument("--user-id", type=int, default=None, help="Process only this user")
    parser.add_argument("--dry-run", action="store_true", help="Compute but do not write")
    parser.add_argument("--force",   action="store_true", help="Recompute even if data already exists")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        user_q = db.query(models.User)
        if args.user_id:
            user_q = user_q.filter(models.User.id == args.user_id)
        users = user_q.all()

        total = skipped = done = errors = ineligible = 0

        for user in users:
            activity_q = (
                db.query(models.Activity)
                .filter(models.Activity.user_id == user.id)
                .order_by(models.Activity.date)
            )

            if not args.force:
                existing_ids = {
                    r.activity_id
                    for r in db.query(models.DurabilityAnalysis.activity_id)
                    .join(models.Activity, models.Activity.id == models.DurabilityAnalysis.activity_id)
                    .filter(models.Activity.user_id == user.id)
                    .all()
                }
                activity_q = activity_q.filter(
                    ~models.Activity.id.in_(existing_ids)
                ) if existing_ids else activity_q

            activities = activity_q.all()
            log.info("User %d — %d activities to process", user.id, len(activities))

            for activity in activities:
                total += 1
                status = process_activity(db, activity, user, args.dry_run)
                prefix = f"  activity {activity.id:>6} ({activity.date.date().isoformat()})"

                if status.startswith("ok") or status.startswith("dry-run"):
                    log.info("%s → %s", prefix, status)
                    done += 1
                elif status.startswith("ineligible"):
                    log.debug("%s → %s", prefix, status)
                    ineligible += 1
                else:
                    log.warning("%s → %s", prefix, status)
                    errors += 1

        log.info(
            "Done. total=%d  computed=%d  ineligible=%d  errors=%d  dry_run=%s",
            total, done, ineligible, errors, args.dry_run,
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
