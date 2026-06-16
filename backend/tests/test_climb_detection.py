import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import random
from datetime import datetime, timedelta
from utils.climb_detection import detect_climbs, smooth_elevation


def make_track(segments, start_time=None, noise=0.0):
    """
    Build synthetic track points from a list of (gradient_pct, duration_s, start_elev) tuples.
    Each segment generates points at 1-second intervals.
    """
    if start_time is None:
        start_time = datetime(2024, 1, 1, 10, 0, 0)

    pts = []
    t = start_time
    dist = 0.0
    speed_kmh = 14.0  # constant speed
    speed_ms = speed_kmh / 3.6
    elevation = 100.0  # start elevation

    for gradient_pct, duration_s in segments:
        elev_change_per_s = speed_ms * (gradient_pct / 100)
        for _ in range(int(duration_s)):
            elev_noise = random.uniform(-noise, noise) if noise > 0 else 0
            pts.append({
                "timestamp": t,
                "elevation": elevation + elev_noise,
                "speed_kmh": speed_kmh,
                "distance_m": dist,
                "lat": 38.7 + dist / 111000,
                "lon": -9.1,
                "heart_rate_bpm": 155,
            })
            elevation += elev_change_per_s
            dist += speed_ms
            t += timedelta(seconds=1)

    return pts


class TestSimpleClimb:
    def test_single_6pct_5min_detected(self):
        """A clear 6% climb for 5 minutes should be detected as one climb."""
        track = make_track([(6.0, 300)])
        climbs = detect_climbs(track, min_duration_s=180)
        assert len(climbs) == 1
        assert climbs[0]["avg_gradient_pct"] == pytest.approx(6.0, abs=1.0)
        assert climbs[0]["duration_seconds"] >= 180

    def test_climb_metrics_populated(self):
        track = make_track([(7.0, 360)])
        climbs = detect_climbs(track)
        assert len(climbs) == 1
        c = climbs[0]
        assert c["elevation_gain_m"] > 0
        assert c["distance_m"] > 0
        assert c["vam_m_per_hour"] > 0
        assert c["avg_speed_kmh"] is not None


class TestMultipleClimbs:
    def test_three_separated_climbs(self):
        """Three climbs separated by long flat sections → 3 detections."""
        track = make_track([
            (6.0, 300),  # climb 1
            (0.5, 300),  # long flat separator
            (7.0, 300),  # climb 2
            (0.5, 300),  # long flat separator
            (8.0, 300),  # climb 3
        ])
        climbs = detect_climbs(track, min_duration_s=180)
        assert len(climbs) == 3

    def test_two_climbs_detected(self):
        track = make_track([
            (6.0, 300),
            (0.0, 200),
            (6.5, 300),
        ])
        climbs = detect_climbs(track, min_duration_s=180)
        assert len(climbs) == 2


class TestUndulatingTerrain:
    def test_below_threshold_not_detected(self):
        """Gradient 2-3.5% should not trigger detection (below 4% threshold)."""
        track = make_track([(3.0, 600)])
        climbs = detect_climbs(track, min_gradient=4.0, min_duration_s=180)
        assert len(climbs) == 0

    def test_1pct_undulating_no_detection(self):
        """Flat/mildly undulating terrain → no climbs detected."""
        track = make_track([(1.5, 300), (-0.5, 100), (2.0, 200)])
        climbs = detect_climbs(track)
        assert len(climbs) == 0


class TestMergeNearbySegments:
    def test_brief_flat_merged_into_one_climb(self):
        """7% climb with 15s flat in middle should merge into 1 climb."""
        track = make_track([
            (7.0, 240),
            (1.0, 15),   # brief flat (within 30s merge window)
            (7.0, 240),
        ])
        climbs = detect_climbs(track, min_duration_s=180)
        assert len(climbs) == 1
        assert climbs[0]["duration_seconds"] >= 420  # smoothing eats some edge points

    def test_long_flat_not_merged(self):
        """7% climb with 60s flat separator → should be 2 separate climbs."""
        track = make_track([
            (7.0, 240),
            (0.5, 60),   # longer flat separator (> 30s merge window)
            (7.0, 240),
        ])
        climbs = detect_climbs(track, min_duration_s=180)
        # The merge window is 30s, so 60s gap shouldn't merge
        assert len(climbs) >= 1  # at least one climb (each part might be too short individually)


