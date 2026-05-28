"""
Tests for utils/indoor_outdoor_gap.py — Indoor/outdoor gap and correction.

Run from the backend directory:
    python -m pytest tests/test_indoor_outdoor_gap.py -v
"""

import sys
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.indoor_outdoor_gap import (
    apply_correction_factors,
    calibrate_from_ftp_values,
    _ema_model,
    _build_interpretation,
    _build_recommendation,
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
