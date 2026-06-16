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


# ── Public entry point: top-level guards ─────────────────────────────────────

def test_empty_track_points_returns_none():
    """No track points at all → immediate None (can't compute anything)."""
    act  = _activity()
    user = _user()
    assert calculate_adjusted_decoupling(act, [], user) is None


def test_fewer_than_60_clean_points_returns_none():
    """After sort/clean, < 60 points means the ride is too sparse to analyze."""
    act  = _activity(duration_seconds=5400)
    user = _user()
    pts  = _flat_pts(n=59, hr_start=140, hr_end=163)
    assert calculate_adjusted_decoupling(act, pts, user) is None


def test_points_missing_speed_or_hr_are_dropped_before_60_check():
    """Points without speed_kmh or heart_rate_bpm are filtered out by _sort_and_clean;
    if that drops the count below 60, the ride is rejected even though len(track_points) >= 60.
    The HR-validity eligibility check (>=80% of points need HR) is satisfied here (90%),
    so this exercises the *separate* post-clean 60-point floor, not the eligibility gate."""
    act  = _activity(duration_seconds=5400)
    user = _user()
    pts  = _flat_pts(n=100, hr_start=140, hr_end=163)
    # Strip HR from only the last 10 points (90% HR-valid, passes eligibility)
    for p in pts[90:]:
        p["heart_rate_bpm"] = None
    # Strip speed from all but the first 51 -> after intersecting with HR, only 51 clean points remain
    for p in pts[51:]:
        p["speed_kmh"] = None
    assert calculate_adjusted_decoupling(act, pts, user) is None


def test_unsorted_points_are_sorted_before_analysis():
    """Track points fed in reverse chronological order should still produce the
    same result as already-sorted points (sorting happens internally)."""
    act  = _activity(weather_temp_c=15.0, duration_seconds=5400)
    user = _user()
    pts_sorted   = _flat_pts(hr_start=140, hr_end=163)
    pts_reversed = list(reversed(pts_sorted))

    r1 = calculate_adjusted_decoupling(act, pts_sorted, user)
    r2 = calculate_adjusted_decoupling(act, pts_reversed, user)
    assert r1 is not None and r2 is not None
    assert r1["decoupling_raw"] == r2["decoupling_raw"]
    assert r1["decoupling_adjusted"] == r2["decoupling_adjusted"]


def test_zero_duration_is_ineligible():
    act  = _activity(duration_seconds=0)
    user = _user()
    pts  = _flat_pts(hr_start=140, hr_end=163)
    result = calculate_adjusted_decoupling(act, pts, user)
    assert result["decoupling_raw"] is None
    assert "45" in result["decoupling_warning"] or "min" in result["decoupling_warning"].lower()


def test_duration_exactly_at_threshold_is_eligible():
    """duration_seconds == 2700 (exactly 45 min) should PASS the eligibility check
    (the code uses `dur < _MIN_DURATION_S`, so equality is allowed)."""
    act  = _activity(duration_seconds=2700, weather_temp_c=15.0)
    user = _user()
    pts  = _flat_pts(n=2700, hr_start=140, hr_end=163)
    result = calculate_adjusted_decoupling(act, pts, user)
    assert result is not None
    assert result["decoupling_raw"] is not None


def test_duration_one_second_under_threshold_is_ineligible():
    act  = _activity(duration_seconds=2699)
    user = _user()
    pts  = _flat_pts(n=2699, hr_start=140, hr_end=163)
    result = calculate_adjusted_decoupling(act, pts, user)
    assert result["decoupling_raw"] is None


def test_hr_range_exactly_at_threshold_is_eligible():
    """HR range of exactly 20 bpm should pass (`< _MIN_HR_RANGE_BPM` excludes only strictly less)."""
    act  = _activity(duration_seconds=5400)
    user = _user()
    pts  = _flat_pts(hr_start=140, hr_end=160)  # exactly 20 bpm range
    result = calculate_adjusted_decoupling(act, pts, user)
    assert result["decoupling_raw"] is not None


