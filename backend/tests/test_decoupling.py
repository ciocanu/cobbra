"""
Tests for utils/decoupling.py — Adjusted HR Decoupling algorithm.

Run from the backend directory:
    python -m pytest tests/test_decoupling.py -v
"""

import sys
import os
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.decoupling import (
    calculate_adjusted_decoupling,
    expected_heat_drift_pct,
    hydration_deficit_pct,
    expected_hydration_drift_pct,
    calculate_sweat_loss_ml,
)


# ── Test helpers ──────────────────────────────────────────────────────────────

def _activity(
    duration_seconds=5400,   # 1.5 h default
    weather_temp_c=15.0,
    hydration_ml=None,
    notes="",
    name="Morning Ride",
    avg_heart_rate_bpm=150.0,
):
    return SimpleNamespace(
        duration_seconds=duration_seconds,
        weather_temp_c=weather_temp_c,
        hydration_ml=hydration_ml,
        notes=notes,
        name=name,
        avg_heart_rate_bpm=avg_heart_rate_bpm,
    )


def _user(weight_kg=70.0, max_hr=185, sweat_rate_ml_per_hour=None):
    return SimpleNamespace(
        weight_kg=weight_kg,
        max_hr=max_hr,
        sweat_rate_ml_per_hour=sweat_rate_ml_per_hour,
    )


def _flat_pts(
    n=5400,          # points (1 Hz → 1.5 h)
    hr_start=140,
    hr_end=163,      # 23 bpm range
    speed=28.0,
    elevation=100.0,
    interval_s=1,
):
    """Generate flat-terrain track points with linear HR drift and constant speed."""
    start = datetime(2024, 7, 1, 8, 0, 0)
    pts = []
    for i in range(n):
        frac = i / max(n - 1, 1)
        hr = hr_start + (hr_end - hr_start) * frac
        pts.append({
            "timestamp":      start + timedelta(seconds=i * interval_s),
            "speed_kmh":      speed,
            "heart_rate_bpm": hr,
            "elevation":      elevation,
            "distance_m":     speed / 3.6 * i * interval_s,
        })
    return pts


def _mostly_hilly_pts(n=5400, hr_start=140, hr_end=163, speed=14.0, interval_s=1):
    """Track points that are climbing for most of the ride.

    Only the last 15 minutes are flat — not enough to meet the 30-min threshold.
    The rest (75 min) has a steady +5% gradient (elevation gain 0.7 m/pt).
    """
    start = datetime(2024, 7, 1, 8, 0, 0)
    pts = []
    flat_start = n - 900   # last 15 min = 900 pts
    for i in range(n):
        frac = i / max(n - 1, 1)
        hr = hr_start + (hr_end - hr_start) * frac
        if i < flat_start:
            elevation = 100.0 + i * 0.7   # ~5% gradient
        else:
            elevation = 100.0 + flat_start * 0.7  # flat at top
        dist = speed / 3.6 * i * interval_s
        pts.append({
            "timestamp":      start + timedelta(seconds=i * interval_s),
            "speed_kmh":      speed,
            "heart_rate_bpm": hr,
            "elevation":      elevation,
            "distance_m":     dist,
        })
    return pts


# ── Test 1: Hot weather false positive ────────────────────────────────────────

def test_hot_weather_reduces_adjusted():
    """
    30°C ride: raw drift is significant but heat accounts for most of it.
    Adjusted should be notably lower than raw.
    """
    act  = _activity(weather_temp_c=30.0, duration_seconds=5400)
    user = _user()
    pts  = _flat_pts(hr_start=140, hr_end=163)  # ~23 bpm range, clear drift

    result = calculate_adjusted_decoupling(act, pts, user)
    assert result is not None
    assert result["decoupling_raw"] is not None
    assert result["decoupling_adjusted"] is not None

    # Adjusted must be strictly lower than raw (heat was subtracted)
    assert result["decoupling_adjusted"] < result["decoupling_raw"]

    import json
    comp = json.loads(result["decoupling_components_json"])
    assert comp["expected_heat_drift_pct"] > 0


# ── Test 2: Cool genuine fatigue ─────────────────────────────────────────────

