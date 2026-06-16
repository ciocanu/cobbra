"""
Tests for utils/hydration.py — Hydration & Heat Strain Analysis algorithms.

Run from the backend directory:
    python -m pytest tests/test_hydration.py -v
"""

import json
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.hydration import (
    estimate_sweat_rate,
    calculate_hydration_deficit,
    classify_risk_level,
    estimate_hr_effects,
    generate_hydration_recommendations,
    update_heat_adaptation,
    build_analysis,
    _heat_index,
    _classify_intensity,
    _analysis_quality,
)


# ── Sweat rate estimation ──────────────────────────────────────────────────────

class TestEstimateSweatRate:
    # estimate_sweat_rate returns (rate_ml_h, quality, effective_temp_c, model_method)
    def test_cool_conditions_low_intensity_returns_moderate_rate(self):
        rate, quality, _, _ = estimate_sweat_rate(18.0, 50.0, 0.55, 1.5)
        assert 400 <= rate <= 1000, f"Expected 400-1000 ml/h, got {rate}"

    def test_hot_humid_high_intensity_raises_rate(self):
        hot_rate,  _, _, _ = estimate_sweat_rate(36.0, 80.0, 0.85, 2.0)
        cool_rate, _, _, _ = estimate_sweat_rate(18.0, 50.0, 0.55, 1.0)
        assert hot_rate > cool_rate

    def test_rate_clamped_at_floor(self):
        rate, _, _, _ = estimate_sweat_rate(-5.0, 10.0, 0.2, 0.5)
        assert rate >= 150

    def test_rate_clamped_at_ceiling(self):
        rate, _, _, _ = estimate_sweat_rate(45.0, 99.0, 1.0, 4.0)
        assert rate <= 2500

    def test_zero_duration_returns_zero(self):
        rate, _, _, _ = estimate_sweat_rate(30.0, 70.0, 0.75, 0.0)
        assert rate == 0.0

    def test_calibrated_rate_anchors_estimate(self):
        # With a calibrated rate, quality should be "high"
        rate, quality, _, method = estimate_sweat_rate(32.0, 70.0, 0.70, 2.0, user_calibrated_ml_h=1100.0)
        assert quality == "high"
        assert method == "calibrated"
        # Should be close to the calibrated rate (modified by environment)
        assert 900 <= rate <= 2000

    def test_uncalibrated_hot_gives_high_quality(self):
        _, quality, _, _ = estimate_sweat_rate(32.0, 75.0, 0.75, 2.0)
        assert quality == "high"

    def test_missing_humidity_defaults_gracefully(self):
        rate, _, _, _ = estimate_sweat_rate(25.0, None, 0.70, 1.0)
        assert rate > 0

    def test_heat_adaptation_high_increases_rate(self):
        low_rate,  _, _, _ = estimate_sweat_rate(32.0, 70.0, 0.75, 2.0, heat_adaptation_level="low")
        high_rate, _, _, _ = estimate_sweat_rate(32.0, 70.0, 0.75, 2.0, heat_adaptation_level="high")
        assert high_rate > low_rate

    def test_very_high_intensity_multiplier_applied(self):
        high_rate, _, _, _ = estimate_sweat_rate(25.0, 60.0, 0.95, 1.0)
        low_rate,  _, _, _ = estimate_sweat_rate(25.0, 60.0, 0.40, 1.0)
        assert high_rate > low_rate


# ── Hydration deficit ─────────────────────────────────────────────────────────

