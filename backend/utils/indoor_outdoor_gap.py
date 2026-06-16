"""
Indoor/Outdoor Gap calculation and correction.

Science basis:
  Jobson et al. (2012) "The relationship between laboratory and field measures."
  Ouvrard et al. (2018) "Thermoregulation and power output differences indoors vs outdoors."
  Practical range: indoor FTP 5-15% lower, HR 5-10 bpm higher for same RPE.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from typing import Optional, Any


# ── Constants ──────────────────────────────────────────────────────────────────

_MIN_DURATION_S   = 1800     # 30 min
_Z3_HR_LOW_FRAC   = 0.70     # Z3 starts at 70% HRmax
_Z3_HR_HIGH_FRAC  = 0.85     # Z3 ends at 85% HRmax
_MIN_Z3_POINTS    = 60       # need ≥60 s worth of Z3 data per ride
_LOOKBACK_DAYS    = 90
_MIN_RIDES_HIGH   = 10       # rides per side for "high" confidence
_MIN_RIDES_MEDIUM = 5
_MIN_RIDES_LOW    = 3


# ── Power gap calculation ─────────────────────────────────────────────────────

def calculate_power_gap(user_id: int, db: Any,
                        min_rides_each: int = _MIN_RIDES_LOW,
                        lookback_days: int = _LOOKBACK_DAYS) -> dict:
    """Calculate the personal indoor/outdoor power and HR gap for a user.

    Returns a dict with power_gap_pct, hr_gap_bpm, confidence, and interpretation.
    """
    from models import Activity, TrackPoint

    cutoff = datetime.utcnow() - timedelta(days=lookback_days)

    activities = (
        db.query(Activity)
        .filter(
            Activity.user_id == user_id,
            Activity.date >= cutoff,
            Activity.duration_seconds >= _MIN_DURATION_S,
            Activity.ride_environment.in_(["indoor", "outdoor"]),
        )
        .order_by(Activity.date)
        .all()
    )

    indoor_acts  = [a for a in activities if a.ride_environment == "indoor"]
    outdoor_acts = [a for a in activities if a.ride_environment == "outdoor"]

    if len(indoor_acts) < _MIN_RIDES_LOW or len(outdoor_acts) < _MIN_RIDES_LOW:
        return {
            "power_gap_pct":        None,
            "hr_gap_bpm":           None,
            "confidence":           "insufficient_data",
            "indoor_rides_used":    len(indoor_acts),
            "outdoor_rides_used":   len(outdoor_acts),
            "indoor_avg_wkg_z3":    None,
            "outdoor_avg_wkg_z3":   None,
            "indoor_avg_hr_z3":     None,
            "outdoor_avg_hr_z3":    None,
            "interpretation":       f"Need at least {_MIN_RIDES_LOW} rides in each environment. "
                                    f"Currently: {len(indoor_acts)} indoor, {len(outdoor_acts)} outdoor.",
            "recommendation":       "Upload more rides to enable automatic gap calculation.",
        }

    indoor_metrics  = [_z3_metrics(a, db) for a in indoor_acts]
    outdoor_metrics = [_z3_metrics(a, db) for a in outdoor_acts]

    indoor_valid  = [m for m in indoor_metrics  if m is not None]
    outdoor_valid = [m for m in outdoor_metrics if m is not None]

    if len(indoor_valid) < _MIN_RIDES_LOW or len(outdoor_valid) < _MIN_RIDES_LOW:
        return {
            "power_gap_pct":      None,
            "hr_gap_bpm":         None,
            "confidence":         "insufficient_data",
            "indoor_rides_used":  len(indoor_valid),
            "outdoor_rides_used": len(outdoor_valid),
            "indoor_avg_wkg_z3":  None,
            "outdoor_avg_wkg_z3": None,
            "indoor_avg_hr_z3":   None,
            "outdoor_avg_hr_z3":  None,
            "interpretation":     "Not enough rides with usable Z3 HR+power data.",
            "recommendation":     "Ensure rides have heart rate data for accurate gap calculation.",
        }

    def safe_avg(lst, key):
        vals = [v[key] for v in lst if v.get(key) is not None]
        return sum(vals) / len(vals) if vals else None

    in_wkg  = safe_avg(indoor_valid,  "wkg_z3")
    out_wkg = safe_avg(outdoor_valid, "wkg_z3")
    in_hr   = safe_avg(indoor_valid,  "hr_z3")
    out_hr  = safe_avg(outdoor_valid, "hr_z3")

    power_gap = None
    if in_wkg and out_wkg and out_wkg > 0:
        power_gap = round((in_wkg - out_wkg) / out_wkg * 100, 1)

    hr_gap = round(in_hr - out_hr, 1) if (in_hr and out_hr) else None

    # Confidence
    n_in  = len(indoor_valid)
    n_out = len(outdoor_valid)
    has_power_both = (
        any(m.get("has_power") for m in indoor_valid) and
        any(m.get("has_power") for m in outdoor_valid)
    )
    if n_in >= _MIN_RIDES_HIGH and n_out >= _MIN_RIDES_HIGH and has_power_both:
        confidence = "high"
    elif n_in >= _MIN_RIDES_MEDIUM and n_out >= _MIN_RIDES_MEDIUM:
        confidence = "medium"
    else:
        confidence = "low"

    interpretation = _build_interpretation(power_gap, hr_gap, confidence)
    recommendation = _build_recommendation(power_gap, hr_gap)

    return {
        "power_gap_pct":        power_gap,
        "hr_gap_bpm":           hr_gap,
        "confidence":           confidence,
        "indoor_rides_used":    n_in,
        "outdoor_rides_used":   n_out,
        "indoor_avg_wkg_z3":    round(in_wkg, 3)  if in_wkg  else None,
        "outdoor_avg_wkg_z3":   round(out_wkg, 3) if out_wkg else None,
        "indoor_avg_hr_z3":     round(in_hr, 1)   if in_hr   else None,
        "outdoor_avg_hr_z3":    round(out_hr, 1)  if out_hr  else None,
        "interpretation":       interpretation,
        "recommendation":       recommendation,
    }


def update_indoor_outdoor_gap(user_id: int, db: Any) -> None:
    """Recompute and persist the IndoorOutdoorProfile for a user.

    Called after each activity upload so the profile stays fresh.
    """
    from models import IndoorOutdoorProfile

    result = calculate_power_gap(user_id, db)

    profile = db.query(IndoorOutdoorProfile).filter(
        IndoorOutdoorProfile.user_id == user_id
    ).first()

    if profile is None:
        profile = IndoorOutdoorProfile(user_id=user_id)
        db.add(profile)

    # Only overwrite calculated fields if new data is better quality
    if result["confidence"] not in ("insufficient_data",):
        profile.power_gap_pct        = result["power_gap_pct"]
        profile.hr_gap_bpm           = result["hr_gap_bpm"]
        profile.power_gap_confidence = result["confidence"]
        profile.indoor_avg_wkg_z3    = result["indoor_avg_wkg_z3"]
        profile.outdoor_avg_wkg_z3   = result["outdoor_avg_wkg_z3"]
        profile.indoor_avg_hr_z3     = result["indoor_avg_hr_z3"]
        profile.outdoor_avg_hr_z3    = result["outdoor_avg_hr_z3"]
        profile.indoor_rides_analyzed  = result["indoor_rides_used"]
        profile.outdoor_rides_analyzed = result["outdoor_rides_used"]
        profile.last_calculated      = datetime.utcnow()
        profile.calculation_json     = json.dumps(result)

    db.commit()


# ── Correction factors ────────────────────────────────────────────────────────

def apply_correction_factors(activity: Any, profile: Any) -> dict:
    """Compute correction factors for an indoor activity.

    Returns dict with power/hr correction factors and corrected TSS.
    Outdoor activities return correction_applied=False.
    """
    if getattr(activity, "ride_environment", None) != "indoor":
        return {
            "power_correction_factor": None,
            "hr_correction_factor":    None,
            "original_tss":            getattr(activity, "tss", None),
            "corrected_tss":           None,
            "correction_applied":      False,
            "correction_source":       None,
        }

    # Pick gap: manual calibration takes precedence
    power_gap = (
        getattr(profile, "manual_power_gap_pct", None)
        if getattr(profile, "manual_power_gap_pct", None) is not None
        else getattr(profile, "power_gap_pct", None)
    )
    hr_gap = getattr(profile, "hr_gap_bpm", None)

    correction_source = (
        "manual_calibration"
        if getattr(profile, "manual_power_gap_pct", None) is not None
        else "calculated_gap"
    )

    power_cf = None
    hr_cf    = None
    corrected_tss = None
    original_tss  = getattr(activity, "tss", None)

    if power_gap is not None:
        # correction_factor > 1 when indoor is lower than outdoor
        power_cf = round(1.0 / (1.0 + power_gap / 100.0), 4) if (1.0 + power_gap / 100.0) > 0 else None

    if hr_gap is not None and hr_gap != 0:
        # HR factor < 1 when indoor HR is higher (we reduce indoor HR to match outdoor)
        avg_hr = getattr(activity, "avg_heart_rate_bpm", None)
        if avg_hr and avg_hr > 0:
            hr_cf = round((avg_hr - hr_gap) / avg_hr, 4)

    # Recalculate TSS with corrected power
    if power_cf is not None and original_tss is not None:
        # TSS ∝ NP² (via IF²), so corrected_TSS = original_TSS × correction_factor²
        corrected_tss = round(original_tss * (power_cf ** 2), 1)
    elif hr_cf is not None and original_tss is not None:
        # Fallback: scale by HR factor
        corrected_tss = round(original_tss * hr_cf, 1)

    return {
        "power_correction_factor": power_cf,
        "hr_correction_factor":    hr_cf,
        "original_tss":            original_tss,
        "corrected_tss":           corrected_tss,
        "correction_applied":      power_cf is not None or hr_cf is not None,
        "correction_source":       correction_source if (power_cf is not None or hr_cf is not None) else None,
    }


# ── Corrected CTL/ATL/TSB ─────────────────────────────────────────────────────

def recalculate_training_load_corrected(user_id: int, db: Any,
                                        days: int = 90) -> dict:
    """Return original and corrected CTL/ATL/TSB side by side."""
    from models import Activity
    from datetime import timedelta

    cutoff = datetime.utcnow() - timedelta(days=days)
    activities = (
        db.query(Activity)
        .filter(Activity.user_id == user_id, Activity.date >= cutoff)
        .order_by(Activity.date)
        .all()
    )

    if not activities:
        return {
            "original":   {"ctl": 0.0, "atl": 0.0, "tsb": 0.0},
            "corrected":  {"ctl": 0.0, "atl": 0.0, "tsb": 0.0},
            "difference": {"ctl_delta": 0.0, "atl_delta": 0.0, "note": "No training data."},
        }

    # Build daily load maps (original and corrected)
    orig_daily: dict[str, float] = {}
    corr_daily: dict[str, float] = {}

    for a in activities:
        day = a.date.date().isoformat()
        orig_tss = a.tss or 0.0
        corr_tss = a.corrected_tss if (a.ride_environment == "indoor" and a.corrected_tss is not None) else orig_tss
        orig_daily[day] = orig_daily.get(day, 0.0) + orig_tss
        corr_daily[day] = corr_daily.get(day, 0.0) + corr_tss

    orig_ctl, orig_atl = _ema_model(orig_daily, activities[0].date, datetime.utcnow())
    corr_ctl, corr_atl = _ema_model(corr_daily, activities[0].date, datetime.utcnow())

    ctl_delta = round(corr_ctl - orig_ctl, 1)
    atl_delta = round(corr_atl - orig_atl, 1)

    if abs(ctl_delta) < 0.5:
        note = "Indoor correction has minimal impact on your training load model."
    elif ctl_delta > 0:
        note = (f"Indoor correction adds ~{ctl_delta} CTL points. "
                f"Your actual fitness is slightly higher than the raw model shows.")
    else:
        note = (f"Indoor correction reduces CTL by ~{abs(ctl_delta)} points. "
                f"Indoor rides may be overestimating training stress.")

    return {
        "original": {
            "ctl": round(orig_ctl, 1),
            "atl": round(orig_atl, 1),
            "tsb": round(orig_ctl - orig_atl, 1),
        },
        "corrected": {
            "ctl": round(corr_ctl, 1),
            "atl": round(corr_atl, 1),
            "tsb": round(corr_ctl - corr_atl, 1),
        },
        "difference": {
            "ctl_delta": ctl_delta,
            "atl_delta": atl_delta,
            "note": note,
        },
    }


# ── Manual calibration ────────────────────────────────────────────────────────

def calibrate_from_ftp_values(user_id: int, indoor_ftp: float,
                               outdoor_ftp: float, db: Any) -> dict:
    """Simple FTP-based calibration. gap = (outdoor - indoor) / outdoor × 100."""
    from models import IndoorOutdoorProfile

    if outdoor_ftp <= 0:
        raise ValueError("outdoor_ftp must be positive")

    power_gap = round((indoor_ftp - outdoor_ftp) / outdoor_ftp * 100, 1)

    profile = db.query(IndoorOutdoorProfile).filter(
        IndoorOutdoorProfile.user_id == user_id
    ).first()
    if profile is None:
        profile = IndoorOutdoorProfile(user_id=user_id)
        db.add(profile)

    profile.manual_power_gap_pct = power_gap
    profile.calibration_date     = datetime.utcnow()
    profile.calibration_method   = "ftp_comparison"
    db.commit()

    return {
        "power_gap_pct":          power_gap,
        "indoor_ftp":             indoor_ftp,
        "outdoor_ftp":            outdoor_ftp,
        "interpretation":         _build_interpretation(power_gap, None, "high"),
        "recommendation":         _build_recommendation(power_gap, None),
    }


def calibrate_from_dual_test(user_id: int, indoor_activity_id: int,
                              outdoor_activity_id: int, db: Any) -> dict:
    """Precise calibration from two matching test activities.

    Finds the best sustained effort (>15 min) in each activity and compares
    average power and HR to calculate the user's personal gap.
    """
    from models import Activity, TrackPoint, IndoorOutdoorProfile

    def get_act(act_id: int) -> Activity:
        a = db.query(Activity).filter(
            Activity.id == act_id, Activity.user_id == user_id
        ).first()
        if not a:
            raise ValueError(f"Activity {act_id} not found")
        return a

    indoor_act  = get_act(indoor_activity_id)
    outdoor_act = get_act(outdoor_activity_id)

    indoor_effort  = _best_sustained_effort(indoor_act,  db, min_minutes=15)
    outdoor_effort = _best_sustained_effort(outdoor_act, db, min_minutes=15)

    if indoor_effort is None or outdoor_effort is None:
        raise ValueError("Could not find ≥15 min sustained effort in one or both activities.")

    in_pwr  = indoor_effort["avg_power"]
    out_pwr = outdoor_effort["avg_power"]
    in_hr   = indoor_effort["avg_hr"]
    out_hr  = outdoor_effort["avg_hr"]

    power_gap = None
    hr_gap    = None
    in_ftp_est = out_ftp_est = None

    if in_pwr and out_pwr and out_pwr > 0:
        power_gap  = round((in_pwr - out_pwr) / out_pwr * 100, 1)
        in_ftp_est  = round(in_pwr  * 0.95, 0)   # 20-min effort → FTP ≈ 95%
        out_ftp_est = round(out_pwr * 0.95, 0)

    if in_hr and out_hr:
        hr_gap = round(in_hr - out_hr, 1)

    profile = db.query(IndoorOutdoorProfile).filter(
        IndoorOutdoorProfile.user_id == user_id
    ).first()
    if profile is None:
        profile = IndoorOutdoorProfile(user_id=user_id)
        db.add(profile)

    profile.manual_power_gap_pct = power_gap
    profile.hr_gap_bpm           = hr_gap
    profile.calibration_date     = datetime.utcnow()
    profile.calibration_method   = "same_route_test"
    db.commit()

    rec = ""
    if in_ftp_est and out_ftp_est:
        rec = f"Use {int(in_ftp_est)}W as your indoor FTP and {int(out_ftp_est)}W outdoor."

    return {
        "power_gap_pct":          power_gap,
        "hr_gap_bpm":             hr_gap,
        "indoor_ftp_estimated":   in_ftp_est,
        "outdoor_ftp_estimated":  out_ftp_est,
        "indoor_effort_minutes":  indoor_effort["duration_min"],
        "outdoor_effort_minutes": outdoor_effort["duration_min"],
        "interpretation":         _build_interpretation(power_gap, hr_gap, "high"),
        "recommendation":         rec or _build_recommendation(power_gap, hr_gap),
    }


# ── Private helpers ────────────────────────────────────────────────────────────

def _z3_metrics(activity: Any, db: Any) -> Optional[dict]:
    """Extract avg Z3 power (W/kg) and HR for one activity from its track points."""
    from models import TrackPoint

    max_hr = getattr(activity, "max_heart_rate_bpm", None)
    weight = getattr(activity, "user", None)
    if not max_hr or max_hr <= 0:
        return None

    # Attempt to get user weight via relationship or direct attr
    try:
        user = db.query(__import__("models").User).filter_by(id=activity.user_id).first()
        weight_kg = getattr(user, "weight_kg", None) if user else None
    except Exception:
        weight_kg = None

    pts = (
        db.query(TrackPoint)
        .filter(TrackPoint.activity_id == activity.id)
        .order_by(TrackPoint.id)
        .all()
    )

    hr_lo = max_hr * _Z3_HR_LOW_FRAC
    hr_hi = max_hr * _Z3_HR_HIGH_FRAC

    z3_pts = [
        p for p in pts
        if p.heart_rate_bpm is not None
        and hr_lo <= p.heart_rate_bpm <= hr_hi
        and p.heart_rate_bpm > 0
    ]

    if len(z3_pts) < _MIN_Z3_POINTS:
        return None

    pwr_pts = [p.power_w for p in z3_pts if (p.power_w or 0) > 20]
    avg_pwr = sum(pwr_pts) / len(pwr_pts) if pwr_pts else None
    avg_hr  = sum(p.heart_rate_bpm for p in z3_pts) / len(z3_pts)

    wkg = round(avg_pwr / weight_kg, 3) if (avg_pwr and weight_kg and weight_kg > 0) else None

    return {
        "wkg_z3":    wkg,
        "hr_z3":     round(avg_hr, 1),
        "has_power": avg_pwr is not None,
        "n_pts":     len(z3_pts),
    }


def _best_sustained_effort(activity: Any, db: Any,
                            min_minutes: int = 15) -> Optional[dict]:
    """Find the window with the highest average power lasting ≥ min_minutes."""
    from models import TrackPoint

    pts = (
        db.query(TrackPoint)
        .filter(TrackPoint.activity_id == activity.id)
        .order_by(TrackPoint.id)
        .all()
    )

    if len(pts) < min_minutes * 30:  # rough check (~2 s/pt)
        return None

    min_pts = min_minutes * 30   # approximate points for window
    best_pwr = 0.0
    best_slice = None

    for i in range(len(pts) - min_pts):
        window = pts[i:i + min_pts]
        pwr_vals = [p.power_w for p in window if (p.power_w or 0) > 20]
        if not pwr_vals:
            continue
        avg = sum(pwr_vals) / len(pwr_vals)
        if avg > best_pwr:
            best_pwr = avg
            best_slice = window

    if best_slice is None:
        return None

    hr_vals = [p.heart_rate_bpm for p in best_slice if p.heart_rate_bpm]
    return {
        "avg_power":    round(best_pwr, 1) if best_pwr else None,
        "avg_hr":       round(sum(hr_vals) / len(hr_vals), 1) if hr_vals else None,
        "duration_min": min_minutes,
    }


def _ema_model(daily_load: dict[str, float],
               start: datetime, end: datetime) -> tuple[float, float]:
    """Banister EMA: CTL (42-day), ATL (7-day). Returns (CTL, ATL) at end."""
    ctl, atl = 0.0, 0.0
    ctl_k, atl_k = 1 / 42, 1 / 7
    cursor = datetime(start.year, start.month, start.day)

    while cursor <= end:
        day_str = cursor.date().isoformat()
        load = daily_load.get(day_str, 0.0)
        ctl = ctl + ctl_k * (load - ctl)
        atl = atl + atl_k * (load - atl)
        cursor += timedelta(days=1)

    return ctl, atl


def _build_interpretation(power_gap: Optional[float], hr_gap: Optional[float],
                           confidence: str) -> str:
    parts = []

    if power_gap is not None:
        direction = "lower" if power_gap < 0 else "higher"
        typical   = -15 <= power_gap <= -5
        inv = power_gap > 0

        if typical:
            parts.append(
                f"Your indoor power is ~{abs(power_gap):.0f}% {direction} than outdoor, "
                f"which is within the typical 5–15% range."
            )
        elif inv:
            parts.append(
                f"Your indoor power reads {power_gap:.0f}% higher than outdoor — unusual. "
                f"This may indicate a calibration issue with your smart trainer or power meter."
            )
        else:
            parts.append(
                f"Your indoor power is {abs(power_gap):.0f}% {direction} than outdoor, "
                f"which is {'slightly outside' if abs(power_gap) > 15 else 'within'} the typical 5–15% range."
            )

    if hr_gap is not None:
        direction = "higher" if hr_gap > 0 else "lower"
        typical   = 5 <= hr_gap <= 10
        if typical:
            parts.append(
                f"Your HR runs {abs(hr_gap):.0f} bpm {direction} indoors, "
                f"suggesting thermoregulation is the main driver of the indoor/outdoor difference."
            )
        else:
            parts.append(f"Your HR runs {abs(hr_gap):.0f} bpm {direction} indoors.")

    if confidence in ("low", "insufficient_data"):
        parts.append("Confidence is low — more rides will improve accuracy.")

    return " ".join(parts) if parts else "No interpretation available."


def _build_recommendation(power_gap: Optional[float],
                           hr_gap: Optional[float]) -> str:
    if power_gap is None:
        return "Enable automatic gap calculation by uploading indoor and outdoor rides with heart rate data."
    if power_gap < -20:
        return (f"Gap of {power_gap:.0f}% is unusually large. "
                "Check trainer calibration and power meter accuracy before applying correction.")
    if power_gap > 0:
        return ("Indoor power reads higher than outdoor. "
                "Verify trainer calibration — ERG mode can sometimes overestimate power at lower cadences.")
    pct = abs(round(power_gap))
    return (f"When planning indoor workouts based on outdoor FTP, "
            f"reduce target power by {pct}% or set an indoor-specific FTP.")
