"""
Durability Profiling — measures how well a rider maintains output over time.

Science basis:
  Maunder et al. (2021) "Quantifying durability and repeatability of professional
  cyclists during multi-stage racing."
  van Erp et al. (2021) "Demands of professional cycling races."
  Smyth (2021) "A new method to quantify durability in endurance athletes."

Core concept: compare output (watts / speed-HR ratio) in Q1 of a ride vs Q4.
Durability Index = (Q4 output / Q1 output) × 100
100 = zero fade; 80 = lost 20% of initial output by the end.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from typing import Optional, Any


# ── Constants ─────────────────────────────────────────────────────────────────

_MIN_DURATION_S  = 2700    # 45 min minimum for meaningful fade
_MIN_TRACK_PTS   = 300     # rough minimum for reliable statistics
_FLAT_GRAD_MIN   = -1.0    # % — lower bound for "flat" segment
_FLAT_GRAD_MAX   = 2.0     # % — upper bound for "flat" segment
_MIN_SPEED_KMH   = 10.0    # below this = stopping / traffic
_HR_FLOOR_FRAC   = 0.55    # fraction of max_hr below which = recovery / coasting
_PWR_FLOOR_W     = 30      # ignore coasting / zero-power points

_CATEGORY_THRESHOLDS = [
    (95, "excellent"),
    (88, "good"),
    (80, "moderate"),
    (70, "poor"),
]


# ── Public API ────────────────────────────────────────────────────────────────

def validate_durability_calculation(
    duration_seconds: int,
    track_point_count: int,
    notes: Optional[str] = None,
    avg_hr: Optional[float] = None,
    max_hr: Optional[float] = None,
) -> tuple[bool, str, str]:
    """Return (can_calculate, quality_override, reason).

    quality_override is "" when can_calculate is True and full quality is allowed,
    or "low" when the ride is marginal but we still try.
    """
    if duration_seconds < _MIN_DURATION_S:
        return False, "", f"Ride under 45 minutes ({duration_seconds // 60} min) — insufficient duration for fade analysis."

    if track_point_count < _MIN_TRACK_PTS:
        return False, "", f"Too few track points ({track_point_count}) for reliable analysis."

    # Interval / race detection from notes
    if notes:
        keywords = ("interval", "intervals", "répétitions", "séries", "race", "criterium")
        note_lower = notes.lower()
        if any(k in note_lower for k in keywords):
            return False, "", "Interval and race sessions skipped — recovery periods distort fade measurement."

    # Very easy ride: HR stayed low throughout
    if avg_hr and max_hr and max_hr > 0:
        hr_frac = avg_hr / max_hr
        if hr_frac < 0.55:
            return True, "low", "Very low average HR — recovery ride; fade measurement has low confidence."

    # Short but valid
    if duration_seconds < 3600:
        return True, "low", f"Ride under 60 minutes ({duration_seconds // 60} min) — durability is less meaningful for shorter efforts."

    return True, "", ""


def calculate_durability(
    duration_seconds: int,
    track_points: list[dict],
    climb_detections: Optional[list] = None,
    max_hr: Optional[float] = None,
    ftp: Optional[int] = None,
    weight_kg: Optional[float] = None,
    tsb_at_start: Optional[float] = None,
    temperature_avg_c: Optional[float] = None,
    notes: Optional[str] = None,
) -> Optional[dict]:
    """Compute durability for one activity.

    track_points is a list of dicts with keys:
        timestamp, speed_kmh, heart_rate_bpm, power_w, elevation, distance_m

    climb_detections is an optional list of objects/dicts with:
        estimated_power_w, gradient_pct, and a timestamp or distance field
        indicating where in the ride the climb sits.
        Pass None or [] if unavailable (Phase B not merged / GPX-only rides).

    Returns None if the ride is ineligible. Otherwise returns the full analysis dict.
    """
    if not track_points:
        return None

    # Guard: validate eligibility
    avg_hr_pts = [p["heart_rate_bpm"] for p in track_points if p.get("heart_rate_bpm")]
    avg_hr = sum(avg_hr_pts) / len(avg_hr_pts) if avg_hr_pts else None

    can_calc, quality_override, reason = validate_durability_calculation(
        duration_seconds, len(track_points), notes, avg_hr, max_hr,
    )
    if not can_calc:
        return None

    # Sort by timestamp if present, otherwise assume order is correct
    pts = _sort_and_clean(track_points)
    if len(pts) < _MIN_TRACK_PTS:
        return None

    # Compute gradients from elevation + distance
    gradients = _compute_gradients(pts)

    # ── Choose best available method ──────────────────────────────────────────
    has_power = _has_real_power(pts)
    has_climbs = _has_distributed_climbs(climb_detections, duration_seconds)
    flat_minutes = _flat_minutes(pts, gradients)

    if has_power:
        method = "power"
    elif has_climbs:
        method = "climbing_power"
    else:
        method = "hr_speed"

    # ── Split into quarters by elapsed time ───────────────────────────────────
    quarters = _split_quarters(pts)

    # ── Calculate output per quarter ──────────────────────────────────────────
    grad_by_quarter: list[list] = [
        [gradients[i] for i in q_idxs]
        for q_idxs in _quarter_indices(pts, quarters)
    ]

    if method == "power":
        outputs, unit, method_quality, method_reason = _power_outputs(
            quarters, max_hr, ftp,
        )
    elif method == "climbing_power":
        outputs, unit, method_quality, method_reason = _climbing_power_outputs(
            climb_detections, duration_seconds, pts,
        )
        # Fall back to hr_speed if not enough quarter coverage. The durability index
        # needs q1 and q4 specifically (see guard below), so a missing q1 or q4 alone
        # is reason enough to fall back, not just ">1 missing overall".
        if outputs.count(None) > 1 or outputs[0] is None or outputs[3] is None:
            method = "hr_speed"
            outputs, unit, method_quality, method_reason = _hr_speed_outputs(
                quarters, grad_by_quarter, max_hr, flat_minutes,
            )
    else:
        outputs, unit, method_quality, method_reason = _hr_speed_outputs(
            quarters, grad_by_quarter, max_hr, flat_minutes,
        )

    q1, q2, q3, q4 = outputs

    # Need at least Q1 and Q4 to compute the index
    if q1 is None or q4 is None or q1 <= 0:
        return None

    # ── Durability Index and derived metrics ──────────────────────────────────
    fade_ratio       = q4 / q1
    durability_index = round(fade_ratio * 100, 1)
    durability_index = max(0.0, min(110.0, durability_index))   # physiological bounds

    duration_hours = duration_seconds / 3600
    fade_rate = round((1 - fade_ratio) / duration_hours * 100, 2) if duration_hours > 0 else None

    category = _classify_durability(durability_index, duration_hours)

    # ── Total work estimate ───────────────────────────────────────────────────
    total_work_kj = _estimate_work_kj(pts, method, avg_hr, max_hr, weight_kg, duration_hours)

    # ── Quality ───────────────────────────────────────────────────────────────
    # Override if validate said "low"; otherwise use method quality
    if quality_override == "low":
        final_quality = "low"
        final_reason = reason or method_reason
    else:
        final_quality = method_quality
        final_reason = method_reason

    # High-temp caveat
    if temperature_avg_c and temperature_avg_c >= 35 and final_quality == "high":
        final_quality = "medium"
        final_reason += f" Heat strain (avg {temperature_avg_c:.0f}°C) may inflate fade."

    # ── Build output ──────────────────────────────────────────────────────────
    analysis = {
        "durability_index":    durability_index,
        "durability_category": category,
        "method":              method,
        "fade_rate_pct_per_hour": fade_rate,
        "q1_output":  round(q1, 3) if q1 is not None else None,
        "q2_output":  round(q2, 3) if q2 is not None else None,
        "q3_output":  round(q3, 3) if q3 is not None else None,
        "q4_output":  round(q4, 3) if q4 is not None else None,
        "output_unit": unit,
        "total_work_kj":     round(total_work_kj, 0) if total_work_kj else None,
        "tsb_at_start":      tsb_at_start,
        "temperature_avg_c": temperature_avg_c,
        "quality":       final_quality,
        "quality_reason": final_reason,
        "context": {
            "duration_hours": round(duration_hours, 2),
            "flat_minutes_analyzed": round(flat_minutes, 0),
            "tsb_at_start":   tsb_at_start,
            "temperature_avg": temperature_avg_c,
        },
    }
    analysis["analysis_json"] = json.dumps(analysis["context"])
    return analysis


def calculate_durability_trend(user_id: int, db: Any, weeks: int = 12) -> dict:
    """Weekly durability trend with linear regression.

    Only includes rides >1h with quality 'high' or 'medium'.
    """
    from models import DurabilityAnalysis, Activity
    from sqlalchemy import func

    cutoff = datetime.utcnow() - timedelta(weeks=weeks)

    rows = (
        db.query(DurabilityAnalysis, Activity.date)
        .join(Activity, Activity.id == DurabilityAnalysis.activity_id)
        .filter(
            Activity.user_id == user_id,
            Activity.date >= cutoff,
            Activity.duration_seconds >= 3600,
            DurabilityAnalysis.quality.in_(["high", "medium"]),
            DurabilityAnalysis.durability_index.isnot(None),
        )
        .order_by(Activity.date)
        .all()
    )

    if not rows:
        return {
            "weekly_averages": [],
            "trend": "stable",
            "trend_slope": 0.0,
            "current_avg": None,
            "best_ever": None,
            "best_ever_date": None,
        }

    # Group by ISO year-week
    week_buckets: dict[str, list[float]] = {}
    best_val, best_date = None, None

    for analysis, date in rows:
        idx = analysis.durability_index
        week_key = date.strftime("%G-W%V")
        week_buckets.setdefault(week_key, []).append(idx)
        if best_val is None or idx > best_val:
            best_val = idx
            best_date = date.date().isoformat()

    weekly_avgs = sorted([
        {
            "week": week,
            "avg_durability": round(sum(vals) / len(vals), 1),
            "ride_count": len(vals),
        }
        for week, vals in week_buckets.items()
    ], key=lambda x: x["week"])

    # Linear regression on sequential week index → slope = change per week
    xs = list(range(len(weekly_avgs)))
    ys = [w["avg_durability"] for w in weekly_avgs]
    slope, _ = _linear_regression(xs, ys)
    slope = round(slope, 3)

    trend = "improving" if slope > 0.5 else "declining" if slope < -0.5 else "stable"
    current_avg = round(ys[-1], 1) if ys else None

    return {
        "weekly_averages": weekly_avgs,
        "trend":           trend,
        "trend_slope":     slope,
        "current_avg":     current_avg,
        "best_ever":       round(best_val, 1) if best_val else None,
        "best_ever_date":  best_date,
    }


def compare_durability_rides(activity_ids: list[int], db: Any) -> dict:
    """Normalized comparison of durability across up to 5 rides."""
    from models import DurabilityAnalysis, Activity

    if len(activity_ids) > 5:
        activity_ids = activity_ids[:5]

    rows = (
        db.query(DurabilityAnalysis, Activity)
        .join(Activity, Activity.id == DurabilityAnalysis.activity_id)
        .filter(Activity.id.in_(activity_ids))
        .all()
    )

    if not rows:
        return {"rides": [], "best_ride_id": None, "comparison_note": "No durability data found."}

    rides = []
    for analysis, activity in rows:
        rides.append({
            "activity_id":      activity.id,
            "name":             activity.name,
            "date":             activity.date.date().isoformat(),
            "durability_index": analysis.durability_index,
            "durability_category": analysis.durability_category,
            "fade_rate":        analysis.fade_rate_pct_per_hour,
            "duration_h":       round(activity.duration_seconds / 3600, 2),
            "avg_temp":         analysis.temperature_avg_c,
            "tsb":              analysis.tsb_at_start,
            "work_kj":          analysis.total_work_kj,
            "method":           analysis.method,
            "quality":          analysis.quality,
        })

    rides.sort(key=lambda r: r["date"])

    # Best ride: highest durability_index among high/medium quality; fall back to any
    scored = [r for r in rides if r["durability_index"] is not None and r["quality"] in ("high", "medium")]
    if not scored:
        scored = [r for r in rides if r["durability_index"] is not None]
    best = max(scored, key=lambda r: r["durability_index"]) if scored else None

    note = _comparison_note(rides, best)

    # Warn on incompatible duration spread
    durations = [r["duration_h"] for r in rides if r["duration_h"]]
    duration_warning = ""
    if durations and max(durations) > min(durations) * 2:
        duration_warning = " Note: ride durations vary significantly — longer rides are inherently harder to sustain, so direct comparison may not be fair."

    return {
        "rides": rides,
        "best_ride_id": best["activity_id"] if best else None,
        "comparison_note": note + duration_warning,
    }


# ── Private helpers ────────────────────────────────────────────────────────────

def _sort_and_clean(track_points: list[dict]) -> list[dict]:
    """Sort by timestamp; fill missing timestamps from index."""
    has_ts = any(p.get("timestamp") for p in track_points)
    if has_ts:
        def ts_key(p):
            t = p.get("timestamp")
            if t is None:
                return datetime(1970, 1, 1)
            if isinstance(t, str):
                return datetime.fromisoformat(t.replace("Z", "+00:00").replace("+00:00", ""))
            return t
        return sorted(track_points, key=ts_key)
    return track_points


def _compute_gradients(pts: list[dict]) -> list[Optional[float]]:
    """Gradient in % for each point; None when distance info is missing."""
    grads: list[Optional[float]] = [None]
    for i in range(1, len(pts)):
        d_dist = (pts[i].get("distance_m") or 0) - (pts[i - 1].get("distance_m") or 0)
        d_elev = (pts[i].get("elevation") or 0) - (pts[i - 1].get("elevation") or 0)
        if d_dist > 1.0:
            grads.append((d_elev / d_dist) * 100.0)
        else:
            grads.append(None)
    return grads


def _has_real_power(pts: list[dict]) -> bool:
    power_pts = [p for p in pts if (p.get("power_w") or 0) > _PWR_FLOOR_W]
    return len(power_pts) / len(pts) > 0.80


def _has_distributed_climbs(climb_detections: Optional[list], duration_s: int) -> bool:
    """True if ≥2 climbs span at least the first and last third of the ride."""
    if not climb_detections or len(climb_detections) < 2:
        return False
    # Each climb needs either a `start_elapsed_s` or we infer from index
    threshold_early = duration_s * 0.40
    threshold_late  = duration_s * 0.60
    has_early = any(_climb_elapsed(c) < threshold_early for c in climb_detections)
    has_late  = any(_climb_elapsed(c) > threshold_late  for c in climb_detections)
    return has_early and has_late


def _climb_elapsed(c) -> float:
    """Extract start elapsed seconds from a climb detection (dict or ORM object)."""
    if isinstance(c, dict):
        return c.get("start_elapsed_s") or c.get("start_seconds") or 0.0
    return getattr(c, "start_elapsed_s", None) or getattr(c, "start_seconds", 0.0)


def _flat_minutes(pts: list[dict], gradients: list[Optional[float]]) -> float:
    """Minutes of track points on flat terrain (-1% to +2%)."""
    flat = sum(
        1 for i, g in enumerate(gradients)
        if g is not None and _FLAT_GRAD_MIN <= g <= _FLAT_GRAD_MAX
           and (pts[i].get("speed_kmh") or 0) >= _MIN_SPEED_KMH
    )
    return flat / 60.0   # assuming ~1 point/second average


def _split_quarters(pts: list[dict]) -> list[list[dict]]:
    """Split track point list into 4 equal quarters by index."""
    n = len(pts)
    q = n // 4
    return [
        pts[0:q],
        pts[q:2*q],
        pts[2*q:3*q],
        pts[3*q:],
    ]


def _quarter_indices(pts: list[dict], quarters: list[list[dict]]) -> list[list[int]]:
    """Map each quarter back to global indices (needed for gradient lookup)."""
    n = len(pts)
    q = n // 4
    return [
        list(range(0, q)),
        list(range(q, 2*q)),
        list(range(2*q, 3*q)),
        list(range(3*q, n)),
    ]


def _power_outputs(
    quarters: list[list[dict]],
    max_hr: Optional[float],
    ftp: Optional[int],
) -> tuple[list[Optional[float]], str, str, str]:
    hr_floor = (max_hr * _HR_FLOOR_FRAC) if max_hr else 0

    def quarter_power(pts_q: list[dict]) -> Optional[float]:
        vals = [
            p["power_w"] for p in pts_q
            if (p.get("power_w") or 0) > _PWR_FLOOR_W
            and (p.get("heart_rate_bpm") or hr_floor + 1) >= hr_floor
        ]
        return round(sum(vals) / len(vals), 1) if vals else None

    outputs = [quarter_power(q) for q in quarters]
    quality = "high"
    reason  = "Based on real power meter data."
    if ftp:
        reason += f" FTP context: {ftp} W."
    return outputs, "watts", quality, reason


def _climbing_power_outputs(
    climb_detections: list,
    duration_s: int,
    pts: list[dict],
) -> tuple[list[Optional[float]], str, str, str]:
    """Assign each climb to a quarter, normalize by gradient, average per quarter."""
    q_size = duration_s / 4
    buckets: list[list[float]] = [[], [], [], []]

    for c in climb_detections:
        elapsed = _climb_elapsed(c)
        power   = _climb_power(c)
        grad    = _climb_gradient(c)
        if power is None or power <= 0:
            continue
        # Normalize: express watts as if gradient were a standard 5%
        norm_power = power * (5.0 / max(grad, 1.0)) if grad and grad > 0 else power
        q_idx = min(int(elapsed / q_size), 3)
        buckets[q_idx].append(norm_power)

    outputs = [
        round(sum(b) / len(b), 1) if b else None
        for b in buckets
    ]
    non_none = [v for v in outputs if v is not None]
    quality = "high" if len(non_none) >= 3 else "medium" if len(non_none) == 2 else "low"
    reason  = f"Based on estimated climbing power from {sum(len(b) for b in buckets)} climb segments, normalized to equivalent 5% gradient."
    return outputs, "watts_normalized", quality, reason


def _climb_power(c) -> Optional[float]:
    if isinstance(c, dict):
        return c.get("estimated_power_w") or c.get("avg_power_w")
    return getattr(c, "estimated_power_w", None) or getattr(c, "avg_power_w", None)


def _climb_gradient(c) -> Optional[float]:
    if isinstance(c, dict):
        return c.get("gradient_pct") or c.get("avg_gradient_pct")
    return getattr(c, "gradient_pct", None) or getattr(c, "avg_gradient_pct", None)


def _hr_speed_outputs(
    quarters: list[list[dict]],
    grad_by_quarter: list[list],
    max_hr: Optional[float],
    flat_minutes: float,
) -> tuple[list[Optional[float]], str, str, str]:
    hr_floor = (max_hr * _HR_FLOOR_FRAC) if max_hr else 0

    def quarter_ef(pts_q: list[dict], grads_q: list) -> Optional[float]:
        vals = []
        for i, p in enumerate(pts_q):
            spd = p.get("speed_kmh") or 0
            hr  = p.get("heart_rate_bpm") or 0
            g   = grads_q[i] if i < len(grads_q) else None
            if spd < _MIN_SPEED_KMH or hr < max(hr_floor, 40):
                continue
            # Allow all gradients if flat data is scarce; else restrict to flat
            if flat_minutes >= 20 and g is not None and not (_FLAT_GRAD_MIN <= g <= _FLAT_GRAD_MAX):
                continue
            vals.append((spd / hr) * 100)
        return round(sum(vals) / len(vals), 3) if vals else None

    outputs = [quarter_ef(quarters[i], grad_by_quarter[i]) for i in range(4)]

    if flat_minutes >= 20:
        quality = "medium"
        reason  = f"Based on speed/HR efficiency ratio on flat segments ({flat_minutes:.0f} min analysed). Less precise than a power meter."
    else:
        quality = "low"
        reason  = f"Limited flat terrain ({flat_minutes:.0f} min). Speed/HR ratio computed across all gradients — lower confidence."

    return outputs, "speed_hr_ratio", quality, reason


def _classify_durability(index: float, duration_hours: float) -> str:
    """Category thresholds; stricter for longer rides (harder to sustain)."""
    # For rides >3h, shift thresholds down by 3 points (sustaining is harder)
    shift = min(5.0, max(0.0, (duration_hours - 3.0) * 1.5))
    for threshold, label in _CATEGORY_THRESHOLDS:
        if index >= threshold - shift:
            return label
    return "very_poor"


def _estimate_work_kj(
    pts: list[dict],
    method: str,
    avg_hr: Optional[float],
    max_hr: Optional[float],
    weight_kg: Optional[float],
    duration_hours: float,
) -> Optional[float]:
    if method == "power":
        # Riemann sum over power × elapsed time
        total_j = 0.0
        for i in range(1, len(pts)):
            p0, p1 = pts[i - 1], pts[i]
            w0 = p0.get("power_w") or 0
            w1 = p1.get("power_w") or 0
            # Estimate dt from timestamps or assume 1 s/point
            t0 = p0.get("timestamp"); t1 = p1.get("timestamp")
            if t0 and t1:
                if isinstance(t0, str):
                    t0 = datetime.fromisoformat(t0.replace("Z", "").replace("+00:00", ""))
                if isinstance(t1, str):
                    t1 = datetime.fromisoformat(t1.replace("Z", "").replace("+00:00", ""))
                dt = (t1 - t0).total_seconds()
            else:
                dt = 1.0
            dt = max(0, min(dt, 10))   # cap gaps at 10 s
            total_j += ((w0 + w1) / 2) * dt
        return total_j / 1000

    # HR-based gross estimate (Keytel 2005 approximation)
    if avg_hr and max_hr and max_hr > 0 and weight_kg and weight_kg > 0:
        hr_frac = avg_hr / max_hr
        # Gross kcal/min ≈ weight × MET × 0.01667, MET ≈ 4 + 12 × hr_frac²
        met = 4 + 12 * hr_frac ** 2
        kcal = met * weight_kg * duration_hours
        return round(kcal * 4.184, 0)   # kcal → kJ

    return None


def _linear_regression(xs: list[float], ys: list[float]) -> tuple[float, float]:
    n = len(xs)
    if n < 2:
        return 0.0, ys[0] if ys else 0.0
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    ss_xx  = sum((x - x_mean) ** 2 for x in xs)
    ss_xy  = sum((xs[i] - x_mean) * (ys[i] - y_mean) for i in range(n))
    if ss_xx == 0:
        return 0.0, y_mean
    slope     = ss_xy / ss_xx
    intercept = y_mean - slope * x_mean
    return slope, intercept


def _comparison_note(rides: list[dict], best: Optional[dict]) -> str:
    if not best or len(rides) < 2:
        return ""

    best_idx  = best["durability_index"]
    best_date = best["date"]
    other_better_temp = any(
        r["avg_temp"] and best.get("avg_temp") and r["avg_temp"] > best["avg_temp"] + 5
        and r["durability_index"] and r["durability_index"] > best_idx - 5
        for r in rides if r["activity_id"] != best["activity_id"]
    )

    note = f"Best durability: {best_idx:.0f} on {best_date}"
    if best.get("tsb") is not None and best["tsb"] < -15:
        note += f" (achieved despite high fatigue — TSB {best['tsb']:.0f})"
    if best.get("avg_temp") and best["avg_temp"] >= 30:
        note += f" in {best['avg_temp']:.0f}°C heat"
    if other_better_temp:
        note += ". Warmer rides showing comparable durability suggest improving heat resilience."
    note += "."
    return note