class TestCalculateHydrationDeficit:
    def test_no_intake_returns_none(self):
        deficit, pct = calculate_hydration_deficit(1500, None, 70.0)
        assert deficit is None
        assert pct is None

    def test_sufficient_intake_zero_deficit(self):
        deficit, _ = calculate_hydration_deficit(1000, 1200, 70.0)
        assert deficit == 0

    def test_deficit_calculated_correctly(self):
        deficit, pct = calculate_hydration_deficit(2000, 800, 80.0)
        assert deficit == 1200
        assert abs(pct - 1.5) < 0.05   # 1200 / 80000 * 100 = 1.5%

    def test_no_weight_gives_none_pct(self):
        deficit, pct = calculate_hydration_deficit(2000, 500, None)
        assert deficit == 1500
        assert pct is None

    def test_exact_replacement_no_deficit(self):
        deficit, pct = calculate_hydration_deficit(1800, 1800, 70.0)
        assert deficit == 0

    def test_large_deficit_over_threshold(self):
        # 4L sweat, 0L intake, 70 kg → 5.7% deficit
        deficit, pct = calculate_hydration_deficit(4000, 0, 70.0)
        assert pct > 5.0


# ── Risk classification ───────────────────────────────────────────────────────

class TestClassifyRiskLevel:
    def test_low_deficit_mild_temp_is_low_risk(self):
        risk = classify_risk_level(0.5, 20.0, 55.0, 1.0)
        assert risk == "low"

    def test_one_pct_deficit_is_moderate(self):
        risk = classify_risk_level(1.2, 22.0, 60.0, 1.5)
        assert risk == "moderate"

    def test_two_pct_deficit_is_high(self):
        risk = classify_risk_level(2.5, 28.0, 70.0, 2.0)
        assert risk == "high"

    def test_four_pct_deficit_is_critical(self):
        risk = classify_risk_level(4.2, 35.0, 75.0, 3.0)
        assert risk == "critical"

    def test_no_deficit_hot_long_ride_is_high(self):
        risk = classify_risk_level(None, 40.0, 70.0, 2.0)
        assert risk in ("moderate", "high")

    def test_no_deficit_cool_short_is_low(self):
        risk = classify_risk_level(None, 18.0, 50.0, 0.5)
        assert risk == "low"

    def test_extreme_heat_index_escalates_risk(self):
        # 38°C + 80% humidity → very high heat index
        risk = classify_risk_level(None, 38.0, 80.0, 2.0)
        assert risk in ("moderate", "high")


# ── HR and performance effects ────────────────────────────────────────────────

class TestEstimateHrEffects:
    def test_cool_conditions_low_heat_drift(self):
        hr_heat, hr_dehyd, perf = estimate_hr_effects(None, 18.0, 50.0, 1.0)
        assert hr_heat < 3.0   # very low heat drift at 18°C

    def test_hot_conditions_positive_heat_drift(self):
        hr_heat, _, _ = estimate_hr_effects(None, 38.0, 80.0, 2.0)
        assert hr_heat > 3.0

    def test_no_deficit_no_dehydration_drift(self):
        _, hr_dehyd, perf = estimate_hr_effects(None, 25.0, 65.0, 1.5)
        assert hr_dehyd is None
        assert perf is None

    def test_deficit_causes_dehydration_drift(self):
        _, hr_dehyd, _ = estimate_hr_effects(2.0, 28.0, 70.0, 2.0)
        assert hr_dehyd is not None
        assert hr_dehyd > 0

    def test_performance_loss_only_above_one_pct(self):
        _, _, perf_zero  = estimate_hr_effects(0.8, 28.0, 70.0, 1.5)  # below 1%
        _, _, perf_above = estimate_hr_effects(2.5, 28.0, 70.0, 1.5)  # above 1%
        assert perf_zero == 0.0
        assert perf_above > 0.0

    def test_performance_loss_scales_with_deficit(self):
        _, _, perf_mild   = estimate_hr_effects(1.5, 30.0, 70.0, 2.0)
        _, _, perf_severe = estimate_hr_effects(3.5, 30.0, 70.0, 2.0)
        assert perf_severe > perf_mild

    def test_heat_drift_scales_with_duration(self):
        hr_short, _, _ = estimate_hr_effects(None, 35.0, 75.0, 0.5)
        hr_long,  _, _ = estimate_hr_effects(None, 35.0, 75.0, 2.5)
        assert hr_long >= hr_short


