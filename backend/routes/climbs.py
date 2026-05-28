from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
from database import get_db
from auth import get_current_user
import models
from utils.power_calibration import calibrate_from_known_ftp, calibrate_from_known_climb
from utils.power_estimation import estimate_climbing_power, BIKE_DEFAULTS

router = APIRouter()


@router.get("/activities/{activity_id}/climbs")
def get_activity_climbs(
    activity_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    activity = db.query(models.Activity).filter(
        models.Activity.id == activity_id,
        models.Activity.user_id == current_user.id,
    ).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    climbs = db.query(models.ClimbDetection).filter(
        models.ClimbDetection.activity_id == activity_id
    ).all()

    return [_climb_to_dict(c) for c in climbs]


class CalibrationInput(BaseModel):
    method: str                   # "ftp" | "climb"
    value: float                  # FTP in watts or known power in watts
    activity_id: Optional[int] = None
    climb_id: Optional[int] = None


@router.post("/user/calibrate-power")
def calibrate_power(
    data: CalibrationInput,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user.weight_kg:
        raise HTTPException(status_code=400, detail="Set your body weight in Settings before calibrating.")

    if data.method == "ftp":
        if data.value < 50 or data.value > 600:
            raise HTTPException(status_code=400, detail="FTP must be between 50 and 600 W.")
        all_climbs = db.query(models.ClimbDetection).join(models.Activity).filter(
            models.Activity.user_id == current_user.id
        ).all()
        if not all_climbs:
            raise HTTPException(status_code=400, detail="No climbs found. Upload activities with climbs first.")
        result = calibrate_from_known_ftp(current_user, all_climbs, data.value)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

    elif data.method == "climb":
        if not data.climb_id:
            raise HTTPException(status_code=400, detail="Provide climb_id for climb-based calibration.")
        climb = db.query(models.ClimbDetection).join(models.Activity).filter(
            models.ClimbDetection.id == data.climb_id,
            models.Activity.user_id == current_user.id,
        ).first()
        if not climb:
            raise HTTPException(status_code=404, detail="Climb not found.")
        result = calibrate_from_known_climb(current_user, climb, data.value)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
    else:
        raise HTTPException(status_code=400, detail="method must be 'ftp' or 'climb'")

    current_user.calibrated_cda = result["calibrated_cda"]
    current_user.calibration_source = result["calibration_source"]
    db.commit()

    # Recalculate all climb estimations with new CdA
    bike_params = BIKE_DEFAULTS.get(current_user.bike_type, BIKE_DEFAULTS[None])
    bike_weight = current_user.bike_weight_kg or bike_params["bike_weight_kg"]
    cda = current_user.calibrated_cda
    crr = current_user.calibrated_crr or bike_params["crr"]

    all_climbs = db.query(models.ClimbDetection).join(models.Activity).filter(
        models.Activity.user_id == current_user.id
    ).all()
    for c in all_climbs:
        power_est = estimate_climbing_power(
            _climb_to_dict(c), current_user.weight_kg,
            bike_weight_kg=bike_weight, crr=crr, cda=cda
        )
        c.estimated_power_w = power_est["estimated_power_w"]
        c.estimated_power_low_w = power_est["estimated_power_low_w"]
        c.estimated_power_high_w = power_est["estimated_power_high_w"]
        c.estimated_wkg = power_est["estimated_wkg"]
        c.estimation_quality = power_est["estimation_quality"]
        c.estimation_method = "calibrated"
    db.commit()

    return {
        "calibrated_cda": result["calibrated_cda"],
        "calibration_source": result["calibration_source"],
        "climbs_recalculated": len(all_climbs),
    }


@router.delete("/user/calibrate-power")
def reset_calibration(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    current_user.calibrated_cda = None
    current_user.calibrated_crr = None
    current_user.calibration_source = None
    db.commit()

    bike_params = BIKE_DEFAULTS.get(current_user.bike_type, BIKE_DEFAULTS[None])
    bike_weight = current_user.bike_weight_kg or bike_params["bike_weight_kg"]
    cda = bike_params["cda"]
    crr = bike_params["crr"]

    if current_user.weight_kg:
        all_climbs = db.query(models.ClimbDetection).join(models.Activity).filter(
            models.Activity.user_id == current_user.id
        ).all()
        for c in all_climbs:
            power_est = estimate_climbing_power(
                _climb_to_dict(c), current_user.weight_kg,
                bike_weight_kg=bike_weight, crr=crr, cda=cda
            )
            c.estimated_power_w = power_est["estimated_power_w"]
            c.estimated_power_low_w = power_est["estimated_power_low_w"]
            c.estimated_power_high_w = power_est["estimated_power_high_w"]
            c.estimated_wkg = power_est["estimated_wkg"]
            c.estimation_quality = power_est["estimation_quality"]
            c.estimation_method = "physics"
        db.commit()

    return {"message": "Calibration reset to defaults"}


def _climb_to_dict(c: models.ClimbDetection) -> dict:
    return {
        "id": c.id,
        "activity_id": c.activity_id,
        "start_trackpoint_idx": c.start_trackpoint_idx,
        "end_trackpoint_idx": c.end_trackpoint_idx,
        "start_distance_m": c.start_distance_m,
        "end_distance_m": c.end_distance_m,
        "distance_m": c.distance_m,
        "elevation_gain_m": c.elevation_gain_m,
        "avg_gradient_pct": c.avg_gradient_pct,
        "max_gradient_pct": c.max_gradient_pct,
        "duration_seconds": c.duration_seconds,
        "avg_speed_kmh": c.avg_speed_kmh,
        "avg_heart_rate": c.avg_heart_rate,
        "max_heart_rate": c.max_heart_rate,
        "vam_m_per_hour": c.vam_m_per_hour,
        "estimated_power_w": c.estimated_power_w,
        "estimated_power_low_w": c.estimated_power_low_w,
        "estimated_power_high_w": c.estimated_power_high_w,
        "estimated_wkg": c.estimated_wkg,
        "estimation_quality": c.estimation_quality,
        "estimation_method": c.estimation_method,
        "pacing_type": c.pacing_type,
        "first_half_speed": c.first_half_speed,
        "second_half_speed": c.second_half_speed,
    }
