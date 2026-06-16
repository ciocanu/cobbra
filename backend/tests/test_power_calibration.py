import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from types import SimpleNamespace

import pytest

from utils.power_calibration import calibrate_from_known_ftp, calibrate_from_known_climb
from utils.power_estimation import _compute_power, AIR_DENSITY_SEA_LEVEL
import math


def make_user(weight_kg=75.0, calibrated_cda=None, calibrated_crr=None):
    return SimpleNamespace(
        weight_kg=weight_kg,
        calibrated_cda=calibrated_cda,
        calibrated_crr=calibrated_crr,
    )


def make_climb(gradient_pct=7.0, speed_kmh=15.0, duration_s=1200, elevation_gain_m=100):
    return SimpleNamespace(
        avg_gradient_pct=gradient_pct,
        avg_speed_kmh=speed_kmh,
        duration_seconds=duration_s,
        elevation_gain_m=elevation_gain_m,
    )


def air_density_for(elevation_gain_m):
    if elevation_gain_m is None:
        return AIR_DENSITY_SEA_LEVEL * math.exp(-0 / 8500)
    return AIR_DENSITY_SEA_LEVEL * math.exp(-elevation_gain_m / 8500)


def power_at_cda(climb, user, cda):
    total_mass = (user.weight_kg or 70) + 9.0
    crr = user.calibrated_crr or 0.005
    air_density = air_density_for(climb.elevation_gain_m)
    return _compute_power(
        climb.avg_gradient_pct or 0, climb.avg_speed_kmh, total_mass,
        air_density, cda, crr, 0.03
    )


class TestCalibrateFromKnownFtpHappyPath:
    def test_converges_to_matching_cda_when_target_is_at_an_extreme(self):
        """Power increases monotonically with CdA, so the bisection should converge toward
        the cda that actually reproduces a known_ftp_w that's exactly achievable at the
        lower bound."""
        user = make_user(weight_kg=75.0)
        climbs = [make_climb(7.0, 15.0, 1500, 200), make_climb(6.0, 16.0, 1800, 150)]
        lower_bound_power = sum(power_at_cda(c, user, 0.15) for c in climbs) / len(climbs)
        known_ftp_w = lower_bound_power
        result = calibrate_from_known_ftp(user, climbs, known_ftp_w)
        assert "error" not in result
        cda = result["calibrated_cda"]
        assert 0.15 <= cda <= 0.80
        assert cda == pytest.approx(0.15, abs=0.03)
        reproduced_avg = sum(power_at_cda(c, user, cda) for c in climbs) / len(climbs)
        assert abs(reproduced_avg - known_ftp_w) < 3.0

    def test_target_strictly_between_bounds_converges(self):
        """A known_ftp_w that's achievable somewhere inside [0.15, 0.80] should yield a cda
        that reproduces it closely."""
        user = make_user(weight_kg=75.0)
        climb = make_climb(7.0, 15.0, 1500, 200)
        p_lo = power_at_cda(climb, user, 0.15)
        p_hi = power_at_cda(climb, user, 0.80)
        known_ftp_w = p_lo + 0.25 * (p_hi - p_lo)
        assert p_lo < known_ftp_w < p_hi

        result = calibrate_from_known_ftp(user, [climb], known_ftp_w)
        assert "error" not in result
        cda = result["calibrated_cda"]
        reproduced = power_at_cda(climb, user, cda)

        assert abs(reproduced - known_ftp_w) < 3.0

    def test_calibration_source_is_manual_ftp(self):
        user = make_user()
        climbs = [make_climb(7.0, 15.0, 1500, 200)]
        result = calibrate_from_known_ftp(user, climbs, 220.0)
        assert result["calibration_source"] == "manual_ftp"


class TestCalibrateFromKnownClimbHappyPath:
    def test_adjustment_direction_increases_cda_for_higher_known_power(self):
        """If known_power_w > estimated (rider produced MORE power than the model predicts),
        the model should increase drag/CdA to explain the higher power at the same speed --
        i.e. new_cda should be > current_cda, and the reproduced estimate should move closer
        to known_power_w."""
        user = make_user(weight_kg=75.0, calibrated_cda=0.32, calibrated_crr=0.004)
        climb = make_climb(7.0, 15.0, 900, 150)
        original = power_at_cda(climb, user, user.calibrated_cda)
        known_power_w = original + 50.0  # rider claims notably more power than estimated

        result = calibrate_from_known_climb(user, climb, known_power_w)
        assert "error" not in result
        cda = result["calibrated_cda"]
        assert cda > user.calibrated_cda

        reproduced = power_at_cda(climb, user, cda)
        assert abs(reproduced - known_power_w) < abs(original - known_power_w)

    def test_calibration_source_is_known_climb(self):
        user = make_user(calibrated_cda=0.32)
        climb = make_climb()
        result = calibrate_from_known_climb(user, climb, 230.0)
        assert result["calibration_source"] == "known_climb"