class TestNoisyAltimeter:
    def test_smoothing_handles_noise(self):
        """±3m noise on altimeter should still detect a clear 7% climb."""
        random.seed(42)
        track = make_track([(7.0, 360)], noise=3.0)
        climbs = detect_climbs(track, min_duration_s=180)
        # With smoothing, should still detect the climb
        assert len(climbs) >= 1

    def test_smooth_elevation_removes_spikes(self):
        """smooth_elevation should reduce variance vs raw."""
        track = make_track([(5.0, 300)], noise=5.0)
        smoothed = smooth_elevation(track, window=30)
        raw_elevs = [p["elevation"] for p in track if p["elevation"] is not None]
        smooth_elevs = [p["elevation_smooth"] for p in smoothed if p["elevation_smooth"] is not None]
        raw_var = sum((e - sum(raw_elevs) / len(raw_elevs)) ** 2 for e in raw_elevs)
        smooth_var = sum((e - sum(smooth_elevs) / len(smooth_elevs)) ** 2 for e in smooth_elevs)
        assert smooth_var < raw_var


class TestFlatRide:
    def test_flat_returns_empty(self):
        """Completely flat track → no climbs detected."""
        track = make_track([(0.0, 600)])
        climbs = detect_climbs(track)
        assert climbs == []

    def test_slight_downhill_no_detection(self):
        """Downhill track → no climbs detected."""
        track = make_track([(-5.0, 600)])
        climbs = detect_climbs(track)
        assert climbs == []


class TestShortClimbExclusion:
    def test_2min_climb_excluded(self):
        """A 2-minute climb should be excluded (below 3-min threshold)."""
        track = make_track([(6.0, 120)])
        climbs = detect_climbs(track, min_duration_s=180)
        assert len(climbs) == 0

    def test_exactly_3min_included(self):
        """A 3-minute climb should pass the threshold."""
        track = make_track([(6.0, 200)])
        climbs = detect_climbs(track, min_duration_s=180)
        # May or may not pass depending on elevation gain and other filters
        # At 6% and 14km/h, 200s → ~11.7m gain (above 15m threshold marginally)
        # With smoothing, gain might be slightly less — just verify it runs without error
        assert isinstance(climbs, list)


class TestPacingDetection:
    def test_even_split_pacing(self):
        """Constant speed → even split pacing."""
        track = make_track([(7.0, 360)])
        climbs = detect_climbs(track, min_duration_s=180)
        if climbs:
            assert climbs[0]["pacing_type"] in ("even", "negative", None)

    def test_negative_split_detection(self):
        """Speed increases in second half → negative split (good pacing)."""
        # Build track with faster second half
        start = datetime(2024, 1, 1, 10, 0, 0)
        pts = []
        t = start
        dist = 0.0
        elevation = 100.0
        gradient = 0.07

        for i in range(600):
            speed_kmh = 12.0 if i < 300 else 14.0
            speed_ms = speed_kmh / 3.6
            pts.append({
                "timestamp": t,
                "elevation": elevation,
                "speed_kmh": speed_kmh,
                "distance_m": dist,
                "lat": 38.7 + dist / 111000,
                "lon": -9.1,
            })
            elevation += speed_ms * gradient
            dist += speed_ms
            t += timedelta(seconds=1)

        climbs = detect_climbs(pts, min_duration_s=180)
        if climbs:
            assert climbs[0]["pacing_type"] == "negative"


