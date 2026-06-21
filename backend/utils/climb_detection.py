import math
from datetime import datetime


def smooth_elevation(track_points: list, window: int = 30) -> list:
    """
    Applies a centered rolling average over elevation to reduce barometric altimeter noise.
    Window is in seconds. Two-pointer sliding window: O(n * window_size) vs original O(n²).
    Also offsets readings if min elevation < -30m (sensor drift).
    Returns a new list of points with 'elevation_smooth' key added.
    """
    pts = []
    for tp in track_points:
        t = tp.get("timestamp")
        if isinstance(t, str):
            t = datetime.fromisoformat(t)
        pts.append({**tp, "_ts": t})

    half = window / 2
    n = len(pts)

    # Pre-compute unix timestamps for fast comparison
    ts_arr = [p["_ts"].timestamp() if isinstance(p["_ts"], datetime) else None for p in pts]

    smoothed = []
    left = 0
    right = 0

    for i in range(n):
        t_i = ts_arr[i]
        if t_i is None:
            smoothed.append({**pts[i], "elevation_smooth": pts[i].get("elevation")})
            continue

        # Expand right pointer while within forward half-window
        while right < n and ts_arr[right] is not None and ts_arr[right] - t_i <= half:
            right += 1
        # Shrink left pointer while outside backward half-window
        while left < i and (ts_arr[left] is None or t_i - ts_arr[left] > half):
            left += 1

        elev_in_window = [pts[k]["elevation"] for k in range(left, right) if pts[k].get("elevation") is not None]
        if elev_in_window:
            smoothed.append({**pts[i], "elevation_smooth": sum(elev_in_window) / len(elev_in_window)})
        else:
            smoothed.append({**pts[i], "elevation_smooth": pts[i].get("elevation")})

    # Fix descalibrated sensors (e.g. Cycplus M1 reading -42m)
    min_elev = min((p["elevation_smooth"] for p in smoothed if p["elevation_smooth"] is not None), default=0)
    if min_elev < -30:
        offset = -min_elev - 30
        for p in smoothed:
            if p["elevation_smooth"] is not None:
                p["elevation_smooth"] += offset

    return smoothed


def _calc_gradient(elev1, elev2, dist1, dist2) -> float | None:
    dist_diff = dist2 - dist1
    if dist_diff <= 0:
        return None
    return (elev2 - elev1) / dist_diff * 100


