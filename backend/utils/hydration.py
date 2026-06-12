"""
Hydration & Heat Strain estimation utilities.

Science basis:
  - Sweat rate model: Sawka et al. (2007) ACSM Position Stand on Exercise and Fluid Replacement
  - Dehydration performance impact: Cheuvront & Haymes (2001), Montain & Coyle (1992)
  - HR drift: Coyle & Gonzalez-Alonso (2001) — ~1 bpm per 1% body-weight loss
  - Cardiac drift from heat: ~3-5 bpm at moderate heat stress
"""

from __future__ import annotations
import json
import math
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BASE_SWEAT_RATE_ML_H = 700        # ml/h at 20°C, 60% humidity, moderate effort
_TEMP_SENSITIVITY     = 20         # ml/h per °C above 15°C (Sawka 2007: ~10-20 ml/h/°C)
_HUMIDITY_SENSITIVITY = 2.0        # ml/h per % humidity above 50%
_INTENSITY_MULTIPLIER = {          # applied to base+temp+humidity estimate
    "low":      0.65,
    "moderate": 1.00,
    "high":     1.35,
    "very_high":1.65,
}
_HEAT_ADAPT_REDUCTION = {          # sweat-rate multiplier (adapted cyclists sweat earlier/more)
    "low":      1.00,
    "moderate": 1.08,   # acclimatised athletes shift fluid earlier — slightly higher vol, lower electrolytes
    "high":     1.15,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_sweat_rate(
    temp_c: float,
    humidity_pct: Optional[float],
    intensity_factor: float,        # 0-1 normalised (IF from TSS, or just duration proxy)
    duration_h: float,
    heat_adaptation_level: Optional[str] = None,
    user_calibrated_ml_h: Optional[float] = None,
) -> tuple[float, str]:
    """Return (estimated_sweat_rate_ml_h, analysis_quality).

    If the user has a calibrated sweat rate from a sweat test we use it as the
    baseline and apply only the environmental modifiers (temp, humidity) on top
    so the estimate stays anchored to their physiology.
    """
    if duration_h <= 0:
        return 0.0, "low"

    humidity = humidity_pct if humidity_pct is not None else 60.0

    # Environmental load above comfortable baseline (15 °C, 50 % RH)
    temp_delta     = max(0.0, temp_c - 15.0)
    humidity_delta = max(0.0, humidity - 50.0)
    env_addition   = temp_delta * _TEMP_SENSITIVITY + humidity_delta * _HUMIDITY_SENSITIVITY

    intensity_label = _classify_intensity(intensity_factor)
    intensity_mult  = _INTENSITY_MULTIPLIER[intensity_label]
    adapt_mult      = _HEAT_ADAPT_REDUCTION.get(heat_adaptation_level or "low", 1.00)

    if user_calibrated_ml_h and user_calibrated_ml_h > 0:
        # Anchor on measured physiology, scale by environment only
        base   = user_calibrated_ml_h
        rate   = (base + env_addition) * adapt_mult
        quality = "high"
    else:
        base   = _BASE_SWEAT_RATE_ML_H
        rate   = (base + env_addition) * intensity_mult * adapt_mult
        quality = _analysis_quality(temp_c, humidity_pct, duration_h)

    rate = max(200.0, min(3000.0, rate))   # physiological bounds
    return round(rate, 1), quality


def calculate_hydration_deficit(
    sweat_total_ml: float,
    intake_ml: Optional[int],
    weight_kg: Optional[float],
) -> tuple[Optional[float], Optional[float]]:
    """Return (deficit_ml, deficit_body_pct).

    deficit_ml      = sweat_loss - intake (positive = under-hydrated)
    deficit_body_pct = deficit / (weight_kg * 1000) * 100
    """
    if intake_ml is None:
        return None, None

    deficit_ml = max(0.0, sweat_total_ml - intake_ml)

    if weight_kg and weight_kg > 0:
        deficit_body_pct = round(deficit_ml / (weight_kg * 1000) * 100, 2)
    else:
        deficit_body_pct = None

    return round(deficit_ml, 0), deficit_body_pct


def classify_risk_level(
    deficit_body_pct: Optional[float],
    temp_c: float,
    humidity_pct: Optional[float],
    duration_h: float,
) -> str:
    """Return "low" | "moderate" | "high" | "critical"."""
    heat_index = _heat_index(temp_c, humidity_pct or 60.0)

    # Deficit-based risk (Cheuvront thresholds)
    if deficit_body_pct is not None:
        if deficit_body_pct >= 4.0:
            return "critical"
        if deficit_body_pct >= 2.0:
            return "high"
        if deficit_body_pct >= 1.0:
            return "moderate"

    # Environmental risk even if deficit unknown
    if heat_index >= 41 or temp_c >= 38:
        return "high" if duration_h >= 1.0 else "moderate"
    if heat_index >= 32 or temp_c >= 30:
        return "moderate"

    return "low"


def estimate_hr_effects(
    deficit_body_pct: Optional[float],
    temp_c: float,
    humidity_pct: Optional[float],
    duration_h: float,
) -> tuple[float, Optional[float], Optional[float]]:
    """Return (hr_drift_heat_bpm, hr_drift_dehydration_bpm, performance_loss_pct).

    Heat cardiac drift: ~3 bpm at 30°C rising linearly to ~8 bpm at 40°C.
    Dehydration drift: ~1 bpm per 1% body-weight deficit (Coyle & Gonzalez-Alonso 2001).
    Performance loss: ~2% per 1% body-weight deficit above 1% threshold (Cheuvront 2001).
    """
    heat_index = _heat_index(temp_c, humidity_pct or 60.0)

    # Heat contribution — rises with time in heat (cardiovascular drift)
    heat_factor  = max(0.0, (heat_index - 20.0) / 20.0)   # 0 at 20°C HI, 1 at 40°C HI
    hr_drift_heat = round(heat_factor * 8.0 * min(1.0, duration_h / 2.0), 1)

    if deficit_body_pct is not None and deficit_body_pct > 0:
        hr_drift_dehydration   = round(deficit_body_pct * 1.0, 1)
        performance_loss_pct   = round(max(0.0, deficit_body_pct - 1.0) * 2.0, 1)
    else:
        hr_drift_dehydration   = None
        performance_loss_pct   = None

    return hr_drift_heat, hr_drift_dehydration, performance_loss_pct


def generate_hydration_recommendations(
    sweat_rate_ml_h:   float,
    total_sweat_ml:    float,
    intake_ml:         Optional[int],
    deficit_ml:        Optional[float],
    deficit_body_pct:  Optional[float],
    risk_level:        str,
    temp_c:            float,
    humidity_pct:      Optional[float],
    duration_h:        float,
    weight_kg:         Optional[float],
    heat_adaptation:   Optional[str],
    has_calibrated_rate: bool,
) -> list[str]:
    """Return an ordered list of actionable recommendation strings."""
    recs: list[str] = []

    # --- Intake target ---
    target_ml_h = round(sweat_rate_ml_h * 0.75)   # GI absorption ceiling ~75% of sweat rate
    target_ml_h = max(400, min(1200, target_ml_h))
    recs.append(
        f"Target intake: ~{target_ml_h} ml/h ({round(target_ml_h / 60 * 15)} ml every 15 min) "
        f"to replace ~75% of estimated sweat loss."
    )

    # --- Pre-ride hydration ---
    if temp_c >= 25 or (humidity_pct or 0) >= 70:
        recs.append(
            "Pre-ride: drink 500-600 ml of water 2 hours before, then 150-250 ml 15 min before start."
        )
    else:
        recs.append("Pre-ride: drink 400-500 ml 1-2 hours before the ride.")

    # --- During-ride cadence ---
    if sweat_rate_ml_h >= 1200:
        recs.append(
            f"High sweat rate ({round(sweat_rate_ml_h)} ml/h): use a large-volume bidon (750 ml+) "
            "and set a reminder every 10-12 min to drink."
        )
    elif sweat_rate_ml_h >= 800:
        recs.append("Drink proactively every 15-20 min — do not wait for thirst.")
    else:
        recs.append("Drink when thirsty; aim for a consistent small sip every 20-25 min.")

    # --- Electrolytes ---
    if duration_h >= 1.5 or sweat_rate_ml_h >= 1000 or temp_c >= 28:
        recs.append(
            "Add electrolytes (sodium 500-700 mg/h) to at least one bottle — plain water causes "
            "dilutional hyponatraemia risk on long/hot rides."
        )

    # --- Post-ride recovery ---
    if intake_ml is not None and deficit_ml is not None and deficit_ml > 0:
        recovery_ml = round(deficit_ml * 1.5)   # 150% replacement for net fluid balance
        recs.append(
            f"Post-ride: replace the ~{round(deficit_ml)} ml deficit — drink ~{recovery_ml} ml "
            "over the next 2-4 hours (include sodium to retain fluid)."
        )
    else:
        recs.append(
            f"Post-ride: drink ~{round(total_sweat_ml * 1.5)} ml over the next 2-4 hours "
            "to restore fluid balance."
        )

    # --- Risk-specific advice ---
    if risk_level == "critical":
        recs.append(
            "CRITICAL dehydration risk: consider shortening or rescheduling this ride type "
            "until you can hydrate adequately throughout."
        )
    elif risk_level == "high":
        recs.append(
            "High dehydration risk: carry more fluid capacity (camelbak or extra bidons) "
            "and plan resupply points on routes > 60 km."
        )

    # --- Heat adaptation ---
    if temp_c >= 25 and (heat_adaptation or "low") == "low":
        recs.append(
            "You have low heat adaptation. Build heat tolerance with 3-5 rides/week in warm "
            "conditions for 10-14 days — reduces cardiovascular strain by ~20-30%."
        )

    # --- Sweat test suggestion ---
    if not has_calibrated_rate:
        recs.append(
            "For personalised targets, run a sweat test: weigh yourself (dry) before and after "
            "a 1-hour effort and record your fluid intake. Enter results in Settings → Sweat Test."
        )

    return recs


def update_heat_adaptation(current_rides: int, is_hot_ride: bool, temp_c: float) -> tuple[int, str]:
    """Return (updated_heat_rides_last_14d, heat_adaptation_level).

    Called after each upload. Increment counter if the ride was 'hot' (≥ 27°C).
    Adaptation levels: low (< 3 rides), moderate (3-7), high (≥ 8).
    The counter represents the last 14-day window; callers should reset it
    periodically (e.g. via a scheduled task) — here we only increment.
    """
    hot = is_hot_ride or temp_c >= 27.0
    updated = current_rides + (1 if hot else 0)
    updated = min(updated, 99)   # cap to avoid unbounded growth

    if updated >= 8:
        level = "high"
    elif updated >= 3:
        level = "moderate"
    else:
        level = "low"

    return updated, level


def build_analysis(
    temp_c: float,
    humidity_pct: Optional[float],
    wind_speed_kmh: Optional[float],
    max_temp_c: Optional[float],
    duration_h: float,
    intensity_factor: float,
    intake_ml: Optional[int],
    weight_kg: Optional[float],
    user_calibrated_ml_h: Optional[float],
    heat_adaptation: Optional[str],
) -> dict:
    """Convenience wrapper that assembles a full HydrationAnalysis dict."""
    sweat_rate, quality = estimate_sweat_rate(
        temp_c, humidity_pct, intensity_factor, duration_h,
        heat_adaptation, user_calibrated_ml_h,
    )
    total_sweat = round(sweat_rate * duration_h)
    deficit_ml, deficit_pct = calculate_hydration_deficit(total_sweat, intake_ml, weight_kg)
    risk = classify_risk_level(deficit_pct, temp_c, humidity_pct, duration_h)
    hr_heat, hr_dehyd, perf_loss = estimate_hr_effects(deficit_pct, temp_c, humidity_pct, duration_h)

    recs = generate_hydration_recommendations(
        sweat_rate_ml_h=sweat_rate,
        total_sweat_ml=total_sweat,
        intake_ml=intake_ml,
        deficit_ml=deficit_ml,
        deficit_body_pct=deficit_pct,
        risk_level=risk,
        temp_c=temp_c,
        humidity_pct=humidity_pct,
        duration_h=duration_h,
        weight_kg=weight_kg,
        heat_adaptation=heat_adaptation,
        has_calibrated_rate=bool(user_calibrated_ml_h),
    )

    return {
        "avg_temperature_c":                   round(temp_c, 1),
        "max_temperature_c":                   round(max_temp_c, 1) if max_temp_c is not None else None,
        "humidity_pct":                         round(humidity_pct, 1) if humidity_pct is not None else None,
        "wind_speed_kmh":                       round(wind_speed_kmh, 1) if wind_speed_kmh is not None else None,
        "estimated_sweat_rate_ml_h":           sweat_rate,
        "estimated_total_sweat_ml":            total_sweat,
        "reported_intake_ml":                   intake_ml,
        "deficit_ml":                           deficit_ml,
        "deficit_body_pct":                     deficit_pct,
        "estimated_hr_drift_heat_bpm":         hr_heat,
        "estimated_hr_drift_dehydration_bpm":  hr_dehyd,
        "estimated_performance_loss_pct":       perf_loss,
        "risk_level":                           risk,
        "analysis_quality":                     quality,
        "recommendations_json":                 json.dumps(recs),
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _classify_intensity(intensity_factor: float) -> str:
    """Map normalised IF (0-1) to a label."""
    if intensity_factor >= 0.90:
        return "very_high"
    if intensity_factor >= 0.75:
        return "high"
    if intensity_factor >= 0.55:
        return "moderate"
    return "low"


def _heat_index(temp_c: float, humidity_pct: float) -> float:
    """Simplified Rothfusz heat index in °C (valid for temp > 27°C)."""
    if temp_c < 27:
        return temp_c
    T = temp_c
    R = humidity_pct
    hi = (
        -8.78469475556
        + 1.61139411    * T
        + 2.33854883889 * R
        - 0.14611605    * T * R
        - 0.012308094   * T * T
        - 0.0164248277778 * R * R
        + 0.002211732   * T * T * R
        + 0.00072546    * T * R * R
        - 0.000003582   * T * T * R * R
    )
    return round(hi, 1)


def _analysis_quality(temp_c: float, humidity_pct: Optional[float], duration_h: float) -> str:
    """Rate confidence of the sweat-rate estimate."""
    score = 0
    if humidity_pct is not None:
        score += 1
    if duration_h >= 0.5:
        score += 1
    if temp_c > 0:   # we have a real temperature reading
        score += 1
    if score >= 3:
        return "high"
    if score == 2:
        return "medium"
    return "low"