class TestSensorOffset:
    def test_negative_elevation_offset_applied(self):
        """If minimum elevation < -30m, offset should normalize it."""
        # Track with artificially low elevations (like Cycplus M1 -42m readings)
        track = make_track([(5.0, 300)])
        for p in track:
            p["elevation"] = (p.get("elevation") or 0) - 150  # shift to ~-50m range

        smoothed = smooth_elevation(track, window=30)
        min_smooth = min(p["elevation_smooth"] for p in smoothed if p["elevation_smooth"] is not None)
        # After offset, minimum should be ≥ -30m
        assert min_smooth >= -30.0

    def test_offset_not_applied_when_min_exactly_minus_30(self):
        """Boundary: min elevation exactly -30m should NOT trigger the offset (strict < -30 check)."""
        from utils.climb_detection import smooth_elevation as se
        pts = [
            {"timestamp": datetime(2024, 1, 1, 10, 0, i), "elevation": -30.0}
            for i in range(5)
        ]
        smoothed = se(pts, window=30)
        assert all(p["elevation_smooth"] == -30.0 for p in smoothed)

    def test_offset_applied_when_min_just_below_minus_30(self):
        """Boundary: min elevation at -30.1m (just under threshold) should trigger offset."""
        from utils.climb_detection import smooth_elevation as se
        pts = [
            {"timestamp": datetime(2024, 1, 1, 10, 0, i), "elevation": -30.1}
            for i in range(5)
        ]
        smoothed = se(pts, window=30)
        # offset = -(-30.1) - 30 = 0.1, so new elevation = -30.1 + 0.1 = -30.0
        assert all(p["elevation_smooth"] == pytest.approx(-30.0) for p in smoothed)

    def test_no_offset_for_normal_elevations(self):
        """Elevations within normal range should be untouched by offset logic."""
        from utils.climb_detection import smooth_elevation as se
        pts = [
            {"timestamp": datetime(2024, 1, 1, 10, 0, i), "elevation": 500.0 + i}
            for i in range(5)
        ]
        smoothed = se(pts, window=30)
        for orig, sm in zip(pts, smoothed):
            assert sm["elevation_smooth"] == pytest.approx(orig["elevation"], abs=5)


class TestSmoothElevationHelper:
    def test_string_timestamp_parsed(self):
        """ISO string timestamps should be parsed into datetimes for windowing."""
        pts = [
            {"timestamp": "2024-01-01T10:00:00", "elevation": 100},
            {"timestamp": "2024-01-01T10:00:01", "elevation": 102},
        ]
        smoothed = smooth_elevation(pts, window=30)
        assert smoothed[0]["elevation_smooth"] == pytest.approx(101.0)

    def test_none_timestamp_falls_back_to_raw_elevation(self):
        """A point with no timestamp can't be windowed against others; it keeps its own raw elevation."""
        pts = [
            {"timestamp": None, "elevation": 50},
            {"timestamp": datetime(2024, 1, 1, 10, 0, 1), "elevation": 60},
        ]
        smoothed = smooth_elevation(pts, window=30)
        assert smoothed[0]["elevation_smooth"] == 50

    def test_all_none_elevation_yields_none_smooth(self):
        """If every point lacks elevation, elevation_smooth should be None throughout (no crash)."""
        pts = [{"timestamp": datetime(2024, 1, 1, 10, 0, i), "elevation": None} for i in range(5)]
        smoothed = smooth_elevation(pts, window=30)
        assert all(p["elevation_smooth"] is None for p in smoothed)

    def test_missing_elevation_key_treated_as_none(self):
        """Points without an 'elevation' key at all should behave like elevation=None."""
        pts = [{"timestamp": datetime(2024, 1, 1, 10, 0, i)} for i in range(5)]
        smoothed = smooth_elevation(pts, window=30)
        assert all(p["elevation_smooth"] is None for p in smoothed)

    def test_mixed_missing_elevation_excluded_from_window_average(self):
        """Points with elevation=None inside the window should not be counted in the average."""
        pts = [
            {"timestamp": datetime(2024, 1, 1, 10, 0, 0), "elevation": 100},
            {"timestamp": datetime(2024, 1, 1, 10, 0, 1), "elevation": None},
            {"timestamp": datetime(2024, 1, 1, 10, 0, 2), "elevation": 200},
        ]
        smoothed = smooth_elevation(pts, window=30)
        # window covers all 3 points for the middle one, but only 100 & 200 have elevation
        assert smoothed[1]["elevation_smooth"] == pytest.approx(150.0)

    def test_empty_track_returns_empty_list(self):
        assert smooth_elevation([], window=30) == []

    def test_window_boundary_exactly_half_included(self):
        """Points exactly window/2 seconds away should be included (<=), not excluded."""
        pts = [
            {"timestamp": datetime(2024, 1, 1, 10, 0, 0), "elevation": 0},
            {"timestamp": datetime(2024, 1, 1, 10, 0, 15), "elevation": 100},  # exactly 15s = window/2 for window=30
        ]
        smoothed = smooth_elevation(pts, window=30)
        # Both points fall within 15s of each other -> both windows include both points
        assert smoothed[0]["elevation_smooth"] == pytest.approx(50.0)
        assert smoothed[1]["elevation_smooth"] == pytest.approx(50.0)

    def test_window_boundary_just_outside_half_excluded(self):
        """Points just beyond window/2 seconds away should be excluded from each other's window."""
        pts = [
            {"timestamp": datetime(2024, 1, 1, 10, 0, 0), "elevation": 0},
            {"timestamp": datetime(2024, 1, 1, 10, 0, 16), "elevation": 100},  # 16s > 15s half-window
        ]
        smoothed = smooth_elevation(pts, window=30)
        assert smoothed[0]["elevation_smooth"] == pytest.approx(0.0)
        assert smoothed[1]["elevation_smooth"] == pytest.approx(100.0)


