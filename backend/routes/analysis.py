import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_user
import models
import anthropic

router = APIRouter()


def _fmt_duration(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}h {m:02d}m" if h > 0 else f"{m}m {s:02d}s"


def _compute_vam(activity: models.Activity) -> int | None:
    pts = [tp for tp in activity.track_points if tp.elevation is not None and tp.timestamp is not None]
    if len(pts) < 2:
        return None
    total_gain, climb_secs = 0.0, 0.0
    for i in range(1, len(pts)):
        d_elev = pts[i].elevation - pts[i - 1].elevation
        if d_elev > 0:
            try:
                dt = (pts[i].timestamp - pts[i - 1].timestamp).total_seconds()
                if 0 < dt < 300:
                    total_gain += d_elev
                    climb_secs += dt
            except Exception:
                pass
    if climb_secs < 60 or total_gain < 10:
        return None
    return round((total_gain / climb_secs) * 3600)


def _compute_hr_decoupling(activity: models.Activity) -> dict | None:
    pts = [tp for tp in activity.track_points if tp.heart_rate_bpm is not None]
    if len(pts) < 20:
        return None
    if not any(tp.speed_kmh is not None for tp in pts):
        return None
    mid = len(pts) // 2
    first, second = pts[:mid], pts[mid:]

    def _avg(lst, attr):
        vals = [getattr(p, attr) for p in lst if getattr(p, attr) is not None]
        return sum(vals) / len(vals) if vals else None

    hr1, hr2 = _avg(first, 'heart_rate_bpm'), _avg(second, 'heart_rate_bpm')
    sp1, sp2 = _avg(first, 'speed_kmh'), _avg(second, 'speed_kmh')
    if not all([hr1, hr2, sp1, sp2]) or hr1 == 0:
        return None
    r1, r2 = sp1 / hr1, sp2 / hr2
    if r1 == 0:
        return None
    pct = round(((r1 - r2) / r1) * 100, 1)
    return {'pct': pct, 'aerobic': pct < 5}


def _estimate_calories(activity: models.Activity, user: models.User) -> int | None:
    if activity.calories:
        return None
    weight = getattr(user, 'weight_kg', None)
    if not weight:
        return None
    speed = activity.avg_speed_kmh or 0
    met = 6.0 if speed < 16 else 8.0 if speed < 19 else 10.0 if speed < 22 else 12.0 if speed < 25 else 14.0
    return round(met * weight * (activity.duration_seconds / 3600))


def _build_prompt(activity: models.Activity, user: models.User) -> str:
    lines = [
        "You are a friendly cycling coach. Write a 2-3 paragraph analysis of the ride below.",
        "Be specific with the numbers. Cover: overall effort level, pacing and speed consistency,",
        "heart rate performance and zone distribution (if available), elevation impact,",
        "aerobic efficiency (HR decoupling and VAM if available), weather effect (if available),",
        "and close with one short recovery or training tip.",
        "Tone: conversational, encouraging, coach-like. No bullet points — flowing paragraphs only.",
        "",
        "RIDE DATA:",
        f"  Name:           {activity.name}",
        f"  Date:           {activity.date.strftime('%A %d %B %Y')}",
        f"  Distance:       {activity.distance_km:.2f} km",
        f"  Duration:       {_fmt_duration(activity.duration_seconds)}",
        f"  Avg speed:      {activity.avg_speed_kmh:.1f} km/h",
        f"  Max speed:      {activity.max_speed_kmh:.1f} km/h",
        f"  Elevation gain: {activity.elevation_gain_m:.0f} m",
        f"  Elevation loss: {activity.elevation_loss_m:.0f} m",
    ]

    if activity.suffer_score is not None:
        lines.append(
            f"  Suffer score:   {activity.suffer_score} "
            f"(reference: <20 easy, 20-50 moderate, 50-100 hard, >100 very hard)"
        )

    if activity.avg_heart_rate_bpm:
        lines.append(f"  Avg HR:         {activity.avg_heart_rate_bpm:.0f} bpm")
        lines.append(f"  Max HR:         {activity.max_heart_rate_bpm:.0f} bpm")
        if user.max_hr:
            max_hr = user.max_hr
            avg_pct = (activity.avg_heart_rate_bpm / max_hr) * 100
            lines.append(f"  Rider max HR:   {max_hr} bpm  (avg was {avg_pct:.0f}% of max)")

    if activity.avg_cadence_rpm:
        lines.append(f"  Avg cadence:    {activity.avg_cadence_rpm:.0f} rpm")
        lines.append(f"  Max cadence:    {activity.max_cadence_rpm:.0f} rpm")

    if activity.avg_power_w:
        lines.append(f"  Avg power:      {activity.avg_power_w:.0f} W")
        lines.append(f"  Max power:      {activity.max_power_w:.0f} W")
        if activity.tss is not None:
            lines.append(f"  TSS:            {activity.tss:.0f} pts  (<150 recoverable overnight, >300 needs days off)")

    # VAM — computed from track points
    vam = _compute_vam(activity)
    if vam:
        lines.append(f"  VAM (climb rate): {vam} m/h  (800 = solid endurance, 1500+ = pro climber)")

    # HR Decoupling — aerobic efficiency
    hr_dec = _compute_hr_decoupling(activity)
    if hr_dec:
        aerobic_note = "good aerobic efficiency" if hr_dec['aerobic'] else "aerobic drift — fatigue or under-fuelled"
        lines.append(
            f"  HR Decoupling:  {hr_dec['pct']:+.1f}%  (<5% = well-conditioned, {aerobic_note})"
        )

    if activity.weather_desc or activity.weather_temp_c is not None:
        parts = []
        if activity.weather_desc:
            parts.append(activity.weather_desc)
        if activity.weather_temp_c is not None:
            parts.append(f"{activity.weather_temp_c}°C")
        if activity.weather_wind_kmh is not None:
            parts.append(f"wind {activity.weather_wind_kmh} km/h")
        lines.append(f"  Weather:        {', '.join(parts)}")

    if activity.calories:
        lines.append(f"  Calories:       {activity.calories} kcal")
    else:
        est = _estimate_calories(activity, user)
        if est:
            lines.append(f"  Est. calories:  {est} kcal  (MET-based estimate)")

    return "\n".join(lines)


@router.get("/{activity_id}/analysis")
def get_analysis(
    activity_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    activity = db.query(models.Activity).filter(models.Activity.id == activity_id, models.Activity.user_id == current_user.id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    if (current_user.membership or "free") == "free":
        raise HTTPException(status_code=403, detail="AI ride analysis is a Pro feature. Upgrade to unlock ride insights.")

    if activity.ai_analysis:
        return {"analysis": activity.ai_analysis, "cached": True}

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY is not set. Add it to your environment and restart the server."
        )

    prompt = _build_prompt(activity, current_user)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=750,
            messages=[{"role": "user", "content": prompt}],
        )
        analysis = message.content[0].text
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {str(e)}")

    activity.ai_analysis = analysis
    db.commit()
    return {"analysis": analysis, "cached": False}


@router.delete("/{activity_id}/analysis")
def clear_analysis(
    activity_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Clear cached analysis so it gets regenerated next time."""
    activity = db.query(models.Activity).filter(models.Activity.id == activity_id, models.Activity.user_id == current_user.id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    activity.ai_analysis = None
    db.commit()
    return {"message": "Analysis cleared"}
