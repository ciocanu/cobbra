import math

G = 9.80665
AIR_DENSITY_SEA_LEVEL = 1.225

BIKE_DEFAULTS = {
    "road": {
        "bike_weight_kg": 8.5,
        "crr": 0.005,
        "cda": 0.35,
    },
    "gravel": {
        "bike_weight_kg": 10.0,
        "crr": 0.007,
        "cda": 0.38,
    },
    "mtb": {
        "bike_weight_kg": 13.0,
        "crr": 0.012,
        "cda": 0.45,
    },
    "tt": {
        "bike_weight_kg": 8.0,
        "crr": 0.004,
        "cda": 0.25,
    },
    "ebike": {
        "bike_weight_kg": 22.0,
        "crr": 0.006,
        "cda": 0.40,
    },
    None: {
        "bike_weight_kg": 9.0,
        "crr": 0.005,
        "cda": 0.35,
    },
}


def _compute_power(gradient_pct: float, speed_kmh: float, total_mass: float,
                   air_density: float, cda: float, crr: float,
                   drivetrain_loss: float) -> float:
    if speed_kmh <= 0:
        return 0.0
    gradient_decimal = gradient_pct / 100
    slope_angle = math.atan(gradient_decimal)
    velocity_ms = speed_kmh / 3.6

    p_gravity = total_mass * G * math.sin(slope_angle) * velocity_ms
    p_rolling = crr * total_mass * G * math.cos(slope_angle) * velocity_ms
    p_aero = 0.5 * air_density * cda * (velocity_ms ** 3)

    p_total = (p_gravity + p_rolling + p_aero) / (1 - drivetrain_loss)
    return max(0.0, p_total)


def estimate_climbing_power(
    climb: dict,
    user_weight_kg: float,
    bike_weight_kg: float = 9.0,
    crr: float = 0.005,
    cda: float = 0.35,
    drivetrain_loss: float = 0.03,
    altitude_m: float = None,
) -> dict:
    """
    Physics-based climbing power estimator.

    P_total = (P_gravity + P_rolling + P_aero) / (1 - drivetrain_loss)

    Only reliable on sustained climbs (gradient >4%, duration >3 min).
    Returns power in watts plus confidence interval and quality rating.
    """
    total_mass = user_weight_kg + bike_weight_kg

    if altitude_m and altitude_m > 0:
        air_density = AIR_DENSITY_SEA_LEVEL * math.exp(-altitude_m / 8500)
    else:
        air_density = AIR_DENSITY_SEA_LEVEL

    gradient_pct = climb.get("avg_gradient_pct", 0)
    speed_kmh = climb.get("avg_speed_kmh") or 0

    if speed_kmh <= 0:
        return {
            "estimated_power_w": None,
            "estimated_power_low_w": None,
            "estimated_power_high_w": None,
            "estimated_wkg": None,
            "estimation_quality": "low",
            "estimation_method": "physics",
        }

    p_nominal = _compute_power(gradient_pct, speed_kmh, total_mass, air_density, cda, crr, drivetrain_loss)
    p_low = _compute_power(gradient_pct, speed_kmh, total_mass, air_density, cda * 0.8, crr * 0.85, drivetrain_loss)
    p_high = _compute_power(gradient_pct, speed_kmh, total_mass, air_density, cda * 1.2, crr * 1.15, drivetrain_loss)

    gradient_decimal = gradient_pct / 100
    slope_angle = math.atan(gradient_decimal)
    velocity_ms = speed_kmh / 3.6
    p_gravity = total_mass * G * math.sin(slope_angle) * velocity_ms
    p_rolling = crr * total_mass * G * math.cos(slope_angle) * velocity_ms
    p_aero = 0.5 * air_density * cda * (velocity_ms ** 3)
    p_total_raw = (p_gravity + p_rolling + p_aero) / (1 - drivetrain_loss)

    wkg = p_nominal / user_weight_kg
    quality = determine_estimation_quality(climb)

    return {
        "estimated_power_w": round(p_nominal, 1),
        "estimated_power_low_w": round(p_low, 1),
        "estimated_power_high_w": round(p_high, 1),
        "estimated_wkg": round(wkg, 2),
        "estimation_quality": quality,
        "estimation_method": "physics",
        "components": {
            "p_gravity_w": round(p_gravity, 1),
            "p_rolling_w": round(p_rolling, 1),
            "p_aero_w": round(p_aero, 1),
            "p_gravity_pct": round(p_gravity / p_total_raw * 100, 1) if p_total_raw > 0 else 0,
            "p_rolling_pct": round(p_rolling / p_total_raw * 100, 1) if p_total_raw > 0 else 0,
            "p_aero_pct": round(p_aero / p_total_raw * 100, 1) if p_total_raw > 0 else 0,
        },
        "params_used": {
            "total_mass_kg": total_mass,
            "crr": crr,
            "cda": cda,
            "air_density": round(air_density, 4),
        },
    }


def determine_estimation_quality(climb: dict) -> str:
    """
    Scores estimation quality based on gradient, duration, and VAM.

    "high":   gradient 6-10%, duration >10 min, VAM 600-2000 m/h
    "medium": gradient 4-6% or 10-12%, duration 5-10 min
    "low":    borderline conditions
    """
    score = 0

    g = climb.get("avg_gradient_pct", 0)
    if 6 <= g <= 10:
        score += 3
    elif 4 <= g <= 12:
        score += 2
    else:
        score += 1

    d = climb.get("duration_seconds", 0)
    if d >= 600:
        score += 3
    elif d >= 300:
        score += 2
    else:
        score += 1

    vam = climb.get("vam_m_per_hour", 0) or 0
    if 600 <= vam <= 2000:
        score += 2
    else:
        score += 1

    if score >= 7:
        return "high"
    elif score >= 5:
        return "medium"
    return "low"
