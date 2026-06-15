"""
Adjusted HR Decoupling — measures genuine aerobic drift, correcting for:
  • Terrain:     only flat segments (-1% to +2% gradient) are compared
  • Temperature: expected cardiovascular drift from heat subtracted
  • Hydration:   estimated performance impact of fluid deficit subtracted

Science basis:
  Coyle & González-Alonso (2001) "Cardiovascular drift during prolonged exercise."
  Cheuvront & Haymes (2001) "Thermoregulation and marathon running."
  Montain & Coyle (1992) "Influence of hydration on cardiovascular drift."
  Jeukendrup & Diemen (1998) "Heart rate monitoring during training and competition."
"""

from __future__ import annotations

import json
import math
from typing import Optional, Any


# ── Constants ─────────────────────────────────────────────────────────────────

_MIN_DURATION_S      = 2700    # 45 min — shorter rides produce unstable decoupling
_MIN_HR_VALID_FRAC   = 0.80    # need HR on ≥80% of points
_MIN_HR_RANGE_BPM    = 20      # < 20 bpm HR variation → recovery/constant-pace, skip
_MIN_FLAT_MINUTES    = 30      # need ≥30 min of flat terrain for terrain-corrected result
_HALF_FLAT_MIN_MIN   = 15      # each half of the flat segments must have ≥15 min
_GRAD_SMOOTH_WINDOW  = 30      # seconds for gradient smoothing moving average
_FLAT_GRAD_LO        = -1.0    # % — lower bound of "flat"
_FLAT_GRAD_HI        = 2.0     # % — upper bound of "flat"

# Race / interval detection keywords (EF drift is meaningless in these)
_SKIP_KEYWORDS = (
    "interval", "intervals", "répétitions", "séries",
    "race", "criterium", "criterio", "corrida", "vo2", "ftp test",
)


# ── Public API ─────────────────────────────────────────────────────────────────

