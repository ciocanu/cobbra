"""
Backfill indoor/outdoor detection and correction for all existing activities.

Usage (from the backend/ directory):
    python scripts/recalculate_indoor_outdoor.py [--user-id USER_ID] [--dry-run] [--force]

Options:
    --user-id USER_ID   Only process activities for this user (default: all users)
    --dry-run           Detect but do not write to the database
    --force             Re-detect even if ride_environment is already set

The script mirrors the detection pipeline used at upload time in routes/activities.py.
After processing all activities it refreshes each user's IndoorOutdoorProfile.
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
from utils.indoor_detection import detect_ride_environment
from utils.indoor_outdoor_gap import apply_correction_factors, update_indoor_outdoor_gap

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def _get_track_points(db, activity_id: int) -> list[dict]:
    pts = (
        db.query(models.TrackPoint)
        .filter(models.TrackPoint.activity_id == activity_id)
        .order_by(models.TrackPoint.id)
        .all()
    )
    return [
        {
            "lat":           p.lat,
            "lon":           p.lon,
            "speed_kmh":     p.speed_kmh,
            "power_w":       p.power_w,
            "heart_rate_bpm": p.heart_rate_bpm,
            "cadence_rpm":   p.cadence_rpm,
        }
        for p in pts
    ]


def process_activities(
    db,
    user_id: int | None,
    force: bool,
    dry_run: bool,
) -> tuple[int, int, int]:
    """Detect environment for activities; returns (processed, skipped, errors)."""
    query = db.query(models.Activity)
    if user_id is not None:
        query = query.filter(models.Activity.user_id == user_id)
    if not force:
        query = query.filter(models.Activity.ride_environment.is_(None))

    activities = query.order_by(models.Activity.date).all()
    log.info("Found %d activities to process.", len(activities))

    processed = skipped = errors = 0

    for act in activities:
        try:
            pts = _get_track_points(db, act.id)
            if not pts:
                log.debug("Activity %d has no track points — skipping.", act.id)
                skipped += 1
                continue

            env = detect_ride_environment(
                pts,
                activity_name=act.name,
            )

            if dry_run:
                log.info(
                    "[dry-run] Activity %d (%s): %s via %s",
                    act.id, act.name[:40], env["environment"], env["source"],
                )
                processed += 1
                continue

            act.ride_environment        = env["environment"]
            act.ride_environment_source = "auto_detected"
            act.indoor_platform         = env.get("platform")

            # Apply correction if indoor and profile exists
            if env["environment"] == "indoor":
                profile = (
                    db.query(models.IndoorOutdoorProfile)
                    .filter(models.IndoorOutdoorProfile.user_id == act.user_id)
                    .first()
                )
                if profile and (
                    profile.power_gap_pct is not None
                    or profile.manual_power_gap_pct is not None
                ):
                    correction = apply_correction_factors(act, profile)
                    act.power_correction_factor = correction["power_correction_factor"]
                    act.hr_correction_factor    = correction["hr_correction_factor"]
                    act.corrected_tss           = correction["corrected_tss"]
            else:
                act.power_correction_factor = None
                act.hr_correction_factor    = None
                act.corrected_tss           = None

            log.info(
                "Activity %d (%s): %s via %s%s",
                act.id, act.name[:40], env["environment"], env["source"],
                f" (corrected_tss={act.corrected_tss})" if act.corrected_tss else "",
            )
            processed += 1

        except Exception as exc:
            log.error("Activity %d: unexpected error — %s", act.id, exc)
            errors += 1

    if not dry_run and processed > 0:
        db.commit()
        log.info("Committed %d updates.", processed)

    return processed, skipped, errors


def refresh_profiles(db, user_id: int | None, dry_run: bool) -> int:
    """Recalculate IndoorOutdoorProfile for affected users."""
    query = db.query(models.User.id)
    if user_id is not None:
        query = query.filter(models.User.id == user_id)
    user_ids = [row[0] for row in query.all()]

    refreshed = 0
    for uid in user_ids:
        if dry_run:
            log.info("[dry-run] Would refresh profile for user %d.", uid)
            refreshed += 1
            continue
        try:
            update_indoor_outdoor_gap(uid, db)
            log.info("Refreshed IndoorOutdoorProfile for user %d.", uid)
            refreshed += 1
        except Exception as exc:
            log.warning("Could not refresh profile for user %d: %s", uid, exc)

    return refreshed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=int, default=None, help="Limit to a specific user")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to the database")
    parser.add_argument("--force",   action="store_true", help="Re-detect already-classified activities")
    args = parser.parse_args()

    if args.dry_run:
        log.info("DRY RUN — no database writes will be made.")

    db = SessionLocal()
    try:
        t0 = datetime.utcnow()

        processed, skipped, errors = process_activities(
            db,
            user_id=args.user_id,
            force=args.force,
            dry_run=args.dry_run,
        )

        refreshed = refresh_profiles(db, user_id=args.user_id, dry_run=args.dry_run)

        elapsed = (datetime.utcnow() - t0).total_seconds()
        log.info(
            "Done in %.1f s — processed=%d  skipped=%d  errors=%d  profiles_refreshed=%d",
            elapsed, processed, skipped, errors, refreshed,
        )

        if errors > 0:
            sys.exit(1)

    finally:
        db.close()


if __name__ == "__main__":
    main()
