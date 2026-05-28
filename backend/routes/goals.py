from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_user
import models
import schemas
from typing import List

router = APIRouter()

VALID_TYPES = {
    "weekly_distance_km", "weekly_rides", "weekly_elevation_m",
    "monthly_distance_km", "monthly_elevation_m",
    "annual_distance_km",
}


@router.get("/", response_model=List[schemas.GoalOut])
def get_goals(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return db.query(models.Goal).filter(models.Goal.user_id == current_user.id).all()


@router.post("/", response_model=schemas.GoalOut)
def set_goal(data: schemas.GoalIn, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if data.goal_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid goal type. Must be one of: {', '.join(VALID_TYPES)}")
    if data.target <= 0:
        raise HTTPException(status_code=400, detail="Target must be greater than 0")
    goal = db.query(models.Goal).filter(models.Goal.goal_type == data.goal_type, models.Goal.user_id == current_user.id).first()
    if goal:
        goal.target = data.target
    else:
        goal = models.Goal(goal_type=data.goal_type, target=data.target, user_id=current_user.id)
        db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


@router.delete("/{goal_id}")
def delete_goal(goal_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    goal = db.query(models.Goal).filter(models.Goal.id == goal_id, models.Goal.user_id == current_user.id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    db.delete(goal)
    db.commit()
    return {"message": "Deleted"}
