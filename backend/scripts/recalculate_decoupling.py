"""
Backfill adjusted decoupling for all existing activities that lack it.

Usage (from the backend/ directory):
    python scripts/recalculate_decoupling.py [--user-id USER_ID] [--dry-run] [--force]

Options:
    --user-id USER_ID   Only process activities for this user (default: all users)
    --dry-run           Compute but do not write to the database
    --force             Re-compute even if decoupling values already exist

The script mirrors the pipeline used at upload time in routes/activities.py.
"""

from __future__ import annotations

import argparse
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import SessionLocal
import models
from utils.decoupling import calculate_adjusted_decoupling

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def process_activity(
    db,
    activity: models.Activity,
    user: models.User,
    dry_run: bool,
) -> str:
    """Return a short status string."""
    track_points = [
        {
            "timestamp":      tp.timestamp,
            "distance_m":     tp.distance_m,
            "elevation":      tp.elevation,
            "speed_kmh":      tp.speed_kmh,
            "heart_rate_bpm": tp.heart_rate_bpm,
            "power_w":        tp.power_w,
        }
        for tp in activity.track_points
    ]

    if not track_points:
        return "skipped (no track points)"

    try:
        result = calculate_adjusted_decoupling(activity, track_points, user)
    except Exception as exc:
        return f"error ({exc})"

    if result is None:
        return "ineligible (returned None)"

    if result.get("decoupling_adjusted") is None:
        return f"ineligible ({result.get('decoupling_warning', 'unknown reason')[:80]})"

    if dry_run:
        return (
            f"dry-run adj={result['decoupling_adjusted']:.1f}% "
            f"raw={result['decoupling_raw']:.1f}% "
            f"quality={result['decoupling_quality']}"
        )

    activity.decoupling_raw             = result["decoupling_raw"]
    activity.decoupling_adjusted        = result["decoupling_adjusted"]
    activity.decoupling_components_json = result["decoupling_components_json"]
    activity.decoupling_quality         = result["decoupling_quality"]
    activity.decoupling_warning         = result["decoupling_warning"]
    db.commit()

    return (
        f"ok adj={result['decoupling_adjusted']:.1f}% "
        f"raw={result['decoupling_raw']:.1f}% "
        f"quality={result['decoupling_quality']}"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Backfill adjusted decoupling for all activities"
    )
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

        total = done = ineligible = skipped = errors = 0

        for user in users:
            activity_q = (
                db.query(models.Activity)
                .filter(models.Activity.user_id == user.id)
                .order_by(models.Activity.date)
            )

            if not args.force:
                activity_q = activity_q.filter(
                    models.Activity.decoupling_adjusted.is_(None)
                )

            activities = activity_q.all()
            log.info("User %d — %d activities to process", user.id, len(activities))

            for activity in activities:
                total += 1
                status = process_activity(db, activity, user, args.dry_run)
                prefix = f"  activity {activity.id:>6} ({activity.date.date().isoformat()})"

                if status.startswith("ok") or status.startswith("dry-run"):
                    log.info("%s → %s", prefix, status)
                    done += 1
                elif status.startswith("skipped"):
                    log.debug("%s → %s", prefix, status)
                    skipped += 1
                elif status.startswith("ineligible"):
                    log.debug("%s → %s", prefix, status)
                    ineligible += 1
                else:
                    log.warning("%s → %s", prefix, status)
                    errors += 1

        log.info(
            "Done. total=%d  computed=%d  ineligible=%d  skipped=%d  errors=%d  dry_run=%s",
            total, done, ineligible, skipped, errors, args.dry_run,
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
