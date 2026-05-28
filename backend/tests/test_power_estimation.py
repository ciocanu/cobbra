import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from utils.power_estimation import estimate_climbing_power, determine_estimation_quality, BIKE_DEFAULTS


def make_climb(gradient_pct, speed_kmh, duration_s, vam=None, elevation_gain_m=50):
    if vam is None:
        vam = (elevation_gain_m / duration_s) * 3600
    return {
        "avg_gradient_pct": gradient_pct,
        "avg_speed_kmh": speed_kmh,
        "duration_seconds": duration_s,
        "vam_m_per_hour": vam,
        "elevation_gain_m": elevation_gain_m,
    }


class TestKnownPhysics:
    def test_7pct_15kmh_75kg(self):
        """7% at 15 km/h, 75kg rider + 9kg bike ≈ 275W theoretical."""
        climb = make_climb(7.0, 15.0, 600, elevation_gain_m=175)
        result = estimate_climbing_power(climb, user_weight_kg=75.0, bike_weight_kg=9.0)
        assert result["estimated_power_w"] is not None
        # Should be within ±10% of theoretical ~275W
        assert 247 <= result["estimated_power_w"] <= 303, f"Got {result['estimated_power_w']}W"

    def test_returns_wkg(self):
        climb = make_climb(7.0, 15.0, 600, elevation_gain_m=175)
        result = estimate_climbing_power(climb, user_weight_kg=75.0)
        assert result["estimated_wkg"] is not None
        assert result["estimated_wkg"] == round(result["estimated_power_w"] / 75.0, 2)

    def test_confidence_interval_ordered(self):
        climb = make_climb(7.0, 15.0, 600, elevation_gain_m=175)
        result = estimate_climbing_power(climb, user_weight_kg=75.0)
        assert result["estimated_power_low_w"] <= result["estimated_power_w"] <= result["estimated_power_high_w"]

    def test_method_is_physics(self):
        climb = make_climb(7.0, 15.0, 600, elevation_gain_m=175)
        result = estimate_climbing_power(climb, user_weight_kg=75.0)
        assert result["estimation_method"] == "physics"


class TestGradientSensitivity:
    def test_higher_gradient_more_power(self):
        """At same speed, higher gradient → higher power."""
        speed = 15.0
        p4 = estimate_climbing_power(make_climb(4.0, speed, 600), user_weight_kg=75.0)["estimated_power_w"]
        p8 = estimate_climbing_power(make_climb(8.0, speed, 600), user_weight_kg=75.0)["estimated_power_w"]
        p12 = estimate_climbing_power(make_climb(12.0, speed, 600), user_weight_kg=75.0)["estimated_power_w"]
        assert p4 < p8 < p12

    def test_roughly_linear_with_gradient(self):
        """Power should scale approximately linearly with gradient for climbs."""
        speed = 12.0
        p4 = estimate_climbing_power(make_climb(4.0, speed, 600), user_weight_kg=75.0)["estimated_power_w"]
        p8 = estimate_climbing_power(make_climb(8.0, speed, 600), user_weight_kg=75.0)["estimated_power_w"]
        ratio = p8 / p4
        # Should roughly double (within 20% of 2.0)
        assert 1.5 <= ratio <= 2.5


class TestSpeedSensitivity:
    def test_higher_speed_more_power(self):
        """At same gradient, higher speed → more power."""
        g = 7.0
        p10 = estimate_climbing_power(make_climb(g, 10.0, 900), user_weight_kg=75.0)["estimated_power_w"]
        p15 = estimate_climbing_power(make_climb(g, 15.0, 600), user_weight_kg=75.0)["estimated_power_w"]
        p20 = estimate_climbing_power(make_climb(g, 20.0, 450), user_weight_kg=75.0)["estimated_power_w"]
        assert p10 < p15 < p20


class TestWeightSensitivity:
    def test_wkg_similar_across_weights(self):
        """W/kg should be similar for different rider weights at same effort."""
        climb = make_climb(7.0, 15.0, 600, elevation_gain_m=175)
        wkg60 = estimate_climbing_power(climb, user_weight_kg=60.0)["estimated_wkg"]
        wkg80 = estimate_climbing_power(climb, user_weight_kg=80.0)["estimated_wkg"]
        wkg100 = estimate_climbing_power(climb, user_weight_kg=100.0)["estimated_wkg"]
        # W/kg should all be within ±0.5 of each other (gravity-dominated)
        assert abs(wkg60 - wkg80) <= 0.5
        assert abs(wkg80 - wkg100) <= 0.5

    def test_absolute_watts_scale_with_weight(self):
        """Heavier rider produces more absolute watts at same speed/gradient."""
        climb = make_climb(7.0, 15.0, 600, elevation_gain_m=175)
        w60 = estimate_climbing_power(climb, user_weight_kg=60.0)["estimated_power_w"]
        w80 = estimate_climbing_power(climb, user_weight_kg=80.0)["estimated_power_w"]
        w100 = estimate_climbing_power(climb, user_weight_kg=100.0)["estimated_power_w"]
        assert w60 < w80 < w100