def test_hr_range_one_bpm_under_threshold_is_ineligible():
    act  = _activity(duration_seconds=5400)
    user = _user()
    pts  = _flat_pts(hr_start=140, hr_end=158.99)  # ~19 bpm range
    result = calculate_adjusted_decoupling(act, pts, user)
    assert result["decoupling_raw"] is None


def test_hr_valid_fraction_exactly_80_percent_is_eligible():
    """Exactly 80% of points with HR data should pass (`< _MIN_HR_VALID_FRAC` is strict).

    Null out a middle slice (not the tail) so the full 140-163 HR range stays
    represented by the first/last points — nulling the tail instead would also
    truncate the observed HR range below the 20bpm eligibility floor, conflating
    two different guards in one test.
    """
    act = _activity(duration_seconds=5400)
    user = _user()
    pts = _flat_pts(n=5400, hr_start=140, hr_end=163)
    # Null out HR on exactly 20% of points (a middle slice), keep speed present
    for p in pts[2160:3240]:
        p["heart_rate_bpm"] = None
    result = calculate_adjusted_decoupling(act, pts, user)
    # Eligibility passes at exactly 80%, though clean points will then drop the nulled ones
    assert result["decoupling_raw"] is not None


def test_hr_valid_fraction_just_under_80_percent_is_ineligible():
    act = _activity(duration_seconds=5400)
    user = _user()
    pts = _flat_pts(n=5400, hr_start=140, hr_end=163)
    # Null out HR on slightly more than 20% of points
    for p in pts[-1100:]:
        p["heart_rate_bpm"] = None
    result = calculate_adjusted_decoupling(act, pts, user)
    assert result["decoupling_raw"] is None
    assert "80%" in result["decoupling_warning"]


def test_notes_keyword_also_triggers_skip():
    """The skip-keyword scan checks notes as well as name."""
    act  = _activity(name="Evening Ride", notes="Did some VO2 work today", duration_seconds=5400)
    user = _user()
    pts  = _flat_pts(hr_start=140, hr_end=163)
    result = calculate_adjusted_decoupling(act, pts, user)
    assert result["decoupling_adjusted"] is None
    assert "vo2" in result["decoupling_warning"].lower()


def test_french_keyword_intervals_skipped():
    act  = _activity(name="Séries 5x5", duration_seconds=5400)
    user = _user()
    pts  = _flat_pts(hr_start=140, hr_end=163)
    result = calculate_adjusted_decoupling(act, pts, user)
    assert result["decoupling_adjusted"] is None


def test_no_skip_keyword_in_normal_ride_name():
    """Sanity check: an ordinary ride name doesn't accidentally match a skip keyword."""
    act  = _activity(name="Sunday long ride", notes="Felt good throughout", duration_seconds=5400)
    user = _user()
    pts  = _flat_pts(hr_start=140, hr_end=163)
    result = calculate_adjusted_decoupling(act, pts, user)
    assert result["decoupling_adjusted"] is not None


def test_terrain_correction_used_when_flat_split_meets_minimums():
    """When flat terrain >= 30 min AND both halves >= 15 min, first/second half EF
    values should appear in the components JSON (terrain-corrected path taken)."""
    act  = _activity(weather_temp_c=15.0, duration_seconds=5400)
    user = _user()
    pts  = _flat_pts(hr_start=140, hr_end=163)  # fully flat ride, 90 min

    result = calculate_adjusted_decoupling(act, pts, user)
    assert result is not None
    import json
    comp = json.loads(result["decoupling_components_json"])
    assert "first_half_ef" in comp
    assert "second_half_ef" in comp
    # Terrain warning should NOT be set in this case (sufficient flat terrain, valid split)
    assert result["decoupling_warning"] is None