def test_cool_weather_preserves_fatigue_signal():
    """
    15°C ride: minimal heat drift, so adjusted ≈ raw.
    A real aerobic drift should remain above 'Excellent'.
    """
    act  = _activity(weather_temp_c=15.0, duration_seconds=5400)
    user = _user()
    # Larger HR drift: 140 → 170 (30 bpm range, pronounced EF drop)
    pts  = _flat_pts(hr_start=140, hr_end=170, speed=28.0)

    result = calculate_adjusted_decoupling(act, pts, user)
    assert result is not None
    assert result["decoupling_adjusted"] is not None

    # At 15°C, heat drift correction is small; adjusted should still show meaningful drift
    import json
    comp = json.loads(result["decoupling_components_json"])
    heat_correction = comp["expected_heat_drift_pct"]
    assert heat_correction < 2.0   # <2% correction at 15°C / 1.5h
    assert result["decoupling_adjusted"] > 2.0  # real fatigue signal preserved


# ── Test 3: Mostly hilly ride triggers terrain warning ────────────────────────

def test_mostly_hilly_ride_triggers_terrain_warning():
    """
    A ride that is climbing for 75 of its 90 minutes has only 15 min of flat
    terrain — below the 30-min threshold. The algorithm should fall back to
    the whole-ride drift and set a terrain warning.
    """
    act  = _activity(weather_temp_c=18.0, duration_seconds=5400)
    user = _user()
    pts  = _mostly_hilly_pts(hr_start=140, hr_end=163)

    result = calculate_adjusted_decoupling(act, pts, user)
    assert result is not None
    # Terrain warning should be set because < 30 min of flat terrain was found
    assert result["decoupling_warning"] is not None
    w = result["decoupling_warning"].lower()
    assert "flat" in w or "terrain" in w or "min" in w


# ── Test 4: Short ride (ineligible) ───────────────────────────────────────────

def test_short_ride_returns_ineligible():
    """
    Rides under 45 min should return a result with None values and a warning.
    """
    act  = _activity(duration_seconds=1800)  # 30 min
    user = _user()
    pts  = _flat_pts(n=1800, hr_start=140, hr_end=163)

    result = calculate_adjusted_decoupling(act, pts, user)
    assert result is not None
    assert result["decoupling_raw"] is None
    assert result["decoupling_adjusted"] is None
    assert result["decoupling_warning"] is not None
    assert "45" in result["decoupling_warning"] or "min" in result["decoupling_warning"].lower()


# ── Test 5: Significant hydration deficit ────────────────────────────────────

def test_hydration_deficit_reduces_adjusted():
    """
    Hot ride with no fluid intake: hydration correction reduces adjusted further.
    """
    act_no_water = _activity(weather_temp_c=28.0, duration_seconds=7200, hydration_ml=0)
    act_hydrated = _activity(weather_temp_c=28.0, duration_seconds=7200, hydration_ml=2000)
    user = _user(weight_kg=70.0)
    # Longer ride (2h), bigger drift
    pts = _flat_pts(n=7200, hr_start=140, hr_end=165)

    r_dry  = calculate_adjusted_decoupling(act_no_water, pts, user)
    r_wet  = calculate_adjusted_decoupling(act_hydrated, pts, user)

    assert r_dry  is not None
    assert r_wet  is not None

    # Dehydrated case subtracts more drift → lower adjusted (floored at 0)
    # The difference should be non-trivial if there's a real deficit
    import json
    comp_dry = json.loads(r_dry["decoupling_components_json"])
    comp_wet = json.loads(r_wet["decoupling_components_json"])
    assert comp_dry["expected_hydration_drift_pct"] >= comp_wet["expected_hydration_drift_pct"]


# ── Test 6: Well-hydrated ride ────────────────────────────────────────────────

def test_adequate_hydration_zero_correction():
    """
    When intake matches estimated sweat loss, hydration drift is 0.
    """
    # At 20°C, base sweat ~500 ml/h, 1.5h ride → ~750 ml estimated loss
    act  = _activity(weather_temp_c=20.0, duration_seconds=5400, hydration_ml=800)
    user = _user(weight_kg=70.0, sweat_rate_ml_per_hour=500)
    pts  = _flat_pts()

    deficit = hydration_deficit_pct(user, act)
    assert deficit == 0.0  # intake > sweat loss → clamped to 0

    drift = expected_hydration_drift_pct(deficit)
    assert drift == 0.0


# ── Test 7: Constant HR (recovery / interval) — ineligible ───────────────────

