"""
Indoor/Outdoor ride detection.

Priority order (highest confidence first):
  1. Explicit metadata — strava_type, file manufacturer, sub_sport
  2. Activity name keywords
  3. GPS analysis — no GPS or static bbox
  4. Data patterns — power with no speed, static cadence
  5. Ambiguous signals — low-confidence fallback
"""

from __future__ import annotations

import math
from typing import Optional

# ── Platform keyword maps ─────────────────────────────────────────────────────

_NAME_PLATFORMS: dict[str, str] = {
    "zwift":        "zwift",
    "trainerroad":  "trainerroad",
    "trainer road": "trainerroad",
    "wahoo":        "wahoo",
    "systm":        "wahoo",
    "sufferfest":   "wahoo",
    "mywhoosh":     "mywhoosh",
    "whoosh":       "mywhoosh",
    "fulgaz":       "other",
    "rouvy":        "other",
    "bkool":        "other",
    "rolo":         "rolo",
    "rodillo":      "rolo",
    "home trainer": "rolo",
    "hometrainer":  "rolo",
    "turbo":        "rolo",
    "indoor":       None,   # generic indoor keyword — no specific platform
}

_MANUFACTURER_PLATFORMS: dict[str, str] = {
    "zwift":          "zwift",
    "trainerroad":    "trainerroad",
    "trainer_road":   "trainerroad",
    "wahoo_fitness":  "wahoo",
    "wahoo":          "wahoo",
    "tacx":           "other",
    "garmin":         None,   # Garmin makes both indoor and outdoor devices
    "mywhoosh":       "mywhoosh",
    "rouvy":          "other",
    "fulgaz":         "other",
    "bkool":          "other",
}

_GPS_BBOX_INDOOR_M = 50.0    # bounding box smaller than this → treated as static GPS


# ── Public API ─────────────────────────────────────────────────────────────────

def detect_ride_environment(
    track_points: list[dict],
    activity_name: Optional[str] = None,
    strava_type: Optional[str] = None,
    file_metadata: Optional[dict] = None,
) -> dict:
    """Classify a ride as indoor / outdoor / unknown.

    Returns:
        {
            'environment': 'indoor' | 'outdoor' | 'unknown',
            'confidence':  'high' | 'medium' | 'low',
            'source':      str,          # which signal decided
            'platform':    str | None,   # 'zwift' etc., None when outdoor
            'signals':     dict,         # raw signal values for debugging
        }
    """
    signals: dict = {}
    meta = file_metadata or {}

    # ── 1. Strava explicit type ───────────────────────────────────────────────
    if strava_type:
        signals["strava_type"] = strava_type
        if strava_type == "VirtualRide":
            platform = _platform_from_name(activity_name)
            return _result("indoor", "high", "strava_type", platform or "zwift", signals)
        if strava_type in ("Ride", "GravelRide", "MountainBikeRide"):
            signals["strava_outdoor"] = True
            # outdoor confirmed by Strava — still run GPS check to be safe
            return _result("outdoor", "high", "strava_type", None, signals)

    # ── 2. .fit file sub_sport / manufacturer ─────────────────────────────────
    sub_sport = meta.get("sub_sport", "")
    manufacturer = (meta.get("manufacturer") or "").lower()

    if sub_sport == "virtual_activity":
        platform = _platform_from_manufacturer(manufacturer) or _platform_from_name(activity_name)
        signals["sub_sport"] = sub_sport
        return _result("indoor", "high", "fit_sub_sport", platform or "other", signals)

    if manufacturer and manufacturer in _MANUFACTURER_PLATFORMS:
        mfr_platform = _MANUFACTURER_PLATFORMS[manufacturer]
        if mfr_platform is not None:
            signals["manufacturer"] = manufacturer
            return _result("indoor", "high", "fit_manufacturer", mfr_platform, signals)

    # ── 3. Activity name keywords ─────────────────────────────────────────────
    name_platform, matched_keywords = _scan_name(activity_name)
    signals["name_keywords"] = matched_keywords

    if name_platform is not False:   # None means generic indoor, str means specific platform
        platform = name_platform if isinstance(name_platform, str) else None
        return _result("indoor", "high", "name_keywords", platform, signals)

    # ── 4. GPS analysis ───────────────────────────────────────────────────────
    has_gps = any(
        p.get("lat") not in (None, 0) and p.get("lon") not in (None, 0)
        for p in track_points
    )
    signals["has_gps"] = has_gps

    if not has_gps:
        platform = _platform_from_name(activity_name)
        has_power = any((p.get("power_w") or 0) > 20 for p in track_points)
        inferred = "rolo" if (has_power and not platform) else (platform or "other")
        return _result("indoor", "high", "no_gps", inferred, signals)

    bbox_m = _gps_bounding_box_m(track_points)
    signals["gps_bbox_m"] = round(bbox_m, 1)

    if bbox_m < _GPS_BBOX_INDOOR_M:
        platform = _platform_from_name(activity_name)
        return _result("indoor", "high", "gps_static_bbox",
                       platform or "rolo", signals)

    # ── 5. Data patterns (medium confidence) ──────────────────────────────────
    power_pts = [p for p in track_points if (p.get("power_w") or 0) > 20]
    speed_zero_frac = _speed_zero_fraction(track_points)
    signals["speed_zero_frac"] = round(speed_zero_frac, 2)

    if power_pts and speed_zero_frac > 0.90:
        # Power present but nearly always stopped → smart trainer with no virtual speed
        return _result("indoor", "medium", "power_no_speed",
                       _platform_from_name(activity_name) or "rolo", signals)

    cad_cv = _cadence_cv(track_points)
    signals["cadence_cv"] = round(cad_cv, 3) if cad_cv is not None else None

    # Convincing GPS movement with no indoor signals → outdoor
    if bbox_m > 500:
        return _result("outdoor", "high", "gps_movement", None, signals)

    # Small bbox 50–500 m: short urban ride or ambiguous
    if bbox_m < 500:
        return _result("unknown", "low", "ambiguous_bbox", None, signals)

    return _result("unknown", "low", "no_signal", None, signals)


