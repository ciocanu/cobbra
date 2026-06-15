import json
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_user
import models
import schemas
from utils.hydration import build_analysis as build_hydration_analysis, update_heat_adaptation
from utils.decoupling import calculate_adjusted_decoupling

router = APIRouter()


def _get_activity_owned(activity_id: int, user, db: Session) -> models.Activity:
    activity = db.query(models.Activity).filter(
        models.Activity.id == activity_id,
        models.Activity.user_id == user.id,
    ).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity


def _run_analysis(activity: models.Activity, user: models.User, db: Session) -> models.HydrationAnalysis:
    """(Re)compute and persist HydrationAnalysis. Returns the saved row."""
    temp_c = (
        activity.sensor_temp_avg_c
        if activity.sensor_temp_avg_c is not None
        else (activity.weather_temp_c if activity.weather_temp_c is not None else 20.0)
    )
    duration_h = (activity.elapsed_seconds or activity.duration_seconds or 0) / 3600

    if activity.normalized_power_w and user.ftp and user.ftp > 0:
        intensity_factor = min(1.0, activity.normalized_power_w / user.ftp)
    elif activity.avg_heart_rate_bpm and user.max_hr and user.max_hr > 0:
        intensity_factor = min(1.0, activity.avg_heart_rate_bpm / user.max_hr)
    else:
        intensity_factor = 0.65

    is_indoor = activity.ride_environment == "indoor"

    data = build_hydration_analysis(
        temp_c=temp_c,
        humidity_pct=activity.weather_humidity_pct,
        wind_speed_kmh=activity.weather_wind_kmh,
        max_temp_c=activity.sensor_temp_max_c,
        duration_h=duration_h,
        intensity_factor=intensity_factor,
        intake_ml=activity.hydration_ml,
        weight_kg=user.weight_kg,
        user_calibrated_ml_h=user.sweat_rate_ml_per_hour,
        heat_adaptation=user.heat_adaptation_level,
        is_indoor=is_indoor,
    )

    row = db.query(models.HydrationAnalysis).filter(
        models.HydrationAnalysis.activity_id == activity.id
    ).first()
    if row:
        for k, v in data.items():
            setattr(row, k, v)
    else:
        row = models.HydrationAnalysis(activity_id=activity.id, **data)
        db.add(row)

    db.commit()
    db.refresh(row)
    return row


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/activities/{activity_id}/hydration", response_model=schemas.HydrationAnalysisOut)
def get_hydration(
    activity_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    activity = _get_activity_owned(activity_id, current_user, db)

    row = db.query(models.HydrationAnalysis).filter(
        models.HydrationAnalysis.activity_id == activity_id
    ).first()

    if not row:
        # Compute on-demand for activities uploaded before this feature existed
        row = _run_analysis(activity, current_user, db)

    return row


@router.patch("/activities/{activity_id}/hydration", response_model=schemas.HydrationAnalysisOut)
def update_hydration_intake(
    activity_id: int,
    intake_ml: int = Body(..., embed=True, ge=0, le=20000),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Log (or update) post-ride fluid intake and recompute analysis."""
    activity = _get_activity_owned(activity_id, current_user, db)
    activity.hydration_ml = intake_ml
    db.flush()
    row = _run_analysis(activity, current_user, db)

    # Recalculate adjusted decoupling — hydration affects the hydration drift correction
    try:
        track_points = [
            {c.name: getattr(tp, c.name) for c in tp.__table__.columns}
            for tp in activity.track_points
        ]
        result = calculate_adjusted_decoupling(activity, track_points, current_user)
        if result is not None:
            activity.decoupling_raw             = result.get("decoupling_raw")
            activity.decoupling_adjusted        = result.get("decoupling_adjusted")
            activity.decoupling_components_json = result.get("decoupling_components_json")
            activity.decoupling_quality         = result.get("decoupling_quality")
            activity.decoupling_warning         = result.get("decoupling_warning")
            db.commit()
    except Exception:
        pass  # non-fatal; hydration row was already saved

    return row


@router.patch("/user/sweat-rate", response_model=schemas.HeatProfileOut)
def set_sweat_rate_directly(
    sweat_rate_ml_per_hour: int = Body(..., embed=True, ge=100, le=4000),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Set sweat rate directly (ml/h) without a formal sweat test."""
    current_user.sweat_rate_ml_per_hour = float(sweat_rate_ml_per_hour)
    db.commit()
    db.refresh(current_user)
    return {
        "heat_adaptation_level":   current_user.heat_adaptation_level,
        "heat_rides_last_14d":     current_user.heat_rides_last_14d or 0,
        "sweat_rate_ml_per_hour":  current_user.sweat_rate_ml_per_hour,
        "has_calibrated_rate":     True,
    }


@router.delete("/user/sweat-rate", response_model=schemas.HeatProfileOut)
def reset_sweat_rate(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Clear the calibrated sweat rate — subsequent analyses use the population model."""
    current_user.sweat_rate_ml_per_hour = None
    db.commit()
    db.refresh(current_user)
    return {
        "heat_adaptation_level":  current_user.heat_adaptation_level,
        "heat_rides_last_14d":    current_user.heat_rides_last_14d or 0,
        "sweat_rate_ml_per_hour": None,
        "has_calibrated_rate":    False,
    }


@router.get("/user/heat-profile", response_model=schemas.HeatProfileOut)
def get_heat_profile(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return {
        "heat_adaptation_level": current_user.heat_adaptation_level,
        "heat_rides_last_14d":   current_user.heat_rides_last_14d or 0,
        "sweat_rate_ml_per_hour": current_user.sweat_rate_ml_per_hour,
        "has_calibrated_rate":   current_user.sweat_rate_ml_per_hour is not None,
    }


@router.post("/user/sweat-test", response_model=schemas.HeatProfileOut)
def record_sweat_test(
    body: schemas.SweatTestIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Compute and persist the user's personal sweat rate from a controlled sweat test.

    Formula (Shirreffs & Maughan 2000):
        sweat_loss_kg = weight_before - weight_after + (intake_ml / 1000)
        sweat_rate_ml_h = (sweat_loss_kg * 1000) / duration_h
    """
    if body.duration_h <= 0:
        raise HTTPException(status_code=400, detail="duration_h must be positive")
    if body.weight_before_kg <= 0 or body.weight_after_kg <= 0:
        raise HTTPException(status_code=400, detail="Weights must be positive")
    if body.weight_after_kg > body.weight_before_kg + 0.5:
        raise HTTPException(status_code=400, detail="Post-ride weight should not exceed pre-ride weight by more than 0.5 kg")

    sweat_loss_kg  = body.weight_before_kg - body.weight_after_kg + (body.intake_ml_during / 1000)
    sweat_rate     = round((sweat_loss_kg * 1000) / body.duration_h, 0)

    if sweat_rate < 100 or sweat_rate > 4000:
        raise HTTPException(
            status_code=400,
            detail=f"Calculated sweat rate ({sweat_rate:.0f} ml/h) is outside physiological range (100-4000 ml/h). Check your inputs."
        )

    current_user.sweat_rate_ml_per_hour = sweat_rate
    db.commit()
    db.refresh(current_user)

    return {
        "heat_adaptation_level": current_user.heat_adaptation_level,
        "heat_rides_last_14d":   current_user.heat_rides_last_14d or 0,
        "sweat_rate_ml_per_hour": current_user.sweat_rate_ml_per_hour,
        "has_calibrated_rate":   True,
    }
