import base64
import csv
import hashlib
import io
import json
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File, Body, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db, SessionLocal
from auth import get_current_user
import models
import schemas
from parsers.gpx_parser import parse_gpx
from parsers.fit_parser import parse_fit
from utils import compute_suffer_score, compute_distance_prs, match_segment, compute_normalized_power, compute_tss, compute_hrtss, compute_hrtss_heat_corrected, estimate_calories_from_hr
from utils.hydration import build_analysis as build_hydration_analysis, update_heat_adaptation, hr_to_intensity_factor
from utils.durability import validate_durability_calculation, calculate_durability
from utils.decoupling import calculate_adjusted_decoupling
from utils.indoor_detection import detect_ride_environment
from utils.indoor_outdoor_gap import apply_correction_factors, update_indoor_outdoor_gap
from utils.climb_detection import detect_climbs
from utils.power_estimation import estimate_climbing_power, BIKE_DEFAULTS
from utils.rate_limit import check_rate_limit
from utils.access import has_full_access
from utils.ai_budget import HAIKU, allow_light_call, api_key as ai_api_key, record_usage
from typing import List, Optional
import httpx

log = logging.getLogger(__name__)


def _moderate_notes(text: str, db: Session, user) -> tuple[bool, str]:
    """
    Returns (is_safe, reason). Defaults to safe on any error, or once the AI
    budget or the user's daily cap is used up, so legitimate notes are never
    blocked by API unavailability. Notes are only visible to their owner.
    """
    if not text or not text.strip() or not allow_light_call(db, user, "moderation"):
        return True, ""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ai_api_key())
        resp = client.messages.create(
            model=HAIKU,
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
        record_usage(db, user.id, "moderation", HAIKU, resp.usage)
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
    # Prefer sensor temp (actual on-bike reading) over weather API (shade / start of ride only)
    temp_c = (
        activity.sensor_temp_avg_c
        if activity.sensor_temp_avg_c is not None
        else (activity.weather_temp_c if activity.weather_temp_c is not None else 20.0)
    )
    # Use elapsed wall-clock time for FIT files (captures heat exposure during stops).
    # GPX duration_seconds already equals elapsed time.
    duration_h = (activity.elapsed_seconds or activity.duration_seconds or 0) / 3600

    if duration_h < 0.1:
        return  # not worth analysing sub-6-min efforts

    # Intensity factor: NP/FTP preferred, Karvonen %HRR fallback (approximates
    # %VO2max, matching the IF scale the sweat-rate model is calibrated against)
    if activity.normalized_power_w and user.ftp and user.ftp > 0:
        intensity_factor = min(1.0, activity.normalized_power_w / user.ftp)
    else:
        hr_if = hr_to_intensity_factor(
            activity.avg_heart_rate_bpm, user.max_hr, getattr(user, "resting_hr", None)
        )
        intensity_factor = hr_if if hr_if is not None else 0.65  # conservative moderate default

    is_indoor = activity.ride_environment == "indoor"

    analysis_data = build_hydration_analysis(
        temp_c=temp_c,
        humidity_pct=activity.weather_humidity_pct,
        wind_speed_kmh=activity.weather_wind_kmh,
        max_temp_c=activity.sensor_temp_max_c,
        duration_h=duration_h,
        intensity_factor=intensity_factor,
        intake_ml=activity.hydration_ml,
        weight_kg=user.weight_kg,
        user_calibrated_ml_h=user.sweat_rate_ml_per_hour,
        heat_adaptation=user.heat_adaptation_level,
        is_indoor=is_indoor,
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


def _run_decoupling_analysis(
    db: Session,
    activity: models.Activity,
    track_points: list,
    user: models.User,
) -> None:
    """Compute and persist adjusted decoupling if the ride is eligible."""
    result = calculate_adjusted_decoupling(activity, track_points, user)
    if result is None:
        return
    activity.decoupling_raw             = result.get("decoupling_raw")
    activity.decoupling_adjusted        = result.get("decoupling_adjusted")
    activity.decoupling_components_json = result.get("decoupling_components_json")
    activity.decoupling_quality         = result.get("decoupling_quality")
    activity.decoupling_warning         = result.get("decoupling_warning")


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


def _run_climb_analysis(
    db: Session,
    activity: models.Activity,
    track_points: list,
    user: models.User,
) -> None:
    """Detect climbs and estimate power (Phase B). No-op without weight or GPS."""
    if not (user.weight_kg and track_points):
        return

    bike_params = dict(BIKE_DEFAULTS.get(user.bike_type, BIKE_DEFAULTS[None]))
    if user.bike_weight_kg:
        bike_params["bike_weight_kg"] = user.bike_weight_kg
    if user.calibrated_cda:
        bike_params["cda"] = user.calibrated_cda
    if user.calibrated_crr:
        bike_params["crr"] = user.calibrated_crr

    climbs = detect_climbs(track_points)
    activity.climb_count = len(climbs)

    climbs_with_power = []
    for climb in climbs:
        avg_alt = None
        seg_pts = track_points[climb["start_trackpoint_idx"]:climb["end_trackpoint_idx"] + 1]
        elev_vals = [p.get("elevation") for p in seg_pts if p.get("elevation") is not None]
        if elev_vals:
            avg_alt = sum(elev_vals) / len(elev_vals)

        power_est = estimate_climbing_power(
            climb, user.weight_kg,
            bike_weight_kg=bike_params["bike_weight_kg"],
            crr=bike_params["crr"],
            cda=bike_params["cda"],
            altitude_m=avg_alt,
        )
        method = "calibrated" if user.calibrated_cda else "physics"

        db_climb = models.ClimbDetection(
            activity_id=activity.id,
            start_trackpoint_idx=climb["start_trackpoint_idx"],
            end_trackpoint_idx=climb["end_trackpoint_idx"],
            start_distance_m=climb["start_distance_m"],
            end_distance_m=climb["end_distance_m"],
            distance_m=climb["distance_m"],
            elevation_gain_m=climb["elevation_gain_m"],
            avg_gradient_pct=climb["avg_gradient_pct"],
            max_gradient_pct=climb["max_gradient_pct"],
            duration_seconds=climb["duration_seconds"],
            avg_speed_kmh=climb["avg_speed_kmh"],
            avg_heart_rate=climb["avg_heart_rate"],
            max_heart_rate=climb["max_heart_rate"],
            vam_m_per_hour=climb["vam_m_per_hour"],
            estimated_power_w=power_est["estimated_power_w"],
            estimated_power_low_w=power_est["estimated_power_low_w"],
            estimated_power_high_w=power_est["estimated_power_high_w"],
            estimated_wkg=power_est["estimated_wkg"],
            estimation_quality=power_est["estimation_quality"],
            estimation_method=method,
            pacing_type=climb["pacing_type"],
            first_half_speed=climb["first_half_speed"],
            second_half_speed=climb["second_half_speed"],
        )
        db.add(db_climb)
        if power_est["estimated_power_w"] is not None:
            climbs_with_power.append({
                "power_w": power_est["estimated_power_w"],
                "duration_s": climb["duration_seconds"],
            })

    if climbs_with_power:
        total_dur = sum(c["duration_s"] for c in climbs_with_power)
        if total_dur > 0:
            activity.total_climbing_power_avg_w = round(
                sum(c["power_w"] * c["duration_s"] for c in climbs_with_power) / total_dur, 1
            )
            activity.total_climbing_wkg_avg = round(
                activity.total_climbing_power_avg_w / user.weight_kg, 2
            )


def _run_post_upload_analysis(activity_id: int, user_id: int, track_points: list) -> None:
    """Run the heavy analysis pipeline off the request path, in its own session.

    Scheduled as a FastAPI background task so the upload response returns as soon
    as the core activity is saved. Each stage is isolated so one failure never
    blocks the rest. ``track_points`` are the plain parsed dicts (not ORM rows),
    so they remain valid after the request session closes.
    """
    db = SessionLocal()
    try:
        activity = db.get(models.Activity, activity_id)
        user = db.get(models.User, user_id)
        if not activity or not user:
            return

        for label, fn in (
            ("Indoor/outdoor detection", lambda: _run_indoor_detection(db, activity, track_points, user)),
            ("Hydration analysis",       lambda: _run_hydration_analysis(db, activity, user)),
            ("Durability analysis",      lambda: _run_durability_analysis(db, activity, track_points, user)),
            ("Decoupling analysis",      lambda: _run_decoupling_analysis(db, activity, track_points, user)),
            ("Climb detection",          lambda: _run_climb_analysis(db, activity, track_points, user)),
        ):
            try:
                fn()
            except Exception as _e:
                log.warning("%s failed for activity %s: %s", label, activity_id, _e)

        db.commit()
    except Exception as _e:
        log.warning("Post-upload analysis failed for activity %s: %s", activity_id, _e)
        db.rollback()
    finally:
        db.close()


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
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    check_rate_limit(request.client.host, "upload", db)
    content = await file.read()
    filename = (file.filename or "").lower()

    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 50 MB.")

    file_hash = hashlib.sha256(content).hexdigest()
    duplicate = db.query(models.Activity).filter(
        models.Activity.user_id == current_user.id,
        models.Activity.file_hash == file_hash,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail=f"This ride was already uploaded (activity #{duplicate.id}).")

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

    # Fuzzy duplicate check — catches rides uploaded before the hash system
    # and cross-format duplicates (same ride as GPX then FIT).
    # Match: same day + duration within 60 s + distance within 0.5 km.
    if data.get("date") and data.get("duration_seconds") and data.get("distance_km"):
        ride_date = data["date"]
        day_start = ride_date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end   = day_start + timedelta(days=1)
        dur       = data["duration_seconds"]
        dist      = data["distance_km"]
        fuzzy_dup = db.query(models.Activity).filter(
            models.Activity.user_id == current_user.id,
            models.Activity.date >= day_start,
            models.Activity.date <  day_end,
            models.Activity.duration_seconds >= dur - 60,
            models.Activity.duration_seconds <= dur + 60,
            models.Activity.distance_km      >= dist - 0.5,
            models.Activity.distance_km      <= dist + 0.5,
        ).first()
        if fuzzy_dup:
            raise HTTPException(status_code=409, detail=f"This ride was already uploaded (activity #{fuzzy_dup.id}).")

    data["suffer_score"] = compute_suffer_score(track_points, data.get("max_heart_rate_bpm"))

    # Recompute avg cadence excluding zeros (coasting / downhill)
    active_cad = [tp["cadence_rpm"] for tp in track_points if tp.get("cadence_rpm") and tp["cadence_rpm"] > 0]
    data["avg_cadence_rpm"] = round(sum(active_cad) / len(active_cad), 1) if active_cad else None

    # Lift sensor temperature out before weather merge (parsers return avg_temperature_c / max_temperature_c)
    sensor_avg_temp = data.pop("avg_temperature_c", None)
    sensor_max_temp = data.pop("max_temperature_c", None)
    if sensor_avg_temp is not None:
        data["sensor_temp_avg_c"] = sensor_avg_temp
    if sensor_max_temp is not None:
        data["sensor_temp_max_c"] = sensor_max_temp

    # Fetch weather from first GPS point (wind, humidity, description; temp is a fallback only)
    first_gps = next((tp for tp in track_points if tp.get("lat") and tp.get("lon")), None)
    if first_gps:
        weather = await _fetch_weather(first_gps["lat"], first_gps["lon"], data["date"])
        data.update(weather)
        # Sensor temperature is more accurate than weather station (which reads in shade at 2m).
        # Override weather_temp_c with the actual on-bike reading when available.
        if sensor_avg_temp is not None:
            data["weather_temp_c"] = sensor_avg_temp

    activity = models.Activity(**data, user_id=current_user.id, file_hash=file_hash)
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

    # HR-TSS (heat-corrected) when no power data
    if not activity.tss and activity.avg_heart_rate_bpm and current_user.max_hr:
        ride_temp = activity.sensor_temp_avg_c or activity.weather_temp_c
        dur_h_elapsed = (activity.elapsed_seconds or activity.duration_seconds or 0) / 3600
        activity.tss = compute_hrtss_heat_corrected(
            activity.duration_seconds,
            activity.avg_heart_rate_bpm,
            current_user.max_hr,
            resting_hr=getattr(current_user, "resting_hr", None),
            temp_c=ride_temp,
            duration_h=dur_h_elapsed,
        )

    # Calorie estimation when device didn't report calories
    if not activity.calories and activity.avg_heart_rate_bpm:
        activity.calories = estimate_calories_from_hr(
            activity.duration_seconds,
            activity.avg_heart_rate_bpm,
            age=getattr(current_user, "age", None),
            weight_kg=current_user.weight_kg,
            max_hr=current_user.max_hr,
        )

    db.commit()
    db.refresh(activity)

    # Heavy analysis (indoor/hydration/durability/decoupling/climbs) runs off the
    # request path so the upload returns immediately. The ActivityDetail page
    # fetches each analysis separately, picking them up once the task finishes.
    background_tasks.add_task(_run_post_upload_analysis, activity.id, current_user.id, track_points)

    return activity


def _encode_cursor(date: datetime, id: int) -> str:
    payload = json.dumps({"date": date.isoformat(), "id": id})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, int]:
    payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    return datetime.fromisoformat(payload["date"]), payload["id"]


PAGE_SIZE = 50


@router.get("/", response_model=schemas.ActivityPage)
def list_activities(
    cursor: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    min_distance_km: Optional[float] = Query(None),
    max_distance_km: Optional[float] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    base = db.query(models.Activity).filter(models.Activity.user_id == current_user.id)
    if search:
        base = base.filter(models.Activity.name.ilike(f"%{search}%"))
    if date_from:
        base = base.filter(models.Activity.date >= datetime.fromisoformat(date_from))
    if date_to:
        base = base.filter(models.Activity.date <= datetime.fromisoformat(date_to))
    if min_distance_km is not None:
        base = base.filter(models.Activity.distance_km >= min_distance_km)
    if max_distance_km is not None:
        base = base.filter(models.Activity.distance_km <= max_distance_km)

    total_count = base.count()

    query = base.order_by(models.Activity.date.desc(), models.Activity.id.desc())
    if cursor:
        c_date, c_id = _decode_cursor(cursor)
        query = query.filter(
            (models.Activity.date < c_date) |
            ((models.Activity.date == c_date) & (models.Activity.id < c_id))
        )
    activities = query.limit(PAGE_SIZE + 1).all()

    has_more = len(activities) > PAGE_SIZE
    activities = activities[:PAGE_SIZE]
    next_cursor = _encode_cursor(activities[-1].date, activities[-1].id) if has_more else None

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
    return {"items": result, "next_cursor": next_cursor, "total_count": total_count}


@router.get("/{activity_id}/export/csv")
def export_csv(activity_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if not has_full_access(current_user):
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
    if not has_full_access(current_user):
        raise HTTPException(status_code=403, detail="Activity export is a Pro feature. Upgrade to export your rides.")
    activity = db.query(models.Activity).filter(models.Activity.id == activity_id, models.Activity.user_id == current_user.id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    gpx_str = _build_gpx(activity)
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in activity.name).strip()
    filename = f"{safe}_{activity.date.strftime('%Y%m%d')}.gpx"
    return StreamingResponse(io.BytesIO(gpx_str.encode()), media_type="application/gpx+xml",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _activity_etag(activity: models.Activity, user: models.User) -> str:
    """Weak ETag over the activity's mutable fields.

    Track points and laps are immutable once parsed, so the payload only
    changes when the user renames, edits notes, (re)generates AI analysis, or
    overrides the indoor/outdoor classification. Hashing just those fields lets
    the browser revalidate cheaply and get a 304 (no body) when nothing changed
    — a big win since the detail payload carries the full track-point series.

    Profile max/resting HR are included because the payload embeds them and
    suffer_score/tss are recalculated when they change.
    """
    parts = (
        activity.id, activity.name, activity.notes, activity.ai_analysis,
        activity.ride_environment, activity.ride_environment_source,
        activity.indoor_platform, activity.corrected_tss,
        activity.decoupling_adjusted, activity.suffer_score, activity.tss,
        user.max_hr, user.resting_hr,
    )
    raw = "|".join("" if p is None else str(p) for p in parts)
    return 'W/"' + hashlib.sha1(raw.encode()).hexdigest() + '"'


@router.get("/{activity_id}", response_model=schemas.ActivityDetail)
def get_activity(
    activity_id: int,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    activity = db.query(models.Activity).filter(models.Activity.id == activity_id, models.Activity.user_id == current_user.id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    user = db.query(models.User).filter(models.User.id == current_user.id).first()

    etag = _activity_etag(activity, user)
    # private: per-user data, never store in shared/CDN caches.
    # no-cache: browser may store the body but must revalidate via the ETag,
    # so an unchanged ride returns a fast bodyless 304.
    cache_headers = {"Cache-Control": "private, no-cache", "ETag": etag}

    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=cache_headers)

    response.headers.update(cache_headers)
    detail = schemas.ActivityDetail.model_validate(activity)
    detail.profile_max_hr = user.max_hr
    detail.profile_resting_hr = user.resting_hr
    return detail


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

    is_safe, reason = _moderate_notes(notes, db, current_user)
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
    # Bulk-delete child rows in one SQL statement each — avoids ORM loading
    # thousands of TrackPoints into memory before deleting them one by one.
    db.query(models.TrackPoint).filter(models.TrackPoint.activity_id == activity_id).delete(synchronize_session=False)
    db.query(models.Lap).filter(models.Lap.activity_id == activity_id).delete(synchronize_session=False)
    db.query(models.HydrationAnalysis).filter(models.HydrationAnalysis.activity_id == activity_id).delete(synchronize_session=False)
    db.query(models.DurabilityAnalysis).filter(models.DurabilityAnalysis.activity_id == activity_id).delete(synchronize_session=False)
    db.query(models.ClimbDetection).filter(models.ClimbDetection.activity_id == activity_id).delete(synchronize_session=False)
    db.query(models.PersonalRecord).filter(models.PersonalRecord.activity_id == activity_id).delete(synchronize_session=False)
    db.delete(activity)
    db.commit()
    return {"message": "Deleted"}
