"""
Recalculates climb detections and power estimates for all existing activities.

Run with:
    cd backend && python -m scripts.recalculate_climbs
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
import models
from utils.climb_detection import detect_climbs
from utils.power_estimation import estimate_climbing_power, BIKE_DEFAULTS


def recalculate():
    db = SessionLocal()
    try:
        activities = db.query(models.Activity).all()
        print(f"Processing {len(activities)} activities...")

        total_climbs = 0
        for activity in activities:
            user = db.query(models.User).filter(models.User.id == activity.user_id).first()
            if not user or not user.weight_kg:
                continue

            track_points = [
                {
                    "timestamp": tp.timestamp,
                    "lat": tp.lat,
                    "lon": tp.lon,
                    "elevation": tp.elevation,
                    "speed_kmh": tp.speed_kmh,
                    "heart_rate_bpm": tp.heart_rate_bpm,
                    "distance_m": tp.distance_m,
                }
                for tp in activity.track_points
            ]
            if not track_points:
                continue

            # Remove existing climb detections
            db.query(models.ClimbDetection).filter(
                models.ClimbDetection.activity_id == activity.id
            ).delete()

            bike_params = dict(BIKE_DEFAULTS.get(user.bike_type, BIKE_DEFAULTS[None]))
            if user.bike_weight_kg:
                bike_params["bike_weight_kg"] = user.bike_weight_kg
            if user.calibrated_cda:
                bike_params["cda"] = user.calibrated_cda
            if user.calibrated_crr:
                bike_params["crr"] = user.calibrated_crr

            climbs = detect_climbs(track_points)
            activity.climb_count = len(climbs)

            climbs_with_power = []
            for climb in climbs:
                seg_pts = track_points[climb["start_trackpoint_idx"]:climb["end_trackpoint_idx"] + 1]
                elev_vals = [p.get("elevation") for p in seg_pts if p.get("elevation") is not None]
                avg_alt = sum(elev_vals) / len(elev_vals) if elev_vals else None

                power_est = estimate_climbing_power(
                    climb, user.weight_kg,
                    bike_weight_kg=bike_params["bike_weight_kg"],
                    crr=bike_params["crr"],
                    cda=bike_params["cda"],
                    altitude_m=avg_alt,
                )
                method = "calibrated" if user.calibrated_cda else "physics"

                db_climb = models.ClimbDetection(
                    activity_id=activity.id,
                    start_trackpoint_idx=climb["start_trackpoint_idx"],
                    end_trackpoint_idx=climb["end_trackpoint_idx"],
                    start_distance_m=climb["start_distance_m"],
                    end_distance_m=climb["end_distance_m"],
                    distance_m=climb["distance_m"],
                    elevation_gain_m=climb["elevation_gain_m"],
                    avg_gradient_pct=climb["avg_gradient_pct"],
                    max_gradient_pct=climb["max_gradient_pct"],
                    duration_seconds=climb["duration_seconds"],
                    avg_speed_kmh=climb["avg_speed_kmh"],
                    avg_heart_rate=climb["avg_heart_rate"],
                    max_heart_rate=climb["max_heart_rate"],
                    vam_m_per_hour=climb["vam_m_per_hour"],
                    estimated_power_w=power_est["estimated_power_w"],
                    estimated_power_low_w=power_est["estimated_power_low_w"],
                    estimated_power_high_w=power_est["estimated_power_high_w"],
                    estimated_wkg=power_est["estimated_wkg"],
                    estimation_quality=power_est["estimation_quality"],
                    estimation_method=method,
                    pacing_type=climb["pacing_type"],
                    first_half_speed=climb["first_half_speed"],
                    second_half_speed=climb["second_half_speed"],
                )
                db.add(db_climb)

                if power_est["estimated_power_w"] is not None:
                    climbs_with_power.append({
                        "power_w": power_est["estimated_power_w"],
                        "duration_s": climb["duration_seconds"],
                    })

            if climbs_with_power:
                total_dur = sum(c["duration_s"] for c in climbs_with_power)
                if total_dur > 0:
                    activity.total_climbing_power_avg_w = round(
                        sum(c["power_w"] * c["duration_s"] for c in climbs_with_power) / total_dur, 1
                    )
                    activity.total_climbing_wkg_avg = round(
                        activity.total_climbing_power_avg_w / user.weight_kg, 2
                    )

            total_climbs += len(climbs)
            if len(climbs) > 0:
                print(f"  Activity {activity.id} ({activity.name}): {len(climbs)} climb(s) detected")

        db.commit()
        print(f"Done. Total climbs detected: {total_climbs}")
    finally:
        db.close()


if __name__ == "__main__":
    recalculate()
