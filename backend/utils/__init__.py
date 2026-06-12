import math
from datetime import datetime


# ── Normalized Power (Coggan) ─────────────────────────────────────────────────

def compute_normalized_power(track_points: list) -> int | None:
    """
    Coggan NP algorithm:
    1. Time-based 30-second rolling average of power.
    2. Raise every value to the 4th power.
    3. Take the mean → 4th root.
    Requires timestamps; returns None if < 30 seconds of power data.
    """
    pts = []
    for tp in track_points:
        t = tp.get("timestamp")
        p = tp.get("power_w")
        if t is not None and p is not None:
            # timestamp may be a datetime object or a string
            if isinstance(t, str):
                from datetime import datetime as dt
                t = dt.fromisoformat(t)
            pts.append((t, float(p)))

    if len(pts) < 30:
        return None

    pts.sort(key=lambda x: x[0])

    WINDOW_S = 30.0
    rolling_avgs = []
    window_sum = 0.0
    j = 0

    for i, (t_i, p_i) in enumerate(pts):
        window_sum += p_i
        while (t_i - pts[j][0]).total_seconds() > WINDOW_S:
            window_sum -= pts[j][1]
            j += 1
        rolling_avgs.append(window_sum / (i - j + 1))

    if not rolling_avgs:
        return None

    mean_4th = sum(v ** 4 for v in rolling_avgs) / len(rolling_avgs)
    return round(mean_4th ** 0.25)


def compute_tss(np_watts: int, duration_seconds: int, ftp: int) -> float | None:
    """TSS = (duration × NP × IF) / (FTP × 3600) × 100  (Coggan)"""
    if not np_watts or not ftp or not duration_seconds:
        return None
    if_val = np_watts / ftp
    return round((duration_seconds * np_watts * if_val) / (ftp * 3600) * 100, 1)


def compute_hrtss(duration_seconds: int, avg_hr: float, max_hr: float,
                  resting_hr: float | None = None) -> float | None:
    """
    TRIMP-based hrTSS (Banister model, male coefficient b=1.92).
    Normalized so that 1 hour at lactate threshold ≈ 100 TSS points.
    Used as fallback when no power data is available.
    """
    if not avg_hr or not max_hr or duration_seconds <= 0:
        return None
    rest = resting_hr or 40.0
    if avg_hr <= rest or max_hr <= rest:
        return None

    hr_ratio = max(0.0, min(1.0, (avg_hr - rest) / (max_hr - rest)))
    trimp = (duration_seconds / 60) * hr_ratio * 0.64 * math.exp(1.92 * hr_ratio)

    # Normalize: threshold effort at ~85% max HR → 100 TSS/hr
    thr_ratio = max(0.01, (0.85 * max_hr - rest) / (max_hr - rest))
    thr_trimp_per_hr = 60.0 * thr_ratio * 0.64 * math.exp(1.92 * thr_ratio)
    if thr_trimp_per_hr <= 0:
        return None

    return round((trimp / thr_trimp_per_hr) * 100, 1)

# ── Suffer Score ─────────────────────────────────────────────────────────────
# Zone weights per second of time spent in each HR zone
_ZONE_WEIGHTS = [0.0, 0.007, 0.015, 0.028, 0.044]
_ZONE_THRESHOLDS = [0.60, 0.70, 0.80, 0.90]  # fraction of max HR


def compute_suffer_score(track_points: list, max_hr: float) -> int | None:
    if not max_hr or max_hr <= 0:
        return None

    pts = [
        (tp.get("timestamp"), tp.get("heart_rate_bpm"))
        for tp in track_points
        if tp.get("timestamp") and tp.get("heart_rate_bpm")
    ]
    if len(pts) < 2:
        return None

    score = 0.0
    for i in range(1, len(pts)):
        t1, hr1 = pts[i - 1]
        t2, hr2 = pts[i]
        dt = (t2 - t1).total_seconds()
        if dt <= 0 or dt > 300:  # skip gaps > 5 min
            continue
        avg_hr = (hr1 + hr2) / 2
        pct = avg_hr / max_hr
        zone = sum(1 for t in _ZONE_THRESHOLDS if pct >= t)
        score += _ZONE_WEIGHTS[zone] * dt

    return round(score) if score > 0 else None


# ── Personal Records ──────────────────────────────────────────────────────────
# Standard distances (meters) for best-time PRs
PR_DISTANCES_M = [400, 1000, 5000, 10000, 20000, 40000]

PR_LABELS = {
    400:   "fastest_400m",
    1000:  "fastest_1km",
    5000:  "fastest_5km",
    10000: "fastest_10km",
    20000: "fastest_20km",
    40000: "fastest_40km",
}


def compute_distance_prs(track_points: list) -> dict:
    """Sliding-window: returns {pr_type: fastest_seconds} for each distance."""
    pts = [
        (tp["distance_m"], tp["timestamp"])
        for tp in track_points
        if tp.get("distance_m") is not None and tp.get("timestamp") is not None
    ]
    if len(pts) < 2:
        return {}

    max_dist = pts[-1][0]
    results = {}

    for target in PR_DISTANCES_M:
        if max_dist < target * 0.95:  # ride not long enough
            continue
        best = None
        j = 0
        for i in range(len(pts)):
            while j < len(pts) and pts[j][0] - pts[i][0] < target:
                j += 1
            if j >= len(pts):
                break
            t = (pts[j][1] - pts[i][1]).total_seconds()
            if t > 0 and (best is None or t < best):
                best = t
        if best:
            results[PR_LABELS[target]] = best

    return results


# ── Segments ──────────────────────────────────────────────────────────────────

_MATCH_RADIUS_M = 50  # metres — how close a track point must be to a segment endpoint


def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def match_segment(track_points: list, seg) -> dict | None:
    """
    Walk through all segment waypoints in order.
    Returns {"elapsed_seconds", "avg_speed_kmh", "avg_hr"} or None.
    """
    import json

    if getattr(seg, "waypoints_json", None):
        waypoints = json.loads(seg.waypoints_json)
    else:
        waypoints = [[seg.start_lat, seg.start_lon], [seg.end_lat, seg.end_lon]]

    if len(waypoints) < 2:
        return None

    pts = [
        (tp.get("timestamp"), tp.get("lat"), tp.get("lon"),
         tp.get("heart_rate_bpm"), tp.get("speed_kmh"))
        for tp in track_points
        if tp.get("lat") and tp.get("lon") and tp.get("timestamp")
    ]
    if len(pts) < 2:
        return None

    best = None
    for i, (ts, lat, lon, hr, spd) in enumerate(pts):
        if _haversine(lat, lon, waypoints[0][0], waypoints[0][1]) > _MATCH_RADIUS_M:
            continue
        # Found a point near the first waypoint — now walk remaining waypoints
        wp_idx = 1
        hrs, spds = [], []
        for j in range(i + 1, len(pts)):
            ts2, lat2, lon2, hr2, spd2 = pts[j]
            if hr2:  hrs.append(hr2)
            if spd2: spds.append(spd2)
            if _haversine(lat2, lon2, waypoints[wp_idx][0], waypoints[wp_idx][1]) <= _MATCH_RADIUS_M:
                wp_idx += 1
                if wp_idx == len(waypoints):
                    elapsed = (ts2 - ts).total_seconds()
                    if elapsed > 0 and (best is None or elapsed < best["elapsed_seconds"]):
                        best = {
                            "elapsed_seconds": elapsed,
                            "avg_speed_kmh": round(sum(spds) / len(spds), 1) if spds else None,
                            "avg_hr": round(sum(hrs) / len(hrs), 1) if hrs else None,
                        }
                    break
    return best