def test_constant_hr_returns_ineligible():
    """
    Rides with < 20 bpm HR variation are flagged as not informative.
    """
    act  = _activity(duration_seconds=5400)
    user = _user()
    # Only 10 bpm variation — below the 20 bpm threshold
    pts  = _flat_pts(hr_start=140, hr_end=149)

    result = calculate_adjusted_decoupling(act, pts, user)
    assert result is not None
    assert result["decoupling_raw"] is None
    assert result["decoupling_adjusted"] is None
    assert result["decoupling_warning"] is not None


# ── Test 8: Race / interval keyword — ineligible ─────────────────────────────

def test_interval_session_skipped():
    """Activities with interval/race keywords in name are skipped."""
    act  = _activity(name="FTP Test Intervals", duration_seconds=5400)
    user = _user()
    pts  = _flat_pts(hr_start=140, hr_end=163)

    result = calculate_adjusted_decoupling(act, pts, user)
    assert result is not None
    assert result["decoupling_adjusted"] is None
    assert result["decoupling_warning"] is not None
    assert "interval" in result["decoupling_warning"].lower() or "ftp" in result["decoupling_warning"].lower()


# ── Unit tests for sub-functions ─────────────────────────────────────────────

def test_heat_drift_increases_with_temperature():
    assert expected_heat_drift_pct(10.0, 1.5) < expected_heat_drift_pct(20.0, 1.5)
    assert expected_heat_drift_pct(20.0, 1.5) < expected_heat_drift_pct(28.0, 1.5)
    assert expected_heat_drift_pct(28.0, 1.5) < expected_heat_drift_pct(35.0, 1.5)


def test_heat_drift_duration_factor_saturates():
    """Duration factor caps at 1.5× (relative to 1.5h base), saturating by 3h."""
    drift_1h5 = expected_heat_drift_pct(25.0, 1.5)
    drift_3h  = expected_heat_drift_pct(25.0, 3.0)
    drift_6h  = expected_heat_drift_pct(25.0, 6.0)
    assert drift_3h == pytest.approx(drift_1h5 * 1.5, abs=0.01)
    assert drift_6h == pytest.approx(drift_3h, abs=0.01)  # cap reached at 3h


def test_hydration_drift_proportional():
    assert expected_hydration_drift_pct(1.0) == pytest.approx(3.0)
    assert expected_hydration_drift_pct(2.0) == pytest.approx(6.0)
    assert expected_hydration_drift_pct(0.0) == 0.0
    assert expected_hydration_drift_pct(None) == 0.0


def test_sweat_loss_uses_calibrated_rate():
    """Calibrated sweat rate overrides the estimate formula (no weight scaling)."""
    user = _user(sweat_rate_ml_per_hour=1200.0)
    act  = _activity(duration_seconds=3600)   # 1h
    loss = calculate_sweat_loss_ml(user, act)
    assert loss == pytest.approx(1200.0, abs=1.0)


def test_sweat_loss_scales_with_body_weight():
    """Uncalibrated estimate must scale with body mass — heavier rider sweats more."""
    act    = _activity(weather_temp_c=25.0, avg_heart_rate_bpm=150, duration_seconds=3600)
    light  = calculate_sweat_loss_ml(_user(weight_kg=55.0), act)
    mid    = calculate_sweat_loss_ml(_user(weight_kg=70.0), act)
    heavy  = calculate_sweat_loss_ml(_user(weight_kg=95.0), act)
    assert light < mid < heavy
    # 70 kg stays the anchor (no scaling)
    assert heavy == pytest.approx(mid * 95.0 / 70.0, rel=0.001)


def test_result_has_all_required_keys():
    act  = _activity(weather_temp_c=20.0, duration_seconds=5400)
    user = _user()
    pts  = _flat_pts(hr_start=140, hr_end=163)

    result = calculate_adjusted_decoupling(act, pts, user)
    assert result is not None
    for key in ("decoupling_raw", "decoupling_adjusted", "decoupling_components_json",
                "decoupling_quality", "decoupling_warning"):
        assert key in result


def test_quality_high_when_all_factors_present():
    """With temp, hydration, and enough flat terrain, quality should be 'high'."""
    act  = _activity(weather_temp_c=22.0, duration_seconds=5400, hydration_ml=750)
    user = _user(weight_kg=70.0)
    pts  = _flat_pts(hr_start=140, hr_end=163)

    result = calculate_adjusted_decoupling(act, pts, user)
    assert result is not None
    assert result["decoupling_quality"] == "high"
