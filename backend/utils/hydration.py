"""
Hydration & Heat Strain estimation utilities.

Science basis:
  - Sweat rate: weight-relative model (mL/kg/h) from Cheuvront & Haymes (2001) and
    Sawka et al. ACSM Position Stand (2007). Base rates 6–21 mL/kg/h by intensity,
    +0.30 mL/kg/h per °C above 20°C reference.
  - Humidity: above 60% RH the body sweats more to compensate for reduced evaporative
    cooling efficiency; each % adds ~0.8% secretion rate.
  - Wind cooling: self-generated cycling airflow (~20 km/h) + ambient wind reduces
    effective temperature by up to 7°C (Steadman model adapted for cycling).
  - Calibrated path: personal rate anchors the estimate; only the delta above assumed
    test conditions (20°C / 55% RH) is added with a halved sensitivity coefficient
    to avoid double-counting the temperature already captured in the measurement.
  - Dehydration HR drift: 3.0–4.5 bpm per 1% body-mass loss, temperature-dependent.
    Source: Montain & Coyle (1992) J Appl Physiol 73:1340–1350.
  - Performance loss: ~2% per 1% deficit above the 2% BML threshold in heat; 1%/% in
    temperate conditions. Source: ACSM (2007); Goulet meta-analysis (2012).
  - Heat cardiac drift: ~0.5 bpm per °C above 20°C, saturating around 90 min.
    Source: Gonzalez-Alonso et al. (2001) J Physiol 536:927–934; Sawka (1992).
  - Heat adaptation sweat increase: 10–20%. Source: Périard et al. (2015) Exp Physiol.
  - Indoor vs outdoor: 10–20% more sweat indoors due to absent convective airflow.
    Sources: Mieras (2014); TrainingPeaks / Nix Biosensors (2024).
"""

from __future__ import annotations
import json
import math
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Population reference body weight when user weight is unknown
_POPULATION_WEIGHT_KG = 70.0

# Base sweat rate by intensity at 20°C, outdoor, ~55% RH (mL/kg/h)
# Source: Cheuvront & Haymes (2001); Sawka et al. ACSM (2007)
_INTENSITY_BASE_ML_KG_H = {
    "low":       6.0,    # easy / recovery (Z1–Z2)
    "moderate":  10.0,   # endurance (Z2–Z3); ~700 mL/h for a 70 kg rider
    "high":      16.0,   # threshold (Z4)
    "very_high": 21.0,   # VO2max / race pace (Z5+)
}

# Temperature sensitivity above 20°C reference (population model)
# Literature: +1–2 mL/kg/h per 5°C → 0.30 mL/kg/h per °C
_TEMP_ML_KG_H_PER_C = 0.30

# Humidity: above 60% RH body sweats more to compensate for reduced evaporation
# Each % RH above 60% adds ~0.8% to secretion rate, capped at +20%
_HUM_REF_PCT         = 60.0
_HUM_RATE_COEFF      = 0.008        # fractional increase per % RH above reference
_HUM_RATE_MAX_FACTOR = 1.20         # maximum humidity boost factor

# Calibrated path adjustments (above assumed test conditions: 20°C / 55% RH)
# Smaller sensitivity coefficients because the calibrated rate already captures
# the user's baseline humidity and temperature response at test conditions.
_CAL_REF_TEMP_C          = 20.0
_CAL_REF_HUM_PCT         = 55.0
_CAL_TEMP_ML_KG_H_PER_C  = 0.15    # half of population sensitivity
_CAL_HUM_RATE_COEFF       = 0.004   # fraction per % RH above 55%

# Heat adaptation — Périard et al. (2015); literature range 10–20%
_HEAT_ADAPT_MULT = {
    "low":       1.00,
    "moderate":  1.08,
    "high":      1.18,   # raised from 1.15; literature supports up to 1.20
}

# Wind cooling for outdoor cycling (Steadman-derived, adapted for cycling speeds)
# Self-generated airflow ~20 km/h + ambient wind; 0.15 °C per km/h of total airflow
_CYCLING_SELF_AIRFLOW_KMH = 20.0
_WIND_COOLING_FACTOR      = 0.15
_WIND_COOLING_MAX_C       = 7.0    # physiological cap on cooling benefit