class TestFtpNoClimbs:
    def test_empty_climb_list_errors(self):
        user = make_user()
        result = calibrate_from_known_ftp(user, [], 220.0)
        assert "error" in result

    def test_only_short_climbs_under_300s_errors(self):
        user = make_user()
        climbs = [make_climb(duration_s=100), make_climb(duration_s=250)]
        result = calibrate_from_known_ftp(user, climbs, 220.0)
        assert "error" in result


class TestFtpFallbackBand:
    def test_climbs_in_300_to_1200_band_used_when_no_long_climbs(self):
        user = make_user()
        climbs = [make_climb(7.0, 15.0, 600, 100), make_climb(6.0, 14.0, 400, 80)]
        result = calibrate_from_known_ftp(user, climbs, 220.0)
        assert "error" not in result
        assert 0.15 <= result["calibrated_cda"] <= 0.80


class TestFtpMixedLongAndShort:
    def test_only_long_climbs_used_when_present(self):
        """When >=1200s climbs exist, short climbs (300-1200s) must be ignored."""
        user = make_user()
        long_climb = make_climb(7.0, 15.0, 1500, 200)
        short_climb = make_climb(20.0, 30.0, 400, 50)  # would skew result heavily if included

        result_with_short = calibrate_from_known_ftp(user, [long_climb, short_climb], 220.0)
        result_without_short = calibrate_from_known_ftp(user, [long_climb], 220.0)

        assert "error" not in result_with_short
        assert "error" not in result_without_short
        assert result_with_short["calibrated_cda"] == result_without_short["calibrated_cda"]


class TestFtpInvalidSpeedClimbsSkipped:
    def test_missing_avg_speed_kmh_skipped_not_crash(self):
        user = make_user()
        bad = make_climb(7.0, None, 1500, 200)
        good = make_climb(7.0, 15.0, 1500, 200)
        result = calibrate_from_known_ftp(user, [bad, good], 220.0)
        assert "error" not in result

    def test_zero_avg_speed_kmh_skipped(self):
        user = make_user()
        bad = make_climb(7.0, 0.0, 1500, 200)
        good = make_climb(7.0, 15.0, 1500, 200)
        result = calibrate_from_known_ftp(user, [bad, good], 220.0)
        assert "error" not in result

    def test_negative_avg_speed_kmh_skipped(self):
        user = make_user()
        bad = make_climb(7.0, -5.0, 1500, 200)
        good = make_climb(7.0, 15.0, 1500, 200)
        result = calibrate_from_known_ftp(user, [bad, good], 220.0)
        assert "error" not in result

    def test_all_climbs_invalid_speed_yields_zero_division_safe(self):
        """All long climbs have invalid speed -> powers list empty -> avg_power_with_cda returns 0.
        Bisection should still terminate without crashing (no qualifying powers ever match known_ftp_w,
        so it will run all 30 iterations and converge toward hi since p_mid(0) < known_ftp_w always)."""
        user = make_user()
        climbs = [make_climb(7.0, 0.0, 1500, 200), make_climb(7.0, -1.0, 1300, 100)]
        result = calibrate_from_known_ftp(user, climbs, 220.0)
        assert "error" not in result
        # p_mid is always 0 < known_ftp_w, so bisection keeps narrowing lo up toward hi
        assert result["calibrated_cda"] == pytest.approx(0.80, abs=1e-3)


class TestFtpElevationGainNone:
    def test_none_elevation_gain_falls_back_to_sea_level_density(self):
        user = make_user()
        climb_none = make_climb(7.0, 15.0, 1500, elevation_gain_m=None)
        climb_zero = make_climb(7.0, 15.0, 1500, elevation_gain_m=0)
        result_none = calibrate_from_known_ftp(user, [climb_none], 220.0)
        result_zero = calibrate_from_known_ftp(user, [climb_zero], 220.0)
        assert "error" not in result_none
        # None and 0 elevation gain should produce identical air density (sea level), hence identical result
        assert result_none["calibrated_cda"] == result_zero["calibrated_cda"]