def calculate_adjusted_decoupling(
    activity: Any,
    track_points: list[dict],
    user: Any,
) -> Optional[dict]:
    """Compute raw and adjusted decoupling for one activity.

    track_points must be a list of dicts with keys:
        timestamp, speed_kmh, heart_rate_bpm, elevation, distance_m
        (power_w is optional — used when present)

    Returns None if the ride is ineligible.
    Otherwise returns:
    {
        decoupling_raw:             float,
        decoupling_adjusted:        float,
        decoupling_components_json: str (JSON),
        decoupling_quality:         "high" | "medium" | "low",
        decoupling_warning:         str | None,
    }
    """
    if not track_points:
        return None

    # ── Step 1: Eligibility check ─────────────────────────────────────────────
    ok, warning = _check_eligibility(activity, track_points)
    if not ok:
        return {
            "decoupling_raw":             None,
            "decoupling_adjusted":        None,
            "decoupling_components_json": json.dumps({"warning": warning}),
            "decoupling_quality":         "low",
            "decoupling_warning":         warning,
        }

    pts = _sort_and_clean(track_points)
    if len(pts) < 60:
        return None

    # ── Step 2: Gradient segmentation ────────────────────────────────────────
    gradients = _compute_gradients_smooth(pts)
    flat_idx  = [i for i, g in enumerate(gradients) if g is not None and _FLAT_GRAD_LO <= g <= _FLAT_GRAD_HI]

    flat_pts  = [pts[i] for i in flat_idx]
    flat_min  = _elapsed_minutes(flat_pts)

    # ── Step 3: Raw decoupling (whole ride, no terrain filter) ────────────────
    drift_raw = _calc_ef_drift(pts)
    if drift_raw is None:
        return None

    # ── Step 4: Terrain-corrected drift ───────────────────────────────────────
    terrain_warning: Optional[str] = None
    drift_for_correction = drift_raw   # default: fall back to whole-ride if not enough flat
    first_half_ef = second_half_ef = None
    flat_minutes_analyzed = round(flat_min, 1)

    if flat_min >= _MIN_FLAT_MINUTES:
        flat_first, flat_second = _split_halves_by_elapsed(flat_pts)
        if (flat_first and flat_second
                and _elapsed_minutes(flat_first) >= _HALF_FLAT_MIN_MIN
                and _elapsed_minutes(flat_second) >= _HALF_FLAT_MIN_MIN):
            ef1 = _avg_ef(flat_first)
            ef2 = _avg_ef(flat_second)
            if ef1 and ef2 and ef1 > 0:
                drift_for_correction = ((ef1 - ef2) / ef1) * 100
                first_half_ef  = round(ef1, 4)
                second_half_ef = round(ef2, 4)
        else:
            terrain_warning = (
                f"Flat terrain found ({flat_min:.0f} min) but each half had "
                f"< {_HALF_FLAT_MIN_MIN} min — using full-ride drift."
            )
    else:
        terrain_warning = (
            f"Only {flat_min:.0f} min of flat terrain (need {_MIN_FLAT_MINUTES} min). "
            f"Decoupling calculated from full ride."
        )

    # ── Step 5: Heat drift correction ─────────────────────────────────────────
    avg_temp  = _get_temperature(activity)
    dur_hours = getattr(activity, "duration_seconds", 0) / 3600
    heat_drift = expected_heat_drift_pct(avg_temp, dur_hours) if avg_temp is not None else 0.0
    heat_explanation: Optional[str] = None
    if avg_temp is not None:
        heat_explanation = (
            f"Temperature averaged {avg_temp:.0f}°C over {dur_hours:.1f}h, "
            f"expected drift ~{heat_drift:.1f}%"
        )

    # ── Step 6: Hydration drift correction ────────────────────────────────────
    weight_kg  = getattr(user, "weight_kg", None)
    intake_ml  = getattr(activity, "hydration_ml", None)
    deficit_p  = hydration_deficit_pct(user, activity) if (weight_kg and intake_ml is not None) else None
    hydration_drift = expected_hydration_drift_pct(deficit_p, avg_temp)
    hydration_explanation: Optional[str] = None
    if deficit_p is not None:
        hydration_explanation = (
            f"Estimated {deficit_p:.1f}% body-weight fluid deficit "
            f"({round(deficit_p * weight_kg * 10)} ml short), "
            f"expected drift ~{hydration_drift:.1f}%"
        )

    # ── Step 7: Adjusted decoupling ───────────────────────────────────────────
    adjusted = max(0.0, drift_for_correction - heat_drift - hydration_drift)
    adjusted = round(adjusted, 2)
    drift_raw_r = round(drift_raw, 2)
    category = _classify(adjusted)

    # ── Step 8: Quality scoring ───────────────────────────────────────────────
    quality_signals = [
        flat_min >= _MIN_FLAT_MINUTES,
        avg_temp is not None,
        deficit_p is not None,
    ]
    quality = "high" if sum(quality_signals) == 3 else "medium" if sum(quality_signals) >= 2 else "low"
    if terrain_warning and quality == "high":
        quality = "medium"

    # Compose components JSON
    components = {
        "drift_raw_pct":               drift_raw_r,
        "expected_heat_drift_pct":     round(heat_drift, 2),
        "expected_hydration_drift_pct": round(hydration_drift, 2),
        "adjusted_pct":                adjusted,
        "category":                    category,
        "flat_minutes_analyzed":       flat_minutes_analyzed,
        "factors_explained": {
            "terrain":    (
                f"Analyzed {flat_minutes_analyzed} min of flat terrain (gradient {_FLAT_GRAD_LO}% to +{_FLAT_GRAD_HI}%)"
                if flat_min >= _MIN_FLAT_MINUTES else terrain_warning
            ),
            "heat":       heat_explanation,
            "hydration":  hydration_explanation,
        },
    }
    if first_half_ef is not None:
        components["first_half_ef"]  = first_half_ef
        components["second_half_ef"] = second_half_ef

    # Combine all warnings
    warnings = [w for w in [terrain_warning] if w]
    final_warning = "; ".join(warnings) if warnings else None

    return {
        "decoupling_raw":             drift_raw_r,
        "decoupling_adjusted":        adjusted,
        "decoupling_components_json": json.dumps(components),
        "decoupling_quality":         quality,
        "decoupling_warning":         final_warning,
    }


# ── Heat drift model ──────────────────────────────────────────────────────────

def expected_heat_drift_pct(avg_temp_c: float, duration_hours: float) -> float:
    """Estimate expected EF drift % caused by thermoregulation alone.

    Continuous model: cardiac drift ≈ 0.5 bpm per °C above 18°C (Gonzalez-Alonso
    et al. 2001), translated to EF% assuming ~150 bpm average HR.
    EF = speed/HR; if HR rises by X bpm at 150 bpm mean, EF drops by X/150 × 100%.

    Duration scaling saturates around 90 min (consistent with drift physiology).
    """
    if avg_temp_c < 18:
        heat_bpm = 0.0
    else:
        # 0.5 bpm per °C above 18°C
        heat_bpm = (avg_temp_c - 18.0) * 0.5

    # Drift accumulates with time, saturating around 90 min
    duration_factor = min(duration_hours / 1.5, 1.5)
    heat_bpm_total  = min(heat_bpm * duration_factor, 12.0)

    # Convert cardiac drift to EF drift % (assumed avg HR 150 bpm)
    ef_drift = heat_bpm_total / 150.0 * 100.0
    return round(ef_drift, 2)


