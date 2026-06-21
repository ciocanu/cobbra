"""One-shot: recalculate climbs for a single activity ID passed as argument."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
import models
from utils.climb_detection import detect_climbs
from utils.power_estimation import estimate_climbing_power, BIKE_DEFAULTS

activity_id = int(sys.argv[1]) if len(sys.argv) > 1 else 220

db = SessionLocal()
try:
    activity = db.get(models.Activity, activity_id)
    if not activity:
        print(f"Activity {activity_id} not found")
        sys.exit(1)
    user = db.get(models.User, activity.user_id)
    if not user or not user.weight_kg:
        print("User has no weight set — cannot estimate power")
        sys.exit(1)

    track_points = [
        {
            "timestamp": tp.timestamp,
            "lat": tp.lat, "lon": tp.lon,
            "elevation": tp.elevation,
            "speed_kmh": tp.speed_kmh,
            "heart_rate_bpm": tp.heart_rate_bpm,
            "distance_m": tp.distance_m,
        }
        for tp in activity.track_points
    ]
    print(f"Track points: {len(track_points)}")

    db.query(models.ClimbDetection).filter(models.ClimbDetection.activity_id == activity_id).delete()

    bike_params = dict(BIKE_DEFAULTS.get(user.bike_type, BIKE_DEFAULTS[None]))
    if user.bike_weight_kg:
        bike_params["bike_weight_kg"] = user.bike_weight_kg
    if user.calibrated_cda:
        bike_params["cda"] = user.calibrated_cda
    if user.calibrated_crr:
        bike_params["crr"] = user.calibrated_crr

    climbs = detect_climbs(track_points)
    activity.climb_count = len(climbs)
    print(f"Climbs detected: {len(climbs)}")

    for climb in climbs:
        seg_pts = track_points[climb["start_trackpoint_idx"]:climb["end_trackpoint_idx"] + 1]
        elev_vals = [p["elevation"] for p in seg_pts if p["elevation"] is not None]
        avg_alt = sum(elev_vals) / len(elev_vals) if elev_vals else None

        power_est = estimate_climbing_power(
            climb, user.weight_kg,
            bike_weight_kg=bike_params["bike_weight_kg"],
            crr=bike_params["crr"],
            cda=bike_params["cda"],
            altitude_m=avg_alt,
        )
        db.add(models.ClimbDetection(
            activity_id=activity_id,
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
            estimation_method="calibrated" if user.calibrated_cda else "physics",
            pacing_type=climb["pacing_type"],
            first_half_speed=climb["first_half_speed"],
            second_half_speed=climb["second_half_speed"],
        ))
        print(f"  {climb['elevation_gain_m']}m @ {climb['avg_gradient_pct']}% avg — {climb['duration_seconds']}s — power: {power_est['estimated_power_w']}W")

    db.commit()
    print("Done.")
finally:
    db.close()
