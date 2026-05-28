import csv
import io
import os
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Body, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_user
import models
import schemas
from parsers.gpx_parser import parse_gpx
from parsers.fit_parser import parse_fit
from utils import compute_suffer_score, compute_distance_prs, match_segment, compute_normalized_power, compute_tss, compute_hrtss
from utils.hydration import build_analysis as build_hydration_analysis, update_heat_adaptation
from utils.durability import validate_durability_calculation, calculate_durability
from utils.indoor_detection import detect_ride_environment
from utils.indoor_outdoor_gap import apply_correction_factors, update_indoor_outdoor_gap
from typing import List, Optional
import httpx

log = logging.getLogger(__name__)


def _moderate_notes(text: str) -> tuple[bool, str]:
    """
    Returns (is_safe, reason). Defaults to safe on any error so legitimate
    notes are never blocked by API unavailability.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or not text or not text.strip():
        return True, ""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=60,
            system=(
                "You are a content moderator for a cycling training app. "
                "Users write personal notes about their rides — venting about hard efforts, "
                "bad weather, or frustration is completely normal and should be allowed. "
                "Only flag content that contains: hate speech targeting a group, harassment "
                "directed at another person, explicit sexual content, or encouragement of "
                "self-harm or violence. "
                "Reply with exactly one word on the first line: SAFE or UNSAFE. "
                "If UNSAFE, add a second line with a brief reason (max 10 words)."
            ),
            messages=[{"role": "user", "content": text[:2000]}],
        )
        lines = resp.content[0].text.strip().splitlines()
        verdict = lines[0].strip().upper()
        reason = lines[1].strip() if len(lines) > 1 else ""
        return verdict != "UNSAFE", reason
    except Exception as e:
        log.warning("Note moderation skipped: %s", e)
        return True, ""

router = APIRouter()

# ── Weather ───────────────────────────────────────────────────────────────────

_WMO = {
    0: "Clear", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
    45: "Fog", 48: "Freezing Fog",
    51: "Light Drizzle", 53: "Drizzle", 55: "Heavy Drizzle",
    61: "Light Rain", 63: "Rain", 65: "Heavy Rain",
    71: "Light Snow", 73: "Snow", 75: "Heavy Snow",
    80: "Showers", 81: "Heavy Showers", 82: "Violent Showers",
    95: "Thunderstorm",
}


async def _fetch_weather(lat: float, lon: float, dt: datetime) -> dict:
    date_str = dt.strftime("%Y-%m-%d")
    url = (
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lat:.4f}&longitude={lon:.4f}"
        f"&start_date={date_str}&end_date={date_str}"
        f"&hourly=temperature_2m,windspeed_10m,weathercode,relative_humidity_2m&timezone=auto"
    )
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(url)
            data = r.json()
        hourly = data.get("hourly", {})
        idx = min(dt.hour, len(hourly.get("time", [])) - 1)
        temps = hourly.get("temperature_2m", [])
        winds = hourly.get("windspeed_10m", [])
        codes = hourly.get("weathercode", [])
        hum   = hourly.get("relative_humidity_2m", [])
        code  = codes[idx] if idx < len(codes) else None
        return {
            "weather_temp_c":    round(temps[idx], 1) if idx < len(temps) else None,
            "weather_wind_kmh":  round(winds[idx], 1) if idx < len(winds) else None,
            "weather_desc":      _WMO.get(int(code), f"Code {code}") if code is not None else None,
            "weather_humidity_pct": round(hum[idx], 1) if idx < len(hum) else None,
        }
    except Exception:
        return {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_hydration_analysis(db: Session, activity: models.Activity, user: models.User) -> None:
    """Create or replace HydrationAnalysis for the given activity."""
    temp_c = activity.weather_temp_c if activity.weather_temp_c is not None else 20.0
    duration_h = (activity.duration_seconds or 0) / 3600

    if duration_h < 0.1:
        return  # not worth analysing sub-6-min efforts

    # Intensity factor: NP/FTP preferred, HR-based fallback
    if activity.normalized_power_w and user.ftp and user.ftp > 0:
        intensity_factor = min(1.0, activity.normalized_power_w / user.ftp)
    elif activity.avg_heart_rate_bpm and user.max_hr and user.max_hr > 0:
        lthr = 0.85 * user.max_hr
        intensity_factor = min(1.0, activity.avg_heart_rate_bpm / lthr)
    else:
        intensity_factor = 0.65  # conservative moderate-effort default

    analysis_data = build_hydration_analysis(
        temp_c=temp_c,
        humidity_pct=activity.weather_humidity_pct,
        wind_speed_kmh=activity.weather_wind_kmh,
        max_temp_c=None,
        duration_h=duration_h,
        intensity_factor=intensity_factor,
        intake_ml=activity.hydration_ml,
        weight_kg=user.weight_kg,
        user_calibrated_ml_h=user.sweat_rate_ml_per_hour,
        heat_adaptation=user.heat_adaptation_level,
    )

    existing = db.query(models.HydrationAnalysis).filter(
        models.HydrationAnalysis.activity_id == activity.id
    ).first()
    if existing:
        for k, v in analysis_data.items():
            setattr(existing, k, v)
    else:
        db.add(models.HydrationAnalysis(activity_id=activity.id, **analysis_data))

    # Update user heat-adaptation counter (hot = ≥ 27°C)
    current_rides = user.heat_rides_last_14d or 0
    new_rides, new_level = update_heat_adaptation(current_rides, False, temp_c)
    user.heat_rides_last_14d = new_rides
    user.heat_adaptation_level = new_level


def _get_tsb_at_date(db: Session, user_id: int, target_date: datetime) -> float | None:
    """Compute TSB (CTL − ATL) using the Banister EMA model up to the day before target_date."""
    from datetime import date as date_type, timedelta
    activities = (
        db.query(models.Activity)
        .filter(
            models.Activity.user_id == user_id,
            models.Activity.date < target_date,
        )
        .order_by(models.Activity.date)
        .all()
    )
    if not activities:
        return None

    daily_load: dict = {}
    for a in activities:
        d = a.date.date()
        load = a.tss or a.suffer_score or 0
        daily_load[d] = daily_load.get(d, 0) + load

    start = activities[0].date.date()
    end   = target_date.date() - timedelta(days=1)
    ctl = atl = 0.0
    cur = start
    while cur <= end:
        load = daily_load.get(cur, 0.0)
        ctl += (load - ctl) / 42
        atl += (load - atl) / 7
        cur += timedelta(days=1)

    return round(ctl - atl, 1)


def _run_durability_analysis(
    db: Session,
    activity: models.Activity,
    track_points: list,
    user: models.User,
) -> None:
    """Compute and persist DurabilityAnalysis if the ride is eligible."""
    if (activity.duration_seconds or 0) < 2700:
        return

    can_calc, _, reason = validate_durability_calculation(
        activity.duration_seconds,
        len(track_points),
        activity.notes,
        activity.avg_heart_rate_bpm,
        activity.max_heart_rate_bpm or user.max_hr,
    )
    if not can_calc:
        log.debug("Durability skipped for activity %s: %s", activity.id, reason)
        return

    tsb = _get_tsb_at_date(db, user.id, activity.date)

    result = calculate_durability(
        duration_seconds=activity.duration_seconds,
        track_points=track_points,
        climb_detections=[],          # Phase B not on this branch; graceful fallback
        max_hr=float(activity.max_heart_rate_bpm or user.max_hr or 0) or None,
        ftp=user.ftp,
        weight_kg=user.weight_kg,
        tsb_at_start=tsb,
        temperature_avg_c=activity.weather_temp_c,
        notes=activity.notes,
    )

    if result is None:
        return

    existing = db.query(models.DurabilityAnalysis).filter(
        models.DurabilityAnalysis.activity_id == activity.id
    ).first()

    db_fields = {k: v for k, v in result.items() if k != "context"}
    if existing:
        for k, v in db_fields.items():
            setattr(existing, k, v)
    else:
        db.add(models.DurabilityAnalysis(activity_id=activity.id, **db_fields))

    activity.durability_index = result["durability_index"]


def _run_indoor_detection(
    db: Session,
    activity: models.Activity,
    track_points: list,
    user,
    file_metadata: dict | None = None,
) -> None:
    """Detect indoor/outdoor environment, apply correction if gap is known."""
    env = detect_ride_environment(
        track_points,
        activity_name=activity.name,
        file_metadata=file_metadata or {},
    )
    activity.ride_environment        = env["environment"]
    activity.ride_environment_source = "auto_detected"
    activity.indoor_platform         = env.get("platform")

    if env["environment"] == "indoor":
        profile = db.query(models.IndoorOutdoorProfile).filter(
            models.IndoorOutdoorProfile.user_id == user.id
        ).first()
        if profile and (
            profile.power_gap_pct is not None
            or profile.manual_power_gap_pct is not None
        ):
            correction = apply_correction_factors(activity, profile)
            activity.power_correction_factor = correction["power_correction_factor"]
            activity.hr_correction_factor    = correction["hr_correction_factor"]
            activity.corrected_tss           = correction["corrected_tss"]

    # Refresh the per-user gap profile with this new ride included
    try:
        update_indoor_outdoor_gap(user.id, db)
    except Exception as _gap_err:
        log.warning("Gap update failed for user %s: %s", user.id, _gap_err)


def _match_segments(db: Session, track_points: list, activity: models.Activity):
    for seg in db.query(models.Segment).all():
        effort = match_segment(track_points, seg)
        if effort:
            db.add(models.SegmentEffort(
                segment_id=seg.id, activity_id=activity.id,
                elapsed_seconds=effort["elapsed_seconds"],
                avg_speed_kmh=effort.get("avg_speed_kmh"),
                avg_hr=effort.get("avg_hr"),
                set_at=activity.date,
            ))


def _update_prs(db: Session, track_points: list, activity: models.Activity):
    prs = compute_distance_prs(track_points)
    for pr_type, value_seconds in prs.items():
        existing = db.query(models.PersonalRecord).filter(
            models.PersonalRecord.pr_type == pr_type,
            models.PersonalRecord.user_id == activity.user_id,
        ).first()
        if existing is None or value_seconds < existing.value:
            if existing:
                existing.value = value_seconds
                existing.activity_id = activity.id
                existing.set_at = activity.date
            else:
                db.add(models.PersonalRecord(
                    pr_type=pr_type, value=value_seconds,
                    activity_id=activity.id, set_at=activity.date,
                    user_id=activity.user_id,
                ))


def _build_gpx(activity: models.Activity) -> str:
    ns = 'xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1"'
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<gpx version="1.1" creator="VeloStats" {ns}>',
        f'<metadata><name>{activity.name}</name><time>{activity.date.isoformat()}Z</time></metadata>',
        '<trk>', f'<name>{activity.name}</name>', '<trkseg>',
    ]
    for tp in activity.track_points:
        if tp.lat is None or tp.lon is None:
            continue
        lines.append(f'<trkpt lat="{tp.lat}" lon="{tp.lon}">')
        if tp.elevation is not None:
            lines.append(f'<ele>{tp.elevation}</ele>')
        if tp.timestamp:
            lines.append(f'<time>{tp.timestamp.isoformat()}Z</time>')
        exts = []
        if tp.heart_rate_bpm:
            exts.append(f'<gpxtpx:hr>{int(tp.heart_rate_bpm)}</gpxtpx:hr>')
        if tp.cadence_rpm:
            exts.append(f'<gpxtpx:cad>{int(tp.cadence_rpm)}</gpxtpx:cad>')
        if exts:
            lines.append('<extensions><gpxtpx:TrackPointExtension>')
            lines.extend(exts)
            lines.append('</gpxtpx:TrackPointExtension></extensions>')
        lines.append('</trkpt>')
    lines += ['</trkseg>', '</trk>', '</gpx>']
    return '\n'.join(lines)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=schemas.ActivityOut)
async def upload_activity(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    content = await file.read()
    filename = (file.filename or "").lower()

    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 50 MB.")

    if (current_user.membership or "free") == "free":
        from sqlalchemy import func as _func
        count = db.query(_func.count(models.Activity.id)).filter(models.Activity.user_id == current_user.id).scalar() or 0
        if count >= 15:
            raise HTTPException(status_code=403, detail="Free plan limit reached (15 activities). Upgrade to Pro to upload unlimited activities.")

    # Validate actual content, not just the extension
    is_gpx_content = content.lstrip()[:5] == b"<?xml" or b"<gpx" in content[:512]
    # FIT files have a fixed 12/14-byte header ending with the ASCII string ".FIT"
    is_fit_content = len(content) >= 12 and content[8:12] == b".FIT"

    if filename.endswith(".gpx") and is_gpx_content:
        data = parse_gpx(content)
    elif filename.endswith(".fit") and is_fit_content:
        data = parse_fit(content)
    elif filename.endswith(".gpx") or filename.endswith(".fit"):
        raise HTTPException(status_code=400, detail="File content does not match the declared file type.")
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type. Upload a .gpx or .fit file.")

    track_points = data.pop("track_points")
    laps_data = data.pop("laps", [])
    data["suffer_score"] = compute_suffer_score(track_points, data.get("max_heart_rate_bpm"))

    # Recompute avg cadence excluding zeros (coasting / downhill)
    active_cad = [tp["cadence_rpm"] for tp in track_points if tp.get("cadence_rpm") and tp["cadence_rpm"] > 0]
    data["avg_cadence_rpm"] = round(sum(active_cad) / len(active_cad), 1) if active_cad else None

    # Fetch weather from first GPS point
    first_gps = next((tp for tp in track_points if tp.get("lat") and tp.get("lon")), None)
    if first_gps:
        weather = await _fetch_weather(first_gps["lat"], first_gps["lon"], data["date"])
        data.update(weather)

    activity = models.Activity(**data, user_id=current_user.id)
    db.add(activity)
    db.flush()

    for tp in track_points:
        db.add(models.TrackPoint(activity_id=activity.id, **tp))

    for lap in laps_data:
        db.add(models.Lap(activity_id=activity.id, **lap))

    _update_prs(db, track_points, activity)
    _match_segments(db, track_points, activity)

    # Compute and store NP + TSS
    np = compute_normalized_power(track_points)
    if np:
        activity.normalized_power_w = np
        if current_user.ftp:
            activity.tss = compute_tss(np, activity.duration_seconds, current_user.ftp)

    # Indoor/outdoor detection + correction
    try:
        _run_indoor_detection(db, activity, track_points, current_user)
    except Exception as _e:
        log.warning("Indoor/outdoor detection failed for activity %s: %s", activity.id, _e)

    # Hydration & heat strain analysis
    try:
        _run_hydration_analysis(db, activity, current_user)
    except Exception as _e:
        log.warning("Hydration analysis failed for activity %s: %s", activity.id, _e)

    # Durability profiling
    try:
        _run_durability_analysis(db, activity, track_points, current_user)
    except Exception as _e:
        log.warning("Durability analysis failed for activity %s: %s", activity.id, _e)

    db.commit()
    db.refresh(activity)
    return activity


@router.get("/", response_model=List[schemas.ActivityOut])
def list_activities(
    skip: int = 0, limit: int = 100,
    search: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    min_distance_km: Optional[float] = Query(None),
    max_distance_km: Optional[float] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    query = db.query(models.Activity).filter(models.Activity.user_id == current_user.id)
    if search:
        query = query.filter(models.Activity.name.ilike(f"%{search}%"))
    if date_from:
        query = query.filter(models.Activity.date >= datetime.fromisoformat(date_from))
    if date_to:
        query = query.filter(models.Activity.date <= datetime.fromisoformat(date_to))
    if min_distance_km is not None:
        query = query.filter(models.Activity.distance_km >= min_distance_km)
    if max_distance_km is not None:
        query = query.filter(models.Activity.distance_km <= max_distance_km)
    activities = query.order_by(models.Activity.date.desc()).offset(skip).limit(limit).all()

    result = []
    for a in activities:
        tss = a.tss
        if tss is None and a.avg_heart_rate_bpm and current_user.max_hr:
            tss_hr = compute_hrtss(a.duration_seconds, a.avg_heart_rate_bpm,
                                   current_user.max_hr, current_user.resting_hr)
            tss = round(tss_hr, 1) if tss_hr else None

        if a.normalized_power_w and current_user.ftp and current_user.ftp > 0:
            intensity_factor = round(a.normalized_power_w / current_user.ftp, 2)
        elif a.avg_heart_rate_bpm and current_user.max_hr and current_user.max_hr > 0:
            lthr = 0.85 * current_user.max_hr
            intensity_factor = round(a.avg_heart_rate_bpm / lthr, 2)
        else:
            intensity_factor = None

        result.append({
            "id": a.id, "name": a.name, "date": a.date,
            "distance_km": a.distance_km, "duration_seconds": a.duration_seconds,
            "avg_speed_kmh": a.avg_speed_kmh, "max_speed_kmh": a.max_speed_kmh,
            "avg_cadence_rpm": a.avg_cadence_rpm, "max_cadence_rpm": a.max_cadence_rpm,
            "avg_heart_rate_bpm": a.avg_heart_rate_bpm,
            "max_heart_rate_bpm": a.max_heart_rate_bpm,
            "elevation_gain_m": a.elevation_gain_m, "elevation_loss_m": a.elevation_loss_m,
            "calories": a.calories, "avg_power_w": a.avg_power_w, "max_power_w": a.max_power_w,
            "suffer_score": a.suffer_score, "notes": a.notes,
            "weather_temp_c": a.weather_temp_c, "weather_wind_kmh": a.weather_wind_kmh,
            "weather_desc": a.weather_desc, "file_type": a.file_type, "created_at": a.created_at,
            "tss": tss, "intensity_factor": intensity_factor,
        })
    return result


@router.get("/{activity_id}/export/csv")
def export_csv(activity_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if (current_user.membership or "free") == "free":
        raise HTTPException(status_code=403, detail="Activity export is a Pro feature. Upgrade to export your rides.")
    activity = db.query(models.Activity).filter(models.Activity.id == activity_id, models.Activity.user_id == current_user.id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "lat", "lon", "elevation_m", "speed_kmh", "heart_rate_bpm", "cadence_rpm", "power_w", "distance_m"])
    for tp in activity.track_points:
        writer.writerow([tp.timestamp, tp.lat, tp.lon, tp.elevation, tp.speed_kmh, tp.heart_rate_bpm, tp.cadence_rpm, tp.power_w, tp.distance_m])
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in activity.name).strip()
    filename = f"{safe}_{activity.date.strftime('%Y%m%d')}.csv"
    return StreamingResponse(io.BytesIO(output.getvalue().encode()), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{activity_id}/export/gpx")
def export_gpx(activity_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if (current_user.membership or "free") == "free":
        raise HTTPException(status_code=403, detail="Activity export is a Pro feature. Upgrade to export your rides.")
    activity = db.query(models.Activity).filter(models.Activity.id == activity_id, models.Activity.user_id == current_user.id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    gpx_str = _build_gpx(activity)
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in activity.name).strip()
    filename = f"{safe}_{activity.date.strftime('%Y%m%d')}.gpx"
    return StreamingResponse(io.BytesIO(gpx_str.encode()), media_type="application/gpx+xml",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{activity_id}", response_model=schemas.ActivityDetail)
def get_activity(activity_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    activity = db.query(models.Activity).filter(models.Activity.id == activity_id, models.Activity.user_id == current_user.id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity


@router.patch("/{activity_id}/rename")
def rename_activity(activity_id: int, name: str = Body(..., embed=True),
                    db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    activity = db.query(models.Activity).filter(models.Activity.id == activity_id, models.Activity.user_id == current_user.id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    activity.name = name
    db.commit()
    return {"id": activity_id, "name": name}


@router.patch("/{activity_id}/notes")
def update_notes(activity_id: int, notes: str = Body(..., embed=True),
                 db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    activity = db.query(models.Activity).filter(models.Activity.id == activity_id, models.Activity.user_id == current_user.id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    is_safe, reason = _moderate_notes(notes)
    if not is_safe:
        raise HTTPException(status_code=400, detail=f"Note contains inappropriate content and was not saved. {reason}".strip())

    activity.notes = notes
    db.commit()
    return {"id": activity_id, "notes": notes}


@router.delete("/{activity_id}")
def delete_activity(activity_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    activity = db.query(models.Activity).filter(models.Activity.id == activity_id, models.Activity.user_id == current_user.id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    db.delete(activity)
    db.commit()
    return {"message": "Deleted"}