class TestFtpUserDefaults:
    def test_no_weight_kg_defaults_to_70(self):
        user_none = make_user(weight_kg=None)
        user_70 = make_user(weight_kg=70.0)
        climbs = [make_climb(7.0, 15.0, 1500, 200)]
        r_none = calibrate_from_known_ftp(user_none, climbs, 220.0)
        r_70 = calibrate_from_known_ftp(user_70, climbs, 220.0)
        assert r_none["calibrated_cda"] == r_70["calibrated_cda"]

    def test_no_calibrated_crr_defaults_to_0_005(self):
        user_none = make_user(calibrated_crr=None)
        user_explicit = make_user(calibrated_crr=0.005)
        climbs = [make_climb(7.0, 15.0, 1500, 200)]
        r_none = calibrate_from_known_ftp(user_none, climbs, 220.0)
        r_explicit = calibrate_from_known_ftp(user_explicit, climbs, 220.0)
        assert r_none["calibrated_cda"] == r_explicit["calibrated_cda"]


class TestFtpExtremeKnownValues:
    def test_very_low_known_ftp_converges_or_hits_lower_bound(self):
        user = make_user()
        climbs = [make_climb(2.0, 20.0, 1500, 20)]  # low power climb
        result = calibrate_from_known_ftp(user, climbs, 50.0)
        assert "error" not in result
        cda = result["calibrated_cda"]
        assert 0.15 <= cda <= 0.80
        # power should be close to target, or cda at boundary if target is unreachable
        power = power_at_cda(climbs[0], user, cda)
        assert abs(power - 50.0) < 5.0 or cda in (0.15, 0.80)

    def test_very_high_known_ftp_converges_or_hits_upper_bound(self):
        user = make_user()
        climbs = [make_climb(10.0, 25.0, 1500, 300)]
        result = calibrate_from_known_ftp(user, climbs, 500.0)
        assert "error" not in result
        cda = result["calibrated_cda"]
        assert 0.15 <= cda <= 0.80
        power = power_at_cda(climbs[0], user, cda)
        assert abs(power - 500.0) < 5.0 or cda in (0.15, 0.80)

    def test_unreachably_high_ftp_hits_a_boundary_gracefully(self):
        """If even max CdA (0.80) underestimates known_ftp_w drastically, bisection should
        gracefully settle at the upper bound rather than erroring or looping forever."""
        user = make_user()
        climbs = [make_climb(1.0, 10.0, 1500, 10)]  # very low natural power climb
        result = calibrate_from_known_ftp(user, climbs, 100000.0)
        assert "error" not in result
        assert result["calibrated_cda"] == pytest.approx(0.80, abs=1e-3)

    def test_unreachably_low_ftp_hits_a_boundary_gracefully(self):
        """An unreachably LOW target should drive the result to the lower bound (0.15)."""
        user = make_user()
        climbs = [make_climb(15.0, 30.0, 1500, 400)]  # very high natural power climb
        result = calibrate_from_known_ftp(user, climbs, 0.001)
        assert "error" not in result
        assert result["calibrated_cda"] == pytest.approx(0.15, abs=1e-3)


class TestCalibrateFromKnownClimbErrors:
    def test_missing_weight_kg_errors(self):
        user = make_user(weight_kg=None)
        climb = make_climb()
        result = calibrate_from_known_climb(user, climb, 200.0)
        assert "error" in result

    def test_missing_avg_speed_kmh_errors(self):
        user = make_user()
        climb = make_climb(speed_kmh=None)
        result = calibrate_from_known_climb(user, climb, 200.0)
        assert "error" in result

    def test_zero_avg_speed_kmh_errors(self):
        user = make_user()
        climb = make_climb(speed_kmh=0.0)
        result = calibrate_from_known_climb(user, climb, 200.0)
        assert "error" in result

    def test_negative_avg_speed_kmh_errors(self):
        user = make_user()
        climb = make_climb(speed_kmh=-10.0)
        result = calibrate_from_known_climb(user, climb, 200.0)
        assert "error" in result

    def test_zero_weight_kg_errors(self):
        """weight_kg=0 is falsy, hits the `not user.weight_kg` check."""
        user = make_user(weight_kg=0)
        climb = make_climb()
        result = calibrate_from_known_climb(user, climb, 200.0)
        assert "error" in result

    def test_estimated_power_zero_errors(self):
        """Flat climb (gradient 0) at very low speed could still be > 0 due to aero/rolling;
        force estimated power to zero by using speed effectively producing 0 total via
        zero gradient + zero crr-like contributions is hard to hit naturally since aero > 0
        for any positive speed. Instead use gradient causing negative total clipped to 0:
        a steep enough negative gradient at low speed should drive p_total below 0, clamped to 0."""
        user = make_user(weight_kg=75.0, calibrated_cda=0.32, calibrated_crr=0.0)
        climb = make_climb(gradient_pct=-45.0, speed_kmh=1.0, duration_s=900, elevation_gain_m=0)
        result = calibrate_from_known_climb(user, climb, 200.0)
        assert "error" in result
        assert "zero" in result["error"].lower()