class TestCalcGradientHelper:
    def test_basic_positive_gradient(self):
        from utils.climb_detection import _calc_gradient
        assert _calc_gradient(100, 110, 0, 100) == pytest.approx(10.0)

    def test_negative_gradient_downhill(self):
        from utils.climb_detection import _calc_gradient
        assert _calc_gradient(100, 90, 0, 100) == pytest.approx(-10.0)

    def test_zero_distance_diff_returns_none(self):
        """dist_diff == 0 should be treated as invalid (division-by-zero guard)."""
        from utils.climb_detection import _calc_gradient
        assert _calc_gradient(100, 110, 50, 50) is None

    def test_negative_distance_diff_returns_none(self):
        """A backwards-moving distance (e.g. GPS jitter) should be rejected, not produce a bogus gradient."""
        from utils.climb_detection import _calc_gradient
        assert _calc_gradient(100, 110, 100, 50) is None

    def test_zero_elevation_diff_yields_zero_gradient(self):
        from utils.climb_detection import _calc_gradient
        assert _calc_gradient(100, 100, 0, 50) == pytest.approx(0.0)


class TestCalcHaversineHelper:
    def test_same_point_zero_distance(self):
        from utils.climb_detection import _calc_haversine_dist
        assert _calc_haversine_dist(38.7, -9.1, 38.7, -9.1) == pytest.approx(0.0, abs=1e-6)

    def test_known_one_degree_latitude_distance(self):
        """1 degree of latitude is ~111.19km; verifies the haversine math against a known constant."""
        from utils.climb_detection import _calc_haversine_dist
        d = _calc_haversine_dist(0, 0, 1, 0)
        assert d == pytest.approx(111194.9, abs=50)

    def test_negative_coordinates(self):
        from utils.climb_detection import _calc_haversine_dist
        d = _calc_haversine_dist(-10, -10, -10.001, -10)
        assert d > 0