# Indoor: no convective cooling → ~10–20% more sweating (mid-range 1.15)
# Mieras (2014); TrainingPeaks / Nix Biosensors (2024)
_INDOOR_SWEAT_MULTIPLIER = 1.15


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_sweat_rate(
    temp_c: float,
    humidity_pct: Optional[float],
    intensity_factor: float,
    duration_h: float,
    heat_adaptation_level: Optional[str] = None,
    user_calibrated_ml_h: Optional[float] = None,
    wind_speed_kmh: Optional[float] = None,
    is_indoor: bool = False,
    weight_kg: Optional[float] = None,
) -> tuple[float, str, float, str]:
    """Return (sweat_rate_ml_h, quality, effective_temp_c, model_method).

    Population path:
        rate = weight_kg × (intensity_base + temp_delta × 0.30) × hum_factor × adapt_mult

    Calibrated path:
        rate = (calibrated_ml_h + temp_delta × 0.15 × weight_kg) × hum_factor × adapt_mult

    Both paths apply wind cooling to effective_temp before computing environmental
    additions. Indoor rides skip wind cooling and add the no-airflow multiplier.
    """
    if duration_h <= 0:
        return 0.0, "low", temp_c, "population"

    humidity    = humidity_pct if humidity_pct is not None else 55.0
    body_weight = weight_kg if (weight_kg and weight_kg > 30) else _POPULATION_WEIGHT_KG

    # ── Wind cooling (outdoor only) ──────────────────────────────────────────
    if is_indoor:
        effective_temp = temp_c
    else:
        total_airflow  = _CYCLING_SELF_AIRFLOW_KMH + (wind_speed_kmh or 0.0)
        wind_cooling   = min(total_airflow * _WIND_COOLING_FACTOR, _WIND_COOLING_MAX_C)
        effective_temp = max(temp_c - wind_cooling, min(temp_c, 15.0))

    intensity_label = _classify_intensity(intensity_factor)
    adapt_mult = _HEAT_ADAPT_MULT.get(heat_adaptation_level or "low", 1.00)

    if user_calibrated_ml_h and user_calibrated_ml_h > 0:
        # ── Calibrated path ──────────────────────────────────────────────────
        # Personal measurement is the anchor at ~20°C / 55% RH test conditions.
        # Add only the delta for warmer / more humid conditions than the assumed test.
        temp_delta    = max(0.0, effective_temp - _CAL_REF_TEMP_C)
        temp_addition = temp_delta * _CAL_TEMP_ML_KG_H_PER_C * body_weight
        hum_factor    = 1.0 + min(
            max(0.0, humidity - _CAL_REF_HUM_PCT) * _CAL_HUM_RATE_COEFF,
            0.12,  # cap calibrated-path humidity boost at +12%
        )
        rate   = (user_calibrated_ml_h + temp_addition) * hum_factor * adapt_mult
        if is_indoor:
            rate *= _INDOOR_SWEAT_MULTIPLIER
        quality = "high"
        method  = "calibrated"
    else:
        # ── Population path ──────────────────────────────────────────────────
        base_ml_kg_h     = _INTENSITY_BASE_ML_KG_H[intensity_label]
        temp_add_ml_kg_h = max(0.0, effective_temp - 20.0) * _TEMP_ML_KG_H_PER_C
        base_rate        = (base_ml_kg_h + temp_add_ml_kg_h) * body_weight

        # High humidity → body sweats more to compensate for poor evaporative cooling
        hum_factor = 1.0 + min(
            max(0.0, humidity - _HUM_REF_PCT) * _HUM_RATE_COEFF,
            _HUM_RATE_MAX_FACTOR - 1.0,
        )
        rate   = base_rate * hum_factor * adapt_mult
        if is_indoor:
            rate *= _INDOOR_SWEAT_MULTIPLIER
        quality = _analysis_quality(temp_c, humidity_pct, duration_h)
        method  = "population"

    rate = max(150.0, min(2500.0, rate))
    return round(rate, 1), quality, round(effective_temp, 1), method