def _calc_haversine_dist(lat1, lon1, lat2, lon2) -> float:
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def detect_climbs(
    track_points: list,
    min_gradient: float = 4.0,
    min_duration_s: int = 180,
    min_elevation_gain_m: float = 15.0,
    smoothing_window: int = 30,
) -> list[dict]:
    """
    Detects sustained climbs in a list of track point dicts.

    Track points must have: timestamp, elevation, distance_m (or lat/lon to compute distance).
    Returns list of climb dicts with metrics.
    """
    if len(track_points) < 10:
        return []

    # Smooth elevation
    pts = smooth_elevation(track_points, smoothing_window)

    # Fill in distance_m from lat/lon if missing
    for i, pt in enumerate(pts):
        if pt.get("distance_m") is None and i > 0:
            prev = pts[i - 1]
            if (prev.get("lat") and prev.get("lon") and pt.get("lat") and pt.get("lon")):
                step = _calc_haversine_dist(prev["lat"], prev["lon"], pt["lat"], pt["lon"])
                pts[i]["distance_m"] = (prev.get("distance_m") or 0) + step

    # Compute gradient per point
    gradients = [None] * len(pts)
    for i in range(1, len(pts)):
        e1 = pts[i - 1].get("elevation_smooth")
        e2 = pts[i].get("elevation_smooth")
        d1 = pts[i - 1].get("distance_m")
        d2 = pts[i].get("distance_m")
        if all(v is not None for v in [e1, e2, d1, d2]):
            gradients[i] = _calc_gradient(e1, e2, d1, d2)

    # Identify segments where gradient > min_gradient
    # Allow gaps ≤ 10s with gradient < min_gradient (transitions)
    # Stop segment on negative gradient
    def get_ts(pt) -> float | None:
        t = pt.get("_ts") or pt.get("timestamp")
        if isinstance(t, str):
            t = datetime.fromisoformat(t)
        if isinstance(t, datetime):
            return t.timestamp()
        return None

    raw_segments = []
    i = 0
    while i < len(pts):
        g = gradients[i]
        if g is not None and g >= min_gradient:
            seg_start = i
            last_above = i
            j = i + 1
            while j < len(pts):
                gj = gradients[j]
                ts_last = get_ts(pts[last_above])
                ts_j = get_ts(pts[j])
                gap_s = (ts_j - ts_last) if (ts_last and ts_j) else 0
                if gj is not None and gj >= min_gradient:
                    last_above = j
                elif gj is not None and gj < 0:
                    break
                elif gap_s > 10:
                    break
                j += 1
            raw_segments.append((seg_start, last_above))
            i = last_above + 1
        else:
            i += 1

    # Merge segments separated by < 30s of flat/easy terrain
    merged = []
    for seg in raw_segments:
        if not merged:
            merged.append(list(seg))
        else:
            prev_end = merged[-1][1]
            ts_prev_end = get_ts(pts[prev_end])
            ts_seg_start = get_ts(pts[seg[0]])
            gap_s = (ts_seg_start - ts_prev_end) if (ts_prev_end and ts_seg_start) else 999
            if gap_s <= 30:
                merged[-1][1] = seg[1]
            else:
                merged.append(list(seg))

    # Filter segments by quality thresholds and compute metrics
    climbs = []
    for start_idx, end_idx in merged:
        seg_pts = pts[start_idx:end_idx + 1]
        if len(seg_pts) < 3:
            continue

        ts_start = get_ts(seg_pts[0])
        ts_end = get_ts(seg_pts[-1])
        if ts_start is None or ts_end is None:
            continue
        duration_s = ts_end - ts_start
        if duration_s < min_duration_s:
            continue

        elevs = [p.get("elevation_smooth") for p in seg_pts if p.get("elevation_smooth") is not None]
        if not elevs:
            continue
        elev_gain = max(0.0, max(elevs) - elevs[0])
        if elev_gain < min_elevation_gain_m:
            continue

        # 60% of points must have gradient > 2%
        seg_grads = [gradients[start_idx + k] for k in range(len(seg_pts)) if gradients[start_idx + k] is not None]
        above_2pct = sum(1 for g in seg_grads if g > 2.0)
        if seg_grads and (above_2pct / len(seg_grads)) < 0.60:
            continue

        d_start = seg_pts[0].get("distance_m") or 0
        d_end = seg_pts[-1].get("distance_m") or 0
        dist_m = d_end - d_start

        if dist_m <= 0:
            continue

        avg_grad = elev_gain / dist_m * 100 if dist_m > 0 else 0
        max_grad = max((g for g in seg_grads if g is not None), default=0)

        speeds = [p.get("speed_kmh") for p in seg_pts if p.get("speed_kmh") is not None]
        avg_speed = sum(speeds) / len(speeds) if speeds else None

        hrs = [p.get("heart_rate_bpm") for p in seg_pts if p.get("heart_rate_bpm") is not None]
        avg_hr = round(sum(hrs) / len(hrs)) if hrs else None
        max_hr = round(max(hrs)) if hrs else None

        vam = (elev_gain / duration_s) * 3600 if duration_s > 0 else 0

        # Pacing: compare first vs second half speeds
        mid = len(seg_pts) // 2
        first_half_speeds = [p.get("speed_kmh") for p in seg_pts[:mid] if p.get("speed_kmh") is not None]
        second_half_speeds = [p.get("speed_kmh") for p in seg_pts[mid:] if p.get("speed_kmh") is not None]
        first_half_speed = sum(first_half_speeds) / len(first_half_speeds) if first_half_speeds else None
        second_half_speed = sum(second_half_speeds) / len(second_half_speeds) if second_half_speeds else None

        if first_half_speed and second_half_speed:
            ratio = second_half_speed / first_half_speed
            if ratio >= 1.0:
                pacing_type = "negative"
            elif ratio >= 0.95:
                pacing_type = "even"
            else:
                pacing_type = "positive"
        else:
            pacing_type = None

        climbs.append({
            "start_trackpoint_idx": start_idx,
            "end_trackpoint_idx": end_idx,
            "start_distance_m": round(d_start, 1),
            "end_distance_m": round(d_end, 1),
            "distance_m": round(dist_m, 1),
            "elevation_gain_m": round(elev_gain, 1),
            "avg_gradient_pct": round(avg_grad, 2),
            "max_gradient_pct": round(max_grad, 2),
            "duration_seconds": int(duration_s),
            "avg_speed_kmh": round(avg_speed, 2) if avg_speed is not None else None,
            "avg_heart_rate": avg_hr,
            "max_heart_rate": max_hr,
            "vam_m_per_hour": round(vam, 1),
            "pacing_type": pacing_type,
            "first_half_speed": round(first_half_speed, 2) if first_half_speed else None,
            "second_half_speed": round(second_half_speed, 2) if second_half_speed else None,
        })

    return climbs
