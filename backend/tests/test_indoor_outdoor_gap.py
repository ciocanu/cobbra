"""
Tests for utils/indoor_outdoor_gap.py — Indoor/outdoor gap and correction.

Run from the backend directory:
    python -m pytest tests/test_indoor_outdoor_gap.py -v
"""

import sys
import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.indoor_outdoor_gap import (
    apply_correction_factors,
    calculate_power_gap,
    calibrate_from_ftp_values,
    calibrate_from_dual_test,
    recalculate_training_load_corrected,
    update_indoor_outdoor_gap,
    _ema_model,
    _build_interpretation,
    _build_recommendation,
    _z3_metrics,
    _best_sustained_effort,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _activity(env="indoor", tss=60.0, avg_power=None, avg_hr=160.0,
              duration_s=3600, max_hr=185.0, user_id=1):
    a = MagicMock()
    a.ride_environment         = env
    a.tss                      = tss
    a.avg_power_w              = avg_power
    a.avg_heart_rate_bpm       = avg_hr
    a.duration_seconds         = duration_s
    a.max_heart_rate_bpm       = max_hr
    a.user_id                  = user_id
    return a


def _profile(power_gap_pct=-10.0, hr_gap_bpm=5.0, manual_power_gap_pct=None):
    p = MagicMock()
    p.power_gap_pct        = power_gap_pct
    p.hr_gap_bpm           = hr_gap_bpm
    p.manual_power_gap_pct = manual_power_gap_pct
    return p


# ── apply_correction_factors ─────────────────────────────────────────────────

class TestApplyCorrectionFactors:
    def test_typical_gap_increases_tss(self):
        """Indoor -10% gap → correction_factor > 1 → corrected TSS > original TSS."""
        act  = _activity(env="indoor", tss=60.0)
        prof = _profile(power_gap_pct=-10.0)
        result = apply_correction_factors(act, prof)
        assert result["correction_applied"] is True
        assert result["power_correction_factor"] > 1.0
        assert result["corrected_tss"] > 60.0

    def test_correction_factor_formula(self):
        """power_gap = -10 → factor = 1/(1 + (-10/100)) = 1/0.9 ≈ 1.1111."""
        act  = _activity(env="indoor", tss=100.0)
        prof = _profile(power_gap_pct=-10.0)
        result = apply_correction_factors(act, prof)
        expected_cf = 1.0 / 0.9
        assert abs(result["power_correction_factor"] - expected_cf) < 0.001
        # corrected_TSS = original_TSS × factor²
        expected_tss = round(100.0 * (expected_cf ** 2), 1)
        assert abs(result["corrected_tss"] - expected_tss) < 1.0

    def test_outdoor_activity_no_correction(self):
        """Outdoor rides must never receive a correction factor."""
        act  = _activity(env="outdoor", tss=80.0)
        prof = _profile(power_gap_pct=-10.0)
        result = apply_correction_factors(act, prof)
        assert result["correction_applied"] is False
        assert result["power_correction_factor"] is None
        assert result["corrected_tss"] is None

    def test_manual_calibration_overrides_calculated_gap(self):
        """manual_power_gap_pct takes precedence over power_gap_pct."""
        act  = _activity(env="indoor", tss=100.0)
        prof = _profile(power_gap_pct=-10.0, manual_power_gap_pct=-15.0)
        result = apply_correction_factors(act, prof)
        expected_cf = 1.0 / 0.85    # 1 / (1 + (-15/100))
        assert abs(result["power_correction_factor"] - expected_cf) < 0.001
        assert result["correction_source"] == "manual_calibration"

    def test_no_tss_yields_no_corrected_tss(self):
        act      = _activity(env="indoor", tss=None)
        prof     = _profile(power_gap_pct=-10.0)
        result   = apply_correction_factors(act, prof)
        assert result["corrected_tss"] is None

    def test_zero_gap_correction_factor_is_one(self):
        """gap=0 → factor=1 → corrected TSS equals original."""
        act  = _activity(env="indoor", tss=50.0)
        prof = _profile(power_gap_pct=0.0, hr_gap_bpm=0.0)
        result = apply_correction_factors(act, prof)
        assert abs(result["power_correction_factor"] - 1.0) < 0.001
        assert abs(result["corrected_tss"] - 50.0) < 0.5

    def test_inverted_gap_correction_reduces_tss(self):
        """Indoor power > outdoor (positive gap) → factor < 1 → TSS decreases."""
        act  = _activity(env="indoor", tss=100.0)
        prof = _profile(power_gap_pct=10.0)   # indoor reads 10% HIGHER
        result = apply_correction_factors(act, prof)
        assert result["power_correction_factor"] < 1.0
        assert result["corrected_tss"] < 100.0


# ── calibrate_from_ftp_values ─────────────────────────────────────────────────

class TestCalibrateFromFtpValues:
    def _make_db(self, user_id=1):
        db    = MagicMock()
        prof  = MagicMock()
        prof.manual_power_gap_pct = None
        db.query.return_value.filter.return_value.first.return_value = prof
        return db, prof

    def test_typical_ftp_comparison(self):
        db, prof = self._make_db()
        result = calibrate_from_ftp_values(1, indoor_ftp=200, outdoor_ftp=230, db=db)
        # gap = (200 - 230) / 230 × 100 ≈ -13.0%
        assert result["power_gap_pct"] < 0
        assert abs(result["power_gap_pct"] - (-13.04)) < 0.1

    def test_saves_to_profile(self):
        db, prof = self._make_db()
        calibrate_from_ftp_values(1, indoor_ftp=200, outdoor_ftp=230, db=db)
        assert prof.manual_power_gap_pct is not None
        db.commit.assert_called_once()

    def test_invalid_outdoor_ftp_raises(self):
        db, _ = self._make_db()
        with pytest.raises((ValueError, ZeroDivisionError)):
            calibrate_from_ftp_values(1, indoor_ftp=200, outdoor_ftp=0, db=db)

    def test_creates_profile_if_none_exists(self):
        db    = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = calibrate_from_ftp_values(1, indoor_ftp=210, outdoor_ftp=230, db=db)
        db.add.assert_called_once()

    def test_indoor_higher_than_outdoor(self):
        db, _ = self._make_db()
        result = calibrate_from_ftp_values(1, indoor_ftp=240, outdoor_ftp=230, db=db)
        # Positive gap: indoor reads higher
        assert result["power_gap_pct"] > 0


# ── _ema_model ────────────────────────────────────────────────────────────────

class TestEmaModel:
    def test_zero_load_produces_zero_ctl(self):
        start = datetime(2024, 1, 1)
        end   = datetime(2024, 1, 31)
        ctl, atl = _ema_model({}, start, end)
        assert abs(ctl) < 0.001
        assert abs(atl) < 0.001

    def test_constant_load_converges(self):
        """Constant daily TSS should move CTL and ATL well above zero."""
        start = datetime(2023, 1, 1)
        end   = datetime(2024, 1, 1)   # ~365 days
        daily = {(start + timedelta(days=i)).date().isoformat(): 100.0
                 for i in range(365)}
        ctl, atl = _ema_model(daily, start, end)
        # Discrete EMA with k=1/42 and k=1/7 converges toward 100 but not exactly;
        # both should be well above 80 after a full year of constant load.
        assert ctl > 80.0
        assert atl > 80.0

    def test_corrected_higher_than_original_when_indoor_gap_positive(self):
        """If indoor rides have corrected_tss > tss, corrected CTL should exceed original."""
        start = datetime(2024, 1, 1)
        end   = datetime(2024, 4, 1)   # ~90 days
        orig = {(start + timedelta(days=i)).date().isoformat(): 60.0 for i in range(90)}
        corr = {(start + timedelta(days=i)).date().isoformat(): 70.0 for i in range(90)}
        orig_ctl, _ = _ema_model(orig, start, end)
        corr_ctl, _ = _ema_model(corr, start, end)
        assert corr_ctl > orig_ctl


# ── _build_interpretation ─────────────────────────────────────────────────────

class TestBuildInterpretation:
    def test_typical_gap_mentions_typical_range(self):
        text = _build_interpretation(-10.0, 5.0, "high")
        assert "lower" in text or "typical" in text

    def test_inverted_gap_flagged(self):
        text = _build_interpretation(10.0, None, "high")
        assert "higher" in text or "unusual" in text or "calibration" in text

    def test_low_confidence_noted(self):
        text = _build_interpretation(-8.0, None, "low")
        assert "low" in text.lower() or "more rides" in text.lower()


# ── _build_recommendation ────────────────────────────────────────────────────

class TestBuildRecommendation:
    def test_no_gap_prompts_upload(self):
        text = _build_recommendation(None, None)
        assert "upload" in text.lower() or "indoor" in text.lower()

    def test_large_gap_warns_calibration(self):
        text = _build_recommendation(-25.0, None)
        assert "calibration" in text.lower() or "unusual" in text.lower()

    def test_positive_gap_advises_trainer_check(self):
        text = _build_recommendation(12.0, None)
        assert "trainer" in text.lower() or "calibration" in text.lower()

    def test_normal_gap_advises_ftp_reduction(self):
        text = _build_recommendation(-10.0, None)
        assert "ftp" in text.lower() or "power" in text.lower() or "%" in text


# ── BUG DOCUMENTATION ─────────────────────────────────────────────────────────
# These tests document confirmed defects in the current implementation. They
# assert the CURRENT (buggy) behavior so regressions are caught, and include a
# commented-out assertion describing the CORRECT expected behavior.

class TestBuildInterpretationTypicalRangeBug:
    def test_negative_gap_within_5_to_15_pct_hits_dedicated_typical_branch(self):
        """utils/indoor_outdoor_gap.py, _build_interpretation: `typical` gates the
        dedicated "~X% lower... within the typical 5-15% range" sentence (marked by
        a "~" prefix before the percentage) and is `-15 <= power_gap <= -5`. Previously
        this was written as the unsatisfiable `-5 <= power_gap <= -15`, making the
        branch permanently dead code; now fixed so it fires for gaps in that band.
        """
        power_gap = -10.0  # squarely inside the typical 5-15% band
        text = _build_interpretation(power_gap, None, "high")
        assert "~10% lower than outdoor, which is within the typical 5–15% range." in text

    def test_negative_gap_outside_5_to_15_pct_does_not_hit_typical_branch(self):
        for power_gap in (-1.0, -20.0, -50.0):
            text = _build_interpretation(power_gap, None, "high")
            assert "~" not in text


class TestApplyCorrectionFactorsSourceTruthinessBug:
    def test_hr_correction_factor_of_exactly_zero_keeps_source(self):
        """utils/indoor_outdoor_gap.py, apply_correction_factors: `correction_source`
        must use an explicit `is not None` check (matching `correction_applied`),
        not truthiness -- otherwise a legitimately computed hr_cf of exactly 0.0
        (when avg_heart_rate_bpm == hr_gap_bpm) would wipe the source to None even
        though a correction was actually applied.
        """
        act = _activity(env="indoor", tss=50.0, avg_hr=10.0)
        # profile has no power_gap_pct (None) so only the HR path is exercised,
        # and hr_gap_bpm == avg_heart_rate_bpm so hr_cf == (10 - 10) / 10 == 0.0
        prof = _profile(power_gap_pct=None, hr_gap_bpm=10.0)

        result = apply_correction_factors(act, prof)

        assert result["hr_correction_factor"] == 0.0
        assert result["power_correction_factor"] is None
        assert result["correction_applied"] is True
        assert result["correction_source"] == "calculated_gap"


# ── calculate_power_gap ──────────────────────────────────────────────────────

def _make_gap_db(activities, user=None, weight_kg=70.0, trackpoints_by_activity=None):
    """Build a MagicMock db that serves Activity, User, and TrackPoint queries
    used by calculate_power_gap / _z3_metrics."""
    db = MagicMock()
    trackpoints_by_activity = trackpoints_by_activity or {}

    def query_side_effect(model):
        name = getattr(model, "__name__", str(model))
        q = MagicMock()
        if name == "Activity":
            q.filter.return_value.order_by.return_value.all.return_value = activities
        elif name == "User":
            q.filter_by.return_value.first.return_value = user or SimpleNamespace(weight_kg=weight_kg)
        elif name == "TrackPoint":
            def filter_tp(*args, **kwargs):
                inner = MagicMock()
                # crude: figure out which activity is being asked about via filter args repr
                inner.order_by.return_value.all.return_value = []
                return inner
            q.filter.side_effect = None
            q.filter.return_value.order_by.return_value.all.return_value = []
        else:
            q.filter.return_value.first.return_value = None
        return q

    db.query.side_effect = query_side_effect
    return db


class TestCalculatePowerGapInsufficientData:
    def test_too_few_indoor_rides_returns_insufficient_data(self):
        outdoor = [_activity(env="outdoor") for _ in range(5)]
        indoor = [_activity(env="indoor") for _ in range(2)]
        db = _make_gap_db(indoor + outdoor)
        result = calculate_power_gap(1, db)
        assert result["confidence"] == "insufficient_data"
        assert result["power_gap_pct"] is None
        assert result["indoor_rides_used"] == 2
        assert result["outdoor_rides_used"] == 5

    def test_too_few_outdoor_rides_returns_insufficient_data(self):
        indoor = [_activity(env="indoor") for _ in range(5)]
        outdoor = [_activity(env="outdoor") for _ in range(1)]
        db = _make_gap_db(indoor + outdoor)
        result = calculate_power_gap(1, db)
        assert result["confidence"] == "insufficient_data"

    def test_no_activities_at_all(self):
        db = _make_gap_db([])
        result = calculate_power_gap(1, db)
        assert result["confidence"] == "insufficient_data"
        assert result["indoor_rides_used"] == 0
        assert result["outdoor_rides_used"] == 0

    def test_exactly_min_rides_low_but_no_z3_data_is_insufficient(self):
        """3 rides each side (== _MIN_RIDES_LOW) pass the first gate, but with
        no valid Z3 metrics (max_hr missing), the second gate also reports
        insufficient_data with a different interpretation message."""
        indoor = [_activity(env="indoor", max_hr=None) for _ in range(3)]
        outdoor = [_activity(env="outdoor", max_hr=None) for _ in range(3)]
        db = _make_gap_db(indoor + outdoor)
        result = calculate_power_gap(1, db)
        assert result["confidence"] == "insufficient_data"
        assert "Z3" in result["interpretation"]


class TestCalculatePowerGapWithMockedZ3Metrics:
    """Patch _z3_metrics directly to control the per-ride metrics fed into
    calculate_power_gap's averaging/confidence logic, since building real
    TrackPoint mocks for every ride is unnecessary to exercise this branch."""

    def _db_with_n_rides(self, n_indoor, n_outdoor):
        indoor = [_activity(env="indoor") for _ in range(n_indoor)]
        outdoor = [_activity(env="outdoor") for _ in range(n_outdoor)]
        db = MagicMock()

        def query_side_effect(model):
            name = getattr(model, "__name__", str(model))
            q = MagicMock()
            if name == "Activity":
                q.filter.return_value.order_by.return_value.all.return_value = indoor + outdoor
            else:
                q.filter.return_value.first.return_value = None
                q.filter_by.return_value.first.return_value = None
            return q

        db.query.side_effect = query_side_effect
        return db

    def test_high_confidence_when_enough_rides_and_power_both_sides(self):
        db = self._db_with_n_rides(10, 10)
        metric_in  = {"wkg_z3": 3.0, "hr_z3": 150.0, "has_power": True, "n_pts": 100}
        metric_out = {"wkg_z3": 3.3, "hr_z3": 145.0, "has_power": True, "n_pts": 100}
        with patch("utils.indoor_outdoor_gap._z3_metrics", side_effect=lambda a, db: (
            metric_in if a.ride_environment == "indoor" else metric_out
        )):
            result = calculate_power_gap(1, db)
        assert result["confidence"] == "high"
        assert result["power_gap_pct"] is not None
        assert result["power_gap_pct"] < 0  # indoor wkg lower than outdoor

    def test_medium_confidence_when_5_to_9_rides_each_side(self):
        db = self._db_with_n_rides(6, 6)
        metric_in  = {"wkg_z3": 3.0, "hr_z3": 150.0, "has_power": True, "n_pts": 100}
        metric_out = {"wkg_z3": 3.3, "hr_z3": 145.0, "has_power": True, "n_pts": 100}
        with patch("utils.indoor_outdoor_gap._z3_metrics", side_effect=lambda a, db: (
            metric_in if a.ride_environment == "indoor" else metric_out
        )):
            result = calculate_power_gap(1, db)
        assert result["confidence"] == "medium"

    def test_low_confidence_when_below_5_rides_each_side(self):
        db = self._db_with_n_rides(3, 3)
        metric_in  = {"wkg_z3": 3.0, "hr_z3": 150.0, "has_power": True, "n_pts": 100}
        metric_out = {"wkg_z3": 3.3, "hr_z3": 145.0, "has_power": True, "n_pts": 100}
        with patch("utils.indoor_outdoor_gap._z3_metrics", side_effect=lambda a, db: (
            metric_in if a.ride_environment == "indoor" else metric_out
        )):
            result = calculate_power_gap(1, db)
        assert result["confidence"] == "low"

    def test_high_ride_count_but_missing_power_on_one_side_downgrades_to_medium(self):
        """has_power_both requires power data on BOTH sides; if outdoor never
        has power, confidence cannot reach 'high' even with >=10 rides each."""
        db = self._db_with_n_rides(10, 10)
        metric_in  = {"wkg_z3": 3.0, "hr_z3": 150.0, "has_power": True,  "n_pts": 100}
        metric_out = {"wkg_z3": None, "hr_z3": 145.0, "has_power": False, "n_pts": 100}
        with patch("utils.indoor_outdoor_gap._z3_metrics", side_effect=lambda a, db: (
            metric_in if a.ride_environment == "indoor" else metric_out
        )):
            result = calculate_power_gap(1, db)
        assert result["confidence"] == "medium"

    def test_insufficient_when_fewer_than_min_rides_low_valid_z3_metrics(self):
        """All rides pass the initial count gate, but _z3_metrics returns None
        for most of them (not enough valid Z3 data) -> second gate triggers."""
        db = self._db_with_n_rides(5, 5)
        with patch("utils.indoor_outdoor_gap._z3_metrics", return_value=None):
            result = calculate_power_gap(1, db)
        assert result["confidence"] == "insufficient_data"
        assert result["indoor_rides_used"] == 0
        assert result["outdoor_rides_used"] == 0

    def test_power_gap_none_when_wkg_missing_but_hr_gap_still_computed(self):
        """If wkg_z3 is None (no power meter) but hr_z3 present on both sides,
        power_gap_pct stays None while hr_gap_bpm is still computed."""
        db = self._db_with_n_rides(5, 5)
        metric_in  = {"wkg_z3": None, "hr_z3": 150.0, "has_power": False, "n_pts": 100}
        metric_out = {"wkg_z3": None, "hr_z3": 145.0, "has_power": False, "n_pts": 100}
        with patch("utils.indoor_outdoor_gap._z3_metrics", side_effect=lambda a, db: (
            metric_in if a.ride_environment == "indoor" else metric_out
        )):
            result = calculate_power_gap(1, db)
        assert result["power_gap_pct"] is None
        assert result["hr_gap_bpm"] == 5.0

    def test_zero_outdoor_wkg_guards_against_division_by_zero(self):
        """out_wkg == 0 fails the `out_wkg > 0` guard, so power_gap stays None
        instead of raising ZeroDivisionError."""
        db = self._db_with_n_rides(5, 5)
        metric_in  = {"wkg_z3": 3.0, "hr_z3": 150.0, "has_power": True, "n_pts": 100}
        metric_out = {"wkg_z3": 0.0, "hr_z3": 145.0, "has_power": True, "n_pts": 100}
        with patch("utils.indoor_outdoor_gap._z3_metrics", side_effect=lambda a, db: (
            metric_in if a.ride_environment == "indoor" else metric_out
        )):
            result = calculate_power_gap(1, db)
        assert result["power_gap_pct"] is None


# ── _z3_metrics ───────────────────────────────────────────────────────────────

def _trackpoint(hr=160.0, power=200.0):
    p = MagicMock()
    p.heart_rate_bpm = hr
    p.power_w = power
    return p


class TestZ3Metrics:
    def _db_with_points(self, points, weight_kg=70.0):
        db = MagicMock()

        def query_side_effect(model):
            name = getattr(model, "__name__", str(model))
            q = MagicMock()
            if name == "TrackPoint":
                q.filter.return_value.order_by.return_value.all.return_value = points
            elif name == "User":
                q.filter_by.return_value.first.return_value = SimpleNamespace(weight_kg=weight_kg)
            else:
                q.filter.return_value.first.return_value = None
            return q

        db.query.side_effect = query_side_effect
        return db

    def test_missing_max_hr_returns_none(self):
        act = _activity(max_hr=None)
        db = self._db_with_points([])
        assert _z3_metrics(act, db) is None

    def test_zero_max_hr_returns_none(self):
        act = _activity(max_hr=0)
        db = self._db_with_points([])
        assert _z3_metrics(act, db) is None

    def test_negative_max_hr_returns_none(self):
        act = _activity(max_hr=-185.0)
        db = self._db_with_points([])
        assert _z3_metrics(act, db) is None

    def test_fewer_than_min_z3_points_returns_none(self):
        act = _activity(max_hr=185.0)
        # 185*0.70=129.5, 185*0.85=157.25 -> hr=140 is in Z3, but only 10 pts
        points = [_trackpoint(hr=140.0) for _ in range(10)]
        db = self._db_with_points(points)
        assert _z3_metrics(act, db) is None

    def test_exactly_min_z3_points_succeeds(self):
        act = _activity(max_hr=185.0)
        points = [_trackpoint(hr=140.0, power=200.0) for _ in range(60)]
        db = self._db_with_points(points)
        result = _z3_metrics(act, db)
        assert result is not None
        assert result["n_pts"] == 60
        assert result["has_power"] is True

    def test_points_outside_z3_band_are_excluded(self):
        act = _activity(max_hr=200.0)  # band: 140 - 170
        in_band = [_trackpoint(hr=150.0) for _ in range(60)]
        out_of_band_low = [_trackpoint(hr=100.0) for _ in range(20)]
        out_of_band_high = [_trackpoint(hr=190.0) for _ in range(20)]
        db = self._db_with_points(in_band + out_of_band_low + out_of_band_high)
        result = _z3_metrics(act, db)
        assert result["n_pts"] == 60

    def test_zero_heart_rate_excluded_even_if_in_numeric_band(self):
        """hr_lo for max_hr<=0 would be <=0 but max_hr is guarded earlier;
        the explicit `p.heart_rate_bpm > 0` check excludes any non-positive hr
        reading from contaminating the Z3 average."""
        act = _activity(max_hr=185.0)
        points = [_trackpoint(hr=0.0) for _ in range(60)] + [_trackpoint(hr=140.0) for _ in range(60)]
        db = self._db_with_points(points)
        result = _z3_metrics(act, db)
        assert result["n_pts"] == 60

    def test_none_heart_rate_excluded(self):
        act = _activity(max_hr=185.0)
        points = [_trackpoint(hr=None) for _ in range(60)] + [_trackpoint(hr=140.0) for _ in range(60)]
        db = self._db_with_points(points)
        result = _z3_metrics(act, db)
        assert result["n_pts"] == 60

    def test_power_at_or_below_20w_excluded_from_power_average(self):
        act = _activity(max_hr=185.0)
        low_power_pts  = [_trackpoint(hr=140.0, power=20.0) for _ in range(30)]
        good_power_pts = [_trackpoint(hr=140.0, power=200.0) for _ in range(30)]
        db = self._db_with_points(low_power_pts + good_power_pts)
        result = _z3_metrics(act, db)
        # n_pts counts all Z3 hr points (60), but wkg should reflect only the
        # >20W points (200W / weight), not be dragged down/contaminated by the
        # excluded low-power points.
        assert result["n_pts"] == 60
        assert result["wkg_z3"] == round(200.0 / 70.0, 3)

    def test_no_power_data_at_all_yields_none_wkg_but_has_power_false(self):
        act = _activity(max_hr=185.0)
        points = [_trackpoint(hr=140.0, power=None) for _ in range(60)]
        db = self._db_with_points(points)
        result = _z3_metrics(act, db)
        assert result["wkg_z3"] is None
        assert result["has_power"] is False

    def test_missing_user_weight_yields_none_wkg(self):
        act = _activity(max_hr=185.0)
        points = [_trackpoint(hr=140.0, power=200.0) for _ in range(60)]
        db = self._db_with_points(points, weight_kg=None)
        result = _z3_metrics(act, db)
        assert result["wkg_z3"] is None
        assert result["has_power"] is True

    def test_user_lookup_exception_falls_back_to_none_weight(self):
        """If db.query(User) raises (e.g. User model missing/misconfigured),
        the try/except around weight lookup should swallow it and treat
        weight_kg as None rather than propagating."""
        act = _activity(max_hr=185.0)
        points = [_trackpoint(hr=140.0, power=200.0) for _ in range(60)]
        db = MagicMock()

        def query_side_effect(model):
            name = getattr(model, "__name__", str(model))
            q = MagicMock()
            if name == "TrackPoint":
                q.filter.return_value.order_by.return_value.all.return_value = points
            else:
                raise RuntimeError("boom")
            return q

        db.query.side_effect = query_side_effect
        result = _z3_metrics(act, db)
        assert result["wkg_z3"] is None


# ── _best_sustained_effort ───────────────────────────────────────────────────

class TestBestSustainedEffort:
    def _db_with_points(self, points):
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = points
        return db

    def test_too_few_points_returns_none(self):
        act = _activity()
        points = [_trackpoint() for _ in range(10)]  # well under 15*30=450
        db = self._db_with_points(points)
        assert _best_sustained_effort(act, db, min_minutes=15) is None

    def test_no_window_with_power_above_threshold_returns_none(self):
        act = _activity()
        points = [_trackpoint(power=10.0) for _ in range(500)]  # all <=20W, excluded
        db = self._db_with_points(points)
        assert _best_sustained_effort(act, db, min_minutes=15) is None

    def test_finds_best_window_average_power(self):
        act = _activity()
        # 450 baseline points at 100W, then a longer (460-point) high-power
        # segment at 300W. The scan's loop is `range(len(pts) - min_pts)`,
        # so the very last start index it tries is len(pts)-min_pts-1 (an
        # off-by-one short of len(pts)-min_pts) -- meaning a purely-high
        # window is only reachable if the high segment is strictly longer
        # than min_pts. Padding it out guarantees a pure 300W window of
        # length min_pts is among the windows scanned.
        low = [_trackpoint(power=100.0, hr=150.0) for _ in range(450)]
        high = [_trackpoint(power=300.0, hr=170.0) for _ in range(460)]
        points = low + high
        db = self._db_with_points(points)
        result = _best_sustained_effort(act, db, min_minutes=15)
        assert result is not None
        assert result["avg_power"] == 300.0
        assert result["avg_hr"] == 170.0
        assert result["duration_min"] == 15

    def test_exactly_min_minutes_worth_of_points_succeeds(self):
        act = _activity()
        # len(pts) must be >= min_minutes*30; use exactly one more than that
        # boundary so a window of min_pts can be formed (range(len-min_pts) needs >=1)
        points = [_trackpoint(power=150.0, hr=160.0) for _ in range(451)]
        db = self._db_with_points(points)
        result = _best_sustained_effort(act, db, min_minutes=15)
        assert result is not None
        assert result["avg_power"] == 150.0

    def test_boundary_exactly_min_pts_total_returns_none(self):
        """len(pts) == min_minutes*30 fails the `< ` check (not equal), so it
        passes the initial gate, but range(len(pts) - min_pts) == range(0) is
        empty, meaning no window is ever evaluated -> best_slice stays None."""
        points = [_trackpoint(power=150.0, hr=160.0) for _ in range(450)]
        db = self._db_with_points(points)
        act = _activity()
        result = _best_sustained_effort(act, db, min_minutes=15)
        assert result is None

    def test_no_heart_rate_data_yields_none_avg_hr(self):
        points = [_trackpoint(power=150.0, hr=None) for _ in range(451)]
        db = self._db_with_points(points)
        act = _activity()
        result = _best_sustained_effort(act, db, min_minutes=15)
        assert result is not None
        assert result["avg_hr"] is None


# ── calibrate_from_dual_test ─────────────────────────────────────────────────

def _make_dual_test_db(indoor_act, outdoor_act, indoor_points, outdoor_points, profile):
    """Build a db mock where each db.query(Activity)/.filter().first() call
    returns activities keyed by id, and each db.query(TrackPoint) call
    returns the right points for the activity being queried -- by inspecting
    the `activity_id` value passed into the filter() call args.

    A plain side_effect=[a, b] list breaks for this module because
    get_act()/db.query(Activity) is called fresh for each activity id, and
    MagicMock(model) returns a *new* child mock each call, so iterator state
    set on it never persists. We instead derive the answer from the actual
    filter() call arguments.
    """
    db = MagicMock()
    _next_activity_call = [indoor_act, outdoor_act]
    _next_trackpoint_call = [indoor_points, outdoor_points]

    def query_side_effect(model):
        name = getattr(model, "__name__", str(model))
        q = MagicMock()
        if name == "Activity":
            def filter_fn(*args, **kwargs):
                inner = MagicMock()
                # args are SQLAlchemy-style boolean clause mocks; with plain
                # MagicMock Activity.id == act_id comparisons we can't
                # inspect them directly, so fall back to call-count based
                # ordering matching get_act()'s call sequence (indoor first).
                inner.first.return_value = _next_activity_call.pop(0)
                return inner
            q.filter.side_effect = filter_fn
        elif name == "TrackPoint":
            def filter_fn(*args, **kwargs):
                inner = MagicMock()
                inner.order_by.return_value.all.return_value = _next_trackpoint_call.pop(0)
                return inner
            q.filter.side_effect = filter_fn
        elif name == "IndoorOutdoorProfile":
            q.filter.return_value.first.return_value = profile
        return q

    db.query.side_effect = query_side_effect
    return db


class TestCalibrateFromDualTest:
    def test_activity_not_found_raises(self):
        db = MagicMock()
        act_q = MagicMock()
        act_q.filter.return_value.first.return_value = None

        def query_side_effect(model):
            name = getattr(model, "__name__", str(model))
            if name == "Activity":
                return act_q
            q = MagicMock()
            q.filter.return_value.first.return_value = None
            return q

        db.query.side_effect = query_side_effect
        with pytest.raises(ValueError, match="not found"):
            calibrate_from_dual_test(1, 99, 100, db)

    def test_full_flow_computes_gap_and_saves_profile(self):
        indoor_act = _activity(env="indoor", user_id=1)
        indoor_act.id = 10
        outdoor_act = _activity(env="outdoor", user_id=1)
        outdoor_act.id = 20

        indoor_points  = [_trackpoint(power=200.0, hr=150.0) for _ in range(451)]
        outdoor_points = [_trackpoint(power=230.0, hr=145.0) for _ in range(451)]

        profile = MagicMock()
        db = _make_dual_test_db(indoor_act, outdoor_act, indoor_points, outdoor_points, profile)

        result = calibrate_from_dual_test(1, 10, 20, db)

        assert result["power_gap_pct"] is not None
        assert result["power_gap_pct"] < 0  # 200W indoor vs 230W outdoor
        assert result["indoor_ftp_estimated"] == round(200.0 * 0.95, 0)
        assert result["outdoor_ftp_estimated"] == round(230.0 * 0.95, 0)
        assert profile.manual_power_gap_pct == result["power_gap_pct"]
        assert profile.calibration_method == "same_route_test"
        db.commit.assert_called_once()

    def test_no_sustained_effort_in_either_activity_raises(self):
        indoor_act = _activity(env="indoor", user_id=1)
        indoor_act.id = 10
        outdoor_act = _activity(env="outdoor", user_id=1)
        outdoor_act.id = 20

        db = _make_dual_test_db(indoor_act, outdoor_act, [], [], profile=MagicMock())

        with pytest.raises(ValueError, match="sustained effort"):
            calibrate_from_dual_test(1, 10, 20, db)

    def test_creates_new_profile_when_none_exists(self):
        indoor_act = _activity(env="indoor", user_id=1)
        indoor_act.id = 10
        outdoor_act = _activity(env="outdoor", user_id=1)
        outdoor_act.id = 20

        indoor_points  = [_trackpoint(power=200.0, hr=150.0) for _ in range(451)]
        outdoor_points = [_trackpoint(power=230.0, hr=145.0) for _ in range(451)]

        db = _make_dual_test_db(indoor_act, outdoor_act, indoor_points, outdoor_points, profile=None)
        calibrate_from_dual_test(1, 10, 20, db)
        db.add.assert_called_once()


# ── recalculate_training_load_corrected ──────────────────────────────────────

class TestRecalculateTrainingLoadCorrected:
    def _db_with_activities(self, activities):
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = activities
        return db

    def test_no_activities_returns_zeroed_result(self):
        db = self._db_with_activities([])
        result = recalculate_training_load_corrected(1, db)
        assert result["original"] == {"ctl": 0.0, "atl": 0.0, "tsb": 0.0}
        assert result["corrected"] == {"ctl": 0.0, "atl": 0.0, "tsb": 0.0}
        assert "No training data." in result["difference"]["note"]

    def test_indoor_activity_uses_corrected_tss_when_present(self):
        now = datetime.utcnow()
        act = SimpleNamespace(
            date=now - timedelta(days=5), tss=60.0, corrected_tss=70.0,
            ride_environment="indoor",
        )
        db = self._db_with_activities([act])
        result = recalculate_training_load_corrected(1, db, days=90)
        assert result["corrected"]["ctl"] >= result["original"]["ctl"]

    def test_outdoor_activity_ignores_corrected_tss_field(self):
        """Even if corrected_tss is set, outdoor rides should use the
        original tss for the 'corrected' daily load too."""
        now = datetime.utcnow()
        act = SimpleNamespace(
            date=now - timedelta(days=5), tss=60.0, corrected_tss=999.0,
            ride_environment="outdoor",
        )
        db = self._db_with_activities([act])
        result = recalculate_training_load_corrected(1, db, days=90)
        assert result["corrected"]["ctl"] == result["original"]["ctl"]

    def test_indoor_activity_with_none_corrected_tss_falls_back_to_original(self):
        now = datetime.utcnow()
        act = SimpleNamespace(
            date=now - timedelta(days=5), tss=60.0, corrected_tss=None,
            ride_environment="indoor",
        )
        db = self._db_with_activities([act])
        result = recalculate_training_load_corrected(1, db, days=90)
        assert result["corrected"]["ctl"] == result["original"]["ctl"]

    def test_none_tss_treated_as_zero(self):
        now = datetime.utcnow()
        act = SimpleNamespace(
            date=now - timedelta(days=5), tss=None, corrected_tss=None,
            ride_environment="outdoor",
        )
        db = self._db_with_activities([act])
        result = recalculate_training_load_corrected(1, db, days=90)
        assert result["original"]["ctl"] >= 0.0

    def test_minimal_delta_below_half_point_yields_minimal_impact_note(self):
        now = datetime.utcnow()
        act = SimpleNamespace(
            date=now - timedelta(days=1), tss=10.0, corrected_tss=10.1,
            ride_environment="indoor",
        )
        db = self._db_with_activities([act])
        result = recalculate_training_load_corrected(1, db, days=90)
        assert "minimal impact" in result["difference"]["note"].lower()

    def test_positive_ctl_delta_phrases_note_as_increase(self):
        now = datetime.utcnow()
        activities = [
            SimpleNamespace(
                date=now - timedelta(days=i), tss=50.0, corrected_tss=80.0,
                ride_environment="indoor",
            )
            for i in range(60)
        ]
        db = self._db_with_activities(activities)
        result = recalculate_training_load_corrected(1, db, days=90)
        assert result["difference"]["ctl_delta"] > 0
        assert "adds" in result["difference"]["note"]

    def test_negative_ctl_delta_phrases_note_as_decrease(self):
        now = datetime.utcnow()
        activities = [
            SimpleNamespace(
                date=now - timedelta(days=i), tss=80.0, corrected_tss=50.0,
                ride_environment="indoor",
            )
            for i in range(60)
        ]
        db = self._db_with_activities(activities)
        result = recalculate_training_load_corrected(1, db, days=90)
        assert result["difference"]["ctl_delta"] < 0
        assert "reduces" in result["difference"]["note"]

    def test_multiple_activities_same_day_sum_tss(self):
        now = datetime.utcnow()
        d = now - timedelta(days=3)
        activities = [
            SimpleNamespace(date=d, tss=20.0, corrected_tss=None, ride_environment="outdoor"),
            SimpleNamespace(date=d, tss=30.0, corrected_tss=None, ride_environment="outdoor"),
        ]
        db = self._db_with_activities(activities)
        result = recalculate_training_load_corrected(1, db, days=90)
        # Just confirm it runs without error and produces non-negative load
        assert result["original"]["ctl"] >= 0.0


# ── update_indoor_outdoor_gap ────────────────────────────────────────────────

class TestUpdateIndoorOutdoorGap:
    def test_insufficient_data_does_not_overwrite_existing_profile(self):
        profile = MagicMock()
        profile.power_gap_pct = -12.0  # pre-existing good value

        db = MagicMock()

        def query_side_effect(model):
            name = getattr(model, "__name__", str(model))
            q = MagicMock()
            if name == "IndoorOutdoorProfile":
                q.filter.return_value.first.return_value = profile
            elif name == "Activity":
                q.filter.return_value.order_by.return_value.all.return_value = []
            return q

        db.query.side_effect = query_side_effect

        with patch("utils.indoor_outdoor_gap.calculate_power_gap",
                   return_value={"confidence": "insufficient_data", "power_gap_pct": None}):
            update_indoor_outdoor_gap(1, db)

        # Should not have been reassigned to None since confidence is insufficient_data
        assert profile.power_gap_pct == -12.0
        db.commit.assert_called_once()

    def test_sufficient_data_creates_new_profile_and_persists_fields(self):
        db = MagicMock()

        def query_side_effect(model):
            name = getattr(model, "__name__", str(model))
            q = MagicMock()
            if name == "IndoorOutdoorProfile":
                q.filter.return_value.first.return_value = None
            return q

        db.query.side_effect = query_side_effect

        fake_result = {
            "power_gap_pct": -9.5, "hr_gap_bpm": 6.0, "confidence": "medium",
            "indoor_avg_wkg_z3": 3.0, "outdoor_avg_wkg_z3": 3.3,
            "indoor_avg_hr_z3": 150.0, "outdoor_avg_hr_z3": 144.0,
            "indoor_rides_used": 6, "outdoor_rides_used": 6,
            "interpretation": "x", "recommendation": "y",
        }
        with patch("utils.indoor_outdoor_gap.calculate_power_gap", return_value=fake_result):
            update_indoor_outdoor_gap(1, db)

        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_high_confidence_overwrites_fields(self):
        profile = MagicMock()
        db = MagicMock()

        def query_side_effect(model):
            name = getattr(model, "__name__", str(model))
            q = MagicMock()
            if name == "IndoorOutdoorProfile":
                q.filter.return_value.first.return_value = profile
            return q

        db.query.side_effect = query_side_effect

        fake_result = {
            "power_gap_pct": -11.0, "hr_gap_bpm": 7.0, "confidence": "high",
            "indoor_avg_wkg_z3": 3.1, "outdoor_avg_wkg_z3": 3.5,
            "indoor_avg_hr_z3": 151.0, "outdoor_avg_hr_z3": 144.0,
            "indoor_rides_used": 12, "outdoor_rides_used": 11,
            "interpretation": "x", "recommendation": "y",
        }
        with patch("utils.indoor_outdoor_gap.calculate_power_gap", return_value=fake_result):
            update_indoor_outdoor_gap(1, db)

        assert profile.power_gap_pct == -11.0
        assert profile.power_gap_confidence == "high"
        assert profile.indoor_rides_analyzed == 12


# ── apply_correction_factors: additional boundary coverage ──────────────────

class TestApplyCorrectionFactorsBoundaries:
    def test_power_gap_exactly_minus_100_guarded_against_division_by_zero(self):
        """1.0 + power_gap/100 == 0 when power_gap == -100; the guard
        `(1.0 + power_gap/100.0) > 0` should keep power_cf as None instead of
        raising ZeroDivisionError."""
        act = _activity(env="indoor", tss=50.0)
        prof = _profile(power_gap_pct=-100.0, hr_gap_bpm=None)
        result = apply_correction_factors(act, prof)
        assert result["power_correction_factor"] is None

    def test_power_gap_below_minus_100_guarded(self):
        act = _activity(env="indoor", tss=50.0)
        prof = _profile(power_gap_pct=-150.0, hr_gap_bpm=None)
        result = apply_correction_factors(act, prof)
        assert result["power_correction_factor"] is None

    def test_hr_gap_none_skips_hr_correction(self):
        act = _activity(env="indoor", tss=50.0)
        prof = _profile(power_gap_pct=None, hr_gap_bpm=None)
        result = apply_correction_factors(act, prof)
        assert result["hr_correction_factor"] is None
        assert result["correction_applied"] is False

    def test_hr_gap_present_but_avg_hr_missing_skips_hr_correction(self):
        act = _activity(env="indoor", tss=50.0, avg_hr=None)
        prof = _profile(power_gap_pct=None, hr_gap_bpm=5.0)
        result = apply_correction_factors(act, prof)
        assert result["hr_correction_factor"] is None

    def test_hr_gap_present_but_avg_hr_zero_skips_hr_correction(self):
        act = _activity(env="indoor", tss=50.0, avg_hr=0.0)
        prof = _profile(power_gap_pct=None, hr_gap_bpm=5.0)
        result = apply_correction_factors(act, prof)
        assert result["hr_correction_factor"] is None

    def test_hr_gap_used_as_fallback_tss_scale_when_no_power_gap(self):
        act = _activity(env="indoor", tss=100.0, avg_hr=160.0)
        prof = _profile(power_gap_pct=None, hr_gap_bpm=8.0)
        result = apply_correction_factors(act, prof)
        expected_hr_cf = round((160.0 - 8.0) / 160.0, 4)
        assert result["hr_correction_factor"] == expected_hr_cf
        assert result["corrected_tss"] == round(100.0 * expected_hr_cf, 1)
        assert result["correction_source"] == "calculated_gap"

    def test_power_correction_takes_precedence_over_hr_for_tss(self):
        """When both power_cf and hr_cf are available, corrected_tss should
        be derived from power_cf (squared), not hr_cf."""
        act = _activity(env="indoor", tss=100.0, avg_hr=160.0)
        prof = _profile(power_gap_pct=-10.0, hr_gap_bpm=8.0)
        result = apply_correction_factors(act, prof)
        power_cf = result["power_correction_factor"]
        expected_tss_via_power = round(100.0 * (power_cf ** 2), 1)
        assert result["corrected_tss"] == expected_tss_via_power

    def test_activity_missing_ride_environment_attr_treated_as_not_indoor(self):
        act = SimpleNamespace()  # no ride_environment attribute at all
        prof = _profile(power_gap_pct=-10.0)
        result = apply_correction_factors(act, prof)
        assert result["correction_applied"] is False

    def test_no_manual_calibration_source_is_calculated_gap(self):
        act = _activity(env="indoor", tss=50.0)
        prof = _profile(power_gap_pct=-10.0, manual_power_gap_pct=None)
        result = apply_correction_factors(act, prof)
        assert result["correction_source"] == "calculated_gap"


# ── _build_interpretation: additional coverage ───────────────────────────────

class TestBuildInterpretationAdditional:
    def test_none_power_gap_and_none_hr_gap_yields_no_interpretation(self):
        text = _build_interpretation(None, None, "high")
        assert text == "No interpretation available."

    def test_hr_gap_typical_range_boundaries(self):
        text_low  = _build_interpretation(None, 5.0, "high")
        text_high = _build_interpretation(None, 10.0, "high")
        assert "thermoregulation" in text_low
        assert "thermoregulation" in text_high

    def test_hr_gap_just_outside_typical_range(self):
        text_low  = _build_interpretation(None, 4.9, "high")
        text_high = _build_interpretation(None, 10.1, "high")
        assert "thermoregulation" not in text_low
        assert "thermoregulation" not in text_high

    def test_negative_hr_gap_described_as_lower(self):
        text = _build_interpretation(None, -3.0, "high")
        assert "lower" in text

    def test_power_gap_exactly_zero_is_not_typical_and_not_inverted(self):
        """power_gap == 0: direction='higher' (since 0 < 0 is False), inv =
        (0 > 0) is False, typical is always False (bug) -> falls to else
        branch with abs(power_gap)=0, which is "within" since 0 is not > 15."""
        text = _build_interpretation(0.0, None, "high")
        assert "higher" in text
        assert "within" in text

    def test_power_gap_far_outside_typical_range_marked_slightly_outside(self):
        text = _build_interpretation(-30.0, None, "high")
        assert "slightly outside" in text

    def test_medium_confidence_does_not_add_low_confidence_note(self):
        text = _build_interpretation(-10.0, None, "medium")
        assert "Confidence is low" not in text

    def test_insufficient_data_confidence_adds_low_confidence_note(self):
        text = _build_interpretation(-10.0, None, "insufficient_data")
        assert "more rides" in text.lower()

    def test_both_power_and_hr_gap_present_combines_sentences(self):
        text = _build_interpretation(-10.0, 7.0, "high")
        assert "indoor power" in text
        assert "HR runs" in text


# ── _build_recommendation: additional coverage ───────────────────────────────

class TestBuildRecommendationAdditional:
    def test_boundary_exactly_minus_20_is_not_unusually_large(self):
        """power_gap < -20 triggers the warning; -20.0 itself does not (strict <)."""
        text = _build_recommendation(-20.0, None)
        assert "unusually large" not in text

    def test_just_below_minus_20_is_unusually_large(self):
        text = _build_recommendation(-20.1, None)
        assert "unusually large" in text

    def test_boundary_zero_gap_is_not_positive_branch(self):
        """power_gap > 0 is strict, so 0.0 should fall to the normal reduction branch."""
        text = _build_recommendation(0.0, None)
        assert "reduce target power by 0%" in text or "%" in text

    def test_typical_negative_gap_includes_correct_percentage(self):
        text = _build_recommendation(-12.0, None)
        assert "12%" in text


# ── _ema_model: additional coverage ──────────────────────────────────────────

class TestEmaModelAdditional:
    def test_single_day_window_uses_only_that_days_load(self):
        d = datetime(2024, 5, 1)
        ctl, atl = _ema_model({"2024-05-01": 100.0}, d, d)
        assert ctl == pytest.approx(100.0 / 42, abs=1e-6)
        assert atl == pytest.approx(100.0 / 7, abs=1e-6)

    def test_missing_days_treated_as_zero_load(self):
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 5)
        ctl, atl = _ema_model({"2024-01-01": 100.0}, start, end)
        # load decays toward zero over the missing days
        assert 0 < ctl < 100.0
        assert 0 < atl < 100.0