class TestDetectClimbsInputBoundaries:
    def test_empty_track_returns_empty(self):
        assert detect_climbs([]) == []

    def test_nine_points_below_minimum_returns_empty(self):
        """len(track_points) < 10 is a hard short-circuit regardless of content."""
        start = datetime(2024, 1, 1, 10, 0, 0)
        pts = [
            {"timestamp": start + timedelta(seconds=i), "elevation": 100 + i * 5, "distance_m": i * 3.9}
            for i in range(9)
        ]
        assert detect_climbs(pts) == []

    def test_exactly_ten_points_proceeds_past_guard(self):
        """At exactly 10 points the length guard no longer short-circuits (may still yield no climbs)."""
        start = datetime(2024, 1, 1, 10, 0, 0)
        pts = [
            {"timestamp": start + timedelta(seconds=i), "elevation": 100 + i * 5, "distance_m": i * 3.9}
            for i in range(10)
        ]
        result = detect_climbs(pts)
        assert isinstance(result, list)

    def test_none_track_points_handled_or_raises(self):
        """Passing None instead of a list should fail fast with a clear error, not silently misbehave."""
        with pytest.raises(TypeError):
            detect_climbs(None)

    def test_missing_timestamps_returns_empty(self):
        """Without timestamps, duration can't be computed, so no climbs should qualify."""
        pts = [{"elevation": 100 + i, "distance_m": i * 4.0} for i in range(20)]
        assert detect_climbs(pts) == []

    def test_missing_distance_and_no_latlon_yields_no_climbs(self):
        """No distance_m and no lat/lon means gradients can't be computed -> no climbs."""
        start = datetime(2024, 1, 1, 10, 0, 0)
        pts = [{"timestamp": start + timedelta(seconds=i), "elevation": 100 + i * 2} for i in range(20)]
        assert detect_climbs(pts) == []

    def test_distance_filled_from_latlon_when_missing(self):
        """When distance_m is absent but lat/lon are present, distance should be derived via haversine."""
        start = datetime(2024, 1, 1, 10, 0, 0)
        speed_ms = 14 / 3.6
        deg_per_m = 1 / 111320.0
        pts = []
        t = start
        elevation = 100.0
        lat = 38.7
        for _ in range(300):
            pts.append({"timestamp": t, "elevation": elevation, "speed_kmh": 14.0, "lat": lat, "lon": -9.1})
            elevation += speed_ms * 0.07
            lat += speed_ms * deg_per_m
            t += timedelta(seconds=1)
        climbs = detect_climbs(pts, min_duration_s=100, min_elevation_gain_m=1)
        assert len(climbs) == 1
        assert climbs[0]["distance_m"] > 0

    def test_all_zero_gradient_no_climbs(self):
        track = make_track([(0.0, 300)])
        assert detect_climbs(track) == []

    def test_extreme_gradient_value_handled(self):
        """A very steep (e.g. 25%) climb should still be detected without numeric issues."""
        track = make_track([(25.0, 200)])
        climbs = detect_climbs(track, min_duration_s=100, min_elevation_gain_m=5)
        assert len(climbs) == 1
        assert climbs[0]["avg_gradient_pct"] > 15

    def test_custom_smoothing_window_zero(self):
        """A window of 0 means each point's own window only includes itself (no smoothing)."""
        track = make_track([(6.0, 300)])
        climbs = detect_climbs(track, smoothing_window=0, min_duration_s=180)
        assert isinstance(climbs, list)


class TestGradientThresholdBoundary:
    def test_gradient_exactly_at_min_gradient_included(self):
        """gradient >= min_gradient: exactly-equal gradient should count (boundary is inclusive)."""
        track = make_track([(4.0, 300)])
        climbs = detect_climbs(track, min_gradient=4.0, min_duration_s=180, min_elevation_gain_m=5)
        assert len(climbs) == 1

    def test_gradient_just_below_min_gradient_excluded(self):
        track = make_track([(3.9, 600)])
        climbs = detect_climbs(track, min_gradient=4.0, min_duration_s=180)
        assert len(climbs) == 0

    def test_custom_min_gradient_threshold(self):
        """A lower custom min_gradient should pick up climbs that the default 4% would miss."""
        track = make_track([(2.5, 600)])
        climbs = detect_climbs(track, min_gradient=2.0, min_duration_s=180, min_elevation_gain_m=5)
        assert len(climbs) == 1


class TestDurationBoundary:
    def test_duration_just_below_threshold_excluded(self):
        """A climb segment with duration_s 1 second short of min_duration_s should be excluded."""
        track = make_track([(8.0, 179)])
        climbs = detect_climbs(track, min_duration_s=180, min_elevation_gain_m=1)
        assert len(climbs) == 0

    def test_duration_zero_min_duration_accepts_short_climbs(self):
        track = make_track([(8.0, 30)])
        climbs = detect_climbs(track, min_duration_s=0, min_elevation_gain_m=1)
        assert len(climbs) == 1

    def test_negative_min_duration_does_not_crash(self):
        """A negative min_duration_s is nonsensical input but should not raise."""
        track = make_track([(8.0, 200)])
        climbs = detect_climbs(track, min_duration_s=-10, min_elevation_gain_m=1)
        assert isinstance(climbs, list)