class TestAltitudeCorrection:
    def test_higher_altitude_slightly_less_power(self):
        """At higher altitude, lower air density → slightly less aero drag → slightly less power."""
        climb = make_climb(7.0, 15.0, 600, elevation_gain_m=175)
        p_sea = estimate_climbing_power(climb, user_weight_kg=75.0, altitude_m=0)["estimated_power_w"]
        p_high = estimate_climbing_power(climb, user_weight_kg=75.0, altitude_m=2000)["estimated_power_w"]
        # At altitude, aero component is smaller → total power slightly less
        assert p_high <= p_sea

    def test_low_altitude_minimal_effect(self):
        """In Lisbon/Setúbal region (0-200m), altitude effect < 2%."""
        climb = make_climb(7.0, 15.0, 600, elevation_gain_m=175)
        p0 = estimate_climbing_power(climb, user_weight_kg=75.0, altitude_m=0)["estimated_power_w"]
        p200 = estimate_climbing_power(climb, user_weight_kg=75.0, altitude_m=200)["estimated_power_w"]
        assert abs(p0 - p200) / p0 < 0.02


class TestQualityClassification:
    def test_high_quality_ideal_conditions(self):
        """8% gradient, 15 min sustained → high quality."""
        climb = make_climb(8.0, 12.0, 900, vam=1100)
        q = determine_estimation_quality(climb)
        assert q == "high"

    def test_medium_quality_borderline(self):
        """5% gradient, 4 min → medium quality."""
        climb = make_climb(5.0, 14.0, 240, vam=850)
        q = determine_estimation_quality(climb)
        assert q in ("medium", "low")

    def test_low_quality_short_climb(self):
        """3 min borderline with poor VAM → low quality."""
        climb = make_climb(4.5, 10.0, 180, vam=400)
        q = determine_estimation_quality(climb)
        assert q == "low"

    def test_long_sustained_is_high(self):
        """15 min at 7% → high quality."""
        climb = make_climb(7.0, 14.0, 900, vam=980)
        q = determine_estimation_quality(climb)
        assert q == "high"


class TestZeroSpeedHandling:
    def test_zero_speed_returns_none(self):
        """If speed is 0, should return None power (can't compute)."""
        climb = make_climb(7.0, 0.0, 300)
        result = estimate_climbing_power(climb, user_weight_kg=75.0)
        assert result["estimated_power_w"] is None


class TestBikeTypeDefaults:
    def test_mtb_more_power_than_road(self):
        """MTB has more weight and rolling resistance → more power needed for same speed."""
        climb = make_climb(7.0, 12.0, 600, elevation_gain_m=140)
        road = BIKE_DEFAULTS["road"]
        mtb = BIKE_DEFAULTS["mtb"]
        p_road = estimate_climbing_power(
            climb, user_weight_kg=75.0,
            bike_weight_kg=road["bike_weight_kg"], crr=road["crr"], cda=road["cda"]
        )["estimated_power_w"]
        p_mtb = estimate_climbing_power(
            climb, user_weight_kg=75.0,
            bike_weight_kg=mtb["bike_weight_kg"], crr=mtb["crr"], cda=mtb["cda"]
        )["estimated_power_w"]
        assert p_mtb > p_road

    def test_tt_less_power_than_road(self):
        """TT bike is lighter with less CdA → less power needed."""
        climb = make_climb(7.0, 12.0, 600, elevation_gain_m=140)
        road = BIKE_DEFAULTS["road"]
        tt = BIKE_DEFAULTS["tt"]
        p_road = estimate_climbing_power(
            climb, user_weight_kg=75.0,
            bike_weight_kg=road["bike_weight_kg"], crr=road["crr"], cda=road["cda"]
        )["estimated_power_w"]
        p_tt = estimate_climbing_power(
            climb, user_weight_kg=75.0,
            bike_weight_kg=tt["bike_weight_kg"], crr=tt["crr"], cda=tt["cda"]
        )["estimated_power_w"]
        assert p_tt < p_road
