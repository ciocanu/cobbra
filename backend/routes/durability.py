from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_user
import models
import schemas
from utils.durability import (
    calculate_durability,
    validate_durability_calculation,
    calculate_durability_trend,
    compare_durability_rides,
)

router = APIRouter()


def _owned_activity(activity_id: int, user, db: Session) -> models.Activity:
    activity = db.query(models.Activity).filter(
        models.Activity.id == activity_id,
        models.Activity.user_id == user.id,
    ).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity


def _recompute(activity: models.Activity, user, db: Session) -> models.DurabilityAnalysis:
    """Compute on-demand and persist. Used for activities uploaded before this feature."""
    track_points = [
        {
            "timestamp":       tp.timestamp,
            "distance_m":      tp.distance_m,
            "elevation":       tp.elevation,
            "speed_kmh":       tp.speed_kmh,
            "heart_rate_bpm":  tp.heart_rate_bpm,
            "power_w":         tp.power_w,
            "cadence_rpm":     tp.cadence_rpm,
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
        raise HTTPException(status_code=422, detail=reason)

    from routes.activities import _get_tsb_at_date
    tsb = _get_tsb_at_date(db, user.id, activity.date)

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
    if result is None:
        raise HTTPException(status_code=422, detail="Could not compute durability for this ride.")

    db_fields = {k: v for k, v in result.items() if k != "context"}
    existing = db.query(models.DurabilityAnalysis).filter(
        models.DurabilityAnalysis.activity_id == activity.id
    ).first()
    if existing:
        for k, v in db_fields.items():
            setattr(existing, k, v)
        row = existing
    else:
        row = models.DurabilityAnalysis(activity_id=activity.id, **db_fields)
        db.add(row)

    activity.durability_index = result["durability_index"]
    db.commit()
    db.refresh(row)
    return row


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/activities/{activity_id}/durability", response_model=schemas.DurabilityAnalysisOut)
def get_durability(
    activity_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return durability analysis for one activity, computing on-demand if missing."""
    activity = _owned_activity(activity_id, current_user, db)

    row = db.query(models.DurabilityAnalysis).filter(
        models.DurabilityAnalysis.activity_id == activity_id
    ).first()

    if not row:
        row = _recompute(activity, current_user, db)

    return row


@router.get("/stats/durability-trend", response_model=schemas.DurabilityTrendOut)
def get_durability_trend(
    weeks: int = 12,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Weekly durability trend with linear regression over the past N weeks."""
    if weeks < 1 or weeks > 104:
        raise HTTPException(status_code=400, detail="weeks must be between 1 and 104")
    return calculate_durability_trend(current_user.id, db, weeks=weeks)


@router.post("/stats/durability-compare", response_model=schemas.DurabilityCompareOut)
def compare_durability(
    body: schemas.DurabilityCompareIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Compare durability across up to 5 activities owned by the current user."""
    if not body.activity_ids:
        raise HTTPException(status_code=400, detail="Provide at least one activity_id")
    if len(body.activity_ids) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 activities per comparison")

    # Verify ownership of all requested activities
    owned = {
        a.id for a in db.query(models.Activity.id).filter(
            models.Activity.id.in_(body.activity_ids),
            models.Activity.user_id == current_user.id,
        ).all()
    }
    forbidden = [i for i in body.activity_ids if i not in owned]
    if forbidden:
        raise HTTPException(status_code=404, detail=f"Activities not found: {forbidden}")

    return compare_durability_rides(body.activity_ids, db)