def test_quality_downgraded_to_medium_when_terrain_warning_present_despite_high_signals():
    """Even when temp + hydration + flat_min>=30 are all present (3/3 signals → 'high'),
    if a terrain_warning was raised (e.g. flat segments are non-contiguous so each half
    doesn't reach 15 min even though total flat minutes >= 30), quality must be downgraded
    to 'medium'."""
    from datetime import datetime, timedelta
    start = datetime(2024, 7, 1, 8, 0, 0)
    n = 5400  # 90 min ride
    pts = []
    for i in range(n):
        minute = i / 60
        frac = i / (n - 1)
        hr = 140 + 23 * frac
        if minute < 5:
            elevation = 100.0          # flat first 5 min
        elif minute < 63:
            elevation = 100.0 + i * 0.7   # hilly middle
        else:
            elevation = 100.0 + 1.0    # flat last 27 min
        pts.append({
            "timestamp": start + timedelta(seconds=i),
            "speed_kmh": 28.0,
            "heart_rate_bpm": hr,
            "elevation": elevation,
            "distance_m": 28.0 / 3.6 * i,
        })

    act  = _activity(weather_temp_c=22.0, duration_seconds=5400, hydration_ml=750)
    user = _user(weight_kg=70.0)
    result = calculate_adjusted_decoupling(act, pts, user)
    assert result is not None
    assert result["decoupling_quality"] == "medium"
    assert result["decoupling_warning"] is not None
    assert "each half had" in result["decoupling_warning"]


def test_quality_medium_with_two_of_three_signals():
    """Temp present + flat terrain present, but no hydration data -> 2/3 signals -> medium."""
    act  = _activity(weather_temp_c=20.0, duration_seconds=5400, hydration_ml=None)
    user = _user(weight_kg=70.0)
    pts  = _flat_pts(hr_start=140, hr_end=163)
    result = calculate_adjusted_decoupling(act, pts, user)
    assert result["decoupling_quality"] == "medium"


def test_quality_low_with_zero_signals():
    """No temp, no hydration, insufficient flat terrain -> 0/3 signals -> low."""
    act  = _activity(weather_temp_c=None, duration_seconds=5400, hydration_ml=None)
    user = _user(weight_kg=70.0)
    pts  = _mostly_hilly_pts(hr_start=140, hr_end=163)
    result = calculate_adjusted_decoupling(act, pts, user)
    assert result["decoupling_quality"] == "low"


def test_adjusted_decoupling_floored_at_zero():
    """If heat+hydration corrections exceed raw drift, adjusted is floored at 0.0,
    never negative."""
    # Very small genuine drift, but hot + dehydrated -> heat/hydration correction
    # could exceed the raw drift entirely.
    act  = _activity(weather_temp_c=35.0, duration_seconds=7200, hydration_ml=0)
    user = _user(weight_kg=70.0)
    # Minimal drift: HR barely rises (just above the 20bpm eligibility threshold)
    pts  = _flat_pts(n=7200, hr_start=140, hr_end=160.5)
    result = calculate_adjusted_decoupling(act, pts, user)
    assert result is not None
    assert result["decoupling_adjusted"] >= 0.0


def test_classification_categories_at_boundaries():
    """Verify the _classify thresholds via the public pipeline's category field,
    using calculate_sweat_loss_ml/expected_*_pct combos is indirect, so we test
    the internal _classify boundary values directly (it's a simple pure function
    central to interpreting decoupling_adjusted)."""
    from utils.decoupling import _classify
    assert _classify(0.0)    == "Excellent"
    assert _classify(1.999)  == "Excellent"
    assert _classify(2.0)    == "Good"
    assert _classify(4.999)  == "Good"
    assert _classify(5.0)    == "Moderate"
    assert _classify(7.999)  == "Moderate"
    assert _classify(8.0)    == "Significant"
    assert _classify(11.999) == "Significant"
    assert _classify(12.0)   == "High"
    assert _classify(100.0)  == "High"


# ── expected_heat_drift_pct: branches & boundaries ───────────────────────────

def test_heat_drift_zero_below_18C():
    assert expected_heat_drift_pct(17.9, 1.5) == 0.0
    assert expected_heat_drift_pct(0.0, 1.5) == 0.0
    assert expected_heat_drift_pct(-10.0, 1.5) == 0.0