def detect_indoor_platform(
    track_points: list[dict],
    activity_name: Optional[str] = None,
    file_metadata: Optional[dict] = None,
) -> Optional[str]:
    """Return the specific indoor platform or None if outdoor/unknown."""
    meta = file_metadata or {}

    # Manufacturer
    manufacturer = (meta.get("manufacturer") or "").lower()
    if manufacturer in _MANUFACTURER_PLATFORMS:
        p = _MANUFACTURER_PLATFORMS[manufacturer]
        if p:
            return p

    # Name
    name_platform, _ = _scan_name(activity_name)
    if name_platform is not False and isinstance(name_platform, str):
        return name_platform

    # Generic indoor (no platform found)
    has_power = any((p.get("power_w") or 0) > 20 for p in track_points)
    if has_power:
        return "rolo"
    return "other"


# ── Private helpers ────────────────────────────────────────────────────────────

def _result(env: str, confidence: str, source: str,
            platform: Optional[str], signals: dict) -> dict:
    return {
        "environment": env,
        "confidence":  confidence,
        "source":      source,
        "platform":    platform,
        "signals":     signals,
    }


def _scan_name(name: Optional[str]) -> tuple:
    """Return (platform_or_None_or_False, matched_keywords).

    False = no indoor keyword found at all.
    None  = generic indoor keyword found (e.g. 'Indoor') but no specific platform.
    str   = specific platform name.
    """
    if not name:
        return False, []
    lower = name.lower()
    found_keywords = []
    found_platform = False   # sentinel for "no keyword found"

    for keyword, platform in _NAME_PLATFORMS.items():
        if keyword in lower:
            found_keywords.append(keyword)
            if found_platform is False:
                found_platform = platform   # first match wins for platform assignment

    if not found_keywords:
        return False, []
    return found_platform, found_keywords   # None = generic, str = specific


def _platform_from_name(name: Optional[str]) -> Optional[str]:
    platform, _ = _scan_name(name)
    return platform if isinstance(platform, str) else None


def _platform_from_manufacturer(manufacturer: str) -> Optional[str]:
    return _MANUFACTURER_PLATFORMS.get(manufacturer.lower())


def _gps_bounding_box_m(track_points: list[dict]) -> float:
    """Return the diagonal of the lat/lon bounding box in metres."""
    lats = [p["lat"] for p in track_points if p.get("lat") not in (None, 0)]
    lons = [p["lon"] for p in track_points if p.get("lon") not in (None, 0)]
    if len(lats) < 2:
        return 0.0
    lat_mid = (max(lats) + min(lats)) / 2
    dlat_m  = (max(lats) - min(lats)) * 111_320
    dlon_m  = (max(lons) - min(lons)) * 111_320 * math.cos(math.radians(lat_mid))
    return math.sqrt(dlat_m ** 2 + dlon_m ** 2)


def _speed_zero_fraction(track_points: list[dict]) -> float:
    if not track_points:
        return 0.0
    zero = sum(1 for p in track_points if (p.get("speed_kmh") or 0) < 0.5)
    return zero / len(track_points)


def _cadence_cv(track_points: list[dict]) -> Optional[float]:
    """Coefficient of variation of cadence — low = very steady (indoor pattern)."""
    vals = [p["cadence_rpm"] for p in track_points
            if p.get("cadence_rpm") is not None and p["cadence_rpm"] > 30]
    if len(vals) < 30:
        return None
    mean = sum(vals) / len(vals)
    if mean == 0:
        return None
    std = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals))
    return std / mean