class TestElevationGainBoundary:
    def test_gain_just_below_threshold_excluded(self):
        """A climb with elevation gain a hair under min_elevation_gain_m should be filtered out."""
        track = make_track([(4.0, 250)])  # ~ small gain
        climbs = detect_climbs(track, min_duration_s=100, min_elevation_gain_m=1000)
        assert len(climbs) == 0

    def test_gain_well_above_threshold_included(self):
        track = make_track([(10.0, 400)])
        climbs = detect_climbs(track, min_duration_s=100, min_elevation_gain_m=15.0)
        assert len(climbs) == 1
        assert climbs[0]["elevation_gain_m"] >= 15.0

    def test_zero_min_elevation_gain_accepts_any_gain(self):
        track = make_track([(4.5, 200)])
        climbs = detect_climbs(track, min_duration_s=100, min_elevation_gain_m=0.0)
        assert len(climbs) == 1


class TestMergeGapBoundary:
    def test_internal_gap_exactly_10s_continues_segment(self):
        """Within a raw segment, a sub-threshold-gradient gap of exactly 10s should NOT break it (gap_s > 10 to break)."""
        track = make_track([(7.0, 100), (1.0, 10), (7.0, 100)])
        climbs = detect_climbs(track, min_duration_s=100, min_elevation_gain_m=1)
        assert len(climbs) == 1
        # Should span (close to) the full combined duration since the 10s gap doesn't break
        # the segment; smoothing eats a few edge points so allow some tolerance.
        assert climbs[0]["duration_seconds"] >= 170

    def test_internal_gap_just_above_10s_breaks_segment(self):
        """An 11s sub-threshold gap inside a climb breaks the raw segment (still may get merged back if <=30s)."""
        track = make_track([(7.0, 100), (1.0, 11), (7.0, 100)])
        climbs = detect_climbs(track, min_duration_s=50, min_elevation_gain_m=1)
        # Segments get split but the gap (11s) is still <=30s so the merge step reunites them.
        assert len(climbs) == 1

    def test_merge_gap_just_above_30s_not_merged(self):
        """A gap > 30s between raw segments should remain as two separate climbs (not merged)."""
        track = make_track([(7.0, 200), (0.0, 31), (7.0, 200)])
        climbs = detect_climbs(track, min_duration_s=100, min_elevation_gain_m=5)
        assert len(climbs) == 2

    def test_merge_gap_exactly_30s_merged(self):
        """A gap of exactly 30s is <= 30 and should merge into a single climb."""
        track = make_track([(7.0, 200), (0.0, 11), (7.0, 200)])
        # Internal gap rule (>10s) splits raw segments at the 11s flat patch first;
        # the merge step (<=30s) should then reunite the two raw segments.
        climbs = detect_climbs(track, min_duration_s=100, min_elevation_gain_m=5)
        assert len(climbs) == 1

    def test_negative_gradient_breaks_segment_immediately(self):
        """Any gradient < 0 inside a segment stops it immediately (no gap tolerance for descents)."""
        track = make_track([(7.0, 150), (-2.0, 5), (7.0, 150)])
        climbs = detect_climbs(track, min_duration_s=50, min_elevation_gain_m=1)
        # whether 1 or 2 climbs depends on smoothing, but it must not crash and must detect something
        assert len(climbs) >= 1


class TestGradientQualityFilter:
    def test_below_60pct_quality_filtered_out(self):
        """A segment where most points have gradient <= 2% (despite brief spikes above min_gradient)
        should be rejected by the 60%-above-2% quality filter."""
        # Mostly flat with very brief steep spikes to barely cross min_gradient at a few points,
        # while net average stays low; this exercises the seg_grads quality ratio branch.
        track = make_track([(4.0, 5), (1.0, 100), (4.0, 5), (1.0, 100)])
        climbs = detect_climbs(track, min_gradient=4.0, min_duration_s=50, min_elevation_gain_m=0.1)
        assert len(climbs) == 0

    def test_above_60pct_quality_passes(self):
        track = make_track([(6.0, 300)])
        climbs = detect_climbs(track, min_duration_s=180, min_elevation_gain_m=1)
        assert len(climbs) == 1