def test_heat_drift_at_exactly_18C_is_zero():
    """avg_temp_c == 18 takes the `< 18` False branch but heat_bpm = (18-18)*0.5 = 0."""
    assert expected_heat_drift_pct(18.0, 1.5) == 0.0


def test_heat_drift_caps_at_12_bpm_total():
    """heat_bpm_total is capped at 12 bpm regardless of how hot/long the ride is."""
    extreme = expected_heat_drift_pct(60.0, 10.0)
    very_extreme = expected_heat_drift_pct(100.0, 100.0)
    assert extreme == very_extreme
    assert extreme == pytest.approx(12.0 / 150.0 * 100.0, abs=0.01)


def test_heat_drift_zero_duration():
    """duration_hours = 0 -> duration_factor = 0 -> heat_bpm_total = 0 -> drift 0."""
    assert expected_heat_drift_pct(30.0, 0.0) == 0.0


def test_heat_drift_negative_duration_yields_negative_or_zero_factor():
    """BUG-ish edge case: negative duration_hours produces a negative duration_factor,
    which (since heat_bpm > 0) makes heat_bpm_total negative via min(), and the final
    ef_drift comes out negative. This is an unrealistic input (duration can't be negative
    in practice) but the function doesn't guard against it."""
    result = expected_heat_drift_pct(30.0, -1.0)
    assert result < 0.0
    # Document current (questionable) behavior; ideally negative duration should be
    # treated as 0 or raise, but the function currently returns a negative "drift %".
    # assert result == 0.0   # <- what *should* happen if duration were clamped to >= 0


def test_heat_drift_duration_factor_boundary_at_90_min():
    """duration_hours = 1.5 (90 min) is the point where duration_factor reaches 1.0
    (1.5/1.5 = 1.0), i.e. full but not yet saturated heat_bpm."""
    drift_90min = expected_heat_drift_pct(25.0, 1.5)
    drift_just_under = expected_heat_drift_pct(25.0, 1.49)
    assert drift_90min > drift_just_under


# ── hydration_deficit_pct / expected_hydration_drift_pct ─────────────────────

def test_hydration_deficit_none_when_weight_missing():
    user = _user(weight_kg=None)
    act  = _activity(hydration_ml=500)
    assert hydration_deficit_pct(user, act) is None


def test_hydration_deficit_none_when_weight_zero():
    """weight_kg=0 is falsy, so `if not weight_kg` triggers -> None, even though
    0 kg is a nonsensical (not just missing) value -- documents current behavior."""
    user = _user(weight_kg=0)
    act  = _activity(hydration_ml=500)
    assert hydration_deficit_pct(user, act) is None


def test_hydration_deficit_none_when_intake_missing():
    user = _user(weight_kg=70.0)
    act  = _activity(hydration_ml=None)
    assert hydration_deficit_pct(user, act) is None


def test_hydration_deficit_zero_intake_is_valid_input():
    """hydration_ml=0 should NOT be treated as missing (the check is `intake_ml is None`)."""
    user = _user(weight_kg=70.0, sweat_rate_ml_per_hour=1000.0)
    act  = _activity(hydration_ml=0, duration_seconds=3600)
    deficit = hydration_deficit_pct(user, act)
    assert deficit is not None
    assert deficit > 0.0


def test_hydration_deficit_negative_intake_increases_deficit():
    """Negative hydration_ml isn't a realistic input, but the formula treats it as
    a larger net deficit (sweat_loss - intake grows). Documents current behavior."""
    user = _user(weight_kg=70.0, sweat_rate_ml_per_hour=1000.0)
    act_neg  = _activity(hydration_ml=-500, duration_seconds=3600)
    act_zero = _activity(hydration_ml=0, duration_seconds=3600)
    deficit_neg  = hydration_deficit_pct(user, act_neg)
    deficit_zero = hydration_deficit_pct(user, act_zero)
    assert deficit_neg > deficit_zero


