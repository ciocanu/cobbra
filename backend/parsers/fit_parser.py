import io
from datetime import datetime
from typing import Dict, Any
from fitparse import FitFile


def semicircles_to_degrees(val):
    return val * (180 / 2 ** 31)


def smooth_elevations(elevations: list, window: int = 5) -> list:
    result = []
    half = window // 2
    for i, e in enumerate(elevations):
        if e is None:
            result.append(None)
            continue
        vals = [elevations[j] for j in range(max(0, i - half), min(len(elevations), i + half + 1)) if elevations[j] is not None]
        result.append(sum(vals) / len(vals) if vals else e)
    return result


def parse_fit(file_content: bytes) -> Dict[str, Any]:
    fitfile = FitFile(io.BytesIO(file_content))

    raw_points = []
    session_data = {}
    speeds, cadences, heart_rates, powers = [], [], [], []
    total_distance = 0.0

    # Session summary
    for record in fitfile.get_messages("session"):
        for field in record:
            session_data[field.name] = field.value

    # Track records
    for record in fitfile.get_messages("record"):
        fields = {f.name: f.value for f in record}

        lat = fields.get("position_lat")
        lon = fields.get("position_long")
        if lat is not None:
            lat = semicircles_to_degrees(lat)
        if lon is not None:
            lon = semicircles_to_degrees(lon)

        speed = fields.get("speed")
        speed_kmh = round(speed * 3.6, 2) if speed is not None else None
        cadence = fields.get("cadence")
        heart_rate = fields.get("heart_rate")
        power = fields.get("power")
        altitude = fields.get("enhanced_altitude") or fields.get("altitude")
        distance = fields.get("distance")
        timestamp = fields.get("timestamp")

        if timestamp and hasattr(timestamp, "replace"):
            timestamp = timestamp.replace(tzinfo=None)

        if distance is not None:
            total_distance = max(total_distance, distance)

        if speed_kmh is not None and speed_kmh < 120:
            speeds.append(speed_kmh)
        if cadence is not None:
            cadences.append(float(cadence))
        if heart_rate is not None:
            heart_rates.append(float(heart_rate))
        if power is not None and power > 0:
            powers.append(float(power))

        raw_points.append({
            "timestamp": timestamp,
            "lat": lat,
            "lon": lon,
            "elevation": altitude,
            "speed_kmh": speed_kmh,
            "cadence_rpm": float(cadence) if cadence is not None else None,
            "heart_rate_bpm": float(heart_rate) if heart_rate is not None else None,
            "power_w": float(power) if power is not None else None,
            "distance_m": round(distance, 1) if distance is not None else None,
        })

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

    # Parse laps
    laps = []
    for lap_num, record in enumerate(fitfile.get_messages("lap"), start=1):
        fields = {f.name: f.value for f in record}
        spd = fields.get("avg_speed")
        laps.append({
            "lap_number": lap_num,
            "elapsed_seconds": float(fields["total_elapsed_time"]) if fields.get("total_elapsed_time") else None,
            "distance_m": float(fields["total_distance"]) if fields.get("total_distance") else None,
            "avg_speed_kmh": round(spd * 3.6, 1) if spd else None,
            "avg_hr": float(fields["avg_heart_rate"]) if fields.get("avg_heart_rate") else None,
            "avg_cadence": float(fields["avg_cadence"]) if fields.get("avg_cadence") else None,
            "elevation_gain_m": float(fields["total_ascent"]) if fields.get("total_ascent") else None,
        })

    duration = float(session_data.get("total_timer_time") or 0)
    calories = session_data.get("total_calories")
    start_ts = raw_points[0]["timestamp"] if raw_points else datetime.utcnow()

    return {
        "name": f"Ride {start_ts.strftime('%Y-%m-%d') if hasattr(start_ts, 'strftime') else 'Unknown'}",
        "date": start_ts if start_ts else datetime.utcnow(),
        "distance_km": round(total_distance / 1000, 3),
        "duration_seconds": int(duration),
        "avg_speed_kmh": round((total_distance / 1000) / (duration / 3600), 2) if duration > 0 else 0,
        "max_speed_kmh": round(max(speeds), 2) if speeds else 0,
        "avg_cadence_rpm": round(sum(cadences) / len(cadences), 1) if cadences else None,
        "max_cadence_rpm": round(max(cadences), 1) if cadences else None,
        "avg_heart_rate_bpm": round(sum(heart_rates) / len(heart_rates), 1) if heart_rates else None,
        "max_heart_rate_bpm": round(max(heart_rates), 1) if heart_rates else None,
        "avg_power_w": round(sum(powers) / len(powers), 1) if powers else None,
        "max_power_w": round(max(powers), 1) if powers else None,
        "elevation_gain_m": round(elevation_gain, 1),
        "elevation_loss_m": round(elevation_loss, 1),
        "calories": int(calories) if calories else None,
        "file_type": "fit",
        "track_points": raw_points,
        "laps": laps,
    }