def estimate_uncalibrated_rate(
    temp_c: float,
    humidity_pct: Optional[float],
    intensity_factor: float,
    duration_h: float,
    heat_adaptation_level: Optional[str] = None,
    wind_speed_kmh: Optional[float] = None,
    is_indoor: bool = False,
    weight_kg: Optional[float] = None,
) -> float:
    """Population-model sweat rate without personal calibration (comparison reference)."""
    rate, _, _, _ = estimate_sweat_rate(
        temp_c, humidity_pct, intensity_factor, duration_h,
        heat_adaptation_level, None, wind_speed_kmh, is_indoor,
        weight_kg=weight_kg,
    )
    return rate


def calculate_hydration_deficit(
    sweat_total_ml: float,
    intake_ml: Optional[int],
    weight_kg: Optional[float],
) -> tuple[Optional[float], Optional[float]]:
    """Return (deficit_ml, deficit_body_pct).

    deficit_ml       = sweat_loss − intake (positive = under-hydrated)
    deficit_body_pct = deficit / (weight_kg × 1000) × 100
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
    effective_temp_c: float,
    humidity_pct: Optional[float],
    duration_h: float,
) -> str:
    """Return "low" | "moderate" | "high" | "critical"."""
    heat_index = _heat_index(effective_temp_c, humidity_pct or 55.0)

    if deficit_body_pct is not None:
        if deficit_body_pct >= 4.0:
            return "critical"
        if deficit_body_pct >= 2.0:
            return "high"
        if deficit_body_pct >= 1.0:
            return "moderate"

    if heat_index >= 41 or effective_temp_c >= 38:
        return "high" if duration_h >= 1.0 else "moderate"
    if heat_index >= 32 or effective_temp_c >= 30:
        return "moderate"

    return "low"


def estimate_hr_effects(
    deficit_body_pct: Optional[float],
    effective_temp_c: float,
    humidity_pct: Optional[float],
    duration_h: float,
) -> tuple[float, Optional[float], Optional[float]]:
    """Return (hr_drift_heat_bpm, hr_drift_dehydration_bpm, performance_loss_pct).

    Heat cardiac drift: ~0.5 bpm per °C of heat-index above 20°C, accumulating up
    to ~90 min. Source: Gonzalez-Alonso et al. (2001); Sawka (1992).

    Dehydration HR drift: temperature-dependent.
      ≥ 28°C:  4.5 bpm per 1% BML  (Montain & Coyle 1992, hot protocol)
      < 28°C:  3.0 bpm per 1% BML  (temperate estimate)

    Performance loss: no meaningful impairment below 2% BML (ACSM 2007).
    Above 2%: 2%/% in heat (≥25°C) or 1%/% in temperate (Goulet 2012 meta-analysis).
    """
    heat_index = _heat_index(effective_temp_c, humidity_pct or 55.0)

    # Heat drift: proportional to heat-index above 20°C, scaled by duration (saturates ~90 min)
    duration_factor = min(duration_h / 1.5, 1.5)
    hr_drift_heat   = round(
        max(0.0, heat_index - 20.0) * 0.5 * duration_factor,
        1,
    )
    hr_drift_heat = min(hr_drift_heat, 12.0)  # cap (Gonzalez-Alonso maximum observed ~10–15 bpm)

    if deficit_body_pct is not None and deficit_body_pct > 0:
        # Temperature-dependent dehydration HR drift (Montain & Coyle 1992)
        dehyd_coeff          = 4.5 if effective_temp_c >= 28 else 3.0
        hr_drift_dehydration = round(deficit_body_pct * dehyd_coeff, 1)

        # Performance: no impairment below 2% BML; rate depends on heat
        threshold            = 2.0
        loss_rate            = 2.0 if effective_temp_c >= 25 else 1.0
        performance_loss_pct = round(max(0.0, deficit_body_pct - threshold) * loss_rate, 1)
    else:
        hr_drift_dehydration = None
        performance_loss_pct = None

    return hr_drift_heat, hr_drift_dehydration, performance_loss_pct


def generate_hydration_recommendations(
    sweat_rate_ml_h:   float,
    total_sweat_ml:    float,
    intake_ml:         Optional[int],
    deficit_ml:        Optional[float],
    deficit_body_pct:  Optional[float],
    risk_level:        str,
    temp_c:            float,
    effective_temp_c:  float,
    humidity_pct:      Optional[float],
    duration_h:        float,
    weight_kg:         Optional[float],
    heat_adaptation:   Optional[str],
    has_calibrated_rate: bool,
    model_method:      str,
) -> list[str]:
    """Return an ordered list of actionable recommendation strings."""
    recs: list[str] = []

    target_ml_h = round(sweat_rate_ml_h * 0.75)
    target_ml_h = max(400, min(1200, target_ml_h))
    recs.append(
        f"Target intake: ~{target_ml_h} ml/h ({round(target_ml_h / 60 * 15)} ml every 15 min) "
        f"to replace ~75% of estimated sweat loss."
    )

    if temp_c >= 25 or (humidity_pct or 0) >= 70:
        recs.append(
            "Pre-ride: drink 500–600 ml of water 2 hours before, then 150–250 ml 15 min before start."
        )
    else:
        recs.append("Pre-ride: drink 400–500 ml 1–2 hours before the ride.")

    if sweat_rate_ml_h >= 1200:
        recs.append(
            f"High sweat rate ({round(sweat_rate_ml_h)} ml/h): use a large-volume bidon (750 ml+) "
            "and set a reminder every 10–12 min to drink."
        )
    elif sweat_rate_ml_h >= 800:
        recs.append("Drink proactively every 15–20 min — do not wait for thirst.")
    else:
        recs.append("Drink when thirsty; aim for a consistent small sip every 20–25 min.")

    if duration_h >= 1.5 or sweat_rate_ml_h >= 1000 or temp_c >= 28:
        recs.append(
            "Add electrolytes (sodium 500–700 mg/h) to at least one bottle — plain water carries "
            "a dilutional hyponatraemia risk on long or hot rides."
        )

    if intake_ml is not None and deficit_ml is not None and deficit_ml > 0:
        recovery_ml = round(deficit_ml * 1.5)
        recs.append(
            f"Post-ride: replace the ~{round(deficit_ml)} ml deficit — drink ~{recovery_ml} ml "
            "over the next 2–4 hours (include sodium to retain fluid)."
        )
    else:
        recs.append(
            f"Post-ride: drink ~{round(total_sweat_ml * 1.5)} ml over the next 2–4 hours "
            "to restore fluid balance."
        )

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

    if temp_c >= 25 and (heat_adaptation or "low") == "low":
        recs.append(
            "You have low heat adaptation. Build heat tolerance with 3–5 rides/week in warm "
            "conditions for 10–14 days — reduces cardiovascular strain by ~20–30%."
        )

    if not has_calibrated_rate:
        recs.append(
            "For personalised targets, run a sweat test: weigh yourself (dry) before and after "
            "a 1-hour effort and record your fluid intake. Enter results in Settings → Sweat Test."
        )
    elif model_method == "calibrated":
        recs.append(
            "Using your personal sweat rate calibration. If this estimate seems off, review your "
            "sweat-test inputs in Settings → Sweat Rate, or reset to use the population model."
        )

    return recs


def update_heat_adaptation(current_rides: int, is_hot_ride: bool, temp_c: float) -> tuple[int, str]:
    """Return (updated_heat_rides_last_14d, heat_adaptation_level).

    Increment counter if the ride was 'hot' (≥ 27°C).
    Levels: low (< 3 rides), moderate (3–7), high (≥ 8).
    """
    hot     = is_hot_ride or temp_c >= 27.0
    updated = min(current_rides + (1 if hot else 0), 99)

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
    is_indoor: bool = False,
) -> dict:
    """Convenience wrapper that assembles a full HydrationAnalysis dict."""
    sweat_rate, quality, effective_temp, method = estimate_sweat_rate(
        temp_c, humidity_pct, intensity_factor, duration_h,
        heat_adaptation, user_calibrated_ml_h, wind_speed_kmh, is_indoor,
        weight_kg=weight_kg,
    )

    # Population reference (shown alongside calibrated to sanity-check calibration)
    uncal_rate = estimate_uncalibrated_rate(
        temp_c, humidity_pct, intensity_factor, duration_h,
        heat_adaptation, wind_speed_kmh, is_indoor,
        weight_kg=weight_kg,
    ) if user_calibrated_ml_h else None

    total_sweat = round(sweat_rate * duration_h)
    deficit_ml, deficit_pct = calculate_hydration_deficit(total_sweat, intake_ml, weight_kg)
    risk = classify_risk_level(deficit_pct, effective_temp, humidity_pct, duration_h)
    hr_heat, hr_dehyd, perf_loss = estimate_hr_effects(
        deficit_pct, effective_temp, humidity_pct, duration_h
    )

    recs = generate_hydration_recommendations(
        sweat_rate_ml_h=sweat_rate,
        total_sweat_ml=total_sweat,
        intake_ml=intake_ml,
        deficit_ml=deficit_ml,
        deficit_body_pct=deficit_pct,
        risk_level=risk,
        temp_c=temp_c,
        effective_temp_c=effective_temp,
        humidity_pct=humidity_pct,
        duration_h=duration_h,
        weight_kg=weight_kg,
        heat_adaptation=heat_adaptation,
        has_calibrated_rate=bool(user_calibrated_ml_h),
        model_method=method,
    )

    wind_cooling_c = round(temp_c - effective_temp, 1)

    return {
        "avg_temperature_c":                   round(temp_c, 1),
        "max_temperature_c":                   round(max_temp_c, 1) if max_temp_c is not None else None,
        "effective_temp_c":                    round(effective_temp, 1),
        "wind_cooling_c":                      wind_cooling_c if wind_cooling_c > 0 else None,
        "humidity_pct":                        round(humidity_pct, 1) if humidity_pct is not None else None,
        "wind_speed_kmh":                      round(wind_speed_kmh, 1) if wind_speed_kmh is not None else None,
        "estimated_sweat_rate_ml_h":           sweat_rate,
        "population_sweat_rate_ml_h":          uncal_rate,
        "model_method":                        method,
        "estimated_total_sweat_ml":            total_sweat,
        "reported_intake_ml":                  intake_ml,
        "deficit_ml":                          deficit_ml,
        "deficit_body_pct":                    deficit_pct,
        "estimated_hr_drift_heat_bpm":         hr_heat,
        "estimated_hr_drift_dehydration_bpm":  hr_dehyd,
        "estimated_performance_loss_pct":      perf_loss,
        "risk_level":                          risk,
        "analysis_quality":                    quality,
        "recommendations_json":                json.dumps(recs),
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _classify_intensity(intensity_factor: float) -> str:
    if intensity_factor >= 0.90:
        return "very_high"
    if intensity_factor >= 0.75:
        return "high"
    if intensity_factor >= 0.55:
        return "moderate"
    return "low"


def _heat_index(temp_c: float, humidity_pct: float) -> float:
    """Rothfusz heat index in °C (valid for temp > 27°C; returns temp below that)."""
    if temp_c < 27:
        return temp_c
    T = temp_c
    R = humidity_pct
    hi = (
        -8.78469475556
        + 1.61139411      * T
        + 2.33854883889   * R
        - 0.14611605      * T * R
        - 0.012308094     * T * T
        - 0.0164248277778 * R * R
        + 0.002211732     * T * T * R
        + 0.00072546      * T * R * R
        - 0.000003582     * T * T * R * R
    )
    return round(hi, 1)


def _analysis_quality(temp_c: float, humidity_pct: Optional[float], duration_h: float) -> str:
    score = 0
    if humidity_pct is not None:
        score += 1
    if duration_h >= 0.5:
        score += 1
    if temp_c > 0:
        score += 1
    if score >= 3:
        return "high"
    if score == 2:
        return "medium"
    return "low"