# ── Hydration model ───────────────────────────────────────────────────────────

def calculate_sweat_loss_ml(user: Any, activity: Any) -> float:
    """Estimate total sweat loss in ml for the activity."""
    avg_temp  = _get_temperature(activity)
    max_hr    = getattr(user, "max_hr", None) or 185
    avg_hr    = getattr(activity, "avg_heart_rate_bpm", None)
    avg_hr_pct = (avg_hr / max_hr) if (avg_hr and max_hr) else 0.70

    cal_rate  = getattr(user, "sweat_rate_ml_per_hour", None)
    if cal_rate:
        base_rate = float(cal_rate)
    else:
        base_rate = 500.0
        if avg_temp is not None:
            base_rate += max(0.0, (avg_temp - 20.0)) * 40.0
        base_rate += max(0.0, (avg_hr_pct - 0.70)) * 1000.0

    dur_hours = getattr(activity, "duration_seconds", 3600) / 3600
    return base_rate * dur_hours


def hydration_deficit_pct(user: Any, activity: Any) -> Optional[float]:
    """Return body-weight fluid deficit as a percentage, or None if data missing."""
    weight_kg = getattr(user, "weight_kg", None)
    intake_ml = getattr(activity, "hydration_ml", None)
    if not weight_kg or intake_ml is None:
        return None
    sweat_loss  = calculate_sweat_loss_ml(user, activity)
    net_deficit = sweat_loss - float(intake_ml)
    deficit_pct = (net_deficit / (weight_kg * 1000)) * 100
    return max(0.0, round(deficit_pct, 2))


def expected_hydration_drift_pct(
    deficit_pct: Optional[float],
    avg_temp_c: Optional[float] = None,
) -> float:
    """Expected EF drift from dehydration (Montain & Coyle 1992).

    Each 1% BML raises HR by ~3–7 bpm; translated to EF% at ~150 bpm avg HR.
      ≥ 28°C: 4.5 bpm / 1% BML → ~3.0% EF drift / 1% BML
      20–28°C: 3.0 bpm / 1% BML → ~2.0% EF drift / 1% BML
      < 20°C:  2.0 bpm / 1% BML → ~1.3% EF drift / 1% BML
    """
    if deficit_pct is None:
        return 0.0

    if avg_temp_c is None or avg_temp_c >= 28:
        bpm_per_pct = 4.5    # hot conditions (Montain & Coyle hot protocol)
    elif avg_temp_c >= 20:
        bpm_per_pct = 3.0    # temperate
    else:
        bpm_per_pct = 2.0    # cool

    ef_drift_per_pct = bpm_per_pct / 150.0 * 100.0   # convert bpm to EF%
    return round(deficit_pct * ef_drift_per_pct, 2)


# ── Classification ────────────────────────────────────────────────────────────

_CATEGORIES = [
    (2,  "Excellent"),
    (5,  "Good"),
    (8,  "Moderate"),
    (12, "Significant"),
]

def _classify(adjusted_pct: float) -> str:
    for threshold, label in _CATEGORIES:
        if adjusted_pct < threshold:
            return label
    return "High"


# ── Private helpers ───────────────────────────────────────────────────────────

def _check_eligibility(activity: Any, pts: list[dict]) -> tuple[bool, Optional[str]]:
    dur = getattr(activity, "duration_seconds", 0)
    if dur < _MIN_DURATION_S:
        return False, f"Ride under 45 minutes ({dur // 60} min) — decoupling not meaningful."

    hr_vals = [p["heart_rate_bpm"] for p in pts if p.get("heart_rate_bpm")]
    if len(hr_vals) / max(len(pts), 1) < _MIN_HR_VALID_FRAC:
        return False, "Less than 80% of track points have HR data."

    if (max(hr_vals) - min(hr_vals)) < _MIN_HR_RANGE_BPM:
        return False, (
            f"HR variation only {max(hr_vals) - min(hr_vals):.0f} bpm — "
            f"constant-pace or recovery ride, decoupling not informative."
        )

    notes = (getattr(activity, "notes", "") or "").lower()
    name  = (getattr(activity, "name",  "") or "").lower()
    combined = notes + " " + name
    for kw in _SKIP_KEYWORDS:
        if kw in combined:
            return False, f"Interval / race session detected ('{kw}') — skipping decoupling."

    return True, None


