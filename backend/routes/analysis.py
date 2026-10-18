import json
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_user
import models
import anthropic
from utils.access import has_full_access
from utils.ai_budget import HAIKU, api_key, check_quota, record_usage

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


def _build_prompt(activity: models.Activity, user: models.User, lang: str = "en") -> str:
    lang_instruction = (
        "Write entirely in European Portuguese (Portugal). Use natural PT-PT phrasing, not Brazilian Portuguese."
        if lang.startswith("pt") else
        "Write entirely in English."
    )
    lines = [
        f"You are a friendly cycling coach. {lang_instruction}",
        "Write a 2-3 paragraph analysis of the ride below.",
        "Be specific with the numbers. Cover: overall effort level, pacing and HR performance,",
        "climbing performance if climbs are listed (VAM, gradient, pacing, estimated power),",
        "aerobic efficiency (decoupling if available), durability/power fade if available,",
        "environment and weather context, and close with one specific coaching tip.",
        "Tone: conversational, encouraging, coach-like. No bullet points — flowing paragraphs only.",
        "Do not start with a markdown heading.",
        "",
        "RIDE DATA:",
        f"  Name:           {activity.name}",
        f"  Date:           {activity.date.strftime('%A %d %B %Y')}",
    ]

    # Indoor/outdoor context
    env = activity.ride_environment
    if env == "indoor":
        platform = activity.indoor_platform or "trainer"
        lines.append(f"  Environment:    Indoor ({platform})")
    elif env == "outdoor":
        lines.append(f"  Environment:    Outdoor")

    lines += [
        f"  Distance:       {activity.distance_km:.2f} km",
        f"  Duration:       {_fmt_duration(activity.duration_seconds)}",
    ]

    # Stop time
    if activity.elapsed_seconds and activity.elapsed_seconds > activity.duration_seconds + 60:
        stop_secs = activity.elapsed_seconds - activity.duration_seconds
        lines.append(f"  Elapsed time:   {_fmt_duration(activity.elapsed_seconds)} ({_fmt_duration(stop_secs)} stopped)")

    lines += [
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
            avg_pct = (activity.avg_heart_rate_bpm / user.max_hr) * 100
            lines.append(f"  Rider max HR:   {user.max_hr} bpm  (avg was {avg_pct:.0f}% of max)")

    if activity.avg_cadence_rpm:
        lines.append(f"  Avg cadence:    {activity.avg_cadence_rpm:.0f} rpm")
        lines.append(f"  Max cadence:    {activity.max_cadence_rpm:.0f} rpm")

    if activity.avg_power_w:
        lines.append(f"  Avg power:      {activity.avg_power_w:.0f} W")
        if activity.normalized_power_w:
            lines.append(f"  Norm. power:    {activity.normalized_power_w} W  (higher NP vs avg = more variable effort)")
        lines.append(f"  Max power:      {activity.max_power_w:.0f} W")
        tss_val = activity.corrected_tss or activity.tss
        if tss_val is not None:
            tss_label = "TSS (corrected)" if activity.corrected_tss else "TSS"
            lines.append(f"  {tss_label}:      {tss_val:.0f} pts  (<150 recoverable overnight, >300 needs days off)")

    # Detailed climbs from climb detection
    climbs = activity.climb_detections
    if climbs:
        lines.append(f"  Climbs detected: {len(climbs)}")
        for i, c in enumerate(climbs, 1):
            parts = [f"{c.elevation_gain_m:.0f}m gain", f"{c.avg_gradient_pct:.1f}% avg gradient"]
            if c.max_gradient_pct:
                parts.append(f"{c.max_gradient_pct:.1f}% max")
            if c.distance_m:
                parts.append(f"{c.distance_m / 1000:.1f} km long")
            if c.duration_seconds:
                parts.append(_fmt_duration(c.duration_seconds))
            if c.vam_m_per_hour:
                parts.append(f"VAM {c.vam_m_per_hour:.0f} m/h")
            if c.pacing_type:
                parts.append(f"pacing={c.pacing_type}")
            if c.estimated_wkg:
                parts.append(f"est. {c.estimated_wkg:.2f} W/kg")
            elif c.estimated_power_w:
                parts.append(f"est. {c.estimated_power_w:.0f} W")
            lines.append(f"    Climb {i}: {', '.join(parts)}")
    elif activity.climb_count:
        lines.append(f"  Climbs:         {activity.climb_count}")
        if activity.total_climbing_wkg_avg:
            lines.append(f"  Avg climb W/kg: {activity.total_climbing_wkg_avg:.2f}")
        # Compute VAM from track points as fallback
        vam = _compute_vam(activity)
        if vam:
            lines.append(f"  VAM (climb rate): {vam} m/h  (800 = solid endurance, 1500+ = pro climber)")
    else:
        # No climbs — still compute VAM if there's any elevation
        if (activity.elevation_gain_m or 0) > 20:
            vam = _compute_vam(activity)
            if vam:
                lines.append(f"  VAM (climb rate): {vam} m/h  (800 = solid endurance, 1500+ = pro climber)")

    # Decoupling — prefer adjusted value
    if activity.decoupling_adjusted is not None:
        adj = activity.decoupling_adjusted
        quality = activity.decoupling_quality or "unknown"
        lines.append(
            f"  Adj. Decoupling: {adj:+.1f}%  (<5% = good aerobic efficiency, quality={quality}; corrected for terrain/heat/hydration)"
        )
        if activity.decoupling_warning:
            lines.append(f"  Decoupling note: {activity.decoupling_warning}")
    else:
        hr_dec = _compute_hr_decoupling(activity)
        if hr_dec:
            aerobic_note = "good aerobic efficiency" if hr_dec['aerobic'] else "aerobic drift — fatigue or under-fuelled"
            lines.append(f"  HR Decoupling:  {hr_dec['pct']:+.1f}%  (<5% = well-conditioned, {aerobic_note})")

    # Durability analysis
    da = activity.durability_analysis
    if da and da.durability_index is not None:
        fade = f", fade {da.fade_rate_pct_per_hour:+.1f}%/h" if da.fade_rate_pct_per_hour is not None else ""
        lines.append(f"  Durability:     {da.durability_index:.0f}/100 ({da.durability_category or 'n/a'}){fade}")
        if all(v is not None for v in [da.q1_output, da.q2_output, da.q3_output, da.q4_output]):
            unit = da.output_unit or ""
            lines.append(
                f"  Quarter outputs ({unit}): Q1={da.q1_output:.1f}, Q2={da.q2_output:.1f}, "
                f"Q3={da.q3_output:.1f}, Q4={da.q4_output:.1f}"
            )

    # Weather (skip for indoor rides)
    if env != "indoor":
        temp_c = activity.sensor_temp_avg_c or activity.weather_temp_c
        if activity.weather_desc or temp_c is not None or activity.weather_wind_kmh is not None:
            parts = []
            if activity.weather_desc:
                parts.append(activity.weather_desc)
            if temp_c is not None:
                label = "sensor" if activity.sensor_temp_avg_c else "station"
                parts.append(f"{temp_c:.0f}°C ({label})")
            if activity.weather_wind_kmh is not None:
                parts.append(f"wind {activity.weather_wind_kmh:.0f} km/h")
            if activity.weather_humidity_pct is not None:
                parts.append(f"humidity {activity.weather_humidity_pct:.0f}%")
            lines.append(f"  Weather:        {', '.join(parts)}")

    # Calories
    if activity.calories:
        lines.append(f"  Calories:       {activity.calories} kcal")
    else:
        est = _estimate_calories(activity, user)
        if est:
            lines.append(f"  Est. calories:  {est} kcal  (MET-based estimate)")

    # Hydration
    if activity.hydration_ml:
        lines.append(f"  Hydration:      {activity.hydration_ml} ml logged")

    return "\n".join(lines)


@router.get("/{activity_id}/analysis")
def get_analysis(
    activity_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    lang: str = Query(default="en"),
    regenerate: bool = Query(default=False),
):
    activity = db.query(models.Activity).filter(models.Activity.id == activity_id, models.Activity.user_id == current_user.id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    if not has_full_access(current_user):
        raise HTTPException(status_code=403, detail="AI ride analysis is a Pro feature. Upgrade to unlock ride insights.")

    if activity.ai_analysis and not regenerate:
        return {"analysis": activity.ai_analysis, "cached": True}

    # The saved analysis is only replaced once a new one exists, so a refused
    # regeneration (quota, budget) never loses it.
    check_quota(db, current_user, "analysis")
    prompt = _build_prompt(activity, current_user, lang)

    try:
        client = anthropic.Anthropic(api_key=api_key())
        message = client.messages.create(
            model=HAIKU,
            max_tokens=900,
            messages=[{"role": "user", "content": prompt}],
        )
        analysis = message.content[0].text
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {str(e)}")
    record_usage(db, current_user.id, "analysis", HAIKU, message.usage)

    activity.ai_analysis = analysis
    db.commit()
    return {"analysis": analysis, "cached": False}


@router.get("/{activity_id}/analysis/stream")
async def stream_analysis(
    activity_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    lang: str = Query(default="en"),
    regenerate: bool = Query(default=False),
):
    activity = db.query(models.Activity).filter(
        models.Activity.id == activity_id,
        models.Activity.user_id == current_user.id,
    ).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    if not has_full_access(current_user):
        raise HTTPException(status_code=403, detail="AI ride analysis is a Pro feature.")

    if activity.ai_analysis and not regenerate:
        async def send_cached():
            yield f"data: {json.dumps({'text': activity.ai_analysis, 'done': True, 'cached': True})}\n\n"
        return StreamingResponse(send_cached(), media_type="text/event-stream",
                                  headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    check_quota(db, current_user, "analysis")
    prompt = _build_prompt(activity, current_user, lang)
    activity_id_val = activity.id
    user_id_val = current_user.id

    async def generate():
        full_text = ""
        try:
            async_client = anthropic.AsyncAnthropic(api_key=api_key())
            async with async_client.messages.stream(
                model=HAIKU,
                max_tokens=900,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                async for text in stream.text_stream:
                    full_text += text
                    yield f"data: {json.dumps({'text': text, 'done': False})}\n\n"
                final = await stream.get_final_message()
            record_usage(db, user_id_val, "analysis", HAIKU, final.usage)

            act = db.query(models.Activity).filter_by(id=activity_id_val).first()
            if act:
                act.ai_analysis = full_text
                db.commit()
            yield f"data: {json.dumps({'text': '', 'done': True, 'cached': False})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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
