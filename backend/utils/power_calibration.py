from utils.power_estimation import _compute_power, AIR_DENSITY_SEA_LEVEL
import math


def calibrate_from_known_ftp(user, climb_detections: list, known_ftp_w: float) -> dict:
    """
    Adjusts CdA so that average estimated power on long climbs matches known FTP.

    Uses bisection to find CdA that produces average power closest to known_ftp_w.
    Returns dict with calibrated_cda and calibration_source.
    """
    long_climbs = [c for c in climb_detections if (c.duration_seconds or 0) >= 1200]
    if not long_climbs:
        long_climbs = [c for c in climb_detections if (c.duration_seconds or 0) >= 300]
    if not long_climbs:
        return {"error": "No climbs long enough for calibration (need ≥5 min)"}

    total_mass = (user.weight_kg or 70) + 9.0
    crr = user.calibrated_crr or 0.005

    def avg_power_with_cda(cda: float) -> float:
        powers = []
        for c in long_climbs:
            if not c.avg_speed_kmh or c.avg_speed_kmh <= 0:
                continue
            air_density = AIR_DENSITY_SEA_LEVEL * math.exp(-(c.elevation_gain_m or 0) / 8500)
            p = _compute_power(
                c.avg_gradient_pct or 0, c.avg_speed_kmh, total_mass,
                air_density, cda, crr, 0.03
            )
            powers.append(p)
        return sum(powers) / len(powers) if powers else 0

    # Bisection: find CdA so avg power ≈ known_ftp_w
    lo, hi = 0.15, 0.80
    for _ in range(30):
        mid = (lo + hi) / 2
        p_mid = avg_power_with_cda(mid)
        if abs(p_mid - known_ftp_w) < 2.0:
            break
        if p_mid < known_ftp_w:
            hi = mid
        else:
            lo = mid

    calibrated_cda = round((lo + hi) / 2, 4)
    return {
        "calibrated_cda": calibrated_cda,
        "calibration_source": "manual_ftp",
    }


def calibrate_from_known_climb(user, climb, known_power_w: float) -> dict:
    """
    Adjusts CdA proportionally so that estimated power matches known_power_w for one climb.
    """
    if not user.weight_kg or not climb.avg_speed_kmh or climb.avg_speed_kmh <= 0:
        return {"error": "Insufficient data for calibration"}

    total_mass = (user.weight_kg or 70) + 9.0
    current_cda = user.calibrated_cda or 0.35
    crr = user.calibrated_crr or 0.005
    air_density = AIR_DENSITY_SEA_LEVEL * math.exp(-(climb.elevation_gain_m or 0) / 8500)

    estimated = _compute_power(
        climb.avg_gradient_pct or 0, climb.avg_speed_kmh, total_mass,
        air_density, current_cda, crr, 0.03
    )

    if estimated <= 0:
        return {"error": "Cannot calibrate: estimated power is zero"}

    ratio = known_power_w / estimated
    # Adjust CdA: higher estimated means too low CdA (less drag → lower power)
    new_cda = round(current_cda / ratio, 4)
    new_cda = max(0.15, min(0.80, new_cda))

    return {
        "calibrated_cda": new_cda,
        "calibration_source": "known_climb",
    }
