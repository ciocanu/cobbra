import json
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_user, verify_password, hash_password
import models
import schemas

router = APIRouter()


_VALID_EXPERIENCE = {"beginner", "intermediate", "advanced"}
_VALID_BIKE_TYPE  = {"road", "gravel", "mtb", "other"}


@router.get("/", response_model=schemas.SettingsOut)
def get_settings(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    return schemas.SettingsOut(
        max_hr=user.max_hr,
        age=user.age,
        resting_hr=user.resting_hr,
        weight_kg=user.weight_kg,
        ftp=user.ftp,
        experience_level=user.experience_level,
        bike_type=user.bike_type,
    )


@router.patch("/", response_model=schemas.SettingsOut)
def update_settings(
    body: schemas.SettingsIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    user = db.query(models.User).filter(models.User.id == current_user.id).first()

    if body.max_hr is not None:
        if not (100 <= body.max_hr <= 250):
            raise HTTPException(status_code=400, detail="Max HR must be between 100 and 250 bpm.")
        user.max_hr = body.max_hr

    if body.age is not None:
        if not (10 <= body.age <= 100):
            raise HTTPException(status_code=400, detail="Age must be between 10 and 100.")
        user.age = body.age

    if body.resting_hr is not None:
        if not (30 <= body.resting_hr <= 100):
            raise HTTPException(status_code=400, detail="Resting HR must be between 30 and 100 bpm.")
        user.resting_hr = body.resting_hr

    if body.weight_kg is not None:
        if not (30 <= body.weight_kg <= 250):
            raise HTTPException(status_code=400, detail="Weight must be between 30 and 250 kg.")
        user.weight_kg = body.weight_kg

    if body.ftp is not None:
        if not (50 <= body.ftp <= 600):
            raise HTTPException(status_code=400, detail="FTP must be between 50 and 600 W.")
        user.ftp = body.ftp

    if body.experience_level is not None:
        if body.experience_level not in _VALID_EXPERIENCE:
            raise HTTPException(status_code=400, detail="Invalid experience level.")
        user.experience_level = body.experience_level

    if body.bike_type is not None:
        if body.bike_type not in _VALID_BIKE_TYPE:
            raise HTTPException(status_code=400, detail="Invalid bike type.")
        user.bike_type = body.bike_type

    db.commit()
    db.refresh(user)
    return schemas.SettingsOut(
        max_hr=user.max_hr,
        age=user.age,
        resting_hr=user.resting_hr,
        weight_kg=user.weight_kg,
        ftp=user.ftp,
        experience_level=user.experience_level,
        bike_type=user.bike_type,
    )


@router.patch("/password")
def change_password(body: dict, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    old = body.get("old_password", "")
    new = body.get("new_password", "")
    if not verify_password(old, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if len(new) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters.")
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    user.hashed_password = hash_password(new)
    user.token_version = (user.token_version or 1) + 1
    db.commit()
    return {"ok": True}


_EMAIL_VERIFY_HOURS = 24


@router.post("/email")
def request_email_change(body: dict, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    new_email = (body.get("email") or "").strip().lower()
    if "@" not in new_email or len(new_email) < 5:
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")
    if new_email == (current_user.email or "").lower():
        raise HTTPException(status_code=400, detail="That is already your current email address.")
    taken = db.query(models.User).filter(
        models.User.email == new_email,
        models.User.id != current_user.id,
    ).first()
    if taken:
        raise HTTPException(status_code=400, detail="That email address is already in use.")

    token      = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=_EMAIL_VERIFY_HOURS)

    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    user.pending_email           = new_email
    user.email_verify_token      = token
    user.email_verify_expires_at = expires_at
    db.commit()

    try:
        from email_service import send_email_verification
        send_email_verification(new_email, current_user.username, token, expires_at)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send verification email: {e}")

    return {"ok": True, "pending_email": new_email}


@router.post("/verify-email")
def verify_email(body: dict, db: Session = Depends(get_db)):
    token = (body.get("token") or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token is required.")
    user = db.query(models.User).filter(models.User.email_verify_token == token).first()
    if not user:
        raise HTTPException(status_code=404, detail="Invalid verification link.")
    if user.email_verify_expires_at and user.email_verify_expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="This verification link has expired. Please request a new one.")
    user.email                   = user.pending_email
    user.pending_email           = None
    user.email_verify_token      = None
    user.email_verify_expires_at = None
    db.commit()
    return {"ok": True, "email": user.email}


@router.get("/export")
def export_my_data(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """GDPR Art. 20 – Data Portability: return all personal data as a JSON download."""
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    activities = db.query(models.Activity).filter(models.Activity.user_id == current_user.id).order_by(models.Activity.date).all()
    records    = db.query(models.PersonalRecord).filter(models.PersonalRecord.user_id == current_user.id).all()
    goals      = db.query(models.Goal).filter(models.Goal.user_id == current_user.id).all()
    segments   = db.query(models.Segment).filter(models.Segment.user_id == current_user.id).all()
    plans      = db.query(models.TrainingPlan).filter(models.TrainingPlan.user_id == current_user.id).all()

    payload = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "profile": {
            "username":         user.username,
            "email":            user.email,
            "membership":       user.membership,
            "created_at":       user.created_at.isoformat() if getattr(user, "created_at", None) else None,
            "age":              user.age,
            "weight_kg":        user.weight_kg,
            "max_hr":           user.max_hr,
            "resting_hr":       user.resting_hr,
            "ftp":              user.ftp,
            "experience_level": user.experience_level,
            "bike_type":        user.bike_type,
        },
        "activities": [
            {
                "id":                  a.id,
                "name":                a.name,
                "date":                a.date.isoformat(),
                "distance_km":         a.distance_km,
                "duration_seconds":    a.duration_seconds,
                "avg_speed_kmh":       a.avg_speed_kmh,
                "max_speed_kmh":       a.max_speed_kmh,
                "elevation_gain_m":    a.elevation_gain_m,
                "elevation_loss_m":    a.elevation_loss_m,
                "avg_heart_rate_bpm":  a.avg_heart_rate_bpm,
                "max_heart_rate_bpm":  a.max_heart_rate_bpm,
                "avg_cadence_rpm":     a.avg_cadence_rpm,
                "avg_power_w":         a.avg_power_w,
                "normalized_power_w":  a.normalized_power_w,
                "tss":                 a.tss,
                "suffer_score":        a.suffer_score,
                "calories":            a.calories,
                "notes":               a.notes,
                "ai_analysis":         a.ai_analysis,
                "weather_temp_c":      a.weather_temp_c,
                "weather_wind_kmh":    a.weather_wind_kmh,
                "weather_desc":        a.weather_desc,
                "file_type":           a.file_type,
                "strava_id":           a.strava_id,
            }
            for a in activities
        ],
        "personal_records": [
            {
                "distance_m":      r.distance_m,
                "elapsed_seconds": r.elapsed_seconds,
                "avg_speed_kmh":   r.avg_speed_kmh,
                "activity_id":     r.activity_id,
                "set_at":          r.set_at.isoformat() if getattr(r, "set_at", None) else None,
            }
            for r in records
        ],
        "goals": [
            {
                "goal_type": g.goal_type,
                "target":    g.target,
            }
            for g in goals
        ],
        "segments_created": [
            {
                "id":         s.id,
                "name":       s.name,
                "distance_m": s.distance_m,
                "start_lat":  s.start_lat,
                "start_lon":  s.start_lon,
                "end_lat":    s.end_lat,
                "end_lon":    s.end_lon,
                "created_at": s.created_at.isoformat() if getattr(s, "created_at", None) else None,
            }
            for s in segments
        ],
        "training_plans": [
            {
                "objective":       getattr(p, "objective", None),
                "event_date":      getattr(p, "event_date", None),
                "available_days":  getattr(p, "available_days", None),
                "plan_text":       getattr(p, "plan_text", None),
                "created_at":      p.created_at.isoformat() if getattr(p, "created_at", None) else None,
            }
            for p in plans
        ],
        "note": "Raw GPS track data (latitude, longitude, heart rate per second) can be exported per-activity via the CSV or GPX export buttons on each activity page.",
    }

    content = json.dumps(payload, indent=2, default=str)
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="velostats-data-{user.username}.json"'},
    )


@router.delete("/account")
def delete_account(body: dict, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """GDPR Art. 17 – Right to Erasure: permanently delete the account and all associated data."""
    password = (body.get("password") or "")
    if not verify_password(password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect password. Please try again.")

    uid = current_user.id

    # Delete in FK-safe order
    activity_ids = [row[0] for row in db.query(models.Activity.id).filter(models.Activity.user_id == uid).all()]
    if activity_ids:
        db.query(models.SegmentEffort).filter(models.SegmentEffort.activity_id.in_(activity_ids)).delete(synchronize_session=False)
        db.query(models.TrackPoint).filter(models.TrackPoint.activity_id.in_(activity_ids)).delete(synchronize_session=False)
        db.query(models.Lap).filter(models.Lap.activity_id.in_(activity_ids)).delete(synchronize_session=False)

    db.query(models.Activity).filter(models.Activity.user_id == uid).delete(synchronize_session=False)
    db.query(models.PersonalRecord).filter(models.PersonalRecord.user_id == uid).delete(synchronize_session=False)
    db.query(models.Goal).filter(models.Goal.user_id == uid).delete(synchronize_session=False)

    # Segments created by this user: delete their efforts first, then the segments
    seg_ids = [row[0] for row in db.query(models.Segment.id).filter(models.Segment.user_id == uid).all()]
    if seg_ids:
        db.query(models.SegmentEffort).filter(models.SegmentEffort.segment_id.in_(seg_ids)).delete(synchronize_session=False)
        db.query(models.Segment).filter(models.Segment.id.in_(seg_ids)).delete(synchronize_session=False)

    db.query(models.TrainingPlan).filter(models.TrainingPlan.user_id == uid).delete(synchronize_session=False)

    user = db.query(models.User).filter(models.User.id == uid).first()
    db.delete(user)
    db.commit()

    response = JSONResponse({"ok": True})
    response.delete_cookie("access_token", path="/", samesite="strict")
    return response
