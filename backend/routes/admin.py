import os
import time
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db, DATABASE_URL
import models
from auth import get_current_user

router = APIRouter()

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")
_start_time = time.time()


def require_admin(current_user=Depends(get_current_user)):
    if not ADMIN_USERNAME or current_user.username != ADMIN_USERNAME:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return current_user


# ── Check ────────────────────────────────────────────────────────────────────

@router.get("/check")
def check(current_user=Depends(require_admin)):
    return {"ok": True}


# ── Stats ────────────────────────────────────────────────────────────────────

@router.get("/stats")
def site_stats(db: Session = Depends(get_db), _=Depends(require_admin)):
    total_users      = db.query(func.count(models.User.id)).scalar() or 0
    total_activities = db.query(func.count(models.Activity.id)).scalar() or 0
    total_distance   = db.query(func.sum(models.Activity.distance_km)).scalar() or 0
    total_elevation  = db.query(func.sum(models.Activity.elevation_gain_m)).scalar() or 0

    weekly_signups = []
    for i in range(7, -1, -1):
        week_start = datetime.utcnow() - timedelta(weeks=i + 1)
        week_end   = datetime.utcnow() - timedelta(weeks=i)
        count = (
            db.query(func.count(models.User.id))
            .filter(models.User.created_at >= week_start, models.User.created_at < week_end)
            .scalar() or 0
        )
        weekly_signups.append({"week": f"{week_start.day} {week_start.strftime('%b')}", "signups": count})

    return {
        "total_users":       total_users,
        "total_activities":  total_activities,
        "total_distance_km": round(total_distance, 1),
        "total_elevation_m": round(total_elevation),
        "weekly_signups":    weekly_signups,
    }


# ── System ───────────────────────────────────────────────────────────────────

@router.get("/system")
def system_info(_=Depends(require_admin)):
    db_path = DATABASE_URL.replace("sqlite:///", "")
    db_size = os.path.getsize(db_path) if os.path.exists(db_path) else None
    return {
        "uptime_seconds": int(time.time() - _start_time),
        "db_size_bytes":  db_size,
    }


# ── Users ────────────────────────────────────────────────────────────────────

@router.get("/users")
def list_users(db: Session = Depends(get_db), _=Depends(require_admin)):
    users = db.query(models.User).order_by(models.User.created_at.desc()).all()
    result = []
    for u in users:
        activity_count = (
            db.query(func.count(models.Activity.id))
            .filter(models.Activity.user_id == u.id)
            .scalar() or 0
        )
        result.append({
            "id":                 u.id,
            "username":           u.username,
            "email":              u.email or "",
            "created_at":         u.created_at.isoformat() if u.created_at else None,
            "activity_count":     activity_count,
            "membership":         u.membership or "free",
            "is_admin":           u.username == ADMIN_USERNAME,
            "subscription_start": u.subscription_start.isoformat() if u.subscription_start else None,
            "subscription_end":   u.subscription_end.isoformat() if u.subscription_end else None,
        })
    return result


_VALID_MEMBERSHIPS = {"free", "pro", "annual", "lifetime"}

