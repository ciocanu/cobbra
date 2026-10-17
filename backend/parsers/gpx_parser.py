import gpxpy
import math
from datetime import datetime
from typing import Dict, Any


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def smooth_elevations(elevations: list, window: int = 5) -> list:
    """Moving-average smoothing to remove GPS altitude noise."""
    result = []
    half = window // 2
    for i, e in enumerate(elevations):
        if e is None:
            result.append(None)
            continue
        vals = [elevations[j] for j in range(max(0, i - half), min(len(elevations), i + half + 1)) if elevations[j] is not None]
        result.append(sum(vals) / len(vals) if vals else e)
    return result


SPEED_TAGS = ("Speed", "speed")
CADENCE_TAGS = ("cad", "cadence", "Cadence")
HR_TAGS = ("hr", "HeartRateBpm")
POWER_TAGS = ("power", "PowerInWatts", "watts")
TEMP_TAGS = ("atemp", "AirTemperature", "airTemp")


def _local_tag(element) -> str:
    tag = element.tag if isinstance(element.tag, str) else ""
    return tag.split("}")[-1] if "}" in tag else tag


def _to_float(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def read_extensions(extensions) -> Dict[str, Any]:
    """Pull sensor values out of a trackpoint's <extensions>.

    Walks every element, so values are found both nested in a container
    (<gpxtpx:TrackPointExtension><gpxtpx:cad>, <gpxpx:PowerExtension><gpxpx:PowerInWatts>)
    and directly under <extensions> (Strava's <power>, a flat <hr>).
    """
    values = {"speed_ms": None, "cadence_rpm": None, "heart_rate_bpm": None, "power_w": None, "temperature_c": None}
    for ext in extensions or []:
        for el in ext.iter():
            tag = _local_tag(el)
            if tag == "HeartRateBpm":
                # TCX-style <HeartRateBpm><Value>142</Value></HeartRateBpm>
                value_el = next((c for c in el if _local_tag(c) == "Value"), None)
                val = _to_float(value_el.text if value_el is not None else el.text)
            else:
                val = _to_float(el.text)
            if val is None:
                continue
            if tag in SPEED_TAGS:
                values["speed_ms"] = val
            elif tag in CADENCE_TAGS:
                values["cadence_rpm"] = val
            elif tag in HR_TAGS:
                values["heart_rate_bpm"] = val
            elif tag in POWER_TAGS:
                values["power_w"] = val
            elif tag in TEMP_TAGS:
                values["temperature_c"] = val
    return values


def parse_gpx(file_content: bytes) -> Dict[str, Any]:
    gpx = gpxpy.parse(file_content.decode("utf-8"))

    raw_points = []
    total_distance = 0.0
    prev_point = None
    min_time = None
    max_time = None
    speeds, cadences, heart_rates, powers, temperatures = [], [], [], [], []

    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                dist_m = 0.0
                if prev_point:
                    dist_m = haversine(prev_point["lat"], prev_point["lon"], point.latitude, point.longitude)
                    total_distance += dist_m

                ext = read_extensions(point.extensions)
                speed_kmh = ext["speed_ms"] * 3.6 if ext["speed_ms"] is not None else None
                cadence_rpm = ext["cadence_rpm"]
                heart_rate_bpm = ext["heart_rate_bpm"]
                power_w = ext["power_w"]
                if ext["temperature_c"] is not None:
                    temperatures.append(ext["temperature_c"])

                if speed_kmh is None and prev_point and prev_point.get("timestamp") and point.time:
                    dt = (point.time.replace(tzinfo=None) - prev_point["timestamp"]).total_seconds()
                    if dt > 0:
                        speed_kmh = (dist_m / dt) * 3.6

                if point.time:
                    ts = point.time.replace(tzinfo=None)
                    if min_time is None or ts < min_time:
                        min_time = ts
                    if max_time is None or ts > max_time:
                        max_time = ts

                if speed_kmh is not None and speed_kmh < 120:
                    speeds.append(speed_kmh)
                if cadence_rpm is not None:
                    cadences.append(cadence_rpm)
                if heart_rate_bpm is not None:
                    heart_rates.append(heart_rate_bpm)
                # Same rule as the FIT parser: zeros (coasting) are kept per point but excluded from avg/max
                if power_w is not None and power_w > 0:
                    powers.append(power_w)

                raw_points.append({
                    "timestamp": point.time.replace(tzinfo=None) if point.time else None,
                    "lat": point.latitude,
                    "lon": point.longitude,
                    "elevation": point.elevation,
                    "speed_kmh": round(speed_kmh, 2) if speed_kmh is not None else None,
                    "cadence_rpm": cadence_rpm,
                    "heart_rate_bpm": heart_rate_bpm,
                    "power_w": power_w,
                    "distance_m": round(total_distance, 1),
                })

                prev_point = {
                    "lat": point.latitude,
                    "lon": point.longitude,
                    "elevation": point.elevation,
                    "timestamp": point.time.replace(tzinfo=None) if point.time else None,
                }

    # Smooth elevation and recompute gain/loss
    raw_elevs = [p["elevation"] for p in raw_points]
    smoothed = smooth_elevations(raw_elevs)
    elevation_gain = 0.0
    elevation_loss = 0.0
    for i, p in enumerate(raw_points):
        p["elevation"] = round(smoothed[i], 1) if smoothed[i] is not None else None
        if i > 0 and smoothed[i] is not None and smoothed[i - 1] is not None:
            diff = smoothed[i] - smoothed[i - 1]
            if diff > 0:
                elevation_gain += diff
            else:
                elevation_loss += abs(diff)

    duration_seconds = int((max_time - min_time).total_seconds()) if min_time and max_time else 0
    name = (
        gpx.name
        or (gpx.tracks[0].name if gpx.tracks else None)
        or f"Ride {(min_time or datetime.utcnow()).strftime('%Y-%m-%d')}"
    )

    # Filter out outlier temperature readings (sensor noise: valid range -20..60°C)
    valid_temps = [t for t in temperatures if -20 <= t <= 60]

    return {
        "name": name,
        "date": min_time or datetime.utcnow(),
        "distance_km": round(total_distance / 1000, 3),
        "duration_seconds": duration_seconds,
        "avg_speed_kmh": round((total_distance / 1000) / (duration_seconds / 3600), 2) if duration_seconds > 0 else 0,
        "max_speed_kmh": round(max(speeds), 2) if speeds else 0,
        "avg_cadence_rpm": round(sum(cadences) / len(cadences), 1) if cadences else None,
        "max_cadence_rpm": round(max(cadences), 1) if cadences else None,
        "avg_heart_rate_bpm": round(sum(heart_rates) / len(heart_rates), 1) if heart_rates else None,
        "max_heart_rate_bpm": round(max(heart_rates), 1) if heart_rates else None,
        "avg_power_w": round(sum(powers) / len(powers), 1) if powers else None,
        "max_power_w": round(max(powers), 1) if powers else None,
        "elevation_gain_m": round(elevation_gain, 1),
        "elevation_loss_m": round(elevation_loss, 1),
        "calories": None,
        "file_type": "gpx",
        "track_points": raw_points,
        "laps": [],
        # Sensor temperature from atemp extension (more accurate than weather API)
        "avg_temperature_c": round(sum(valid_temps) / len(valid_temps), 1) if valid_temps else None,
        "max_temperature_c": round(max(valid_temps), 1) if valid_temps else None,
    }