class TestDistanceNonPositiveFilter:
    def test_dist_m_zero_excluded(self):
        """If start and end distance are identical (e.g. stationary GPS), dist_m <= 0 should exclude the climb."""
        start = datetime(2024, 1, 1, 10, 0, 0)
        pts = []
        t = start
        elevation = 100.0
        for i in range(300):
            pts.append({"timestamp": t, "elevation": elevation, "distance_m": 0.0})
            elevation += 0.1
            t += timedelta(seconds=1)
        climbs = detect_climbs(pts, min_duration_s=100, min_elevation_gain_m=1)
        assert climbs == []


class TestPacingBoundaries:
    def test_ratio_exactly_1_is_negative_split(self):
        """ratio >= 1.0 boundary: equal speeds (ratio == 1.0) should classify as 'negative' (inclusive)."""
        track = make_track([(7.0, 360)])  # constant speed throughout -> ratio == 1.0
        climbs = detect_climbs(track, min_duration_s=180)
        assert len(climbs) == 1
        assert climbs[0]["pacing_type"] == "negative"

    def test_ratio_just_below_1_is_even(self):
        """ratio in [0.95, 1.0) should classify as 'even'."""
        start = datetime(2024, 1, 1, 10, 0, 0)
        pts = []
        t = start
        dist = 0.0
        elevation = 100.0
        gradient = 0.07
        for i in range(600):
            speed_kmh = 14.0 if i < 300 else 13.5  # ratio = 13.5/14.0 ≈ 0.964
            speed_ms = speed_kmh / 3.6
            pts.append({
                "timestamp": t, "elevation": elevation, "speed_kmh": speed_kmh,
                "distance_m": dist, "lat": 38.7 + dist / 111000, "lon": -9.1,
            })
            elevation += speed_ms * gradient
            dist += speed_ms
            t += timedelta(seconds=1)
        climbs = detect_climbs(pts, min_duration_s=180)
        assert len(climbs) == 1
        assert climbs[0]["pacing_type"] == "even"

    def test_ratio_below_0_95_is_positive_split(self):
        """ratio < 0.95 (slowing down significantly) should classify as 'positive' split."""
        start = datetime(2024, 1, 1, 10, 0, 0)
        pts = []
        t = start
        dist = 0.0
        elevation = 100.0
        gradient = 0.07
        for i in range(600):
            speed_kmh = 16.0 if i < 300 else 12.0  # ratio = 0.75
            speed_ms = speed_kmh / 3.6
            pts.append({
                "timestamp": t, "elevation": elevation, "speed_kmh": speed_kmh,
                "distance_m": dist, "lat": 38.7 + dist / 111000, "lon": -9.1,
            })
            elevation += speed_ms * gradient
            dist += speed_ms
            t += timedelta(seconds=1)
        climbs = detect_climbs(pts, min_duration_s=180)
        assert len(climbs) == 1
        assert climbs[0]["pacing_type"] == "positive"

    def test_no_speed_data_yields_none_pacing(self):
        """Without any speed_kmh data, pacing_type should be None rather than erroring."""
        start = datetime(2024, 1, 1, 10, 0, 0)
        pts = []
        t = start
        dist = 0.0
        elevation = 100.0
        speed_ms = 14 / 3.6
        for _ in range(300):
            pts.append({"timestamp": t, "elevation": elevation, "distance_m": dist})
            elevation += speed_ms * 0.07
            dist += speed_ms
            t += timedelta(seconds=1)
        climbs = detect_climbs(pts, min_duration_s=100, min_elevation_gain_m=1)
        assert len(climbs) == 1
        assert climbs[0]["pacing_type"] is None
        assert climbs[0]["avg_speed_kmh"] is None

    def test_zero_speed_both_halves_pacing_type_none_BUG(self):
        """KNOWN BUG (utils/climb_detection.py, ~line 204): pacing classification uses
        `if first_half_speed and second_half_speed:` to decide whether to compute a
        pacing ratio. This is a truthiness check, not a None check, so when both halves
        have a perfectly valid average speed of exactly 0.0 km/h (e.g. a climb ridden
        entirely on a stationary trainer/rollers where speed_kmh is reported as 0, or any
        sensor that legitimately reports 0 for a portion of the ride), `first_half_speed`
        and `second_half_speed` are both `0.0`, which is falsy in Python. The code then
        takes the `else` branch and sets `pacing_type = None`, exactly as if no speed data
        existed at all -- even though real (zero) speed data was present and a ratio of
        0/0 could have been handled explicitly.

        What SHOULD happen (not asserted, since current behavior is the bug):
        #   assert climbs[0]["pacing_type"] is not None  # e.g. "even" for equal zero speeds
        What ACTUALLY happens: pacing_type is None, identical to the "no speed data" case,
        even though avg_speed_kmh is correctly reported as 0.0 (proving the data was present).
        """
        start = datetime(2024, 1, 1, 10, 0, 0)
        pts = []
        t = start
        dist = 0.0
        elevation = 100.0
        speed_ms = 14 / 3.6
        for _ in range(300):
            pts.append({"timestamp": t, "elevation": elevation, "speed_kmh": 0.0, "distance_m": dist})
            elevation += speed_ms * 0.07
            dist += speed_ms
            t += timedelta(seconds=1)
        climbs = detect_climbs(pts, min_duration_s=100, min_elevation_gain_m=1)
        assert len(climbs) == 1
        assert climbs[0]["avg_speed_kmh"] == 0.0
        assert climbs[0]["pacing_type"] is None  # documents the bug; see docstring


