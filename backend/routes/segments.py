import json
import math
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_user
import models
import schemas
from utils import match_segment
from typing import List

router = APIRouter()

DUPLICATE_RADIUS_M = 150  # start AND end must both be within this to flag as duplicate


def _haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _find_duplicate(db: Session, waypoints: list) -> models.Segment | None:
    start_lat, start_lon = waypoints[0]
    end_lat, end_lon = waypoints[-1]
    for seg in db.query(models.Segment).all():
        d_start = _haversine_m(start_lat, start_lon, seg.start_lat, seg.start_lon)
        d_end   = _haversine_m(end_lat,   end_lon,   seg.end_lat,   seg.end_lon)
        # Also check reversed direction (same segment, opposite way)
        d_start_rev = _haversine_m(start_lat, start_lon, seg.end_lat, seg.end_lon)
        d_end_rev   = _haversine_m(end_lat,   end_lon,   seg.start_lat, seg.start_lon)
        if (d_start <= DUPLICATE_RADIUS_M and d_end <= DUPLICATE_RADIUS_M) or \
           (d_start_rev <= DUPLICATE_RADIUS_M and d_end_rev <= DUPLICATE_RADIUS_M):
            return seg
    return None


def _seg_dict(seg, efforts, creator_name: str, current_user_id: int):
    best = efforts[0] if efforts else None
    waypoints = json.loads(seg.waypoints_json) if seg.waypoints_json else [
        [seg.start_lat, seg.start_lon], [seg.end_lat, seg.end_lon]
    ]
    return {
        "id": seg.id,
        "name": seg.name,
        "waypoints": waypoints,
        "start_lat": seg.start_lat,
        "start_lon": seg.start_lon,
        "end_lat": seg.end_lat,
        "end_lon": seg.end_lon,
        "distance_m": seg.distance_m,
        "created_at": seg.created_at.isoformat(),
        "created_by": creator_name or "Unknown",
        "is_mine": seg.user_id == current_user_id,
        "effort_count": len(efforts),
        "best_time": best.elapsed_seconds if best else None,
        "best_speed": best.avg_speed_kmh if best else None,
        "best_activity_id": best.activity_id if best else None,
    }


