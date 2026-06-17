from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_user
import models
import schemas
from utils.indoor_outdoor_gap import (
    calculate_power_gap,
    apply_correction_factors,
    recalculate_training_load_corrected,
    calibrate_from_ftp_values,
    calibrate_from_dual_test,
    update_indoor_outdoor_gap,
)

router = APIRouter()


# ── Profile ───────────────────────────────────────────────────────────────────

@router.get("/user/indoor-outdoor-profile", response_model=schemas.IndoorOutdoorProfileOut)
def get_indoor_outdoor_profile(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return the user's indoor/outdoor gap profile (or empty defaults)."""
    profile = db.query(models.IndoorOutdoorProfile).filter(
        models.IndoorOutdoorProfile.user_id == current_user.id
    ).first()

    if not profile:
        return schemas.IndoorOutdoorProfileOut(
            power_gap_pct=None, hr_gap_bpm=None,
            power_gap_confidence=None,
            indoor_avg_wkg_z3=None, outdoor_avg_wkg_z3=None,
            indoor_avg_hr_z3=None, outdoor_avg_hr_z3=None,
            indoor_rides_analyzed=0, outdoor_rides_analyzed=0,
            manual_power_gap_pct=None, calibration_date=None,
            calibration_method=None, last_calculated=None,
            effective_power_gap_pct=None,
        )

    effective = (
        profile.manual_power_gap_pct
        if profile.manual_power_gap_pct is not None
        else profile.power_gap_pct
    )

    out = schemas.IndoorOutdoorProfileOut.model_validate(profile)
    out.effective_power_gap_pct = effective
    return out


@router.post("/user/indoor-outdoor-profile/recalculate",
             response_model=schemas.IndoorOutdoorProfileOut)
def recalculate_profile(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Trigger manual recalculation of the gap from existing rides."""
    update_indoor_outdoor_gap(current_user.id, db)
    return get_indoor_outdoor_profile(db=db, current_user=current_user)


# ── Calibration ───────────────────────────────────────────────────────────────

@router.post("/user/indoor-outdoor-calibrate", response_model=schemas.CalibrateOut)
def calibrate(
    body: schemas.CalibrateIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Manually calibrate the indoor/outdoor gap.

    method="ftp_comparison": supply indoor_ftp and outdoor_ftp.
    method="dual_test": supply indoor_activity_id and outdoor_activity_id.
    """
    if body.method == "ftp_comparison":
        if body.indoor_ftp is None or body.outdoor_ftp is None:
            raise HTTPException(status_code=400, detail="indoor_ftp and outdoor_ftp are required.")
        if body.outdoor_ftp <= 0:
            raise HTTPException(status_code=400, detail="outdoor_ftp must be positive.")
        result = calibrate_from_ftp_values(
            current_user.id, body.indoor_ftp, body.outdoor_ftp, db
        )
        return schemas.CalibrateOut(
            power_gap_pct=result["power_gap_pct"],
            hr_gap_bpm=None,
            indoor_ftp_estimated=body.indoor_ftp,
            outdoor_ftp_estimated=body.outdoor_ftp,
            interpretation=result["interpretation"],
            recommendation=result["recommendation"],
        )

    if body.method == "dual_test":
        if body.indoor_activity_id is None or body.outdoor_activity_id is None:
            raise HTTPException(status_code=400,
                                detail="indoor_activity_id and outdoor_activity_id are required.")
        try:
            result = calibrate_from_dual_test(
                current_user.id,
                body.indoor_activity_id,
                body.outdoor_activity_id,
                db,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        return schemas.CalibrateOut(
            power_gap_pct=result["power_gap_pct"],
            hr_gap_bpm=result["hr_gap_bpm"],
            indoor_ftp_estimated=result["indoor_ftp_estimated"],
            outdoor_ftp_estimated=result["outdoor_ftp_estimated"],
            interpretation=result["interpretation"],
            recommendation=result["recommendation"],
        )

    raise HTTPException(status_code=400,
                        detail="method must be 'ftp_comparison' or 'dual_test'.")


# ── Environment override ───────────────────────────────────────────────────────

@router.patch("/activities/{activity_id}/environment")
def override_environment(
    activity_id: int,
    body: schemas.EnvironmentOverrideIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Manually correct the indoor/outdoor classification of an activity."""
    activity = db.query(models.Activity).filter(
        models.Activity.id == activity_id,
        models.Activity.user_id == current_user.id,
    ).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found.")

    valid_envs = ("indoor", "outdoor", "unknown")
    if body.environment not in valid_envs:
        raise HTTPException(status_code=400,
                            detail=f"environment must be one of {valid_envs}")

    activity.ride_environment        = body.environment
    activity.ride_environment_source = "user_override"
    activity.indoor_platform         = body.platform

    # Re-apply or clear correction factors
    if body.environment == "indoor":
        profile = db.query(models.IndoorOutdoorProfile).filter(
            models.IndoorOutdoorProfile.user_id == current_user.id
        ).first()
        if profile and (
            profile.power_gap_pct is not None
            or profile.manual_power_gap_pct is not None
        ):
            correction = apply_correction_factors(activity, profile)
            activity.power_correction_factor = correction["power_correction_factor"]
            activity.hr_correction_factor    = correction["hr_correction_factor"]
            activity.corrected_tss           = correction["corrected_tss"]
    else:
        activity.power_correction_factor = None
        activity.hr_correction_factor    = None
        activity.corrected_tss           = None

    db.commit()

    # Refresh gap profile with updated classification
    try:
        update_indoor_outdoor_gap(current_user.id, db)
    except Exception:
        pass

    return {
        "activity_id":     activity_id,
        "ride_environment": activity.ride_environment,
        "indoor_platform":  activity.indoor_platform,
        "corrected_tss":    activity.corrected_tss,
    }


# ── Training load comparison ───────────────────────────────────────────────────

@router.get("/stats/training-load-comparison",
            response_model=schemas.TrainingLoadComparisonOut)
def get_training_load_comparison(
    days: int = 90,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return original vs corrected CTL/ATL/TSB side by side."""
    if days < 7 or days > 365:
        raise HTTPException(status_code=400, detail="days must be between 7 and 365.")
    return recalculate_training_load_corrected(current_user.id, db, days=days)