# ── Recommendations ────────────────────────────────────────────────────────────

class TestGenerateRecommendations:
    def _call(self, **kwargs):
        defaults = dict(
            sweat_rate_ml_h=900.0,
            total_sweat_ml=1800.0,
            intake_ml=700,
            deficit_ml=1100.0,
            deficit_body_pct=1.6,
            risk_level="moderate",
            temp_c=28.0,
            effective_temp_c=24.0,
            humidity_pct=65.0,
            duration_h=2.0,
            weight_kg=72.0,
            heat_adaptation="low",
            has_calibrated_rate=False,
            model_method="population",
        )
        defaults.update(kwargs)
        return generate_hydration_recommendations(**defaults)

    def test_returns_list(self):
        recs = self._call()
        assert isinstance(recs, list)
        assert len(recs) >= 4

    def test_first_rec_is_intake_target(self):
        recs = self._call()
        assert "ml/h" in recs[0].lower() or "target" in recs[0].lower()

    def test_critical_risk_includes_warning(self):
        recs = self._call(risk_level="critical", deficit_body_pct=4.5)
        assert any("critical" in r.lower() for r in recs)

    def test_sweat_test_nudge_when_not_calibrated(self):
        recs = self._call(has_calibrated_rate=False)
        assert any("sweat test" in r.lower() for r in recs)

    def test_no_sweat_test_nudge_when_calibrated(self):
        recs = self._call(has_calibrated_rate=True)
        assert not any("sweat test" in r.lower() for r in recs)

    def test_electrolyte_advice_for_long_hot_ride(self):
        recs = self._call(duration_h=2.5, temp_c=30.0)
        assert any("electrolyte" in r.lower() or "sodium" in r.lower() for r in recs)

    def test_heat_adaptation_advice_when_low(self):
        recs = self._call(temp_c=28.0, heat_adaptation="low")
        assert any("heat" in r.lower() and "adapt" in r.lower() for r in recs)

    def test_no_heat_adapt_advice_when_already_high(self):
        recs = self._call(heat_adaptation="high")
        # shouldn't push adaptation advice when already adapted
        assert not any("heat tolerance" in r.lower() and "build" in r.lower() for r in recs)

    def test_recovery_drink_included_when_deficit_known(self):
        recs = self._call(intake_ml=500, deficit_ml=1200.0)
        assert any("post" in r.lower() or "recover" in r.lower() for r in recs)


# ── Heat adaptation ────────────────────────────────────────────────────────────

class TestUpdateHeatAdaptation:
    def test_hot_ride_increments_counter(self):
        rides, level = update_heat_adaptation(2, False, 30.0)
        assert rides == 3

    def test_cold_ride_does_not_increment(self):
        rides, level = update_heat_adaptation(4, False, 15.0)
        assert rides == 4

    def test_low_level_below_three_rides(self):
        _, level = update_heat_adaptation(1, False, 28.0)
        assert level == "low"

    def test_moderate_level_three_to_seven_rides(self):
        _, level = update_heat_adaptation(3, False, 30.0)
        assert level == "moderate"

    def test_high_level_eight_or_more_rides(self):
        _, level = update_heat_adaptation(8, False, 30.0)
        assert level == "high"

    def test_counter_cap_at_99(self):
        rides, _ = update_heat_adaptation(99, True, 35.0)
        assert rides == 99

    def test_threshold_at_27c(self):
        cold, _ = update_heat_adaptation(0, False, 26.9)
        hot,  _ = update_heat_adaptation(0, False, 27.0)
        assert cold == 0
        assert hot  == 1

    def test_explicit_hot_flag_overrides_temp(self):
        rides, _ = update_heat_adaptation(2, True, 10.0)  # cold temp, but flagged
        assert rides == 3


# ── Full build_analysis integration ───────────────────────────────────────────

