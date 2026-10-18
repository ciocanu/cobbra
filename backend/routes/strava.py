import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import httpx

from database import get_db
from auth import get_current_user
import models
from utils import compute_normalized_power, compute_tss
from utils.access import has_full_access

router = APIRouter()

# Strava API migration (effective 2027-06-01):
# _STRAVA_API_BASE must be changed to https://www.api-v3.strava.com on that date.
# oauth/deauthorize was already replaced by oauth/revoke (done, endpoint is live).
_STRAVA_AUTH_URL   = "https://www.strava.com/oauth/authorize"
_STRAVA_TOKEN_URL  = "https://www.strava.com/oauth/token"
_STRAVA_REVOKE_URL = "https://www.strava.com/oauth/revoke"
_STRAVA_API_BASE   = "https://www.strava.com/api/v3"  # TODO 2027-06-01: change to https://www.api-v3.strava.com

_FREE_ACTIVITY_CAP = 15
_CYCLING_TYPES = {"Ride", "VirtualRide", "GravelRide", "MountainBikeRide", "EBikeRide"}
# Max activities to backfill streams for in one sync (rate-limit friendly)
_BACKFILL_CAP = 20


def _client_id():
    v = os.getenv("STRAVA_CLIENT_ID", "")
    if not v:
        raise HTTPException(status_code=503, detail="Strava integration is not configured on this server.")
    return v


def _client_secret():
    v = os.getenv("STRAVA_CLIENT_SECRET", "")
    if not v:
        raise HTTPException(status_code=503, detail="Strava integration is not configured on this server.")
    return v


def _redirect_uri():
    return os.getenv("STRAVA_REDIRECT_URI", "http://localhost:5173/strava/callback")


def _ensure_fresh_token(user, db: Session) -> str:
    if not user.strava_refresh_token:
        raise HTTPException(status_code=400, detail="Strava is not connected.")
    if user.strava_token_expires_at and user.strava_token_expires_at > datetime.utcnow() + timedelta(minutes=5):
        return user.strava_access_token

    with httpx.Client(timeout=15) as client:
        resp = client.post(_STRAVA_TOKEN_URL, json={
            "client_id": _client_id(),
            "client_secret": _client_secret(),
            "refresh_token": user.strava_refresh_token,
            "grant_type": "refresh_token",
        })
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to refresh Strava token. Please reconnect.")

    data = resp.json()
    user.strava_access_token = data.get("access_token")
    user.strava_refresh_token = data.get("refresh_token", user.strava_refresh_token)
    expires_at = data.get("expires_at")
    user.strava_token_expires_at = datetime.utcfromtimestamp(expires_at) if expires_at else None
    db.commit()
    return user.strava_access_token


def _fetch_streams(activity_id: str, token: str, date: datetime, client: httpx.Client) -> list[dict]:
    """
    Fetch GPS + sensor streams at full device resolution — equivalent to a GPX/FIT file.
    Returns [] on any failure (rate limit, no data, etc.).
    """
    try:
        resp = client.get(
            f"{_STRAVA_API_BASE}/activities/{activity_id}/streams",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "keys": "latlng,altitude,time,distance,heartrate,cadence,watts,velocity_smooth,temp,grade_smooth",
                "key_by_type": "true",
                "resolution": "high",
            },
            timeout=30,
        )
        if resp.status_code == 429:
            return []  # rate limited — caller will skip silently
        if resp.status_code != 200:
            return []

        streams = resp.json()
        time_s = streams.get("time", {}).get("data", [])
        if not time_s:
            return []

        latlng   = streams.get("latlng",          {}).get("data", [])
        altitude = streams.get("altitude",         {}).get("data", [])
        distance = streams.get("distance",         {}).get("data", [])
        hr       = streams.get("heartrate",        {}).get("data", [])
        cadence  = streams.get("cadence",          {}).get("data", [])
        watts    = streams.get("watts",            {}).get("data", [])
        velocity = streams.get("velocity_smooth",  {}).get("data", [])

        points = []
        for i, t in enumerate(time_s):
            ll = latlng[i] if i < len(latlng) else None
            points.append({
                "timestamp":      date + timedelta(seconds=t),
                "lat":            ll[0]                        if ll else None,
                "lon":            ll[1]                        if ll else None,
                "elevation":      altitude[i]                  if i < len(altitude) else None,
                "distance_m":     distance[i]                  if i < len(distance) else None,
                "heart_rate_bpm": hr[i]                        if i < len(hr)       else None,
                "cadence_rpm":    cadence[i]                   if i < len(cadence)  else None,
                "power_w":        watts[i]                     if i < len(watts)    else None,
                "speed_kmh":      round(velocity[i] * 3.6, 2)  if i < len(velocity) else None,
            })
        return points
    except Exception:
        return []