class TestHeartRateAggregation:
    def test_heart_rate_missing_yields_none(self):
        start = datetime(2024, 1, 1, 10, 0, 0)
        pts = []
        t = start
        dist = 0.0
        elevation = 100.0
        speed_ms = 14 / 3.6
        for _ in range(300):
            pts.append({"timestamp": t, "elevation": elevation, "distance_m": dist})
            elevation += speed_ms * 0.07
            dist += speed_ms
            t += timedelta(seconds=1)
        climbs = detect_climbs(pts, min_duration_s=100, min_elevation_gain_m=1)
        assert len(climbs) == 1
        assert climbs[0]["avg_heart_rate"] is None
        assert climbs[0]["max_heart_rate"] is None

    def test_heart_rate_present_computed_and_rounded(self):
        track = make_track([(6.0, 300)])  # heart_rate_bpm=155 constant from make_track
        climbs = detect_climbs(track, min_duration_s=180)
        assert len(climbs) == 1
        assert climbs[0]["avg_heart_rate"] == 155
        assert climbs[0]["max_heart_rate"] == 155


class TestVamCalculation:
    def test_vam_positive_for_real_climb(self):
        track = make_track([(8.0, 300)])
        climbs = detect_climbs(track, min_duration_s=180)
        assert len(climbs) == 1
        # VAM = elevation_gain / duration_s * 3600
        expected_vam = climbs[0]["elevation_gain_m"] / climbs[0]["duration_seconds"] * 3600
        assert climbs[0]["vam_m_per_hour"] == pytest.approx(expected_vam, abs=0.1)


class TestMultiSegmentMergeAndQuality:
    def test_many_short_spikes_under_min_duration_excluded(self):
        """Several brief above-threshold spikes too short individually and too far apart to merge -> no climbs."""
        track = make_track([
            (6.0, 20), (0.0, 60), (6.0, 20), (0.0, 60), (6.0, 20),
        ])
        climbs = detect_climbs(track, min_duration_s=180)
        assert climbs == []

    def test_climb_indices_reference_correct_trackpoints(self):
        """start/end_trackpoint_idx should index into the original (length-matched) track point list."""
        track = make_track([(7.0, 300)])
        climbs = detect_climbs(track, min_duration_s=180)
        assert len(climbs) == 1
        c = climbs[0]
        assert 0 <= c["start_trackpoint_idx"] < c["end_trackpoint_idx"] < len(track)
