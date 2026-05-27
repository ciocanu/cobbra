import math as _math
from datetime import date, timedelta, datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_user
import models
import schemas
from utils import compute_hrtss

router = APIRouter()


@router.get("/summary", response_model=schemas.StatsOut)
def get_summary(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    activities = db.query(models.Activity).filter(models.Activity.user_id == current_user.id).all()

    if not activities:
        return schemas.StatsOut(
            total_activities=0,
            total_distance_km=0,
            total_duration_seconds=0,
            total_elevation_gain_m=0,
            avg_speed_kmh=0,
            best_avg_speed_kmh=0,
            longest_ride_km=0,
        )

    total_distance = sum(a.distance_km for a in activities)
    total_duration = sum(a.duration_seconds for a in activities)
    total_elevation = sum(a.elevation_gain_m for a in activities)
    avg_speed = (total_distance / (total_duration / 3600)) if total_duration > 0 else 0

    return schemas.StatsOut(
        total_activities=len(activities),
        total_distance_km=round(total_distance, 2),
        total_duration_seconds=total_duration,
        total_elevation_gain_m=round(total_elevation, 1),
        avg_speed_kmh=round(avg_speed, 1),
        best_avg_speed_kmh=round(max(a.avg_speed_kmh for a in activities), 1),
        longest_ride_km=round(max(a.distance_km for a in activities), 2),
    )


@router.get("/monthly")
def get_monthly(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    activities = db.query(models.Activity).filter(models.Activity.user_id == current_user.id).order_by(models.Activity.date).all()
    monthly = {}
    for a in activities:
        key = a.date.strftime("%Y-%m")
        if key not in monthly:
            monthly[key] = {"month": key, "distance_km": 0, "rides": 0, "elevation_m": 0}
        monthly[key]["distance_km"] += a.distance_km
        monthly[key]["rides"] += 1
        monthly[key]["elevation_m"] += a.elevation_gain_m

    result = list(monthly.values())
    for m in result:
        m["distance_km"] = round(m["distance_km"], 1)
        m["elevation_m"] = round(m["elevation_m"], 0)
    return result


@router.get("/fitness")
def get_fitness(days: int = 90, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """
    Returns daily CTL/ATL/TSB (Fitness/Fatigue/Form) for the past N days.
    Daily load = stored TSS → hrTSS fallback → suffer_score fallback.
    CTL = 42-day EMA, ATL = 7-day EMA, TSB = CTL - ATL (Banister model).
    """
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    activities = db.query(models.Activity).filter(models.Activity.user_id == current_user.id).order_by(models.Activity.date).all()

    def _daily_tss(a) -> float:
        if a.tss is not None:
            return a.tss
        ht = compute_hrtss(a.duration_seconds, a.avg_heart_rate_bpm, user.max_hr, user.resting_hr)
        if ht is not None:
            return ht
        return a.suffer_score or 0

    daily_load: dict[date, float] = {}
    for a in activities:
        d = a.date.date()
        daily_load[d] = daily_load.get(d, 0) + _daily_tss(a)

    today = date.today()
    start = today - timedelta(days=days + 42)  # extra history for EMA warmup

    ctl = 0.0
    atl = 0.0
    result = []

    current = start
    while current <= today:
        load = daily_load.get(current, 0)
        ctl += (load - ctl) / 42
        atl += (load - atl) / 7

        if current >= today - timedelta(days=days):
            result.append({
                "date": current.isoformat(),
                "load": load,
                "ctl": round(ctl, 1),
                "atl": round(atl, 1),
                "tsb": round(ctl - atl, 1),
            })
        current += timedelta(days=1)

    return result


@router.get("/weekly")
def get_weekly(weeks: int = 16, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Returns weekly aggregates for the past N weeks (distance, elevation, rides, TSS)."""
    activities = db.query(models.Activity).filter(models.Activity.user_id == current_user.id).order_by(models.Activity.date).all()

    today = date.today()
    # Start from Monday of (weeks) weeks ago
    days_since_monday = today.weekday()
    this_monday = today - timedelta(days=days_since_monday)
    start_monday = this_monday - timedelta(weeks=weeks - 1)

    user = db.query(models.User).filter(models.User.id == current_user.id).first()

    def _act_tss(a) -> float:
        if a.tss is not None:
            return a.tss
        ht = compute_hrtss(a.duration_seconds, a.avg_heart_rate_bpm, user.max_hr, user.resting_hr)
        if ht is not None:
            return ht
        return a.suffer_score or 0

    weekly: dict[str, dict] = {}
    for i in range(weeks):
        week_start = start_monday + timedelta(weeks=i)
        key = week_start.isoformat()
        weekly[key] = {
            "week": key,
            "distance_km": 0.0,
            "elevation_m": 0.0,
            "rides": 0,
            "tss": 0.0,
            "duration_seconds": 0,
        }

    for a in activities:
        d = a.date.date()
        if d < start_monday:
            continue
        # Find week bucket
        days_from_start = (d - start_monday).days
        week_idx = days_from_start // 7
        if week_idx >= weeks:
            continue
        key = (start_monday + timedelta(weeks=week_idx)).isoformat()
        if key in weekly:
            weekly[key]["distance_km"] += a.distance_km
            weekly[key]["elevation_m"] += a.elevation_gain_m
            weekly[key]["rides"] += 1
            weekly[key]["tss"] += _act_tss(a)
            weekly[key]["duration_seconds"] += a.duration_seconds

    result = list(weekly.values())
    for w in result:
        w["distance_km"] = round(w["distance_km"], 1)
        w["elevation_m"] = round(w["elevation_m"], 0)
        w["tss"] = round(w["tss"], 1)
    return result


@router.get("/year")
def get_year(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Year in Sport: current year vs previous year comparison + monthly breakdown."""
    activities = db.query(models.Activity).filter(models.Activity.user_id == current_user.id).order_by(models.Activity.date).all()

    current_year = date.today().year
    prev_year = current_year - 1

    years: dict[int, dict] = {
        current_year: {"distance_km": 0.0, "elevation_m": 0.0, "rides": 0, "duration_seconds": 0, "suffer_score": 0},
        prev_year: {"distance_km": 0.0, "elevation_m": 0.0, "rides": 0, "duration_seconds": 0, "suffer_score": 0},
    }
    monthly_current: dict[int, dict] = {m: {"distance_km": 0.0, "elevation_m": 0.0, "rides": 0} for m in range(1, 13)}

    for a in activities:
        yr = a.date.year
        if yr in years:
            years[yr]["distance_km"] += a.distance_km
            years[yr]["elevation_m"] += a.elevation_gain_m
            years[yr]["rides"] += 1
            years[yr]["duration_seconds"] += a.duration_seconds
            years[yr]["suffer_score"] += a.suffer_score or 0
        if yr == current_year:
            mo = a.date.month
            monthly_current[mo]["distance_km"] += a.distance_km
            monthly_current[mo]["elevation_m"] += a.elevation_gain_m
            monthly_current[mo]["rides"] += 1

    # Round
    for yr in years:
        years[yr]["distance_km"] = round(years[yr]["distance_km"], 1)
        years[yr]["elevation_m"] = round(years[yr]["elevation_m"], 0)
    for mo in monthly_current:
        monthly_current[mo]["distance_km"] = round(monthly_current[mo]["distance_km"], 1)
        monthly_current[mo]["elevation_m"] = round(monthly_current[mo]["elevation_m"], 0)

    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    monthly_list = [
        {"month": month_labels[m - 1], "month_num": m, **monthly_current[m]}
        for m in range(1, 13)
    ]

    return {
        "current_year": current_year,
        "prev_year": prev_year,
        "current": years[current_year],
        "previous": years[prev_year],
        "monthly": monthly_list,
    }


@router.get("/consistency")
def get_consistency(weeks: int = 12, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """
    Consistency Score (0-100): how evenly training load is distributed over N weeks.
    Based on coefficient of variation of weekly TSS + active-weeks ratio.
    100 = perfect consistency every week. Score penalised for skipped weeks.
    """
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    activities = (
        db.query(models.Activity)
        .filter(models.Activity.user_id == current_user.id)
        .order_by(models.Activity.date)
        .all()
    )

    def _tss(a) -> float:
        if a.tss is not None:
            return float(a.tss)
        ht = compute_hrtss(a.duration_seconds, a.avg_heart_rate_bpm, user.max_hr, user.resting_hr)
        return float(ht) if ht is not None else float(a.suffer_score or 0)

    today = date.today()
    this_monday = today - timedelta(days=today.weekday())
    start_monday = this_monday - timedelta(weeks=weeks)

    weekly_tss = []
    for i in range(weeks):
        w_start = start_monday + timedelta(weeks=i)
        w_end   = w_start + timedelta(days=7)
        total   = sum(_tss(a) for a in activities if w_start <= a.date.date() < w_end)
        weekly_tss.append(round(total, 1))

    active_weeks = [t for t in weekly_tss if t > 0]
    if len(active_weeks) < 2:
        return {
            "score": None,
            "weeks_active": len(active_weeks),
            "weeks": weeks,
            "avg_weekly_tss": 0.0,
            "weekly_tss": weekly_tss,
        }

    mean_tss = sum(active_weeks) / len(active_weeks)
    variance = sum((t - mean_tss) ** 2 for t in active_weeks) / len(active_weeks)
    std_tss  = _math.sqrt(variance)

    # cv=0 → perfect (score 100); cv≥1 → chaotic (score 0)
    # Active-weeks ratio penalises gaps (training 8/12 weeks → max 67 pts)
    cv           = std_tss / mean_tss if mean_tss > 0 else 1.0
    cv_score     = max(0.0, 1.0 - min(cv, 1.0))
    active_ratio = len(active_weeks) / weeks
    score        = round(cv_score * active_ratio * 100)

    return {
        "score": score,
        "weeks_active": len(active_weeks),
        "weeks": weeks,
        "avg_weekly_tss": round(mean_tss, 1),
        "weekly_tss": weekly_tss,
    }


@router.get("/efficiency")
def get_efficiency_trend(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """
    Aerobic Efficiency Factor (EF) trend, grouped by month.
    EF = (avg_speed_kmh / avg_heart_rate_bpm) × 100.
    Only Z2 endurance rides included (avg HR 60–78% of max HR, duration ≥ 30 min).
    A rising EF line = improving aerobic fitness.
    """
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    max_hr = user.max_hr

    activities = (
        db.query(models.Activity)
        .filter(
            models.Activity.user_id == current_user.id,
            models.Activity.avg_heart_rate_bpm.isnot(None),
            models.Activity.avg_speed_kmh > 5,
            models.Activity.duration_seconds >= 1800,  # at least 30 min
        )
        .order_by(models.Activity.date)
        .all()
    )

    monthly: dict[str, list] = {}
    for a in activities:
        hr_ref = max_hr or a.max_heart_rate_bpm
        if not hr_ref:
            continue
        hr_ratio = a.avg_heart_rate_bpm / hr_ref
        if not (0.60 <= hr_ratio <= 0.78):   # Z2 endurance band
            continue
        ef = (a.avg_speed_kmh / a.avg_heart_rate_bpm) * 100
        key = a.date.strftime("%Y-%m")
        monthly.setdefault(key, []).append(round(ef, 3))

    result = []
    for month in sorted(monthly):
        vals = monthly[month]
        result.append({
            "month": month,
            "ef":    round(sum(vals) / len(vals), 2),
            "rides": len(vals),
        })

    return {
        "data":       result,
        "has_max_hr": max_hr is not None,
    }