def _sort_and_clean(pts: list[dict]) -> list[dict]:
    """Sort by timestamp; drop points without speed and HR."""
    from datetime import datetime

    def _ts(p):
        t = p.get("timestamp")
        if t is None:
            return datetime.min
        if isinstance(t, str):
            try:
                return datetime.fromisoformat(t)
            except ValueError:
                return datetime.min
        return t

    sorted_pts = sorted(pts, key=_ts)
    return [p for p in sorted_pts
            if p.get("speed_kmh") is not None and p.get("heart_rate_bpm") is not None]


def _compute_gradients_smooth(pts: list[dict]) -> list[Optional[float]]:
    """Compute smoothed gradient (%) at each point using a ~30-second window."""
    n = len(pts)
    raw: list[Optional[float]] = [None] * n

    for i in range(1, n):
        e1 = pts[i - 1].get("elevation")
        e2 = pts[i].get("elevation")
        d1 = pts[i - 1].get("distance_m", 0) or 0
        d2 = pts[i].get("distance_m", 0) or 0
        delta_d = d2 - d1
        if e1 is None or e2 is None or delta_d <= 0:
            raw[i] = None
        else:
            raw[i] = ((e2 - e1) / delta_d) * 100.0

    # Simple moving-average smoothing using time window
    smooth: list[Optional[float]] = [None] * n
    half_w = _GRAD_SMOOTH_WINDOW // 2
    for i in range(n):
        window = [raw[j] for j in range(max(0, i - half_w), min(n, i + half_w + 1)) if raw[j] is not None]
        smooth[i] = sum(window) / len(window) if window else None

    return smooth


def _elapsed_minutes(pts: list[dict]) -> float:
    """Duration in minutes spanned by a list of sorted track points."""
    if len(pts) < 2:
        return 0.0
    from datetime import datetime

    def _ts(p):
        t = p.get("timestamp")
        if t is None:
            return None
        if isinstance(t, str):
            try:
                return datetime.fromisoformat(t)
            except ValueError:
                return None
        return t

    t_start = _ts(pts[0])
    t_end   = _ts(pts[-1])
    if t_start is None or t_end is None:
        return len(pts) / 60.0  # rough fallback: assume ~1 pt/s
    delta = (t_end - t_start).total_seconds()
    return max(0.0, delta / 60.0)


def _split_halves_by_elapsed(pts: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split a sorted point list into two equal-duration halves."""
    if len(pts) < 4:
        return pts[:len(pts) // 2], pts[len(pts) // 2:]

    total_min = _elapsed_minutes(pts)
    if total_min <= 0:
        mid = len(pts) // 2
        return pts[:mid], pts[mid:]

    from datetime import datetime

    def _ts(p):
        t = p.get("timestamp")
        if t is None:
            return None
        if isinstance(t, str):
            try:
                return datetime.fromisoformat(t)
            except ValueError:
                return None
        return t

    t_start = _ts(pts[0])
    if t_start is None:
        mid = len(pts) // 2
        return pts[:mid], pts[mid:]

    half_s = total_min * 60 / 2  # seconds for first half
    split_i = len(pts) // 2
    for i, p in enumerate(pts):
        t = _ts(p)
        if t is not None and (t - t_start).total_seconds() >= half_s:
            split_i = i
            break
    return pts[:split_i], pts[split_i:]


def _avg_ef(pts: list[dict]) -> Optional[float]:
    """EF = mean(speed_kmh / heart_rate_bpm) over valid points."""
    vals = [
        p["speed_kmh"] / p["heart_rate_bpm"]
        for p in pts
        if p.get("speed_kmh", 0) > 3.0 and p.get("heart_rate_bpm", 0) > 40
    ]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _calc_ef_drift(pts: list[dict]) -> Optional[float]:
    """Drift = ((EF_first_half - EF_second_half) / EF_first_half) × 100."""
    first, second = _split_halves_by_elapsed(pts)
    ef1 = _avg_ef(first)
    ef2 = _avg_ef(second)
    if ef1 is None or ef2 is None or ef1 == 0:
        return None
    return ((ef1 - ef2) / ef1) * 100.0


def _get_temperature(activity: Any) -> Optional[float]:
    """Return best available temperature — prefer sensor data over weather API."""
    t = getattr(activity, "sensor_temp_avg_c", None) or getattr(activity, "weather_temp_c", None)
    return float(t) if t is not None else None