def test_hydration_drift_temperature_tiers():
    """Verify the three temperature tiers for bpm-per-percent scaling."""
    cool = expected_hydration_drift_pct(1.0, avg_temp_c=15.0)     # < 20 -> 2.0 bpm/pct
    temperate = expected_hydration_drift_pct(1.0, avg_temp_c=24.0)  # 20-28 -> 3.0 bpm/pct
    hot = expected_hydration_drift_pct(1.0, avg_temp_c=30.0)        # >= 28 -> 4.5 bpm/pct
    assert cool < temperate < hot
    # The production function rounds to 2 decimal places, so allow for that.
    assert cool == pytest.approx(2.0 / 150.0 * 100.0, abs=0.01)
    assert temperate == pytest.approx(3.0 / 150.0 * 100.0, abs=0.01)
    assert hot == pytest.approx(4.5 / 150.0 * 100.0, abs=0.01)


def test_hydration_drift_temperature_boundaries():
    """Boundaries: exactly 20°C is 'temperate' tier, exactly 28°C is 'hot' tier."""
    at_20 = expected_hydration_drift_pct(1.0, avg_temp_c=20.0)
    just_under_20 = expected_hydration_drift_pct(1.0, avg_temp_c=19.99)
    at_28 = expected_hydration_drift_pct(1.0, avg_temp_c=28.0)
    just_under_28 = expected_hydration_drift_pct(1.0, avg_temp_c=27.99)

    assert at_20 > just_under_20      # 20.0 enters the 3.0 bpm/pct tier
    assert at_28 > just_under_28      # 28.0 enters the 4.5 bpm/pct tier


def test_hydration_drift_none_temp_defaults_to_hot_tier():
    """When avg_temp_c is None, the code uses the hot-conditions multiplier (4.5 bpm/pct),
    same as >=28°C — i.e. unknown temperature is treated as worst-case hot."""
    no_temp = expected_hydration_drift_pct(1.0, avg_temp_c=None)
    hot     = expected_hydration_drift_pct(1.0, avg_temp_c=30.0)
    assert no_temp == hot


def test_hydration_drift_negative_deficit_not_possible_but_function_is_linear():
    """If somehow given a negative deficit_pct (shouldn't happen since
    hydration_deficit_pct clamps to >=0), the drift scales linearly and goes negative too."""
    assert expected_hydration_drift_pct(-1.0) == pytest.approx(-3.0, abs=0.01)


# ── calculate_sweat_loss_ml branches ─────────────────────────────────────────

def test_sweat_loss_default_rate_no_temp_no_high_hr():
    """No calibration, no temperature data, default avg_hr_pct (0.70) -> base 500 ml/h."""
    user = _user(weight_kg=70.0, sweat_rate_ml_per_hour=None)
    act  = _activity(weather_temp_c=None, avg_heart_rate_bpm=None, duration_seconds=3600)
    loss = calculate_sweat_loss_ml(user, act)
    assert loss == pytest.approx(500.0, abs=1.0)


def test_sweat_loss_high_hr_increases_rate():
    """avg_hr_pct > 0.70 adds extra ml/h beyond the temperature contribution."""
    user = _user(weight_kg=70.0, max_hr=185, sweat_rate_ml_per_hour=None)
    act_low_hr  = _activity(weather_temp_c=None, avg_heart_rate_bpm=120.0, duration_seconds=3600)
    act_high_hr = _activity(weather_temp_c=None, avg_heart_rate_bpm=180.0, duration_seconds=3600)
    loss_low  = calculate_sweat_loss_ml(user, act_low_hr)
    loss_high = calculate_sweat_loss_ml(user, act_high_hr)
    assert loss_high > loss_low