class TestCalibrateFromKnownClimbCdaDefaults:
    def test_none_calibrated_cda_defaults_to_0_35(self):
        user_none = make_user(calibrated_cda=None)
        user_explicit = make_user(calibrated_cda=0.35)
        climb = make_climb()
        r_none = calibrate_from_known_climb(user_none, climb, 230.0)
        r_explicit = calibrate_from_known_climb(user_explicit, climb, 230.0)
        assert r_none["calibrated_cda"] == r_explicit["calibrated_cda"]

    def test_none_calibrated_crr_defaults_to_0_005(self):
        user_none = make_user(calibrated_cda=0.32, calibrated_crr=None)
        user_explicit = make_user(calibrated_cda=0.32, calibrated_crr=0.005)
        climb = make_climb()
        r_none = calibrate_from_known_climb(user_none, climb, 230.0)
        r_explicit = calibrate_from_known_climb(user_explicit, climb, 230.0)
        assert r_none["calibrated_cda"] == r_explicit["calibrated_cda"]


class TestCalibrateFromKnownClimbClamping:
    def test_known_power_much_higher_clamps_to_a_bound(self):
        """A known_power_w far ABOVE the estimate drives new_cda = current_cda * ratio toward
        the UPPER bound (0.80), as physically expected (more power needs more drag)."""
        user = make_user(weight_kg=75.0, calibrated_cda=0.32, calibrated_crr=0.004)
        climb = make_climb(7.0, 15.0, 900, 150)
        result = calibrate_from_known_climb(user, climb, known_power_w=1_000_000.0)
        assert result["calibrated_cda"] == 0.80

    def test_known_power_much_lower_clamps_to_a_bound(self):
        """Inverse of the above: a known_power_w far BELOW the estimate drives new_cda toward
        the LOWER bound (0.15)."""
        user = make_user(weight_kg=75.0, calibrated_cda=0.32, calibrated_crr=0.004)
        climb = make_climb(7.0, 15.0, 900, 150)
        result = calibrate_from_known_climb(user, climb, known_power_w=0.0001)
        assert result["calibrated_cda"] == 0.15

    def test_known_power_matches_estimate_cda_unchanged(self):
        user = make_user(weight_kg=75.0, calibrated_cda=0.32, calibrated_crr=0.004)
        climb = make_climb(7.0, 15.0, 900, 150)
        estimated = power_at_cda(climb, user, user.calibrated_cda)
        result = calibrate_from_known_climb(user, climb, known_power_w=estimated)
        assert result["calibrated_cda"] == pytest.approx(0.32, abs=1e-3)


class TestBoundaryGradientAndDuration:
    def test_flat_gradient_zero(self):
        user = make_user()
        climb = make_climb(gradient_pct=0.0, speed_kmh=20.0, duration_s=1500)
        result = calibrate_from_known_ftp(user, [climb], 150.0)
        assert "error" not in result

    def test_negative_gradient_descending(self):
        user = make_user()
        climb = make_climb(gradient_pct=-5.0, speed_kmh=30.0, duration_s=1500)
        result = calibrate_from_known_ftp(user, [climb], 50.0)
        assert "error" not in result

    def test_duration_exactly_1200_counts_as_long(self):
        """duration_seconds == 1200 should be included in the long-climb bucket (>= comparison)."""
        user = make_user()
        long_exact = make_climb(7.0, 15.0, 1200, 200)
        short = make_climb(20.0, 30.0, 400, 50)  # would skew result if used instead
        result_with_short = calibrate_from_known_ftp(user, [long_exact, short], 220.0)
        result_without_short = calibrate_from_known_ftp(user, [long_exact], 220.0)
        assert result_with_short["calibrated_cda"] == result_without_short["calibrated_cda"]

    def test_duration_1199_is_not_long_falls_to_fallback_band(self):
        """duration_seconds == 1199 should NOT be in the long bucket; with no other climbs >=1200,
        it should fall back to the >=300s band and be used (since 1199 >= 300)."""
        user = make_user()
        climb = make_climb(7.0, 15.0, 1199, 200)
        result = calibrate_from_known_ftp(user, [climb], 220.0)
        assert "error" not in result

    def test_duration_exactly_300_counts_in_fallback_band(self):
        user = make_user()
        climb = make_climb(7.0, 15.0, 300, 200)
        result = calibrate_from_known_ftp(user, [climb], 220.0)
        assert "error" not in result

    def test_duration_299_excluded_from_fallback_band(self):
        """duration_seconds == 299 is below both thresholds -> no qualifying climbs -> error."""
        user = make_user()
        climb = make_climb(7.0, 15.0, 299, 200)
        result = calibrate_from_known_ftp(user, [climb], 220.0)
        assert "error" in result