def _fetch_laps(activity_id: str, token: str, client: httpx.Client) -> list[dict]:
    """Fetch lap splits for one activity. Returns [] on failure."""
    try:
        resp = client.get(
            f"{_STRAVA_API_BASE}/activities/{activity_id}/laps",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if resp.status_code != 200:
            return []

        laps = []
        for lap in resp.json():
            avg_speed_ms = lap.get("average_speed") or 0
            laps.append({
                "lap_number":      lap.get("lap_index") or lap.get("split", 0),
                "elapsed_seconds": lap.get("elapsed_time"),
                "distance_m":      lap.get("distance"),
                "avg_speed_kmh":   round(avg_speed_ms * 3.6, 2),
                "avg_hr":          lap.get("average_heartrate"),
                "avg_cadence":     lap.get("average_cadence"),
                "elevation_gain_m": lap.get("total_elevation_gain"),
            })
        return laps
    except Exception:
        return []


def _save_streams(activity: models.Activity, points: list[dict], db: Session, ftp: int | None = None):
    db.query(models.TrackPoint).filter(models.TrackPoint.activity_id == activity.id).delete()
    for p in points:
        db.add(models.TrackPoint(activity_id=activity.id, **p))
    # Compute NP + TSS from the stream data
    np = compute_normalized_power(points)
    if np:
        activity.normalized_power_w = np
        if ftp:
            activity.tss = compute_tss(np, activity.duration_seconds, ftp)


def _save_laps(activity: models.Activity, laps: list[dict], db: Session):
    db.query(models.Lap).filter(models.Lap.activity_id == activity.id).delete()
    for lap in laps:
        db.add(models.Lap(activity_id=activity.id, **lap))


@router.get("/auth-url")
def get_auth_url(current_user=Depends(get_current_user)):
    url = (
        f"{_STRAVA_AUTH_URL}"
        f"?client_id={_client_id()}"
        f"&redirect_uri={_redirect_uri()}"
        f"&response_type=code"
        f"&approval_prompt=auto"
        f"&scope=read,activity:read"
    )
    return {"url": url}


@router.post("/callback")
def strava_callback(body: dict, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    code = (body.get("code") or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code is required.")

    with httpx.Client(timeout=15) as client:
        resp = client.post(_STRAVA_TOKEN_URL, json={
            "client_id": _client_id(),
            "client_secret": _client_secret(),
            "code": code,
            "grant_type": "authorization_code",
        })
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to exchange authorization code with Strava.")

    data = resp.json()
    athlete = data.get("athlete", {})
    expires_at = data.get("expires_at")

    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    user.strava_athlete_id = str(athlete.get("id", ""))
    user.strava_access_token = data.get("access_token")
    user.strava_refresh_token = data.get("refresh_token")
    user.strava_token_expires_at = datetime.utcfromtimestamp(expires_at) if expires_at else None
    db.commit()

    name = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip()
    return {"ok": True, "athlete_name": name or "Strava Athlete"}


@router.get("/status")
def strava_status(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user.strava_athlete_id:
        return {"connected": False}
    return {
        "connected": True,
        "athlete_id": user.strava_athlete_id,
        "last_sync_at": user.strava_last_sync_at.isoformat() if user.strava_last_sync_at else None,
    }


@router.post("/disconnect")
def strava_disconnect(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    token = user.strava_access_token
    if token:
        try:
            with httpx.Client(timeout=10) as client:
                client.post(_STRAVA_REVOKE_URL, headers={"Authorization": f"Bearer {token}"})
        except Exception:
            pass  # revoke is best-effort; clear local tokens regardless
    user.strava_athlete_id = None
    user.strava_access_token = None
    user.strava_refresh_token = None
    user.strava_token_expires_at = None
    user.strava_last_sync_at = None
    db.commit()
    return {"ok": True}


@router.post("/sync")
def strava_sync(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user.strava_athlete_id:
        raise HTTPException(status_code=400, detail="Strava is not connected.")

    token = _ensure_fresh_token(user, db)
    is_free = not has_full_access(user)

    if is_free:
        existing_count = db.query(models.Activity).filter(models.Activity.user_id == current_user.id).count()
        if existing_count >= _FREE_ACTIVITY_CAP:
            raise HTTPException(
                status_code=403,
                detail=f"Free plan limit reached ({_FREE_ACTIVITY_CAP} activities). Upgrade to Pro to sync more."
            )

    imported = 0
    skipped = 0
    capped = False

    with httpx.Client(timeout=30) as client:
        headers = {"Authorization": f"Bearer {token}"}

        # ── Phase 1: import new activities ───────────────────────────────────
        for page in range(1, 11):
            resp = client.get(
                f"{_STRAVA_API_BASE}/athlete/activities",
                headers=headers,
                params={"per_page": 50, "page": page},
            )
            if resp.status_code != 200:
                break

            activities_data = resp.json()
            if not activities_data:
                break

            for a in activities_data:
                activity_type = a.get("sport_type") or a.get("type") or ""
                if activity_type not in _CYCLING_TYPES:
                    skipped += 1
                    continue

                strava_id = str(a["id"])

                # Check 1: already imported from Strava
                already_imported = db.query(models.Activity).filter(
                    models.Activity.strava_id == strava_id,
                    models.Activity.user_id == current_user.id,
                ).first()
                if already_imported:
                    skipped += 1
                    continue

                # Parse date and distance before fuzzy check
                start_date_str = a.get("start_date") or ""
                try:
                    date = datetime.strptime(start_date_str, "%Y-%m-%dT%H:%M:%SZ")
                except Exception:
                    date = datetime.utcnow()

                distance_km = round((a.get("distance") or 0) / 1000, 3)

                # Check 2: fuzzy match against manually uploaded rides (same day ± 1 km)
                day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end   = date.replace(hour=23, minute=59, second=59, microsecond=999999)
                fuzzy_match = db.query(models.Activity).filter(
                    models.Activity.user_id == current_user.id,
                    models.Activity.strava_id.is_(None),
                    models.Activity.date >= day_start,
                    models.Activity.date <= day_end,
                    models.Activity.distance_km >= distance_km - 1.0,
                    models.Activity.distance_km <= distance_km + 1.0,
                ).first()
                if fuzzy_match:
                    # Tag existing ride so future syncs skip it instantly
                    fuzzy_match.strava_id = strava_id
                    # Backfill streams onto the manually uploaded ride if it has no GPS
                    if not fuzzy_match.track_points:
                        points = _fetch_streams(strava_id, token, date, client)
                        if points:
                            _save_streams(fuzzy_match, points, db, ftp=user.ftp)
                    db.commit()
                    skipped += 1
                    continue

                # Free tier cap check
                if is_free:
                    current_count = db.query(models.Activity).filter(
                        models.Activity.user_id == current_user.id
                    ).count()
                    if current_count >= _FREE_ACTIVITY_CAP:
                        capped = True
                        break

                avg_speed_ms = a.get("average_speed") or 0
                max_speed_ms = a.get("max_speed") or 0

                activity = models.Activity(
                    user_id=current_user.id,
                    strava_id=strava_id,
                    name=a.get("name") or "Strava Ride",
                    date=date,
                    distance_km=distance_km,
                    duration_seconds=a.get("moving_time") or 0,
                    avg_speed_kmh=round(avg_speed_ms * 3.6, 2),
                    max_speed_kmh=round(max_speed_ms * 3.6, 2),
                    avg_cadence_rpm=a.get("average_cadence"),
                    avg_heart_rate_bpm=a.get("average_heartrate"),
                    max_heart_rate_bpm=a.get("max_heartrate"),
                    elevation_gain_m=a.get("total_elevation_gain") or 0,
                    calories=a.get("calories"),
                    avg_power_w=a.get("average_watts"),
                    max_power_w=a.get("max_watts"),
                    suffer_score=a.get("suffer_score"),
                    file_type="strava",
                )
                db.add(activity)
                db.flush()  # get activity.id before fetching streams

                points = _fetch_streams(strava_id, token, date, client)
                if points:
                    _save_streams(activity, points, db, ftp=user.ftp)

                laps = _fetch_laps(strava_id, token, client)
                if laps:
                    _save_laps(activity, laps, db)

                db.commit()
                imported += 1

            if capped:
                break
            if len(activities_data) < 50:
                break

        # ── Phase 2: backfill streams for previously imported activities ──────
        # Find Strava activities that have no track points yet
        no_streams = (
            db.query(models.Activity)
            .filter(
                models.Activity.user_id == current_user.id,
                models.Activity.strava_id.isnot(None),
                ~models.Activity.track_points.any(),
            )
            .order_by(models.Activity.date.desc())
            .limit(_BACKFILL_CAP)
            .all()
        )

        backfilled = 0
        for act in no_streams:
            points = _fetch_streams(act.strava_id, token, act.date, client)
            laps   = _fetch_laps(act.strava_id, token, client)
            if points:
                _save_streams(act, points, db, ftp=user.ftp)
            if laps:
                _save_laps(act, laps, db)
            if points or laps:
                db.commit()
                backfilled += 1

    user.strava_last_sync_at = datetime.utcnow()
    db.commit()

    result = {"ok": True, "imported": imported, "skipped": skipped, "backfilled": backfilled}
    if capped:
        result["capped"] = True
        result["detail"] = f"Free plan limit of {_FREE_ACTIVITY_CAP} activities reached. Upgrade to Pro to import more."
    return result