def test_sweat_loss_weight_scaling_only_applies_above_30kg():
    """Riders <= 30 kg don't get the weight-scaling multiplier applied (guards against
    nonsensical scaling for very low/garbage weight values)."""
    user_tiny = _user(weight_kg=20.0, sweat_rate_ml_per_hour=None)
    user_70   = _user(weight_kg=70.0, sweat_rate_ml_per_hour=None)
    act = _activity(weather_temp_c=None, avg_heart_rate_bpm=None, duration_seconds=3600)
    loss_tiny = calculate_sweat_loss_ml(user_tiny, act)
    loss_70   = calculate_sweat_loss_ml(user_70, act)
    # 20 kg rider gets no scaling applied (base_rate stays 500), 70kg also stays at
    # anchor 500 (no scaling needed since 70/70=1) -> both equal base rate.
    assert loss_tiny == pytest.approx(loss_70, abs=1.0)


def test_sweat_loss_missing_weight_kg_no_scaling():
    """weight_kg=None means the scaling branch is skipped entirely."""
    user = _user(weight_kg=None, sweat_rate_ml_per_hour=None)
    act  = _activity(weather_temp_c=None, avg_heart_rate_bpm=None, duration_seconds=3600)
    loss = calculate_sweat_loss_ml(user, act)
    assert loss == pytest.approx(500.0, abs=1.0)


def test_sweat_loss_default_duration_when_missing():
    """If activity.duration_seconds is missing entirely, defaults to 3600s (1h)."""
    user = _user(weight_kg=70.0, sweat_rate_ml_per_hour=None)
    act  = SimpleNamespace(weather_temp_c=None, avg_heart_rate_bpm=None, hydration_ml=None,
                            notes="", name="Ride")  # no duration_seconds attr at all
    loss = calculate_sweat_loss_ml(user, act)
    assert loss == pytest.approx(500.0, abs=1.0)


def test_sweat_loss_temperature_above_20_increases_base_rate():
    user = _user(weight_kg=70.0, sweat_rate_ml_per_hour=None)
    act_cool = _activity(weather_temp_c=18.0, avg_heart_rate_bpm=None, duration_seconds=3600)
    act_hot  = _activity(weather_temp_c=35.0, avg_heart_rate_bpm=None, duration_seconds=3600)
    loss_cool = calculate_sweat_loss_ml(user, act_cool)
    loss_hot  = calculate_sweat_loss_ml(user, act_hot)
    assert loss_hot > loss_cool


# ── _get_temperature: sensor vs weather precedence (BUG documentation) ──────

def test_get_temperature_prefers_sensor_over_weather():
    from utils.decoupling import _get_temperature
    act = SimpleNamespace(sensor_temp_avg_c=25.0, weather_temp_c=15.0)
    assert _get_temperature(act) == 25.0


def test_get_temperature_sensor_zero_incorrectly_falls_back_to_weather():
    """BUG: _get_temperature (utils/decoupling.py, line 462) uses
    `getattr(activity, "sensor_temp_avg_c", None) or getattr(activity, "weather_temp_c", None)`.
    A sensor reading of exactly 0.0°C (a perfectly valid, real temperature — freezing point)
    is falsy in Python, so `or` incorrectly falls through to weather_temp_c instead of using
    the genuine sensor value. The function should distinguish "missing" (None) from
    "zero" (a valid float) by checking `is not None` rather than relying on truthiness.
    """
    act = SimpleNamespace(sensor_temp_avg_c=0.0, weather_temp_c=15.0)
    from utils.decoupling import _get_temperature
    result = _get_temperature(act)
    # Current (buggy) behavior: falls back to weather_temp_c instead of using sensor 0.0
    assert result == 15.0
    # Correct behavior once fixed:
    # assert result == 0.0


def test_get_temperature_none_when_both_missing():
    from utils.decoupling import _get_temperature
    act = SimpleNamespace(sensor_temp_avg_c=None, weather_temp_c=None)
    assert _get_temperature(act) is None


def test_get_temperature_falls_back_to_weather_when_sensor_missing():
    from utils.decoupling import _get_temperature
    act = SimpleNamespace(sensor_temp_avg_c=None, weather_temp_c=12.5)
    assert _get_temperature(act) == 12.5


# ── _avg_ef / _calc_ef_drift boundary semantics ───────────────────────────────

