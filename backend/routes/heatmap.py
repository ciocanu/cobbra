from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_user
import models

router = APIRouter()


def _downsample(points: list, max_pts: int = 300) -> list:
    if len(points) <= max_pts:
        return points
    step = len(points) // max_pts
    return points[::step]


@router.get("/")
def get_heatmap(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    activities = (
        db.query(models.Activity)
        .filter(models.Activity.user_id == current_user.id)
        .order_by(models.Activity.date.desc())
        .all()
    )
    result = []
    for act in activities:
        pts = [
            [tp.lat, tp.lon]
            for tp in act.track_points
            if tp.lat is not None and tp.lon is not None
        ]
        if not pts:
            continue
        result.append({
            "id": act.id,
            "name": act.name,
            "date": act.date.isoformat(),
            "distance_km": act.distance_km,
            "points": _downsample(pts),
        })
    return result