@router.patch("/users/{user_id}")
def update_user(user_id: int, body: dict, db: Session = Depends(get_db), _=Depends(require_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    membership = (body.get("membership") or "").strip().lower()
    if membership not in _VALID_MEMBERSHIPS:
        raise HTTPException(status_code=400, detail=f"Invalid membership. Must be one of: {', '.join(_VALID_MEMBERSHIPS)}")
    user.membership = membership
    db.commit()
    return {"ok": True, "membership": user.membership}


_OFFER_HOURS = 48

@router.post("/users/{user_id}/offer")
def send_lifetime_offer(user_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if not user.email:
        raise HTTPException(status_code=400, detail="This user has no email address on file.")

    token      = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=_OFFER_HOURS)
    user.offer_token      = token
    user.offer_expires_at = expires_at
    db.commit()

    try:
        from email_service import send_lifetime_offer as send_email
        send_email(user.email, user.username, token, expires_at)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {e}")
    return {"ok": True}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.username == ADMIN_USERNAME:
        raise HTTPException(status_code=400, detail="Cannot delete the admin account.")

    # Collect IDs first for bulk deletes
    activity_ids = [
        r[0] for r in db.query(models.Activity.id).filter(models.Activity.user_id == user_id).all()
    ]
    segment_ids = [
        r[0] for r in db.query(models.Segment.id).filter(models.Segment.user_id == user_id).all()
    ]

    # Delete leaf rows that reference activities
    if activity_ids:
        db.query(models.SegmentEffort).filter(
            models.SegmentEffort.activity_id.in_(activity_ids)
        ).delete(synchronize_session=False)
        db.query(models.TrackPoint).filter(
            models.TrackPoint.activity_id.in_(activity_ids)
        ).delete(synchronize_session=False)
        db.query(models.Lap).filter(
            models.Lap.activity_id.in_(activity_ids)
        ).delete(synchronize_session=False)

    # Delete segment efforts for this user's segments (from other users' activities)
    if segment_ids:
        db.query(models.SegmentEffort).filter(
            models.SegmentEffort.segment_id.in_(segment_ids)
        ).delete(synchronize_session=False)

    db.query(models.PersonalRecord).filter(models.PersonalRecord.user_id == user_id).delete()
    db.query(models.Goal).filter(models.Goal.user_id == user_id).delete()
    db.query(models.TrainingPlan).filter(models.TrainingPlan.user_id == user_id).delete()
    db.query(models.Activity).filter(models.Activity.user_id == user_id).delete()
    db.query(models.Segment).filter(models.Segment.user_id == user_id).delete()
    db.query(models.User).filter(models.User.id == user_id).delete()
    db.commit()
    return {"ok": True}


# ── Segments ─────────────────────────────────────────────────────────────────

@router.get("/segments")
def list_segments(db: Session = Depends(get_db), _=Depends(require_admin)):
    segments = db.query(models.Segment).order_by(models.Segment.created_at.desc()).all()
    result = []
    for s in segments:
        creator = db.query(models.User).filter(models.User.id == s.user_id).first()
        effort_count = (
            db.query(func.count(models.SegmentEffort.id))
            .filter(models.SegmentEffort.segment_id == s.id)
            .scalar() or 0
        )
        result.append({
            "id":             s.id,
            "name":           s.name,
            "created_by":     creator.username if creator else "unknown",
            "created_at":     s.created_at.isoformat() if s.created_at else None,
            "effort_count":   effort_count,
            "start_lat":      s.start_lat,
            "start_lon":      s.start_lon,
            "end_lat":        s.end_lat,
            "end_lon":        s.end_lon,
            "waypoints_json": s.waypoints_json,
        })
    return result


@router.patch("/segments/{segment_id}")
def update_segment(segment_id: int, body: dict, db: Session = Depends(get_db), _=Depends(require_admin)):
    seg = db.query(models.Segment).filter(models.Segment.id == segment_id).first()
    if not seg:
        raise HTTPException(status_code=404, detail="Segment not found.")

    if "name" in body:
        name = (body.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name cannot be empty.")
        seg.name = name

    if "user_id" in body:
        new_owner = db.query(models.User).filter(models.User.id == body["user_id"]).first()
        if not new_owner:
            raise HTTPException(status_code=404, detail="User not found.")
        seg.user_id = body["user_id"]

    db.commit()
    creator = db.query(models.User).filter(models.User.id == seg.user_id).first()
    return {"ok": True, "name": seg.name, "created_by": creator.username if creator else "unknown"}


@router.delete("/segments/{segment_id}")
def delete_segment(segment_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    seg = db.query(models.Segment).filter(models.Segment.id == segment_id).first()
    if not seg:
        raise HTTPException(status_code=404, detail="Segment not found.")
    db.query(models.SegmentEffort).filter(models.SegmentEffort.segment_id == segment_id).delete()
    db.delete(seg)
    db.commit()
    return {"ok": True}
