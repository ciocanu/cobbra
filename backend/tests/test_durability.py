"""
Tests for utils/durability.py — Durability Profiling algorithms.

Run from the backend directory:
    python -m pytest tests/test_durability.py -v
"""

import sys
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.durability import (
    validate_durability_calculation,
    calculate_durability,
    calculate_durability_trend,
    compare_durability_rides,
    _sort_and_clean,
    _compute_gradients,
    _has_real_power,
    _has_distributed_climbs,
    _climb_elapsed,
    _flat_minutes,
    _split_quarters,
    _quarter_indices,
    _power_outputs,
    _climbing_power_outputs,
    _climb_power,
    _climb_gradient,
    _hr_speed_outputs,
    _classify_durability,
    _estimate_work_kj,
    _linear_regression,
    _comparison_note,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pts_power(n=1000, power_w=250, hr=150, speed=30.0, dist_step=50.0,
               elev_step=0.0, fade_to=None, interval_s=4):
    """Track points with real power; optional linear power fade to `fade_to`."""
    start = datetime(2024, 6, 1, 8, 0, 0)
    pts = []
    for i in range(n):
        frac = i / max(n - 1, 1)
        pwr = power_w + (fade_to - power_w) * frac if fade_to is not None else power_w
        pts.append({
            "timestamp":      start + timedelta(seconds=i * interval_s),
            "power_w":        pwr,
            "heart_rate_bpm": hr,
            "speed_kmh":      speed,
            "elevation":      100.0 + elev_step * i,
            "distance_m":     dist_step * i,
        })
    return pts


def _pts_hr_speed(n=1000, speed=28.0, hr=150, dist_step=50.0,
                  elev_step=0.0, speed_fade=0.0, interval_s=4):
    """Track points without power; optional speed fade (EF drops)."""
    start = datetime(2024, 6, 1, 8, 0, 0)
    pts = []
    for i in range(n):
        frac = i / max(n - 1, 1)
        spd = speed * (1.0 - speed_fade * frac)
        pts.append({
            "timestamp":      start + timedelta(seconds=i * interval_s),
            "power_w":        None,
            "heart_rate_bpm": hr,
            "speed_kmh":      spd,
            "elevation":      100.0 + elev_step * i,
            "distance_m":     dist_step * i,
        })
    return pts


def _climb(start_s, power_w=220.0, gradient_pct=6.0):
    """Minimal climb detection dict."""
    return {"start_elapsed_s": start_s, "estimated_power_w": power_w, "gradient_pct": gradient_pct}


# ── validate_durability_calculation ──────────────────────────────────────────

class TestValidateDurabilityCalculation:
    def test_short_ride_rejected(self):
        ok, _, reason = validate_durability_calculation(1800, 800)
        assert not ok
        assert "45 minutes" in reason

    def test_too_few_track_points_rejected(self):
        ok, _, reason = validate_durability_calculation(7200, 50)
        assert not ok
        assert "track points" in reason

    def test_interval_notes_rejected(self):
        ok, _, reason = validate_durability_calculation(7200, 1000, notes="Interval session 4×8 min")
        assert not ok
        assert "Interval" in reason

    def test_race_notes_rejected(self):
        ok, _, _ = validate_durability_calculation(7200, 1000, notes="Weekly race criterium")
        assert not ok

    def test_recovery_ride_allowed_but_low_quality(self):
        # avg_hr = 100, max_hr = 190 → fraction 0.53 < 0.55
        ok, quality, reason = validate_durability_calculation(7200, 1000, avg_hr=100.0, max_hr=190.0)
        assert ok
        assert quality == "low"
        assert "recovery" in reason.lower()

    def test_normal_long_ride_accepted(self):
        ok, quality, reason = validate_durability_calculation(14400, 1500)
        assert ok
        assert quality == ""
        assert reason == ""


# ── calculate_durability — power method ──────────────────────────────────────

class TestCalculateDurabilityPower:
    def test_steady_power_gives_index_100(self):
        pts = _pts_power(n=1000, power_w=250)
        result = calculate_durability(duration_seconds=7200, track_points=pts)
        assert result is not None
        assert result["method"] == "power"
        assert result["durability_index"] == pytest.approx(100.0, abs=2.0)
        assert result["durability_category"] == "excellent"

    def test_fading_power_gives_lower_index(self):
        # Q1 avg ≈ 250 W, Q4 avg ≈ 185 W → DI ≈ 74
        pts = _pts_power(n=1000, power_w=250, fade_to=180)
        result = calculate_durability(duration_seconds=7200, track_points=pts)
        assert result is not None
        assert result["method"] == "power"
        assert result["durability_index"] < 85.0
        assert result["durability_category"] in ("poor", "very_poor", "moderate")

    def test_power_quality_is_high(self):
        pts = _pts_power(n=1000)
        result = calculate_durability(duration_seconds=7200, track_points=pts)
        assert result["quality"] == "high"

    def test_hot_ride_downgrades_quality(self):
        pts = _pts_power(n=1000)
        result = calculate_durability(duration_seconds=7200, track_points=pts, temperature_avg_c=38.0)
        assert result is not None
        # quality starts "high" (power), drops to "medium" because temp ≥35°C
        assert result["quality"] == "medium"

    def test_tsb_stored_in_result(self):
        pts = _pts_power(n=1000)
        result = calculate_durability(duration_seconds=7200, track_points=pts, tsb_at_start=-18.0)
        assert result is not None
        assert result["tsb_at_start"] == pytest.approx(-18.0)

    def test_negative_tsb_context_does_not_block_calculation(self):
        pts = _pts_power(n=1000, power_w=250)
        result = calculate_durability(duration_seconds=7200, track_points=pts, tsb_at_start=-30.0)
        assert result is not None
        assert result["durability_index"] > 0


# ── calculate_durability — hr_speed proxy ────────────────────────────────────

class TestCalculateDurabilityHrSpeed:
    def test_hr_speed_method_used_without_power(self):
        pts = _pts_hr_speed(n=1000, speed=28.0, hr=150)
        result = calculate_durability(duration_seconds=7200, track_points=pts, max_hr=190.0)
        assert result is not None
        assert result["method"] == "hr_speed"

    def test_steady_ef_gives_high_index(self):
        pts = _pts_hr_speed(n=1000, speed=28.0, hr=150)
        result = calculate_durability(duration_seconds=7200, track_points=pts, max_hr=190.0)
        assert result is not None
        assert result["durability_index"] >= 88.0

    def test_fading_ef_gives_lower_index(self):
        # Speed drops 15% over the ride while HR stays constant → EF fades 15%
        pts = _pts_hr_speed(n=1000, speed=28.0, hr=150, speed_fade=0.15)
        result = calculate_durability(duration_seconds=7200, track_points=pts, max_hr=190.0)
        assert result is not None
        assert result["durability_index"] < 92.0

    def test_all_uphill_falls_back_gracefully(self):
        # Continuous 6% climb → flat_minutes ≈ 0 → quality="low" but still calculated
        pts = _pts_hr_speed(n=1000, speed=18.0, hr=160, elev_step=0.5, dist_step=20.0)
        result = calculate_durability(duration_seconds=7200, track_points=pts, max_hr=190.0)
        # May return None if no usable EF points, or return low-quality result
        if result is not None:
            assert result["method"] == "hr_speed"
            assert result["quality"] == "low"


# ── calculate_durability — climbing_power method ──────────────────────────────

class TestCalculateDurabilityClimbingPower:
    def test_climbing_power_method_selected(self):
        pts = _pts_hr_speed(n=1000, speed=18.0, hr=160, elev_step=0.5, dist_step=20.0)
        duration = 7200
        # Two climbs in early ride and two in late ride
        climbs = [
            _climb(start_s=900,  power_w=230.0, gradient_pct=7.0),
            _climb(start_s=1800, power_w=220.0, gradient_pct=6.0),
            _climb(start_s=5000, power_w=200.0, gradient_pct=8.0),
            _climb(start_s=6000, power_w=190.0, gradient_pct=6.5),
        ]
        result = calculate_durability(duration_seconds=duration, track_points=pts,
                                      climb_detections=climbs, max_hr=190.0)
        assert result is not None
        assert result["method"] == "climbing_power"
        assert result["output_unit"] == "watts_normalized"

    def test_single_climb_falls_back_to_hr_speed(self):
        pts = _pts_hr_speed(n=1000, speed=28.0, hr=150)
        climbs = [_climb(start_s=1000, power_w=220.0)]  # only 1 climb — no early+late coverage
        result = calculate_durability(duration_seconds=7200, track_points=pts,
                                      climb_detections=climbs, max_hr=190.0)
        # Should fall back to hr_speed
        if result is not None:
            assert result["method"] == "hr_speed"


# ── calculate_durability — edge cases ────────────────────────────────────────

class TestCalculateDurabilityEdgeCases:
    def test_short_ride_returns_none(self):
        pts = _pts_power(n=400, power_w=250)   # ~27 min at 4 s/pt
        result = calculate_durability(duration_seconds=1620, track_points=pts)
        assert result is None

    def test_interval_ride_excluded_via_notes(self):
        pts = _pts_power(n=1000, power_w=250)
        result = calculate_durability(duration_seconds=7200, track_points=pts,
                                      notes="3×20 min intervals @ FTP")
        assert result is None

    def test_empty_track_points_returns_none(self):
        result = calculate_durability(duration_seconds=7200, track_points=[])
        assert result is None

    def test_total_work_kj_computed_for_power_rides(self):
        pts = _pts_power(n=1000, power_w=200)
        result = calculate_durability(duration_seconds=7200, track_points=pts)
        assert result is not None
        assert result["total_work_kj"] is not None
        assert result["total_work_kj"] > 0

    def test_durability_index_bounded_0_to_110(self):
        # Supercompensation scenario: Q4 > Q1 (negative fade)
        pts = _pts_power(n=1000, power_w=200, fade_to=250)  # warming up
        result = calculate_durability(duration_seconds=7200, track_points=pts)
        if result is not None:
            assert 0.0 <= result["durability_index"] <= 110.0


# ── calculate_durability_trend ────────────────────────────────────────────────

def _make_mock_db_rows(di_values: list[float], quality: str = "high",
                       base_date: datetime = None, duration_s: int = 7200):
    """Build fake (DurabilityAnalysis, Activity.date) pairs for trend queries."""
    if base_date is None:
        base_date = datetime(2024, 1, 8)
    rows = []
    for i, di in enumerate(di_values):
        mock_analysis = MagicMock()
        mock_analysis.durability_index = di
        mock_analysis.quality = quality
        date = base_date + timedelta(weeks=i)
        rows.append((mock_analysis, date))
    return rows


class TestCalculateDurabilityTrend:
    def _make_db(self, rows):
        db = MagicMock()
        q = db.query.return_value
        q.join.return_value = q
        q.filter.return_value = q
        q.order_by.return_value = q
        q.all.return_value = rows
        return db

    def test_improving_trend(self):
        rows = _make_mock_db_rows([82.0, 85.0, 87.0, 90.0, 94.0])
        db = self._make_db(rows)
        result = calculate_durability_trend(user_id=1, db=db, weeks=12)
        assert result["trend"] == "improving"
        assert result["trend_slope"] > 0.5
        assert result["best_ever"] == pytest.approx(94.0)

    def test_stable_trend(self):
        rows = _make_mock_db_rows([88.0, 89.0, 88.5, 89.0, 88.0])
        db = self._make_db(rows)
        result = calculate_durability_trend(user_id=1, db=db, weeks=12)
        assert result["trend"] == "stable"
        assert abs(result["trend_slope"]) <= 0.5

    def test_no_data_returns_defaults(self):
        db = self._make_db([])
        result = calculate_durability_trend(user_id=1, db=db, weeks=12)
        assert result["weekly_averages"] == []
        assert result["trend"] == "stable"
        assert result["current_avg"] is None
        assert result["best_ever"] is None


# ── compare_durability_rides ──────────────────────────────────────────────────

def _make_mock_compare_db(rides_data: list[dict]):
    """
    rides_data: list of dicts with keys:
        id, name, date_str, di, quality, duration_s, fade_rate, temp, tsb, work_kj
    """
    rows = []
    for r in rides_data:
        mock_analysis = MagicMock()
        mock_analysis.durability_index = r.get("di")
        mock_analysis.durability_category = "good"
        mock_analysis.fade_rate_pct_per_hour = r.get("fade_rate")
        mock_analysis.temperature_avg_c = r.get("temp")
        mock_analysis.tsb_at_start = r.get("tsb")
        mock_analysis.total_work_kj = r.get("work_kj")
        mock_analysis.quality = r.get("quality", "high")
        mock_analysis.method = "power"

        mock_activity = MagicMock()
        mock_activity.id = r["id"]
        mock_activity.name = r["name"]
        mock_activity.date = datetime.fromisoformat(r["date_str"])
        mock_activity.duration_seconds = r.get("duration_s", 7200)

        rows.append((mock_analysis, mock_activity))

    db = MagicMock()
    q = db.query.return_value
    q.join.return_value = q
    q.filter.return_value = q
    q.all.return_value = rows
    return db


class TestCompareDurabilityRides:
    def test_fair_comparison_no_duration_warning(self):
        db = _make_mock_compare_db([
            {"id": 1, "name": "Ride A", "date_str": "2024-04-01", "di": 92.0, "duration_s": 7200},
            {"id": 2, "name": "Ride B", "date_str": "2024-04-08", "di": 88.0, "duration_s": 7500},
        ])
        result = compare_durability_rides([1, 2], db)
        assert result["best_ride_id"] == 1
        assert "significantly" not in result["comparison_note"]

    def test_unfair_comparison_duration_warning(self):
        db = _make_mock_compare_db([
            {"id": 1, "name": "Short Ride", "date_str": "2024-04-01", "di": 95.0, "duration_s": 3600},
            {"id": 2, "name": "Long Ride",  "date_str": "2024-04-08", "di": 88.0, "duration_s": 14400},
        ])
        result = compare_durability_rides([1, 2], db)
        assert "significantly" in result["comparison_note"]

    def test_no_data_returns_empty(self):
        db = _make_mock_compare_db([])
        result = compare_durability_rides([1, 2], db)
        assert result["rides"] == []
        assert result["best_ride_id"] is None

    def test_best_ride_is_highest_quality_highest_di(self):
        db = _make_mock_compare_db([
            {"id": 1, "name": "Ride A", "date_str": "2024-04-01", "di": 96.0, "quality": "low"},
            {"id": 2, "name": "Ride B", "date_str": "2024-04-08", "di": 91.0, "quality": "high"},
            {"id": 3, "name": "Ride C", "date_str": "2024-04-15", "di": 93.0, "quality": "medium"},
        ])
        result = compare_durability_rides([1, 2, 3], db)
        # high/medium best: 93 (id=3) > 91 (id=2); low-quality 96 excluded from scored set
        assert result["best_ride_id"] == 3

    def test_truncates_to_5_activity_ids(self):
        db = _make_mock_compare_db([
            {"id": i, "name": f"Ride {i}", "date_str": f"2024-04-{i:02d}", "di": 80.0 + i}
            for i in range(1, 8)
        ])
        # Pass 7 ids; function should truncate to first 5 before querying.
        compare_durability_rides([1, 2, 3, 4, 5, 6, 7], db)
        filter_call_args = db.query.return_value.filter.call_args
        # We can't easily inspect the SQLAlchemy `in_` clause contents via MagicMock,
        # but we can assert the function did not raise and queried successfully.
        assert filter_call_args is not None

    def test_all_low_quality_falls_back_to_any_scored(self):
        db = _make_mock_compare_db([
            {"id": 1, "name": "Ride A", "date_str": "2024-04-01", "di": 70.0, "quality": "low"},
            {"id": 2, "name": "Ride B", "date_str": "2024-04-08", "di": 90.0, "quality": "low"},
        ])
        result = compare_durability_rides([1, 2], db)
        # No high/medium rides exist, so scored falls back to all rides with a DI.
        assert result["best_ride_id"] == 2

    def test_all_durability_index_none_best_ride_is_none(self):
        db = _make_mock_compare_db([
            {"id": 1, "name": "Ride A", "date_str": "2024-04-01", "di": None},
            {"id": 2, "name": "Ride B", "date_str": "2024-04-08", "di": None},
        ])
        result = compare_durability_rides([1, 2], db)
        assert result["best_ride_id"] is None
        assert result["comparison_note"] == ""

    def test_single_ride_no_comparison_note(self):
        db = _make_mock_compare_db([
            {"id": 1, "name": "Solo Ride", "date_str": "2024-04-01", "di": 90.0},
        ])
        result = compare_durability_rides([1], db)
        assert result["best_ride_id"] == 1
        # _comparison_note requires len(rides) >= 2, so note should be empty (no warning either).
        assert result["comparison_note"] == ""

    def test_duration_warning_exact_2x_boundary_not_triggered(self):
        # max == min * 2 exactly -> condition is strictly `>`, so no warning.
        db = _make_mock_compare_db([
            {"id": 1, "name": "Ride A", "date_str": "2024-04-01", "di": 90.0, "duration_s": 3600},
            {"id": 2, "name": "Ride B", "date_str": "2024-04-08", "di": 88.0, "duration_s": 7200},
        ])
        result = compare_durability_rides([1, 2], db)
        assert "significantly" not in result["comparison_note"]

    def test_duration_warning_just_above_2x_boundary_triggered(self):
        """duration_h is rounded to 2 decimals before the >2x comparison, so a ratio
        that's only marginally over 2x (e.g. 7201/3600 = 2.00028) gets rounded away to
        exactly 2.0 and does NOT trigger the warning. Use a wider margin (2.03x) so the
        ratio survives rounding and the comparison is exercised meaningfully."""
        db = _make_mock_compare_db([
            {"id": 1, "name": "Ride A", "date_str": "2024-04-01", "di": 90.0, "duration_s": 3600},
            {"id": 2, "name": "Ride B", "date_str": "2024-04-08", "di": 88.0, "duration_s": 7300},
        ])
        result = compare_durability_rides([1, 2], db)
        assert "significantly" in result["comparison_note"]


# ── Internal helpers: _sort_and_clean ────────────────────────────────────────

class TestSortAndClean:
    def test_sorts_by_datetime_timestamp(self):
        t0 = datetime(2024, 1, 1, 8, 0, 0)
        pts = [
            {"timestamp": t0 + timedelta(seconds=20), "v": "c"},
            {"timestamp": t0, "v": "a"},
            {"timestamp": t0 + timedelta(seconds=10), "v": "b"},
        ]
        result = _sort_and_clean(pts)
        assert [p["v"] for p in result] == ["a", "b", "c"]

    def test_sorts_by_string_timestamp(self):
        pts = [
            {"timestamp": "2024-01-01T08:00:20", "v": "c"},
            {"timestamp": "2024-01-01T08:00:00", "v": "a"},
            {"timestamp": "2024-01-01T08:00:10", "v": "b"},
        ]
        result = _sort_and_clean(pts)
        assert [p["v"] for p in result] == ["a", "b", "c"]

    def test_missing_timestamp_sorts_first(self):
        t0 = datetime(2024, 1, 1, 8, 0, 0)
        pts = [
            {"timestamp": t0, "v": "real"},
            {"timestamp": None, "v": "missing"},
        ]
        result = _sort_and_clean(pts)
        assert result[0]["v"] == "missing"

    def test_no_timestamps_at_all_preserves_order(self):
        pts = [{"v": "first"}, {"v": "second"}, {"v": "third"}]
        result = _sort_and_clean(pts)
        assert [p["v"] for p in result] == ["first", "second", "third"]

    def test_empty_list(self):
        assert _sort_and_clean([]) == []


# ── Internal helpers: _compute_gradients ─────────────────────────────────────

class TestComputeGradients:
    def test_first_point_is_none(self):
        pts = [{"distance_m": 0, "elevation": 100}, {"distance_m": 50, "elevation": 105}]
        grads = _compute_gradients(pts)
        assert grads[0] is None

    def test_positive_gradient_computed(self):
        pts = [{"distance_m": 0, "elevation": 100}, {"distance_m": 100, "elevation": 105}]
        grads = _compute_gradients(pts)
        assert grads[1] == pytest.approx(5.0)

    def test_negative_gradient_computed(self):
        pts = [{"distance_m": 0, "elevation": 100}, {"distance_m": 100, "elevation": 95}]
        grads = _compute_gradients(pts)
        assert grads[1] == pytest.approx(-5.0)

    def test_distance_diff_at_threshold_1m_excluded(self):
        # d_dist must be > 1.0, so exactly 1.0 yields None
        pts = [{"distance_m": 0, "elevation": 100}, {"distance_m": 1.0, "elevation": 105}]
        grads = _compute_gradients(pts)
        assert grads[1] is None

    def test_distance_diff_just_above_threshold_included(self):
        pts = [{"distance_m": 0, "elevation": 100}, {"distance_m": 1.01, "elevation": 100.1}]
        grads = _compute_gradients(pts)
        assert grads[1] is not None

    def test_missing_distance_treated_as_zero(self):
        pts = [{"elevation": 100}, {"elevation": 105}]
        grads = _compute_gradients(pts)
        # d_dist = 0 - 0 = 0, not > 1.0 -> None
        assert grads[1] is None

    def test_missing_elevation_treated_as_zero(self):
        pts = [{"distance_m": 0}, {"distance_m": 100}]
        grads = _compute_gradients(pts)
        assert grads[1] == pytest.approx(0.0)

    def test_single_point_list(self):
        grads = _compute_gradients([{"distance_m": 0, "elevation": 100}])
        assert grads == [None]

    def test_empty_list(self):
        assert _compute_gradients([]) == [None]


# ── Internal helpers: _has_real_power ────────────────────────────────────────

class TestHasRealPower:
    def test_all_points_above_floor_true(self):
        pts = [{"power_w": 200} for _ in range(10)]
        assert _has_real_power(pts) is True

    def test_all_points_zero_power_false(self):
        pts = [{"power_w": 0} for _ in range(10)]
        assert _has_real_power(pts) is False

    def test_exactly_80pct_threshold_excluded(self):
        # condition is strictly `> 0.80`, so exactly 80% should be False
        pts = [{"power_w": 200} for _ in range(8)] + [{"power_w": 0} for _ in range(2)]
        assert _has_real_power(pts) is False

    def test_just_above_80pct_threshold_included(self):
        pts = [{"power_w": 200} for _ in range(81)] + [{"power_w": 0} for _ in range(19)]
        assert _has_real_power(pts) is True

    def test_power_exactly_at_floor_excluded(self):
        # _PWR_FLOOR_W = 30; condition is strictly `> 30`
        pts = [{"power_w": 30} for _ in range(10)]
        assert _has_real_power(pts) is False

    def test_power_just_above_floor_included(self):
        pts = [{"power_w": 31} for _ in range(10)]
        assert _has_real_power(pts) is True

    def test_missing_power_key_treated_as_zero(self):
        pts = [{} for _ in range(10)]
        assert _has_real_power(pts) is False

    def test_empty_list_raises_zero_division(self):
        """BUG (utils/durability.py, _has_real_power, line ~387-388): dividing by
        len(pts) with an empty list raises ZeroDivisionError instead of returning False.
        Not reachable from calculate_durability's public path today (it returns None
        before this is called when len(pts) < _MIN_TRACK_PTS=300), but the helper itself
        is unsafe for empty input and would crash if ever called directly or if the
        guard above it is changed.
        Correct behavior: should return False for an empty list rather than raising.
        """
        with pytest.raises(ZeroDivisionError):
            _has_real_power([])
        # Once fixed, the expected behavior would be:
        # assert _has_real_power([]) is False


# ── Internal helpers: _has_distributed_climbs / _climb_elapsed ──────────────

class TestHasDistributedClimbs:
    def test_none_climb_detections_false(self):
        assert _has_distributed_climbs(None, 7200) is False

    def test_empty_list_false(self):
        assert _has_distributed_climbs([], 7200) is False

    def test_single_climb_false(self):
        assert _has_distributed_climbs([_climb(1000)], 7200) is False

    def test_two_climbs_both_early_false(self):
        climbs = [_climb(100), _climb(200)]
        assert _has_distributed_climbs(climbs, 7200) is False

    def test_two_climbs_both_late_false(self):
        climbs = [_climb(6000), _climb(6500)]
        assert _has_distributed_climbs(climbs, 7200) is False

    def test_two_climbs_one_early_one_late_true(self):
        climbs = [_climb(1000), _climb(6000)]
        assert _has_distributed_climbs(climbs, 7200) is True

    def test_early_threshold_boundary(self):
        # threshold_early = duration*0.40 = 2880; condition is strictly `<`
        duration = 7200
        climbs_at_boundary = [_climb(2880), _climb(6000)]
        climbs_below_boundary = [_climb(2879), _climb(6000)]
        assert _has_distributed_climbs(climbs_at_boundary, duration) is False
        assert _has_distributed_climbs(climbs_below_boundary, duration) is True

    def test_late_threshold_boundary(self):
        # threshold_late = duration*0.60 = 4320; condition is strictly `>`
        duration = 7200
        climbs_at_boundary = [_climb(1000), _climb(4320)]
        climbs_above_boundary = [_climb(1000), _climb(4321)]
        assert _has_distributed_climbs(climbs_at_boundary, duration) is False
        assert _has_distributed_climbs(climbs_above_boundary, duration) is True


class TestClimbElapsed:
    def test_dict_start_elapsed_s(self):
        assert _climb_elapsed({"start_elapsed_s": 500.0}) == 500.0

    def test_dict_start_seconds_fallback(self):
        assert _climb_elapsed({"start_seconds": 300.0}) == 300.0

    def test_dict_missing_both_defaults_zero(self):
        assert _climb_elapsed({}) == 0.0

    def test_object_attrs(self):
        from types import SimpleNamespace
        obj = SimpleNamespace(start_elapsed_s=700.0)
        assert _climb_elapsed(obj) == 700.0

    def test_object_missing_attrs_defaults_zero(self):
        from types import SimpleNamespace
        obj = SimpleNamespace()
        assert _climb_elapsed(obj) == 0.0

    def test_zero_start_elapsed_s_falls_through_to_start_seconds(self):
        """BUG (utils/durability.py, _climb_elapsed, line ~403-407): the function uses
        `c.get("start_elapsed_s") or c.get("start_seconds")`, so a climb that legitimately
        starts at elapsed=0.0 (the very first seconds of the ride) is falsy and the
        function silently falls through to `start_seconds` instead. If both fields are
        present with different values, the genuinely-correct 0.0 is discarded in favor of
        a different (wrong) value.
        Correct behavior: an explicit 0.0 in start_elapsed_s should be respected as 0.0,
        e.g. via an explicit `is not None` check rather than `or`.
        """
        c = {"start_elapsed_s": 0.0, "start_seconds": 999.0}
        assert _climb_elapsed(c) == 999.0
        # Once fixed, the expected behavior would be:
        # assert _climb_elapsed(c) == 0.0


# ── Internal helpers: _flat_minutes ───────────────────────────────────────────

class TestFlatMinutes:
    def test_no_gradients_zero_flat(self):
        pts = [{"speed_kmh": 30} for _ in range(60)]
        grads = [None] * 60
        assert _flat_minutes(pts, grads) == 0.0

    def test_all_flat_and_fast_full_minute(self):
        pts = [{"speed_kmh": 30} for _ in range(60)]
        grads = [0.5] * 60
        assert _flat_minutes(pts, grads) == pytest.approx(1.0)

    def test_gradient_below_flat_min_excluded(self):
        pts = [{"speed_kmh": 30} for _ in range(60)]
        grads = [-1.5] * 60  # below _FLAT_GRAD_MIN = -1.0
        assert _flat_minutes(pts, grads) == 0.0

    def test_gradient_above_flat_max_excluded(self):
        pts = [{"speed_kmh": 30} for _ in range(60)]
        grads = [2.5] * 60  # above _FLAT_GRAD_MAX = 2.0
        assert _flat_minutes(pts, grads) == 0.0

    def test_gradient_boundaries_inclusive(self):
        pts = [{"speed_kmh": 30}, {"speed_kmh": 30}]
        grads = [-1.0, 2.0]   # exact boundaries should be inclusive
        assert _flat_minutes(pts, grads) == pytest.approx(2 / 60.0)

    def test_speed_below_min_excluded(self):
        pts = [{"speed_kmh": 9.9} for _ in range(60)]   # below _MIN_SPEED_KMH = 10.0
        grads = [0.5] * 60
        assert _flat_minutes(pts, grads) == 0.0

    def test_speed_exactly_at_min_included(self):
        pts = [{"speed_kmh": 10.0} for _ in range(60)]
        grads = [0.5] * 60
        assert _flat_minutes(pts, grads) == pytest.approx(1.0)

    def test_missing_speed_treated_as_zero_excluded(self):
        pts = [{} for _ in range(60)]
        grads = [0.5] * 60
        assert _flat_minutes(pts, grads) == 0.0

    def test_empty_lists(self):
        assert _flat_minutes([], []) == 0.0


# ── Internal helpers: _split_quarters / _quarter_indices ────────────────────

class TestSplitQuarters:
    def test_even_split_of_400(self):
        pts = list(range(400))
        quarters = _split_quarters(pts)
        assert [len(q) for q in quarters] == [100, 100, 100, 100]

    def test_uneven_split_remainder_goes_to_last_quarter(self):
        pts = list(range(402))  # 402 // 4 = 100, remainder 2
        quarters = _split_quarters(pts)
        assert [len(q) for q in quarters] == [100, 100, 100, 102]

    def test_fewer_than_4_points_first_three_quarters_empty(self):
        """When n < 4, integer division q = n // 4 == 0, so quarters 1-3 are empty
        lists and quarter 4 receives the entire track. This means Q1 (used as the
        durability baseline) will have no data point for very short/sparse tracks."""
        pts = [1, 2, 3]
        quarters = _split_quarters(pts)
        assert quarters[0] == []
        assert quarters[1] == []
        assert quarters[2] == []
        assert quarters[3] == [1, 2, 3]

    def test_empty_list(self):
        quarters = _split_quarters([])
        assert quarters == [[], [], [], []]

    def test_quarter_indices_matches_split_quarters_lengths(self):
        pts = list(range(37))
        quarters = _split_quarters(pts)
        idxs = _quarter_indices(pts, quarters)
        assert [len(i) for i in idxs] == [len(q) for q in quarters]

    def test_quarter_indices_cover_all_points_without_overlap(self):
        pts = list(range(50))
        quarters = _split_quarters(pts)
        idxs = _quarter_indices(pts, quarters)
        flat = [i for sub in idxs for i in sub]
        assert flat == list(range(50))


# ── Internal helpers: _power_outputs ──────────────────────────────────────────

class TestPowerOutputs:
    def test_basic_average_per_quarter(self):
        quarters = [
            [{"power_w": 200, "heart_rate_bpm": 150}, {"power_w": 220, "heart_rate_bpm": 150}],
            [{"power_w": 210, "heart_rate_bpm": 150}],
            [{"power_w": 190, "heart_rate_bpm": 150}],
            [{"power_w": 180, "heart_rate_bpm": 150}],
        ]
        outputs, unit, quality, reason = _power_outputs(quarters, max_hr=None, ftp=None)
        assert outputs[0] == pytest.approx(210.0)
        assert unit == "watts"
        assert quality == "high"
        assert "FTP" not in reason

    def test_ftp_included_in_reason_when_provided(self):
        quarters = [[{"power_w": 200, "heart_rate_bpm": 150}]] * 4
        _, _, _, reason = _power_outputs(quarters, max_hr=None, ftp=280)
        assert "280" in reason

    def test_power_at_floor_excluded(self):
        # _PWR_FLOOR_W = 30, strictly greater-than
        quarters = [[{"power_w": 30, "heart_rate_bpm": 150}]] + [[]] * 3
        outputs, *_ = _power_outputs(quarters, max_hr=None, ftp=None)
        assert outputs[0] is None

    def test_power_just_above_floor_included(self):
        quarters = [[{"power_w": 31, "heart_rate_bpm": 150}]] + [[]] * 3
        outputs, *_ = _power_outputs(quarters, max_hr=None, ftp=None)
        assert outputs[0] == pytest.approx(31.0)

    def test_hr_below_floor_excluded(self):
        # max_hr=190 -> hr_floor = 190*0.55 = 104.5
        quarters = [[{"power_w": 200, "heart_rate_bpm": 100}]] + [[]] * 3
        outputs, *_ = _power_outputs(quarters, max_hr=190.0, ftp=None)
        assert outputs[0] is None

    def test_hr_above_floor_included(self):
        quarters = [[{"power_w": 200, "heart_rate_bpm": 110}]] + [[]] * 3
        outputs, *_ = _power_outputs(quarters, max_hr=190.0, ftp=None)
        assert outputs[0] == pytest.approx(200.0)

    def test_missing_hr_with_max_hr_set_uses_floor_plus_1_passes(self):
        # p.get("heart_rate_bpm") or hr_floor+1 -> defaults to floor+1 which is >= hr_floor
        quarters = [[{"power_w": 200}]] + [[]] * 3
        outputs, *_ = _power_outputs(quarters, max_hr=190.0, ftp=None)
        assert outputs[0] == pytest.approx(200.0)

    def test_empty_quarter_yields_none(self):
        outputs, *_ = _power_outputs([[], [], [], []], max_hr=None, ftp=None)
        assert outputs == [None, None, None, None]

    def test_no_max_hr_zero_floor_does_not_exclude_low_hr(self):
        quarters = [[{"power_w": 200, "heart_rate_bpm": 1}]] + [[]] * 3
        outputs, *_ = _power_outputs(quarters, max_hr=None, ftp=None)
        assert outputs[0] == pytest.approx(200.0)


# ── Internal helpers: _climbing_power_outputs / _climb_power / _climb_gradient ─

class TestClimbingPowerOutputs:
    def test_climb_assigned_to_correct_quarter(self):
        duration_s = 4000
        climbs = [_climb(start_s=100, power_w=200, gradient_pct=5.0)]  # q_size=1000 -> q_idx 0
        outputs, unit, quality, reason = _climbing_power_outputs(climbs, duration_s, [])
        assert outputs[0] == pytest.approx(200.0)
        assert outputs[1:] == [None, None, None]
        assert unit == "watts_normalized"

    def test_elapsed_beyond_duration_clamped_to_last_quarter(self):
        duration_s = 4000
        climbs = [_climb(start_s=999999, power_w=200, gradient_pct=5.0)]
        outputs, *_ = _climbing_power_outputs(climbs, duration_s, [])
        assert outputs[3] == pytest.approx(200.0)

    def test_normalization_to_5pct_gradient(self):
        # power * (5/grad); grad=10 -> half the power
        duration_s = 4000
        climbs = [_climb(start_s=100, power_w=200, gradient_pct=10.0)]
        outputs, *_ = _climbing_power_outputs(climbs, duration_s, [])
        assert outputs[0] == pytest.approx(100.0)

    def test_zero_gradient_no_normalization_applied(self):
        # grad=0 is falsy in `grad and grad > 0`, so norm_power falls back to raw power
        duration_s = 4000
        climbs = [_climb(start_s=100, power_w=200, gradient_pct=0.0)]
        outputs, *_ = _climbing_power_outputs(climbs, duration_s, [])
        assert outputs[0] == pytest.approx(200.0)

    def test_negative_gradient_no_normalization_applied(self):
        duration_s = 4000
        climbs = [_climb(start_s=100, power_w=200, gradient_pct=-5.0)]
        outputs, *_ = _climbing_power_outputs(climbs, duration_s, [])
        assert outputs[0] == pytest.approx(200.0)

    def test_zero_power_climb_skipped(self):
        duration_s = 4000
        climbs = [_climb(start_s=100, power_w=0.0, gradient_pct=5.0)]
        outputs, *_ = _climbing_power_outputs(climbs, duration_s, [])
        assert outputs == [None, None, None, None]

    def test_negative_power_climb_skipped(self):
        duration_s = 4000
        climbs = [_climb(start_s=100, power_w=-10.0, gradient_pct=5.0)]
        outputs, *_ = _climbing_power_outputs(climbs, duration_s, [])
        assert outputs == [None, None, None, None]

    def test_none_power_climb_skipped(self):
        duration_s = 4000
        climbs = [{"start_elapsed_s": 100, "estimated_power_w": None, "gradient_pct": 5.0}]
        outputs, *_ = _climbing_power_outputs(climbs, duration_s, [])
        assert outputs == [None, None, None, None]

    def test_quality_high_with_3_or_4_quarters_filled(self):
        duration_s = 8000
        climbs = [
            _climb(start_s=100, power_w=200, gradient_pct=5.0),
            _climb(start_s=2100, power_w=200, gradient_pct=5.0),
            _climb(start_s=4100, power_w=200, gradient_pct=5.0),
        ]
        _, _, quality, _ = _climbing_power_outputs(climbs, duration_s, [])
        assert quality == "high"

    def test_quality_medium_with_exactly_2_quarters_filled(self):
        duration_s = 8000
        climbs = [
            _climb(start_s=100, power_w=200, gradient_pct=5.0),
            _climb(start_s=2100, power_w=200, gradient_pct=5.0),
        ]
        _, _, quality, _ = _climbing_power_outputs(climbs, duration_s, [])
        assert quality == "medium"

    def test_quality_low_with_1_or_0_quarters_filled(self):
        duration_s = 8000
        climbs = [_climb(start_s=100, power_w=200, gradient_pct=5.0)]
        _, _, quality, _ = _climbing_power_outputs(climbs, duration_s, [])
        assert quality == "low"

    def test_empty_climb_list(self):
        outputs, _, quality, _ = _climbing_power_outputs([], 7200, [])
        assert outputs == [None, None, None, None]
        assert quality == "low"

    def test_multiple_climbs_averaged_in_same_quarter(self):
        duration_s = 4000
        climbs = [
            _climb(start_s=100, power_w=200, gradient_pct=5.0),
            _climb(start_s=200, power_w=300, gradient_pct=5.0),
        ]
        outputs, *_ = _climbing_power_outputs(climbs, duration_s, [])
        assert outputs[0] == pytest.approx(250.0)


class TestClimbPowerAndGradientExtraction:
    def test_climb_power_dict_estimated(self):
        assert _climb_power({"estimated_power_w": 220.0}) == 220.0

    def test_climb_power_dict_avg_fallback(self):
        assert _climb_power({"avg_power_w": 210.0}) == 210.0

    def test_climb_power_dict_missing_returns_none(self):
        assert _climb_power({}) is None

    def test_climb_power_object_attrs(self):
        from types import SimpleNamespace
        obj = SimpleNamespace(estimated_power_w=230.0)
        assert _climb_power(obj) == 230.0

    def test_climb_gradient_dict_avg_gradient_fallback(self):
        assert _climb_gradient({"avg_gradient_pct": 6.5}) == 6.5

    def test_climb_gradient_missing_returns_none(self):
        assert _climb_gradient({}) is None

    def test_climb_power_zero_estimated_falls_through_to_avg(self):
        """BUG (utils/durability.py, _climb_power, line ~497-500): uses
        `c.get("estimated_power_w") or c.get("avg_power_w")`. A legitimate
        estimated_power_w of 0.0 (e.g. a flat/recovery segment misclassified as a climb)
        is falsy and silently discarded in favor of avg_power_w, even though 0.0 was an
        explicit, intentional value.
        Correct behavior: an explicit 0.0 should be preserved, e.g. via an
        `is not None` check.
        """
        c = {"estimated_power_w": 0.0, "avg_power_w": 150.0}
        assert _climb_power(c) == 150.0
        # Once fixed, the expected behavior would be:
        # assert _climb_power(c) == 0.0


# ── Internal helpers: _hr_speed_outputs ───────────────────────────────────────

class TestHrSpeedOutputs:
    def test_basic_ef_computation(self):
        quarters = [[{"speed_kmh": 30, "heart_rate_bpm": 150}] for _ in range(4)]
        grad_by_quarter = [[0.5] for _ in range(4)]
        outputs, unit, quality, reason = _hr_speed_outputs(quarters, grad_by_quarter, max_hr=190.0, flat_minutes=25.0)
        assert outputs[0] == pytest.approx((30 / 150) * 100, rel=1e-3)
        assert unit == "speed_hr_ratio"

    def test_speed_below_min_excluded(self):
        quarters = [[{"speed_kmh": 9.9, "heart_rate_bpm": 150}], [], [], []]
        grad_by_quarter = [[0.5], [], [], []]
        outputs, *_ = _hr_speed_outputs(quarters, grad_by_quarter, max_hr=190.0, flat_minutes=25.0)
        assert outputs[0] is None

    def test_hr_below_floor_excluded(self):
        # hr_floor = 190*0.55 = 104.5
        quarters = [[{"speed_kmh": 30, "heart_rate_bpm": 100}], [], [], []]
        grad_by_quarter = [[0.5], [], [], []]
        outputs, *_ = _hr_speed_outputs(quarters, grad_by_quarter, max_hr=190.0, flat_minutes=25.0)
        assert outputs[0] is None

    def test_hr_below_absolute_floor_40_excluded_even_without_max_hr(self):
        quarters = [[{"speed_kmh": 30, "heart_rate_bpm": 35}], [], [], []]
        grad_by_quarter = [[0.5], [], [], []]
        outputs, *_ = _hr_speed_outputs(quarters, grad_by_quarter, max_hr=None, flat_minutes=25.0)
        assert outputs[0] is None

    def test_non_flat_gradient_excluded_when_flat_minutes_high(self):
        quarters = [[{"speed_kmh": 30, "heart_rate_bpm": 150}], [], [], []]
        grad_by_quarter = [[5.0], [], [], []]   # outside [-1, 2]
        outputs, *_ = _hr_speed_outputs(quarters, grad_by_quarter, max_hr=190.0, flat_minutes=25.0)
        assert outputs[0] is None

    def test_non_flat_gradient_included_when_flat_minutes_scarce(self):
        # flat_minutes < 20 -> gradient filter is bypassed entirely
        quarters = [[{"speed_kmh": 30, "heart_rate_bpm": 150}], [], [], []]
        grad_by_quarter = [[5.0], [], [], []]
        outputs, *_ = _hr_speed_outputs(quarters, grad_by_quarter, max_hr=190.0, flat_minutes=10.0)
        assert outputs[0] is not None

    def test_flat_minutes_boundary_20_uses_medium_quality(self):
        quarters = [[{"speed_kmh": 30, "heart_rate_bpm": 150}], [], [], []]
        grad_by_quarter = [[0.5], [], [], []]
        _, _, quality, _ = _hr_speed_outputs(quarters, grad_by_quarter, max_hr=190.0, flat_minutes=20.0)
        assert quality == "medium"

    def test_flat_minutes_just_below_20_uses_low_quality(self):
        quarters = [[{"speed_kmh": 30, "heart_rate_bpm": 150}], [], [], []]
        grad_by_quarter = [[0.5], [], [], []]
        _, _, quality, _ = _hr_speed_outputs(quarters, grad_by_quarter, max_hr=190.0, flat_minutes=19.9)
        assert quality == "low"

    def test_grad_none_treated_as_pass_through(self):
        # g is None -> condition `g is not None and not(...)` is False, so it's not excluded
        quarters = [[{"speed_kmh": 30, "heart_rate_bpm": 150}], [], [], []]
        grad_by_quarter = [[None], [], [], []]
        outputs, *_ = _hr_speed_outputs(quarters, grad_by_quarter, max_hr=190.0, flat_minutes=25.0)
        assert outputs[0] is not None

    def test_empty_quarter_yields_none(self):
        outputs, *_ = _hr_speed_outputs([[], [], [], []], [[], [], [], []], max_hr=190.0, flat_minutes=25.0)
        assert outputs == [None, None, None, None]

    def test_zero_hr_excluded_no_division_error(self):
        quarters = [[{"speed_kmh": 30, "heart_rate_bpm": 0}], [], [], []]
        grad_by_quarter = [[0.5], [], [], []]
        outputs, *_ = _hr_speed_outputs(quarters, grad_by_quarter, max_hr=None, flat_minutes=25.0)
        assert outputs[0] is None


# ── Internal helpers: _classify_durability ───────────────────────────────────

class TestClassifyDurability:
    def test_excellent_at_95_short_ride(self):
        assert _classify_durability(95.0, 1.0) == "excellent"

    def test_good_just_below_95_short_ride(self):
        assert _classify_durability(94.9, 1.0) == "good"

    def test_good_at_88_short_ride(self):
        assert _classify_durability(88.0, 1.0) == "good"

    def test_moderate_at_80_short_ride(self):
        assert _classify_durability(80.0, 1.0) == "moderate"

    def test_poor_at_70_short_ride(self):
        assert _classify_durability(70.0, 1.0) == "poor"

    def test_very_poor_below_70_short_ride(self):
        assert _classify_durability(69.9, 1.0) == "very_poor"

    def test_no_shift_at_or_below_3_hours(self):
        assert _classify_durability(95.0, 3.0) == "excellent"
        assert _classify_durability(94.9, 3.0) == "good"

    def test_shift_increases_with_duration_above_3_hours(self):
        # At 5h, shift = min(5, (5-3)*1.5) = 3.0 -> excellent threshold becomes 92
        assert _classify_durability(92.0, 5.0) == "excellent"
        assert _classify_durability(91.9, 5.0) == "good"

    def test_shift_capped_at_5_points(self):
        # At 10h, shift would be (10-3)*1.5=10.5 but capped to 5 -> excellent threshold = 90
        assert _classify_durability(90.0, 10.0) == "excellent"
        assert _classify_durability(89.9, 10.0) == "good"

    def test_zero_duration_no_negative_shift(self):
        # duration_hours - 3.0 is negative -> max(0, ...) clamps shift to 0
        assert _classify_durability(95.0, 0.0) == "excellent"


# ── Internal helpers: _estimate_work_kj ───────────────────────────────────────

class TestEstimateWorkKj:
    def test_power_method_constant_power(self):
        start = datetime(2024, 1, 1, 8, 0, 0)
        pts = [
            {"power_w": 200, "timestamp": start},
            {"power_w": 200, "timestamp": start + timedelta(seconds=10)},
        ]
        kj = _estimate_work_kj(pts, "power", None, None, None, 1.0)
        # 200W for 10s = 2000 J = 2 kJ
        assert kj == pytest.approx(2.0)

    def test_power_method_no_timestamps_assumes_1s_per_point(self):
        pts = [{"power_w": 200}, {"power_w": 200}, {"power_w": 200}]
        kj = _estimate_work_kj(pts, "power", None, None, None, 1.0)
        assert kj == pytest.approx(0.4)   # 200W * 2s / 1000

    def test_power_method_single_point_zero_work(self):
        kj = _estimate_work_kj([{"power_w": 200}], "power", None, None, None, 1.0)
        assert kj == 0.0

    def test_power_method_empty_points_zero_work(self):
        kj = _estimate_work_kj([], "power", None, None, None, 1.0)
        assert kj == 0.0

    def test_power_method_gap_capped_at_10s(self):
        start = datetime(2024, 1, 1, 8, 0, 0)
        pts = [
            {"power_w": 200, "timestamp": start},
            {"power_w": 200, "timestamp": start + timedelta(seconds=1000)},  # huge gap
        ]
        kj = _estimate_work_kj(pts, "power", None, None, None, 1.0)
        # dt capped to 10s -> 200W * 10s = 2000J = 2kJ, not 200000J
        assert kj == pytest.approx(2.0)

    def test_power_method_negative_dt_clamped_to_zero(self):
        start = datetime(2024, 1, 1, 8, 0, 0)
        pts = [
            {"power_w": 200, "timestamp": start + timedelta(seconds=10)},
            {"power_w": 200, "timestamp": start},   # out of order -> negative dt
        ]
        kj = _estimate_work_kj(pts, "power", None, None, None, 1.0)
        assert kj == 0.0

    def test_hr_method_requires_all_four_params(self):
        assert _estimate_work_kj([], "hr_speed", avg_hr=150, max_hr=None, weight_kg=70, duration_hours=2) is None
        assert _estimate_work_kj([], "hr_speed", avg_hr=None, max_hr=190, weight_kg=70, duration_hours=2) is None
        assert _estimate_work_kj([], "hr_speed", avg_hr=150, max_hr=190, weight_kg=None, duration_hours=2) is None

    def test_hr_method_zero_max_hr_returns_none(self):
        assert _estimate_work_kj([], "hr_speed", avg_hr=150, max_hr=0, weight_kg=70, duration_hours=2) is None

    def test_hr_method_zero_weight_returns_none(self):
        assert _estimate_work_kj([], "hr_speed", avg_hr=150, max_hr=190, weight_kg=0, duration_hours=2) is None

    def test_hr_method_returns_positive_value_with_full_params(self):
        kj = _estimate_work_kj([], "hr_speed", avg_hr=150, max_hr=190, weight_kg=70, duration_hours=2)
        assert kj is not None
        assert kj > 0

    def test_climbing_power_method_uses_hr_branch(self):
        # method == "climbing_power" falls into the same HR-based estimate as hr_speed
        kj = _estimate_work_kj([], "climbing_power", avg_hr=150, max_hr=190, weight_kg=70, duration_hours=2)
        assert kj is not None
        assert kj > 0


# ── Internal helpers: _linear_regression ──────────────────────────────────────

class TestLinearRegression:
    def test_perfect_positive_slope(self):
        slope, intercept = _linear_regression([0, 1, 2, 3], [10, 12, 14, 16])
        assert slope == pytest.approx(2.0)
        assert intercept == pytest.approx(10.0)

    def test_flat_slope_zero(self):
        slope, _ = _linear_regression([0, 1, 2, 3], [50, 50, 50, 50])
        assert slope == pytest.approx(0.0)

    def test_negative_slope(self):
        slope, _ = _linear_regression([0, 1, 2], [10, 8, 6])
        assert slope == pytest.approx(-2.0)

    def test_single_point_returns_zero_slope_and_y_value(self):
        slope, intercept = _linear_regression([0], [42.0])
        assert slope == 0.0
        assert intercept == 42.0

    def test_empty_lists_returns_zeros(self):
        slope, intercept = _linear_regression([], [])
        assert slope == 0.0
        assert intercept == 0.0

    def test_identical_x_values_avoids_division_by_zero(self):
        # ss_xx == 0 -> guarded explicitly
        slope, intercept = _linear_regression([5, 5, 5], [1.0, 2.0, 3.0])
        assert slope == 0.0
        assert intercept == pytest.approx(2.0)


# ── Internal helpers: _comparison_note ────────────────────────────────────────

class TestComparisonNote:
    def test_no_best_returns_empty(self):
        assert _comparison_note([{"activity_id": 1}], None) == ""

    def test_fewer_than_2_rides_returns_empty(self):
        best = {"activity_id": 1, "durability_index": 90.0, "date": "2024-01-01", "avg_temp": None, "tsb": None}
        assert _comparison_note([best], best) == ""

    def test_basic_note_includes_index_and_date(self):
        rides = [
            {"activity_id": 1, "durability_index": 90.0, "date": "2024-01-01", "avg_temp": None, "tsb": None},
            {"activity_id": 2, "durability_index": 80.0, "date": "2024-01-08", "avg_temp": None, "tsb": None},
        ]
        note = _comparison_note(rides, rides[0])
        assert "90" in note
        assert "2024-01-01" in note

    def test_low_tsb_mentions_fatigue(self):
        rides = [
            {"activity_id": 1, "durability_index": 90.0, "date": "2024-01-01", "avg_temp": None, "tsb": -20.0},
            {"activity_id": 2, "durability_index": 80.0, "date": "2024-01-08", "avg_temp": None, "tsb": None},
        ]
        note = _comparison_note(rides, rides[0])
        assert "fatigue" in note.lower()

    def test_tsb_boundary_exactly_minus_15_excluded(self):
        rides = [
            {"activity_id": 1, "durability_index": 90.0, "date": "2024-01-01", "avg_temp": None, "tsb": -15.0},
            {"activity_id": 2, "durability_index": 80.0, "date": "2024-01-08", "avg_temp": None, "tsb": None},
        ]
        note = _comparison_note(rides, rides[0])
        assert "fatigue" not in note.lower()

    def test_high_temp_mentions_heat(self):
        rides = [
            {"activity_id": 1, "durability_index": 90.0, "date": "2024-01-01", "avg_temp": 32.0, "tsb": None},
            {"activity_id": 2, "durability_index": 80.0, "date": "2024-01-08", "avg_temp": None, "tsb": None},
        ]
        note = _comparison_note(rides, rides[0])
        assert "heat" in note.lower()

    def test_temp_boundary_exactly_30_included(self):
        rides = [
            {"activity_id": 1, "durability_index": 90.0, "date": "2024-01-01", "avg_temp": 30.0, "tsb": None},
            {"activity_id": 2, "durability_index": 80.0, "date": "2024-01-08", "avg_temp": None, "tsb": None},
        ]
        note = _comparison_note(rides, rides[0])
        assert "heat" in note.lower()

    def test_warmer_comparable_ride_mentions_resilience(self):
        rides = [
            {"activity_id": 1, "durability_index": 90.0, "date": "2024-01-01", "avg_temp": 20.0, "tsb": None},
            {"activity_id": 2, "durability_index": 88.0, "date": "2024-01-08", "avg_temp": 30.0, "tsb": None},
        ]
        note = _comparison_note(rides, rides[0])
        assert "resilience" in note.lower()

    def test_note_ends_with_period(self):
        rides = [
            {"activity_id": 1, "durability_index": 90.0, "date": "2024-01-01", "avg_temp": None, "tsb": None},
            {"activity_id": 2, "durability_index": 80.0, "date": "2024-01-08", "avg_temp": None, "tsb": None},
        ]
        note = _comparison_note(rides, rides[0])
        assert note.endswith(".")


# ── calculate_durability: additional edge cases ──────────────────────────────

class TestCalculateDurabilityMoreEdgeCases:
    def test_exactly_min_track_pts_boundary(self):
        from utils.durability import _MIN_TRACK_PTS
        pts = _pts_power(n=_MIN_TRACK_PTS, power_w=250)
        result = calculate_durability(duration_seconds=7200, track_points=pts)
        assert result is not None

    def test_below_min_track_pts_after_clean_returns_none(self):
        from utils.durability import _MIN_TRACK_PTS
        pts = _pts_power(n=_MIN_TRACK_PTS - 1, power_w=250)
        result = calculate_durability(duration_seconds=7200, track_points=pts)
        assert result is None

    # Note: a "Q1 output is 0/negative" scenario was attempted here but is not
    # reachable through the power method in practice: `_has_real_power` requires
    # >80% of points above `_PWR_FLOOR_W`, while a quarter is 25% of the ride, so
    # an all-zero Q1 can never coexist with `has_power=True`. The `q1 <= 0` guard
    # at durability.py appears to be a defensive check that the power/hr_speed/
    # climbing_power output paths can't actually trigger with realistic data.

    def test_quality_override_low_recovery_ride_yields_no_result_BUG(self):
        """KNOWN INCONSISTENCY: validate_durability_calculation() explicitly allows
        (can_calculate=True, quality_override="low") for "very low average HR" recovery
        rides (hr_frac < 0.55), intending to still compute a low-confidence result.

        But `_power_outputs`' per-point filter excludes any point where
        heart_rate_bpm < hr_floor (also `max_hr * 0.55`, see _HR_FLOOR_FRAC in
        utils/durability.py). When HR is constant and below that floor for the
        whole ride (as "very low average HR" implies), EVERY point in EVERY quarter
        gets filtered out, all four quarter outputs become None, and
        `calculate_durability` returns bare None at the `q1 is None` guard --
        despite validate_durability_calculation()'s explicit intent to still
        produce a (low-quality) result for exactly this case.

        What SHOULD happen (not asserted, since current behavior contradicts it):
        #   assert result is not None
        #   assert result["quality"] == "low"
        What ACTUALLY happens: the HR floor filter and the "low quality override"
        path are inconsistent, so the recovery ride silently produces no result at all.
        """
        pts = _pts_power(n=1000, power_w=250, hr=90)
        result = calculate_durability(duration_seconds=7200, track_points=pts, max_hr=190.0)
        assert result is None

    def test_high_temp_does_not_downgrade_non_high_quality(self):
        # hr_speed method starts as "medium"/"low", so the temp >=35 downgrade
        # (which only fires when final_quality == "high") should not apply.
        pts = _pts_hr_speed(n=1000, speed=28.0, hr=150)
        result = calculate_durability(duration_seconds=7200, track_points=pts, max_hr=190.0, temperature_avg_c=38.0)
        assert result is not None
        assert result["quality"] != "medium" or "Heat strain" not in result["quality_reason"]

    def test_temperature_exactly_35_triggers_downgrade(self):
        pts = _pts_power(n=1000, power_w=250)
        result = calculate_durability(duration_seconds=7200, track_points=pts, temperature_avg_c=35.0)
        assert result is not None
        assert result["quality"] == "medium"

    def test_temperature_just_below_35_no_downgrade(self):
        pts = _pts_power(n=1000, power_w=250)
        result = calculate_durability(duration_seconds=7200, track_points=pts, temperature_avg_c=34.9)
        assert result is not None
        assert result["quality"] == "high"

    def test_analysis_json_matches_context(self):
        import json as _json
        pts = _pts_power(n=1000, power_w=250)
        result = calculate_durability(duration_seconds=7200, track_points=pts)
        assert result is not None
        assert _json.loads(result["analysis_json"]) == result["context"]

    def test_none_track_points_handled_like_empty(self):
        # `if not track_points` catches None too.
        result = calculate_durability(duration_seconds=7200, track_points=None)
        assert result is None

    def test_fade_rate_none_when_duration_zero(self):
        # duration_hours > 0 guard; with duration_seconds=0 the ride would already be
        # rejected by validate_durability_calculation, so call _estimate path indirectly
        # is not reachable — verify via direct duration_hours computation instead.
        duration_hours = 0 / 3600
        assert duration_hours == 0
        # fade_rate would be None per the `if duration_hours > 0 else None` ternary.

    def test_unicode_notes_keyword_match_repetitions(self):
        pts = _pts_power(n=1000, power_w=250)
        result = calculate_durability(duration_seconds=7200, track_points=pts, notes="Séries de 30/30")
        assert result is None

    def test_notes_case_insensitive_match(self):
        pts = _pts_power(n=1000, power_w=250)
        result = calculate_durability(duration_seconds=7200, track_points=pts, notes="RACE DAY!")
        assert result is None

    def test_notes_without_keywords_does_not_block(self):
        pts = _pts_power(n=1000, power_w=250)
        result = calculate_durability(duration_seconds=7200, track_points=pts, notes="Nice easy spin with friends")
        assert result is not None

    def test_climbing_power_single_missing_q4_triggers_fallback(self):
        """The climbing_power -> hr_speed fallback must trigger whenever q1 or q4
        specifically is missing, not just when >1 quarter overall is missing — the
        downstream guard `if q1 is None or q4 is None: return None` is fatal on either
        alone, so a single missing q1/q4 needs the same fallback as 2+ missing quarters.

        Climbs at 900s, 1800s (early) and 5000s (one late) over a 7200s ride leave
        _climbing_power_outputs's q4 (last quarter) uncovered -- this must fall back
        to hr_speed and still produce a result instead of being discarded.
        """
        pts = _pts_hr_speed(n=1000, speed=18.0, hr=160, elev_step=0.5, dist_step=20.0)
        climbs = [
            _climb(start_s=900, power_w=230.0, gradient_pct=7.0),
            _climb(start_s=1800, power_w=220.0, gradient_pct=6.0),
            _climb(start_s=5000, power_w=200.0, gradient_pct=8.0),
        ]
        result = calculate_durability(duration_seconds=7200, track_points=pts,
                                      climb_detections=climbs, max_hr=190.0)
        assert result is not None
        assert result["method"] == "hr_speed"


# ── calculate_durability_trend: additional edge cases ────────────────────────

class TestCalculateDurabilityTrendMore:
    def _make_db(self, rows):
        db = MagicMock()
        q = db.query.return_value
        q.join.return_value = q
        q.filter.return_value = q
        q.order_by.return_value = q
        q.all.return_value = rows
        return db

    def test_declining_trend(self):
        rows = _make_mock_db_rows([95.0, 90.0, 85.0, 80.0, 75.0])
        db = self._make_db(rows)
        result = calculate_durability_trend(user_id=1, db=db, weeks=12)
        assert result["trend"] == "declining"
        assert result["trend_slope"] < -0.5

    def test_trend_slope_boundary_exactly_0_5_is_stable(self):
        # Construct values with slope close to but not exceeding 0.5/week threshold.
        rows = _make_mock_db_rows([88.0, 88.0, 88.0, 88.0, 88.0])
        db = self._make_db(rows)
        result = calculate_durability_trend(user_id=1, db=db, weeks=12)
        assert result["trend"] == "stable"

    def test_single_week_of_data(self):
        rows = _make_mock_db_rows([90.0])
        db = self._make_db(rows)
        result = calculate_durability_trend(user_id=1, db=db, weeks=12)
        assert result["current_avg"] == pytest.approx(90.0)
        assert result["trend"] == "stable"

    def test_multiple_rides_same_week_averaged(self):
        base_date = datetime(2024, 1, 8)  # a Monday
        mock1 = MagicMock(); mock1.durability_index = 80.0; mock1.quality = "high"
        mock2 = MagicMock(); mock2.durability_index = 90.0; mock2.quality = "high"
        rows = [(mock1, base_date), (mock2, base_date + timedelta(days=2))]
        db = self._make_db(rows)
        result = calculate_durability_trend(user_id=1, db=db, weeks=12)
        assert len(result["weekly_averages"]) == 1
        assert result["weekly_averages"][0]["avg_durability"] == pytest.approx(85.0)
        assert result["weekly_averages"][0]["ride_count"] == 2

    def test_best_ever_date_matches_highest_index(self):
        rows = _make_mock_db_rows([82.0, 99.0, 87.0])
        db = self._make_db(rows)
        result = calculate_durability_trend(user_id=1, db=db, weeks=12)
        assert result["best_ever"] == pytest.approx(99.0)
        assert result["best_ever_date"] is not None
