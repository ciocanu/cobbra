from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_user
import models
import schemas
from typing import List

router = APIRouter()

PR_META = {
    "fastest_400m":  {"label": "Fastest 400m",  "unit": "time"},
    "fastest_1km":   {"label": "Fastest 1 km",  "unit": "time"},
    "fastest_5km":   {"label": "Fastest 5 km",  "unit": "time"},
    "fastest_10km":  {"label": "Fastest 10 km", "unit": "time"},
    "fastest_20km":  {"label": "Fastest 20 km", "unit": "time"},
    "fastest_40km":  {"label": "Fastest 40 km", "unit": "time"},
    "longest_ride":  {"label": "Longest Ride",  "unit": "km"},
    "best_avg_speed":{"label": "Best Avg Speed","unit": "km/h"},
    "most_elevation":{"label": "Most Elevation","unit": "m"},
}


@router.get("/")
def get_records(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    stored = {pr.pr_type: pr for pr in db.query(models.PersonalRecord).filter(models.PersonalRecord.user_id == current_user.id).all()}

    # Always recompute activity-level PRs from the database
    activities = db.query(models.Activity).filter(models.Activity.user_id == current_user.id).all()
    if activities:
        longest = max(activities, key=lambda a: a.distance_km)
        fastest = max(activities, key=lambda a: a.avg_speed_kmh)
        highest = max(activities, key=lambda a: a.elevation_gain_m)

        activity_prs = {
            "longest_ride":   (longest.distance_km,     longest),
            "best_avg_speed": (fastest.avg_speed_kmh,   fastest),
            "most_elevation": (highest.elevation_gain_m, highest),
        }
        for pr_type, (value, act) in activity_prs.items():
            existing = stored.get(pr_type)
            if existing is None or value > existing.value:
                if existing:
                    existing.value = value
                    existing.activity_id = act.id
                    existing.set_at = act.date
                else:
                    db.add(models.PersonalRecord(
                        pr_type=pr_type, value=value,
                        activity_id=act.id, set_at=act.date,
                        user_id=current_user.id,
                    ))
        db.commit()

    prs = db.query(models.PersonalRecord).filter(models.PersonalRecord.user_id == current_user.id).all()
    result = []
    for pr in prs:
        activity_name = None
        if pr.activity_id:
            act = db.query(models.Activity.name).filter(models.Activity.id == pr.activity_id).first()
            if act:
                activity_name = act[0]
        result.append({
            "pr_type": pr.pr_type,
            "value": pr.value,
            "activity_id": pr.activity_id,
            "activity_name": activity_name,
            "set_at": pr.set_at.isoformat(),
        })
    return result