@router.get("/")
def get_segments(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    rows = (
        db.query(models.Segment, models.User.username)
        .outerjoin(models.User, models.Segment.user_id == models.User.id)
        .order_by(models.Segment.created_at.desc())
        .all()
    )
    result = []
    for seg, creator_name in rows:
        efforts = (
            db.query(models.SegmentEffort)
            .filter(models.SegmentEffort.segment_id == seg.id)
            .order_by(models.SegmentEffort.elapsed_seconds)
            .all()
        )
        result.append(_seg_dict(seg, efforts, creator_name, current_user.id))
    return result


@router.post("/")
def create_segment(
    data: schemas.SegmentIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not data.name.strip():
        raise HTTPException(status_code=400, detail="Segment name is required")
    if len(data.waypoints) < 2:
        raise HTTPException(status_code=400, detail="Segment needs at least 2 points")

    dup = _find_duplicate(db, data.waypoints)
    if dup:
        raise HTTPException(
            status_code=409,
            detail=f'A very similar segment already exists: "{dup.name}". Move the start or end point further away to create a distinct segment.'
        )

    seg = models.Segment(
        name=data.name.strip(),
        start_lat=data.waypoints[0][0],
        start_lon=data.waypoints[0][1],
        end_lat=data.waypoints[-1][0],
        end_lon=data.waypoints[-1][1],
        waypoints_json=json.dumps(data.waypoints),
        user_id=current_user.id,
    )
    db.add(seg)
    db.commit()
    db.refresh(seg)

    # Retroactively match ALL users' activities against the new segment
    for act in db.query(models.Activity).all():
        track_points = [
            {
                "timestamp": tp.timestamp,
                "lat": tp.lat,
                "lon": tp.lon,
                "heart_rate_bpm": tp.heart_rate_bpm,
                "speed_kmh": tp.speed_kmh,
            }
            for tp in act.track_points
        ]
        effort = match_segment(track_points, seg)
        if effort:
            db.add(models.SegmentEffort(
                segment_id=seg.id,
                activity_id=act.id,
                elapsed_seconds=effort["elapsed_seconds"],
                avg_speed_kmh=effort.get("avg_speed_kmh"),
                avg_hr=effort.get("avg_hr"),
                set_at=act.date,
            ))
    db.commit()

    efforts = db.query(models.SegmentEffort).filter(models.SegmentEffort.segment_id == seg.id).all()
    return _seg_dict(seg, efforts, current_user.username, current_user.id)


@router.delete("/{segment_id}")
def delete_segment(
    segment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    seg = db.query(models.Segment).filter(models.Segment.id == segment_id).first()
    if not seg:
        raise HTTPException(status_code=404, detail="Segment not found")
    if seg.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only delete segments you created")
    db.delete(seg)
    db.commit()
    return {"message": "Deleted"}


@router.get("/{segment_id}/efforts")
def get_efforts(
    segment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    seg = db.query(models.Segment).filter(models.Segment.id == segment_id).first()
    if not seg:
        raise HTTPException(status_code=404, detail="Segment not found")

    rows = (
        db.query(models.SegmentEffort, models.Activity.user_id, models.User.username)
        .join(models.Activity, models.SegmentEffort.activity_id == models.Activity.id)
        .join(models.User, models.Activity.user_id == models.User.id)
        .filter(models.SegmentEffort.segment_id == segment_id)
        .order_by(models.SegmentEffort.elapsed_seconds)
        .all()
    )

    # Best effort per user (leaderboard — one row per rider)
    seen = set()
    leaderboard = []
    for effort, activity_user_id, username in rows:
        if username not in seen:
            seen.add(username)
            leaderboard.append({
                "id": effort.id,
                "segment_id": effort.segment_id,
                "activity_id": effort.activity_id,
                "elapsed_seconds": effort.elapsed_seconds,
                "avg_speed_kmh": effort.avg_speed_kmh,
                "avg_hr": effort.avg_hr,
                "set_at": effort.set_at.isoformat(),
                "username": username,
                "is_me": activity_user_id == current_user.id,
            })
    return leaderboard


@router.get("/{segment_id}/my-trend")
def get_my_segment_trend(
    segment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    All of the current user's own efforts on a segment, ordered by date.
    Used for personal HR efficiency trend (is your HR dropping over time?).
    """
    seg = db.query(models.Segment).filter(models.Segment.id == segment_id).first()
    if not seg:
        raise HTTPException(status_code=404, detail="Segment not found")

    efforts = (
        db.query(models.SegmentEffort)
        .join(models.Activity, models.SegmentEffort.activity_id == models.Activity.id)
        .filter(
            models.SegmentEffort.segment_id == segment_id,
            models.Activity.user_id == current_user.id,
        )
        .order_by(models.SegmentEffort.set_at)
        .all()
    )

    return [
        {
            "date": e.set_at.isoformat(),
            "elapsed_seconds": e.elapsed_seconds,
            "avg_speed_kmh":   e.avg_speed_kmh,
            "avg_hr":          e.avg_hr,
            "activity_id":     e.activity_id,
        }
        for e in efforts
    ]


@router.get("/activity/{activity_id}")
def get_activity_efforts(
    activity_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """All segment efforts for a specific activity, enriched with segment names."""
    activity = db.query(models.Activity).filter(
        models.Activity.id == activity_id,
        models.Activity.user_id == current_user.id,
    ).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    efforts = (
        db.query(models.SegmentEffort)
        .filter(models.SegmentEffort.activity_id == activity_id)
        .order_by(models.SegmentEffort.elapsed_seconds)
        .all()
    )
    result = []
    for e in efforts:
        seg = db.query(models.Segment).filter(models.Segment.id == e.segment_id).first()
        best = (
            db.query(models.SegmentEffort)
            .filter(models.SegmentEffort.segment_id == e.segment_id)
            .order_by(models.SegmentEffort.elapsed_seconds)
            .first()
        )
        result.append({
            "id": e.id,
            "segment_id": e.segment_id,
            "segment_name": seg.name if seg else "Unknown",
            "activity_id": e.activity_id,
            "elapsed_seconds": e.elapsed_seconds,
            "avg_speed_kmh": e.avg_speed_kmh,
            "avg_hr": e.avg_hr,
            "set_at": e.set_at.isoformat(),
            "is_pr": best and best.id == e.id,
        })
    return result