def test_avg_ef_excludes_points_at_exact_thresholds():
    """_avg_ef requires speed_kmh > 3.0 (strict) and heart_rate_bpm > 40 (strict);
    points exactly at the threshold are excluded."""
    from utils.decoupling import _avg_ef
    pts = [
        {"speed_kmh": 3.0, "heart_rate_bpm": 40},     # excluded (not strictly greater)
        {"speed_kmh": 10.0, "heart_rate_bpm": 100},   # included
    ]
    ef = _avg_ef(pts)
    assert ef == pytest.approx(10.0 / 100.0)


def test_avg_ef_none_when_no_valid_points():
    from utils.decoupling import _avg_ef
    pts = [{"speed_kmh": 1.0, "heart_rate_bpm": 30}]
    assert _avg_ef(pts) is None


def test_avg_ef_empty_list_returns_none():
    from utils.decoupling import _avg_ef
    assert _avg_ef([]) is None


def test_calc_ef_drift_none_when_ef_zero_in_first_half():
    """If ef1 == 0 exactly, drift calc divides by it -> guarded to return None."""
    from utils.decoupling import _calc_ef_drift
    # Can't naturally get ef1 == 0.0 with positive speed/hr, but ef1 is None
    # if no points qualify -> covered by the None branch already. We test the
    # explicit ef1==0 guard isn't reachable through public data, so just confirm
    # the function returns None when not enough valid points exist in a half.
    pts = [{"speed_kmh": 1.0, "heart_rate_bpm": 30}] * 10
    assert _calc_ef_drift(pts) is None


# ── _split_halves_by_elapsed / _elapsed_minutes edge cases ───────────────────

def test_elapsed_minutes_single_point_is_zero():
    from utils.decoupling import _elapsed_minutes
    assert _elapsed_minutes([{"timestamp": datetime(2024, 1, 1)}]) == 0.0


def test_elapsed_minutes_empty_list_is_zero():
    from utils.decoupling import _elapsed_minutes
    assert _elapsed_minutes([]) == 0.0


def test_split_halves_by_elapsed_tiny_list_uses_index_split():
    """Lists with < 4 points fall back to a simple index-based split, not elapsed-time."""
    from utils.decoupling import _split_halves_by_elapsed
    pts = [{"timestamp": datetime(2024, 1, 1, 0, 0, i)} for i in range(3)]
    first, second = _split_halves_by_elapsed(pts)
    assert first == pts[:1]
    assert second == pts[1:]


def test_split_halves_by_elapsed_missing_timestamps_falls_back_to_midpoint():
    from utils.decoupling import _split_halves_by_elapsed
    pts = [{"timestamp": None} for _ in range(10)]
    first, second = _split_halves_by_elapsed(pts)
    assert len(first) == 5
    assert len(second) == 5


def test_compute_gradients_smooth_returns_none_for_decreasing_distance():
    """Gradient is None for points where distance doesn't increase (delta_d <= 0),
    e.g. duplicate/out-of-order distance values."""
    from utils.decoupling import _compute_gradients_smooth
    pts = [
        {"elevation": 100.0, "distance_m": 0},
        {"elevation": 105.0, "distance_m": 0},   # delta_d == 0 -> raw gradient None at i=1
    ]
    grads = _compute_gradients_smooth(pts)
    assert grads[0] is None  # i=0 always None (no previous point)
    # i=1's raw gradient is None, but the smoothing window may pick up neighbors;
    # with only 2 points and both raw values None, smoothed must also be None.
    assert grads[1] is None


def test_compute_gradients_smooth_handles_missing_elevation():
    from utils.decoupling import _compute_gradients_smooth
    pts = [
        {"elevation": None, "distance_m": 0},
        {"elevation": 100.0, "distance_m": 10},
    ]
    grads = _compute_gradients_smooth(pts)
    assert grads[1] is None  # e1 is None -> raw[1] is None


def test_compute_gradients_smooth_empty_list():
    from utils.decoupling import _compute_gradients_smooth
    assert _compute_gradients_smooth([]) == []
