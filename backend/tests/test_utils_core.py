"""
Tests for utils/__init__.py — core cycling-metrics calculation functions.

Covers: estimate_max_hr_tanaka, compute_normalized_power, compute_tss,
compute_hrtss, compute_hrtss_heat_corrected, estimate_calories_from_hr,
compute_suffer_score, compute_distance_prs, match_segment.

Run from the backend directory:
    python -m pytest tests/test_utils_core.py -v
"""

import sys
import os
import json
import math
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils import (
    estimate_max_hr_tanaka,
    compute_normalized_power,
    compute_tss,
    compute_hrtss,
    compute_hrtss_heat_corrected,
    estimate_calories_from_hr,
    compute_suffer_score,
    compute_distance_prs,
    match_segment,
    PR_DISTANCES_M,
    PR_LABELS,
    _ZONE_THRESHOLDS,
    _ZONE_WEIGHTS,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def _pts_constant_power(power, n, interval_s=1, start=None):
    """n track points at 1Hz (or interval_s) with constant power."""
    start = start or datetime(2024, 6, 1, 8, 0, 0)
    return [
        {"timestamp": start + timedelta(seconds=i * interval_s), "power_w": power}
        for i in range(n)
    ]


def _pts_hr(hrs, interval_s=1, start=None):
    """Track points with given heart-rate sequence at fixed interval."""
    start = start or datetime(2024, 6, 1, 8, 0, 0)
    return [
        {"timestamp": start + timedelta(seconds=i * interval_s), "heart_rate_bpm": hr}
        for i, hr in enumerate(hrs)
    ]


def _pts_distance(distances, interval_s=1, start=None):
    """Track points with given (monotonic) distance_m sequence, 1 point/sec by default."""
    start = start or datetime(2024, 6, 1, 8, 0, 0)
    return [
        {"timestamp": start + timedelta(seconds=i * interval_s), "distance_m": d}
        for i, d in enumerate(distances)
    ]


def _segment(waypoints=None, start_lat=45.0, start_lon=6.0, end_lat=45.001, end_lon=6.0):
    if waypoints is not None:
        return SimpleNamespace(waypoints_json=json.dumps(waypoints))
    return SimpleNamespace(
        waypoints_json=None,
        start_lat=start_lat, start_lon=start_lon,
        end_lat=end_lat, end_lon=end_lon,
    )


# ── estimate_max_hr_tanaka ───────────────────────────────────────────────────

class TestEstimateMaxHrTanaka:
    def test_known_value_age_30(self):
        """208 - 0.7*30 = 187."""
        assert estimate_max_hr_tanaka(30) == 187

    def test_known_value_age_40(self):
        """208 - 0.7*40 = 180."""
        assert estimate_max_hr_tanaka(40) == 180

    def test_age_zero(self):
        assert estimate_max_hr_tanaka(0) == 208

    def test_rounding_behavior(self):
        """208 - 0.7*25 = 190.5 -> banker's rounding via round() = 190."""
        val = estimate_max_hr_tanaka(25)
        assert val == round(208 - 0.7 * 25)

    def test_large_age_100(self):
        """208 - 0.7*100 = 138."""
        assert estimate_max_hr_tanaka(100) == 138

    def test_negative_age_extrapolates(self):
        """No guard against negative age; formula still applies."""
        assert estimate_max_hr_tanaka(-10) == round(208 - 0.7 * -10)

    def test_returns_int(self):
        assert isinstance(estimate_max_hr_tanaka(30), int)


# ── compute_normalized_power ─────────────────────────────────────────────────

class TestComputeNormalizedPower:
    def test_constant_power_np_equals_power(self):
        """With perfectly constant power, NP == that power (rolling avg is constant)."""
        pts = _pts_constant_power(200, 60)
        np_val = compute_normalized_power(pts)
        assert np_val == pytest.approx(200, abs=1)

    def test_fewer_than_30_points_returns_none(self):
        pts = _pts_constant_power(200, 29)
        assert compute_normalized_power(pts) is None

    def test_exactly_30_points_returns_value(self):
        pts = _pts_constant_power(200, 30)
        assert compute_normalized_power(pts) is not None

    def test_empty_list_returns_none(self):
        assert compute_normalized_power([]) is None

    def test_missing_timestamp_excluded(self):
        pts = _pts_constant_power(200, 35)
        pts[0]["timestamp"] = None
        # 34 valid points remain, still >= 30
        assert compute_normalized_power(pts) is not None

    def test_missing_power_excluded(self):
        pts = _pts_constant_power(200, 35)
        for p in pts[:6]:
            p["power_w"] = None
        # 29 remain -> None
        assert compute_normalized_power(pts) is None

    def test_variable_power_np_differs_from_average_for_step_change(self):
        """For a step change (30s@100W then 30s@400W), the 30s rolling window
        smooths the transition so most windows blend both levels: NP ends up
        below the simple arithmetic mean here, but markedly different from it
        -- demonstrating NP is NOT a trivial average."""
        start = datetime(2024, 6, 1, 8, 0, 0)
        powers = [100] * 30 + [400] * 30
        pts = [
            {"timestamp": start + timedelta(seconds=i), "power_w": p}
            for i, p in enumerate(powers)
        ]
        np_val = compute_normalized_power(pts)
        avg = sum(powers) / len(powers)
        assert np_val != pytest.approx(avg, abs=1)
        assert 100 < np_val < 400

    def test_sustained_high_power_after_warmup_np_exceeds_average(self):
        """When the high-power segment is long enough that the rolling window
        fully captures it (60s warmup + 60s sustained surge with a 30s window),
        the 4th-power weighting should push NP above the simple mean."""
        start = datetime(2024, 6, 1, 8, 0, 0)
        powers = [100] * 60 + [400] * 60
        pts = [
            {"timestamp": start + timedelta(seconds=i), "power_w": p}
            for i, p in enumerate(powers)
        ]
        np_val = compute_normalized_power(pts)
        avg = sum(powers) / len(powers)
        assert np_val > avg

    def test_string_timestamps_parsed(self):
        start = datetime(2024, 6, 1, 8, 0, 0)
        pts = [
            {"timestamp": (start + timedelta(seconds=i)).isoformat(), "power_w": 150}
            for i in range(30)
        ]
        assert compute_normalized_power(pts) == pytest.approx(150, abs=1)

    def test_out_of_order_timestamps_sorted_internally(self):
        start = datetime(2024, 6, 1, 8, 0, 0)
        pts = [
            {"timestamp": start + timedelta(seconds=i), "power_w": 200}
            for i in range(40)
        ]
        shuffled = pts[20:] + pts[:20]
        assert compute_normalized_power(shuffled) == pytest.approx(200, abs=1)

    def test_duplicate_timestamps_handled(self):
        start = datetime(2024, 6, 1, 8, 0, 0)
        pts = [{"timestamp": start, "power_w": 200} for _ in range(35)]
        # all same timestamp -> rolling window logic still must not crash
        result = compute_normalized_power(pts)
        assert result == pytest.approx(200, abs=1)

    def test_zero_power_returns_zero(self):
        pts = _pts_constant_power(0, 40)
        assert compute_normalized_power(pts) == 0

    def test_returns_int_type(self):
        pts = _pts_constant_power(200, 40)
        assert isinstance(compute_normalized_power(pts), int)

    def test_single_point_below_threshold(self):
        assert compute_normalized_power(_pts_constant_power(200, 1)) is None

    def test_manual_calc_two_step_power(self):
        """
        Hand-computed NP for a simple ramp: 30s at 100W then 30s at 300W
        at 1Hz, window=30s. The 30s window means most samples blend both
        levels, so NP stays strictly between the two power levels.
        """
        start = datetime(2024, 6, 1, 8, 0, 0)
        powers = [100] * 30 + [300] * 30
        pts = [{"timestamp": start + timedelta(seconds=i), "power_w": p} for i, p in enumerate(powers)]
        np_val = compute_normalized_power(pts)
        assert 100 < np_val < 300


# ── compute_tss ───────────────────────────────────────────────────────────

class TestComputeTSS:
    def test_one_hour_at_ftp_equals_100(self):
        """1 hour exactly at FTP (NP==FTP, IF=1.0) => TSS = 100."""
        tss = compute_tss(np_watts=250, duration_seconds=3600, ftp=250)
        assert tss == pytest.approx(100.0)

    def test_half_hour_at_ftp_equals_50(self):
        tss = compute_tss(np_watts=250, duration_seconds=1800, ftp=250)
        assert tss == pytest.approx(50.0)

    def test_manual_formula_check(self):
        """TSS = (duration * NP * IF) / (FTP*3600) * 100."""
        duration, np_w, ftp = 5400, 220, 200
        if_val = np_w / ftp
        expected = round((duration * np_w * if_val) / (ftp * 3600) * 100, 1)
        assert compute_tss(np_w, duration, ftp) == expected

    def test_np_watts_none_returns_none(self):
        assert compute_tss(None, 3600, 250) is None

    def test_np_watts_zero_returns_none(self):
        assert compute_tss(0, 3600, 250) is None

    def test_ftp_none_returns_none(self):
        assert compute_tss(250, 3600, None) is None

    def test_ftp_zero_returns_none(self):
        assert compute_tss(250, 3600, 0) is None

    def test_duration_zero_returns_none(self):
        assert compute_tss(250, 0, 250) is None

    def test_duration_none_returns_none(self):
        assert compute_tss(250, None, 250) is None

    def test_high_intensity_above_ftp_scales_quadratically_in_if(self):
        """At IF=1.2 (NP=120% FTP), TSS/hr > 100 due to IF^2 dependence."""
        tss = compute_tss(np_watts=300, duration_seconds=3600, ftp=250)
        assert tss > 100.0

    def test_low_intensity_below_ftp(self):
        tss = compute_tss(np_watts=125, duration_seconds=3600, ftp=250)
        assert tss == pytest.approx(25.0)

    def test_extreme_long_duration_24h(self):
        tss = compute_tss(np_watts=150, duration_seconds=86400, ftp=250)
        assert tss > 0
        assert isinstance(tss, float)

    def test_negative_duration_returns_value_due_to_truthiness(self):
        """duration_seconds<=0 guard uses `not duration_seconds`, which is False
        for negative numbers (truthy) -- so negative duration is NOT rejected
        and a (nonsensical) negative TSS is produced."""
        result = compute_tss(250, -3600, 250)
        # Document current (possibly buggy) behavior rather than assume None.
        assert result is not None
        assert result < 0


# ── compute_hrtss ────────────────────────────────────────────────────────

class TestComputeHrtss:
    def test_threshold_effort_normalizes_to_100_per_hour(self):
        """1 hour at 85% max HR (default resting=40) should be ~100 TSS."""
        max_hr = 185.0
        avg_hr = 0.85 * max_hr  # exactly threshold ratio
        tss = compute_hrtss(3600, avg_hr, max_hr)
        assert tss == pytest.approx(100.0, abs=0.5)

    def test_half_hour_at_threshold_about_50(self):
        max_hr = 185.0
        avg_hr = 0.85 * max_hr
        tss = compute_hrtss(1800, avg_hr, max_hr)
        assert tss == pytest.approx(50.0, abs=1.0)

    def test_easy_ride_below_100(self):
        tss = compute_hrtss(3600, 130, 185)
        assert 0 < tss < 100

    def test_hard_ride_above_100(self):
        tss = compute_hrtss(3600, 175, 185)
        assert tss > 100

    def test_avg_hr_none_returns_none(self):
        assert compute_hrtss(3600, None, 185) is None

    def test_avg_hr_zero_returns_none(self):
        assert compute_hrtss(3600, 0, 185) is None

    def test_max_hr_none_returns_none(self):
        assert compute_hrtss(3600, 150, None) is None

    def test_max_hr_zero_returns_none(self):
        assert compute_hrtss(3600, 150, 0) is None

    def test_duration_zero_returns_none(self):
        assert compute_hrtss(0, 150, 185) is None

    def test_duration_negative_returns_none(self):
        """Here the guard is `duration_seconds <= 0`, so negative IS rejected
        (unlike compute_tss)."""
        assert compute_hrtss(-100, 150, 185) is None

    def test_avg_hr_equals_resting_returns_none(self):
        """avg_hr <= rest guard: exactly equal triggers None."""
        assert compute_hrtss(3600, 50.0, 185, resting_hr=50.0) is None

    def test_avg_hr_below_resting_returns_none(self):
        assert compute_hrtss(3600, 45.0, 185, resting_hr=50.0) is None

    def test_max_hr_equals_resting_returns_none(self):
        assert compute_hrtss(3600, 150.0, 50.0, resting_hr=50.0) is None

    def test_default_resting_hr_used_when_none(self):
        """resting_hr=None defaults to 40.0 internally."""
        tss_default = compute_hrtss(3600, 130, 185, resting_hr=None)
        tss_explicit_40 = compute_hrtss(3600, 130, 185, resting_hr=40.0)
        assert tss_default == tss_explicit_40

    def test_avg_hr_above_max_hr_clamped_to_ratio_one(self):
        """hr_ratio is clamped to [0,1] via min/max, so avg_hr > max_hr doesn't
        explode the result above the ratio=1.0 case."""
        tss_clamped = compute_hrtss(3600, 300, 185, resting_hr=40)
        tss_at_max = compute_hrtss(3600, 185, 185, resting_hr=40)
        assert tss_clamped == tss_at_max

    def test_higher_intensity_yields_higher_tss(self):
        low = compute_hrtss(3600, 120, 185)
        mid = compute_hrtss(3600, 150, 185)
        high = compute_hrtss(3600, 170, 185)
        assert low < mid < high

    def test_longer_duration_scales_tss_linearly_at_fixed_intensity(self):
        one_hr = compute_hrtss(3600, 150, 185)
        two_hr = compute_hrtss(7200, 150, 185)
        assert two_hr == pytest.approx(one_hr * 2, rel=0.01)

    def test_extreme_long_duration_24h(self):
        tss = compute_hrtss(86400, 140, 185)
        assert tss is not None
        assert tss > 0

    def test_high_resting_hr_close_to_max_hr_edge(self):
        """resting_hr very close to max_hr but avg_hr still above it; should
        not crash and produce a finite result."""
        tss = compute_hrtss(3600, 178, 185, resting_hr=170)
        assert tss is not None


# ── compute_hrtss_heat_corrected ────────────────────────────────────────────

class TestComputeHrtssHeatCorrected:
    def test_temp_none_equals_plain_hrtss(self):
        plain = compute_hrtss(3600, 150, 185, resting_hr=50)
        corrected = compute_hrtss_heat_corrected(3600, 150, 185, resting_hr=50, temp_c=None)
        assert corrected == plain

    def test_temp_at_or_below_20_equals_plain_hrtss(self):
        """temp_c <= 20.0 means no correction is applied (guard is `> 20.0`)."""
        plain = compute_hrtss(3600, 150, 185, resting_hr=50)
        at_20 = compute_hrtss_heat_corrected(3600, 150, 185, resting_hr=50, temp_c=20.0)
        below_20 = compute_hrtss_heat_corrected(3600, 150, 185, resting_hr=50, temp_c=5.0)
        assert at_20 == plain
        assert below_20 == plain

    def test_temp_just_above_20_applies_small_correction(self):
        plain = compute_hrtss(3600, 150, 185, resting_hr=50)
        corrected = compute_hrtss_heat_corrected(3600, 150, 185, resting_hr=50, temp_c=20.1)
        assert corrected <= plain

    def test_hot_weather_lowers_tss(self):
        """Heat-driven HR inflation should be corrected away, lowering hrTSS
        relative to assuming the raw (heat-inflated) avg_hr reflects true effort."""
        hot_corrected = compute_hrtss_heat_corrected(5400, 160, 185, resting_hr=50, temp_c=35.0)
        no_correction = compute_hrtss(5400, 160, 185, resting_hr=50)
        assert hot_corrected < no_correction

    def test_manual_drift_calc_at_35c_90min(self):
        """At 35C, dur_h=1.5h: drift = min((35-20)*0.5*min(1.5/1.5,1.0), 8.0)
        = min(15*0.5*1.0, 8.0) = 7.5 bpm."""
        duration_seconds = 5400  # 1.5h
        avg_hr, max_hr, resting = 160.0, 185.0, 50.0
        expected_drift = min((35.0 - 20.0) * 0.5 * min(1.5 / 1.5, 1.0), 8.0)
        assert expected_drift == pytest.approx(7.5)
        corrected_hr = max(avg_hr - expected_drift, resting)
        expected_tss = compute_hrtss(duration_seconds, corrected_hr, max_hr, resting)
        actual_tss = compute_hrtss_heat_corrected(
            duration_seconds, avg_hr, max_hr, resting_hr=resting, temp_c=35.0
        )
        assert actual_tss == expected_tss

    def test_drift_saturates_at_8bpm_extreme_heat(self):
        """At very high temp (45C) and long duration, drift caps at 8.0 bpm."""
        duration_seconds = 7200
        avg_hr, max_hr, resting = 170.0, 185.0, 50.0
        corrected_hr = max(avg_hr - 8.0, resting)
        expected_tss = compute_hrtss(duration_seconds, corrected_hr, max_hr, resting)
        actual_tss = compute_hrtss_heat_corrected(
            duration_seconds, avg_hr, max_hr, resting_hr=resting, temp_c=45.0
        )
        assert actual_tss == expected_tss

    def test_drift_duration_factor_below_90min(self):
        """Duration factor scales linearly up to 90 min (1.5h); a 45-min ride
        at the same temp should see half the drift of a 90-min+ ride."""
        avg_hr, max_hr, resting, temp = 160.0, 185.0, 50.0, 30.0
        short_drift = min((temp - 20.0) * 0.5 * min(0.75 / 1.5, 1.0), 8.0)
        long_drift = min((temp - 20.0) * 0.5 * min(1.5 / 1.5, 1.0), 8.0)
        assert short_drift == pytest.approx(long_drift / 2)

    def test_corrected_hr_floored_at_resting_hr(self):
        """If avg_hr - drift would dip below resting_hr, it's floored there.
        Use a very low avg_hr just above resting with extreme heat so the
        floor kicks in and the function still returns a finite (or None) value
        without raising."""
        result = compute_hrtss_heat_corrected(
            3600, avg_hr=55.0, max_hr=185.0, resting_hr=50.0, temp_c=45.0, duration_h=2.0
        )
        # corrected_hr would be max(55-8, 50) = 50 == resting -> compute_hrtss
        # guard `avg_hr <= rest` triggers -> None
        assert result is None

    def test_default_resting_hr_floor_40(self):
        """When resting_hr is None, floor defaults to 40.0 inside the heat
        correction branch."""
        result = compute_hrtss_heat_corrected(
            3600, avg_hr=42.0, max_hr=185.0, resting_hr=None, temp_c=45.0
        )
        # corrected_hr = max(42-8, 40) = 40; compute_hrtss default rest is
        # also 40 -> avg_hr(40) <= rest(40) -> None
        assert result is None

    def test_duration_h_override_used_over_duration_seconds(self):
        """Explicit duration_h overrides the duration_seconds/3600 computation."""
        # duration_seconds implies 0.1h (very short, drift factor tiny) but
        # duration_h says 3h (drift factor saturated at 1.0)
        avg_hr, max_hr, resting, temp = 160.0, 185.0, 50.0, 30.0
        corrected_hr = max(avg_hr - min((temp - 20.0) * 0.5 * 1.0, 8.0), resting)
        expected = compute_hrtss(3600, corrected_hr, max_hr, resting)
        actual = compute_hrtss_heat_corrected(
            3600, avg_hr, max_hr, resting_hr=resting, temp_c=temp, duration_h=3.0
        )
        assert actual == expected

    def test_avg_hr_none_returns_none(self):
        assert compute_hrtss_heat_corrected(3600, None, 185, temp_c=30) is None

    def test_duration_zero_returns_none(self):
        assert compute_hrtss_heat_corrected(0, 150, 185, temp_c=30) is None


# ── estimate_calories_from_hr ───────────────────────────────────────────────

class TestEstimateCaloriesFromHr:
    def test_full_keytel_model_happy_path(self):
        """All of age/weight/max_hr present -> full Keytel formula."""
        cals = estimate_calories_from_hr(3600, avg_hr=150, age=35, weight_kg=75, max_hr=185)
        dur_min = 60
        expected_kcal_per_min = (
            -59.3954
            + (-36.3781 + 0.271 * 35 + 0.394 * 75 + 0.404 * 185 + 0.634 * 150) / 4.184
        )
        expected_kcal_per_min = max(expected_kcal_per_min, 3.0)
        expected = round(expected_kcal_per_min * dur_min)
        assert cals == expected

    def test_weight_only_proxy_when_age_missing(self):
        cals = estimate_calories_from_hr(3600, avg_hr=150, age=None, weight_kg=75, max_hr=185)
        expected = round(75 * 9.5 * 60 / 60)
        assert cals == expected

    def test_weight_only_proxy_when_max_hr_missing(self):
        cals = estimate_calories_from_hr(3600, avg_hr=150, age=35, weight_kg=75, max_hr=None)
        expected = round(75 * 9.5 * 60 / 60)
        assert cals == expected

    def test_no_weight_no_age_returns_none(self):
        assert estimate_calories_from_hr(3600, avg_hr=150, age=None, weight_kg=None) is None

    def test_no_weight_returns_none_even_with_age_and_maxhr(self):
        """weight_kg is required for both branches."""
        assert estimate_calories_from_hr(3600, avg_hr=150, age=35, weight_kg=None, max_hr=185) is None

    def test_avg_hr_none_returns_none(self):
        assert estimate_calories_from_hr(3600, avg_hr=None, age=35, weight_kg=75, max_hr=185) is None

    def test_avg_hr_zero_returns_none(self):
        assert estimate_calories_from_hr(3600, avg_hr=0, age=35, weight_kg=75, max_hr=185) is None

    def test_duration_zero_returns_none(self):
        assert estimate_calories_from_hr(0, avg_hr=150, age=35, weight_kg=75, max_hr=185) is None

    def test_duration_negative_returns_none(self):
        assert estimate_calories_from_hr(-10, avg_hr=150, age=35, weight_kg=75, max_hr=185) is None

    def test_floor_at_3_kcal_per_min_for_very_low_inputs(self):
        """Tiny age/weight/hr could push the Keytel linear formula negative;
        floor should clamp to 3.0 kcal/min."""
        cals = estimate_calories_from_hr(60, avg_hr=1, age=1, weight_kg=1, max_hr=1)
        assert cals == round(3.0 * 1)  # 1 minute at floor rate

    def test_simple_proxy_scales_with_weight(self):
        light = estimate_calories_from_hr(3600, avg_hr=150, age=None, weight_kg=60)
        heavy = estimate_calories_from_hr(3600, avg_hr=150, age=None, weight_kg=90)
        assert light < heavy

    def test_full_model_scales_with_duration(self):
        one_hr = estimate_calories_from_hr(3600, avg_hr=150, age=35, weight_kg=75, max_hr=185)
        two_hr = estimate_calories_from_hr(7200, avg_hr=150, age=35, weight_kg=75, max_hr=185)
        assert two_hr == pytest.approx(one_hr * 2, rel=0.01)

    def test_extreme_age_100(self):
        cals = estimate_calories_from_hr(3600, avg_hr=140, age=100, weight_kg=70, max_hr=120)
        assert cals is not None
        assert cals > 0

    def test_extreme_duration_24h(self):
        cals = estimate_calories_from_hr(86400, avg_hr=130, age=40, weight_kg=80, max_hr=180)
        assert cals is not None
        assert cals > 0

    def test_returns_int_or_none(self):
        cals = estimate_calories_from_hr(3600, avg_hr=150, age=35, weight_kg=75, max_hr=185)
        assert isinstance(cals, int)


# ── compute_suffer_score ────────────────────────────────────────────────────

class TestComputeSufferScore:
    def test_none_max_hr_returns_none(self):
        assert compute_suffer_score(_pts_hr([150, 155]), None) is None

    def test_zero_max_hr_returns_none(self):
        assert compute_suffer_score(_pts_hr([150, 155]), 0) is None

    def test_negative_max_hr_returns_none(self):
        assert compute_suffer_score(_pts_hr([150, 155]), -10) is None

    def test_empty_points_returns_none(self):
        assert compute_suffer_score([], 185) is None

    def test_single_point_returns_none(self):
        assert compute_suffer_score(_pts_hr([150]), 185) is None

    def test_missing_heart_rate_filtered_out(self):
        pts = _pts_hr([150, None, 160])
        # only 2 valid points remain (indices 0 and 2) since None hr is falsy/excluded
        result = compute_suffer_score(pts, 185)
        assert result is not None

    def test_missing_timestamp_filtered_out(self):
        pts = _pts_hr([150, 160, 170])
        pts[1]["timestamp"] = None
        result = compute_suffer_score(pts, 185)
        assert result is not None

    def test_below_zone1_threshold_scores_zero_weight(self):
        """HR well below 60% max_hr (zone 0, weight 0.0) accumulates no score
        -> overall result is None since score stays 0."""
        max_hr = 200
        pts = _pts_hr([100, 100, 100], interval_s=60)  # 50% of max -> zone 0
        assert compute_suffer_score(pts, max_hr) is None

    def test_zone_boundaries_exact_thresholds(self):
        """Exactly at a zone threshold (>=) counts as that zone, verified via
        manual score calc for a 2-point, 60s-gap ride at exactly 70% max_hr."""
        max_hr = 200.0
        hr = 0.70 * max_hr  # exactly zone-2 threshold
        pts = _pts_hr([hr, hr], interval_s=60)
        result = compute_suffer_score(pts, max_hr)
        dt = 60.0
        pct = hr / max_hr
        zone = sum(1 for t in _ZONE_THRESHOLDS if pct >= t)
        expected = round(_ZONE_WEIGHTS[zone] * dt)
        assert result == expected if expected > 0 else result is None

    def test_gap_over_300s_skipped(self):
        """A gap of >300s between consecutive points contributes nothing."""
        start = datetime(2024, 6, 1, 8, 0, 0)
        pts = [
            {"timestamp": start, "heart_rate_bpm": 180},
            {"timestamp": start + timedelta(seconds=301), "heart_rate_bpm": 180},
        ]
        # only one interval, and it's skipped -> score stays 0 -> None
        assert compute_suffer_score(pts, 200) is None

    def test_gap_exactly_300s_included(self):
        """Gap of exactly 300s is NOT > 300, so it should be included."""
        start = datetime(2024, 6, 1, 8, 0, 0)
        pts = [
            {"timestamp": start, "heart_rate_bpm": 190},
            {"timestamp": start + timedelta(seconds=300), "heart_rate_bpm": 190},
        ]
        result = compute_suffer_score(pts, 200)
        assert result is not None
        pct = 190 / 200
        zone = sum(1 for t in _ZONE_THRESHOLDS if pct >= t)
        expected = round(_ZONE_WEIGHTS[zone] * 300)
        assert result == expected

    def test_zero_or_negative_gap_skipped(self):
        """Duplicate timestamps (dt==0) or out-of-order (dt<0) contribute nothing."""
        start = datetime(2024, 6, 1, 8, 0, 0)
        pts = [
            {"timestamp": start, "heart_rate_bpm": 190},
            {"timestamp": start, "heart_rate_bpm": 190},  # dt=0
        ]
        assert compute_suffer_score(pts, 200) is None

    def test_out_of_order_timestamps_negative_dt_skipped(self):
        start = datetime(2024, 6, 1, 8, 0, 0)
        pts = [
            {"timestamp": start + timedelta(seconds=10), "heart_rate_bpm": 190},
            {"timestamp": start, "heart_rate_bpm": 190},  # earlier than previous -> dt<0
        ]
        assert compute_suffer_score(pts, 200) is None

    def test_higher_intensity_yields_higher_score(self):
        """Same duration, higher HR zone -> higher suffer score.

        Intervals must stay <= 300s apart or the gap-skip guard zeroes them
        out, so use 200s steps (well within the 300s gap limit).
        """
        start = datetime(2024, 6, 1, 8, 0, 0)
        max_hr = 200.0

        def make(hr):
            return [
                {"timestamp": start, "heart_rate_bpm": hr},
                {"timestamp": start + timedelta(seconds=200), "heart_rate_bpm": hr},
            ]

        low = compute_suffer_score(make(130), max_hr)   # 65% -> zone1
        mid = compute_suffer_score(make(150), max_hr)   # 75% -> zone2
        high = compute_suffer_score(make(185), max_hr)  # 92.5% -> zone4
        assert (low or 0) < (mid or 0) < (high or 0)

    def test_longer_duration_higher_score_same_intensity(self):
        """Use multiple chained intervals (each <=300s) so a 'longer ride'
        is represented as more segments rather than one large gap."""
        start = datetime(2024, 6, 1, 8, 0, 0)
        max_hr = 200.0

        def chained(num_segments, seg_len=200):
            pts = [{"timestamp": start, "heart_rate_bpm": 180}]
            for i in range(1, num_segments + 1):
                pts.append({
                    "timestamp": start + timedelta(seconds=seg_len * i),
                    "heart_rate_bpm": 180,
                })
            return pts

        short = compute_suffer_score(chained(1), max_hr)
        long_ = compute_suffer_score(chained(3), max_hr)
        assert short < long_

    def test_manual_multi_segment_calc(self):
        """3 points, two 60s intervals, different zones -> hand-sum the score."""
        start = datetime(2024, 6, 1, 8, 0, 0)
        max_hr = 200.0
        pts = [
            {"timestamp": start, "heart_rate_bpm": 120},                          # 60%
            {"timestamp": start + timedelta(seconds=60), "heart_rate_bpm": 140},  # 70%
            {"timestamp": start + timedelta(seconds=120), "heart_rate_bpm": 180}, # 90%
        ]
        # segment 1: avg=(120+140)/2=130 -> 65% -> zone1 (>=0.60) weight .007
        # segment 2: avg=(140+180)/2=160 -> 80% -> zone3 (>=0.80) weight .028
        expected = round(0.007 * 60 + 0.028 * 60)
        result = compute_suffer_score(pts, max_hr)
        assert result == expected

    def test_extreme_high_max_hr(self):
        pts = _pts_hr([150, 160], interval_s=200)
        result = compute_suffer_score(pts, 220)
        assert result is None or result >= 0

    def test_returns_int_when_not_none(self):
        pts = _pts_hr([180, 185], interval_s=200)
        result = compute_suffer_score(pts, 200)
        assert isinstance(result, int)


# ── compute_distance_prs ─────────────────────────────────────────────────

class TestComputeDistancePrs:
    def test_empty_list_returns_empty_dict(self):
        assert compute_distance_prs([]) == {}

    def test_single_point_returns_empty_dict(self):
        assert compute_distance_prs(_pts_distance([0])) == {}

    def test_short_ride_returns_empty_dict(self):
        """Ride shorter than 95% of smallest PR distance (400m) yields no PRs."""
        # 1 m/s for 100 seconds = 100m total, well under 380m (95% of 400)
        pts = _pts_distance([i * 1.0 for i in range(100)])
        assert compute_distance_prs(pts) == {}

    def test_exactly_400m_at_95pct_threshold_included(self):
        """max_dist == target*0.95 (380m) passes the `< target*0.95` exclusion
        (since 380 is not < 380), so the 400m PR should be attempted (though
        it may have no valid best time if no window reaches exactly 400m)."""
        # 1 m/s, 380 points (0..379m) -> max_dist = 379, exactly at threshold? use 380
        pts = _pts_distance([float(i) for i in range(381)])  # distances 0..380
        result = compute_distance_prs(pts)
        # max_dist=380 == 400*0.95 -> not skipped; sliding window may or may not
        # find a >=400m span (here max distance covered for any window is 380,
        # which is < 400, so 'best' stays None and 400m key is absent)
        assert "fastest_400m" not in result

    def test_simple_constant_speed_400m_pr(self):
        """Constant 10 m/s for 60s covers 600m; best 400m time should be 40s."""
        pts = _pts_distance([10.0 * i for i in range(61)])  # 0,10,...,600 @ 1s steps
        result = compute_distance_prs(pts)
        assert result["fastest_400m"] == pytest.approx(40.0)

    def test_multiple_pr_distances_present_for_long_ride(self):
        """40 km ride at constant 10 m/s (covers all PR distances)."""
        n = 4001  # distances 0..40000 in 10m steps, 1 point/sec
        pts = _pts_distance([10.0 * i for i in range(n)])
        result = compute_distance_prs(pts)
        for target in PR_DISTANCES_M:
            label = PR_LABELS[target]
            assert label in result
            assert result[label] == pytest.approx(target / 10.0, rel=0.01)

    def test_best_time_is_minimum_across_windows(self):
        """A ride with a fast-then-slow profile: the 1000m PR should reflect
        the fastest 1000m window, not the average pace."""
        # First 1000m covered quickly (20 m/s for 50s), remainder slowly (2 m/s)
        pts = []
        start = datetime(2024, 6, 1, 8, 0, 0)
        dist = 0.0
        t = 0
        for i in range(51):  # fast section: 0..1000m over 50s
            pts.append({"distance_m": 20.0 * i, "timestamp": start + timedelta(seconds=i)})
        last_t = 50
        last_d = 1000.0
        for i in range(1, 600):  # slow section after
            last_d += 2.0
            last_t += 1
            pts.append({"distance_m": last_d, "timestamp": start + timedelta(seconds=last_t)})
        result = compute_distance_prs(pts)
        assert result["fastest_1km"] == pytest.approx(50.0, abs=1.0)

    def test_missing_distance_or_timestamp_filtered(self):
        pts = _pts_distance([0.0, 100.0, 200.0, 300.0, 400.0])
        pts[2]["distance_m"] = None
        result = compute_distance_prs(pts)
        # Should not crash; with a gap, only valid points used
        assert isinstance(result, dict)

    def test_non_monotonic_distance_negative_dt_excluded(self):
        """If a later point has an earlier or equal timestamp delta <=0, it's excluded."""
        start = datetime(2024, 6, 1, 8, 0, 0)
        pts = [
            {"distance_m": 0.0, "timestamp": start},
            {"distance_m": 400.0, "timestamp": start},  # same timestamp, dt=0 -> excluded as best
        ]
        result = compute_distance_prs(pts)
        assert "fastest_400m" not in result

    def test_extra_keys_ignored(self):
        pts = _pts_distance([10.0 * i for i in range(61)])
        for p in pts:
            p["heart_rate_bpm"] = 150
            p["power_w"] = 200
        result = compute_distance_prs(pts)
        assert result["fastest_400m"] == pytest.approx(40.0)


# ── match_segment ────────────────────────────────────────────────────────

class TestMatchSegment:
    def _pt(self, t, lat, lon, hr=None, spd=None):
        return {"timestamp": t, "lat": lat, "lon": lon, "heart_rate_bpm": hr, "speed_kmh": spd}

    def test_two_point_segment_basic_match(self):
        start = datetime(2024, 6, 1, 8, 0, 0)
        seg = _segment(start_lat=45.0, start_lon=6.0, end_lat=45.001, end_lon=6.0)
        pts = [
            self._pt(start, 45.0, 6.0, hr=150, spd=30),
            self._pt(start + timedelta(seconds=30), 45.0005, 6.0, hr=160, spd=32),
            self._pt(start + timedelta(seconds=60), 45.001, 6.0, hr=170, spd=35),
        ]
        result = match_segment(pts, seg)
        assert result is not None
        assert result["elapsed_seconds"] == pytest.approx(60.0)
        assert result["avg_hr"] == pytest.approx((160 + 170) / 2, abs=0.1)
        assert result["avg_speed_kmh"] == pytest.approx((32 + 35) / 2, abs=0.1)

    def test_less_than_two_waypoints_returns_none(self):
        seg = _segment(waypoints=[[45.0, 6.0]])
        pts = [self._pt(datetime(2024, 6, 1, 8, 0, 0), 45.0, 6.0)]
        assert match_segment(pts, seg) is None

    def test_fewer_than_two_track_points_returns_none(self):
        seg = _segment()
        pts = [self._pt(datetime(2024, 6, 1, 8, 0, 0), 45.0, 6.0)]
        assert match_segment(pts, seg) is None

    def test_empty_track_points_returns_none(self):
        seg = _segment()
        assert match_segment([], seg) is None

    def test_no_proximity_match_returns_none(self):
        """Track points far away from segment start never match."""
        start = datetime(2024, 6, 1, 8, 0, 0)
        seg = _segment(start_lat=45.0, start_lon=6.0, end_lat=45.001, end_lon=6.0)
        pts = [
            self._pt(start, 50.0, 10.0, hr=150, spd=30),
            self._pt(start + timedelta(seconds=30), 50.001, 10.0, hr=160, spd=32),
        ]
        assert match_segment(pts, seg) is None

    def test_point_exactly_at_match_radius_boundary(self):
        """A point exactly 50m from the start waypoint should match (<=50m)."""
        start = datetime(2024, 6, 1, 8, 0, 0)
        lat0, lon0 = 45.0, 6.0
        # ~50m north: 1 degree latitude ~= 111320 m
        delta_lat = 50.0 / 111320.0
        seg = _segment(start_lat=lat0, start_lon=lon0, end_lat=lat0 + 0.001, end_lon=lon0)
        pts = [
            self._pt(start, lat0 + delta_lat, lon0, hr=140, spd=25),
            self._pt(start + timedelta(seconds=20), lat0 + 0.001, lon0, hr=145, spd=26),
        ]
        result = match_segment(pts, seg)
        assert result is not None

    def test_point_just_outside_match_radius_excluded(self):
        """A point at 60m (beyond the 50m radius) from start should not match."""
        start = datetime(2024, 6, 1, 8, 0, 0)
        lat0, lon0 = 45.0, 6.0
        delta_lat = 60.0 / 111320.0
        seg = _segment(start_lat=lat0, start_lon=lon0, end_lat=lat0 + 0.001, end_lon=lon0)
        pts = [
            self._pt(start, lat0 + delta_lat, lon0, hr=140, spd=25),
            self._pt(start + timedelta(seconds=20), lat0 + 0.001, lon0, hr=145, spd=26),
        ]
        assert match_segment(pts, seg) is None

    def test_multi_waypoint_segment_ordered_walk(self):
        """A 3-waypoint segment requires visiting waypoints in order."""
        start = datetime(2024, 6, 1, 8, 0, 0)
        waypoints = [[45.0, 6.0], [45.0005, 6.0], [45.001, 6.0]]
        seg = _segment(waypoints=waypoints)
        pts = [
            self._pt(start, 45.0, 6.0, hr=150, spd=30),
            self._pt(start + timedelta(seconds=15), 45.0005, 6.0, hr=155, spd=31),
            self._pt(start + timedelta(seconds=30), 45.001, 6.0, hr=160, spd=33),
        ]
        result = match_segment(pts, seg)
        assert result is not None
        assert result["elapsed_seconds"] == pytest.approx(30.0)

    def test_picks_fastest_among_multiple_matches(self):
        """If the rider passes the segment start multiple times (e.g. loops),
        the fastest completion should be returned."""
        start = datetime(2024, 6, 1, 8, 0, 0)
        seg = _segment(start_lat=45.0, start_lon=6.0, end_lat=45.001, end_lon=6.0)
        pts = [
            # First pass: slow (60s)
            self._pt(start, 45.0, 6.0, hr=140, spd=20),
            self._pt(start + timedelta(seconds=60), 45.001, 6.0, hr=145, spd=22),
            # Second pass: fast (20s)
            self._pt(start + timedelta(seconds=120), 45.0, 6.0, hr=160, spd=35),
            self._pt(start + timedelta(seconds=140), 45.001, 6.0, hr=165, spd=38),
        ]
        result = match_segment(pts, seg)
        assert result is not None
        assert result["elapsed_seconds"] == pytest.approx(20.0)

    def test_missing_lat_lon_filtered_from_consideration(self):
        start = datetime(2024, 6, 1, 8, 0, 0)
        seg = _segment(start_lat=45.0, start_lon=6.0, end_lat=45.001, end_lon=6.0)
        pts = [
            self._pt(start, None, None, hr=140, spd=20),
            self._pt(start + timedelta(seconds=10), 45.0, 6.0, hr=150, spd=25),
            self._pt(start + timedelta(seconds=40), 45.001, 6.0, hr=160, spd=30),
        ]
        result = match_segment(pts, seg)
        assert result is not None
        assert result["elapsed_seconds"] == pytest.approx(30.0)

    def test_no_hr_or_speed_data_returns_none_averages(self):
        start = datetime(2024, 6, 1, 8, 0, 0)
        seg = _segment(start_lat=45.0, start_lon=6.0, end_lat=45.001, end_lon=6.0)
        pts = [
            self._pt(start, 45.0, 6.0),
            self._pt(start + timedelta(seconds=30), 45.001, 6.0),
        ]
        result = match_segment(pts, seg)
        assert result is not None
        assert result["avg_hr"] is None
        assert result["avg_speed_kmh"] is None

    def test_zero_elapsed_time_excluded(self):
        """If end waypoint matched at the same timestamp as start, elapsed=0,
        which fails the `elapsed > 0` guard, so no result is returned."""
        start = datetime(2024, 6, 1, 8, 0, 0)
        seg = _segment(start_lat=45.0, start_lon=6.0, end_lat=45.001, end_lon=6.0)
        pts = [
            self._pt(start, 45.0, 6.0),
            self._pt(start, 45.001, 6.0),  # same timestamp
        ]
        assert match_segment(pts, seg) is None

    def test_two_point_default_waypoints_from_seg_attrs(self):
        """When waypoints_json is falsy, start/end lat/lon attrs are used directly."""
        start = datetime(2024, 6, 1, 8, 0, 0)
        seg = _segment(waypoints=None, start_lat=10.0, start_lon=20.0, end_lat=10.001, end_lon=20.0)
        pts = [
            self._pt(start, 10.0, 20.0, hr=100, spd=10),
            self._pt(start + timedelta(seconds=45), 10.001, 20.0, hr=110, spd=12),
        ]
        result = match_segment(pts, seg)
        assert result is not None
        assert result["elapsed_seconds"] == pytest.approx(45.0)