class TestBuildAnalysis:
    def _build(self, **kwargs):
        defaults = dict(
            temp_c=28.0,
            humidity_pct=65.0,
            wind_speed_kmh=15.0,
            max_temp_c=32.0,
            duration_h=2.0,
            intensity_factor=0.75,
            intake_ml=800,
            weight_kg=72.0,
            user_calibrated_ml_h=None,
            heat_adaptation=None,
        )
        defaults.update(kwargs)
        return build_analysis(**defaults)

    def test_returns_all_required_keys(self):
        result = self._build()
        required = [
            "avg_temperature_c", "estimated_sweat_rate_ml_h", "estimated_total_sweat_ml",
            "reported_intake_ml", "deficit_ml", "deficit_body_pct",
            "estimated_hr_drift_heat_bpm", "risk_level", "analysis_quality",
            "recommendations_json",
        ]
        for key in required:
            assert key in result, f"Missing key: {key}"

    def test_recommendations_is_valid_json_list(self):
        result = self._build()
        recs = json.loads(result["recommendations_json"])
        assert isinstance(recs, list)
        assert len(recs) > 0

    def test_risk_level_is_valid(self):
        result = self._build()
        assert result["risk_level"] in ("low", "moderate", "high", "critical")

    def test_analysis_quality_is_valid(self):
        result = self._build()
        assert result["analysis_quality"] in ("low", "medium", "high")

    def test_total_sweat_matches_rate_times_duration(self):
        result = self._build(duration_h=2.0)
        expected = result["estimated_sweat_rate_ml_h"] * 2.0
        assert abs(result["estimated_total_sweat_ml"] - expected) < 5

    def test_deficit_reflects_intake(self):
        with_intake    = self._build(intake_ml=1000)
        without_intake = self._build(intake_ml=0)
        if with_intake["deficit_ml"] is not None and without_intake["deficit_ml"] is not None:
            assert with_intake["deficit_ml"] <= without_intake["deficit_ml"]

    def test_none_intake_omits_deficit(self):
        result = self._build(intake_ml=None)
        assert result["deficit_ml"] is None
        assert result["deficit_body_pct"] is None

    def test_no_weight_gives_none_pct(self):
        result = self._build(weight_kg=None)
        assert result["deficit_body_pct"] is None

    def test_hot_conditions_give_high_risk(self):
        result = self._build(temp_c=38.0, humidity_pct=85.0, intake_ml=0, weight_kg=70.0)
        assert result["risk_level"] in ("high", "critical")

    def test_cool_short_low_intensity_is_low_risk(self):
        result = self._build(temp_c=15.0, humidity_pct=50.0, duration_h=0.5,
                             intensity_factor=0.50, intake_ml=500)
        assert result["risk_level"] == "low"

    def test_wind_speed_stored(self):
        result = self._build(wind_speed_kmh=20.0)
        assert result["wind_speed_kmh"] == 20.0

    def test_max_temp_stored(self):
        result = self._build(max_temp_c=35.0)
        assert result["max_temperature_c"] == 35.0


# ── Private helpers ────────────────────────────────────────────────────────────

class TestHelpers:
    def test_heat_index_below_27c_returns_temp(self):
        assert _heat_index(20.0, 60.0) == 20.0

    def test_heat_index_above_27c_exceeds_temp(self):
        hi = _heat_index(35.0, 80.0)
        assert hi > 35.0

    def test_classify_intensity_boundaries(self):
        assert _classify_intensity(0.4)  == "low"
        assert _classify_intensity(0.60) == "moderate"
        assert _classify_intensity(0.80) == "high"
        assert _classify_intensity(0.95) == "very_high"

    def test_analysis_quality_needs_humidity_and_duration(self):
        assert _analysis_quality(25.0, None,  0.3) == "low"
        assert _analysis_quality(25.0, 65.0,  0.3) == "medium"
        assert _analysis_quality(25.0, 65.0,  1.0) == "high"
