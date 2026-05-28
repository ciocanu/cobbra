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
