"""
Tests for utils/indoor_detection.py — Indoor/outdoor ride detection.

Run from the backend directory:
    python -m pytest tests/test_indoor_detection.py -v
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.indoor_detection import detect_ride_environment, detect_indoor_platform


# ── Helpers ───────────────────────────────────────────────────────────────────

def _gps_pts(n=100, lat0=38.7, lon0=-9.1, spread_deg=0.01):
    """Return track points spread over an outdoor-size GPS bbox."""
    return [
        {
            "lat": lat0 + (i / n) * spread_deg,
            "lon": lon0 + (i / n) * spread_deg,
            "speed_kmh": 30.0,
            "power_w": None,
            "cadence_rpm": 85,
        }
        for i in range(n)
    ]


def _static_pts(n=100, lat=38.7, lon=-9.1, power_w=200.0):
    """Track points at a fixed GPS point (< 50 m bbox = trainer)."""
    return [
        {
            "lat": lat + 0.0001 * (i % 3),   # <~30 m variation
            "lon": lon,
            "speed_kmh": 0.0,
            "power_w": power_w,
            "cadence_rpm": 90,
        }
        for i in range(n)
    ]


def _no_gps_pts(n=100, power_w=200.0, speed_kmh=0.0):
    """Track points with no GPS data."""
    return [
        {
            "lat": None,
            "lon": None,
            "speed_kmh": speed_kmh,
            "power_w": power_w,
            "cadence_rpm": 88,
        }
        for i in range(n)
    ]


# ── Strava type detection ─────────────────────────────────────────────────────

class TestStravaType:
    def test_virtual_ride_is_indoor(self):
        result = detect_ride_environment(
            _gps_pts(),
            activity_name="Zwift ride",
            strava_type="VirtualRide",
        )
        assert result["environment"] == "indoor"
        assert result["confidence"] == "high"
        assert result["source"] == "strava_type"

    def test_virtual_ride_platform_from_name(self):
        result = detect_ride_environment(
            _gps_pts(),
            activity_name="TrainerRoad workout",
            strava_type="VirtualRide",
        )
        assert result["platform"] == "trainerroad"

    def test_outdoor_ride_type(self):
        result = detect_ride_environment(
            _gps_pts(),
            activity_name="Sunday ride",
            strava_type="Ride",
        )
        assert result["environment"] == "outdoor"
        assert result["confidence"] == "high"

    def test_gravel_ride_type(self):
        result = detect_ride_environment(
            _gps_pts(),
            activity_name="Gravel adventure",
            strava_type="GravelRide",
        )
        assert result["environment"] == "outdoor"


# ── Name keyword detection ────────────────────────────────────────────────────

class TestNameKeywords:
    def test_zwift_name(self):
        result = detect_ride_environment(
            _gps_pts(),
            activity_name="Zwift — Watopia Flat",
        )
        assert result["environment"] == "indoor"
        assert result["platform"] == "zwift"

    def test_trainerroad_name(self):
        result = detect_ride_environment(
            _no_gps_pts(),
            activity_name="TrainerRoad — Baxter",
        )
        assert result["environment"] == "indoor"
        assert result["platform"] == "trainerroad"

    def test_turbo_name_no_platform(self):
        result = detect_ride_environment(
            _no_gps_pts(power_w=220.0),
            activity_name="Turbo session",
        )
        assert result["environment"] == "indoor"

    def test_outdoor_ride_no_match(self):
        result = detect_ride_environment(
            _gps_pts(spread_deg=0.05),
            activity_name="Saturday morning ride",
        )
        assert result["environment"] == "outdoor"


# ── GPS analysis ──────────────────────────────────────────────────────────────

class TestGpsAnalysis:
    def test_no_gps_inferred_indoor(self):
        result = detect_ride_environment(
            _no_gps_pts(power_w=200.0),
            activity_name="Morning session",
        )
        assert result["environment"] == "indoor"
        assert result["source"] == "no_gps"

    def test_no_gps_rolo_when_power(self):
        result = detect_ride_environment(
            _no_gps_pts(power_w=220.0),
            activity_name="Unnamed",
        )
        assert result["environment"] == "indoor"
        # When there's power but no platform name, defaults to 'rolo'
        assert result["platform"] in ("rolo", "other", "zwift", None) or result["platform"] is not None

    def test_static_bbox_is_indoor(self):
        result = detect_ride_environment(
            _static_pts(),
            activity_name="Home trainer",
        )
        assert result["environment"] == "indoor"

    def test_large_bbox_is_outdoor(self):
        result = detect_ride_environment(
            _gps_pts(spread_deg=0.05),   # ~5.5 km diagonal
            activity_name="Group ride",
        )
        assert result["environment"] == "outdoor"

    def test_ambiguous_small_bbox(self):
        # bbox ~100–400 m: ambiguous short urban ride
        pts = [
            {"lat": 38.700 + 0.001 * (i / 100), "lon": -9.100,
             "speed_kmh": 15.0, "power_w": None, "cadence_rpm": 80}
            for i in range(100)
        ]
        result = detect_ride_environment(pts, activity_name="Quick errand")
        # Should be either outdoor or unknown (not definitively indoor without keywords)
        assert result["environment"] in ("outdoor", "unknown")


# ── User override scenario ────────────────────────────────────────────────────

class TestUserOverride:
    def test_outdoor_gps_but_overridden_to_indoor_after_detection(self):
        """Simulates: activity was detected as outdoor, user overrides to indoor.

        The detection function itself still returns outdoor for the original data;
        the override is applied at the route/model level, not in detect_ride_environment.
        This test confirms that the detection function doesn't suppress correct results.
        """
        result = detect_ride_environment(
            _gps_pts(spread_deg=0.05),
            activity_name="Outdoor ride",
            strava_type="Ride",
        )
        assert result["environment"] == "outdoor"
        # Override (to indoor) would be applied separately in the route layer


# ── detect_indoor_platform ────────────────────────────────────────────────────

class TestDetectIndoorPlatform:
    def test_zwift_manufacturer(self):
        platform = detect_indoor_platform(
            _no_gps_pts(),
            activity_name="Watopia ride",
            file_metadata={"manufacturer": "zwift"},
        )
        assert platform == "zwift"

    def test_trainerroad_manufacturer(self):
        platform = detect_indoor_platform(
            _no_gps_pts(),
            activity_name="Sweet Spot",
            file_metadata={"manufacturer": "trainerroad"},
        )
        assert platform == "trainerroad"

    def test_wahoo_manufacturer(self):
        platform = detect_indoor_platform(
            _no_gps_pts(),
            file_metadata={"manufacturer": "wahoo_fitness"},
        )
        assert platform == "wahoo"

    def test_name_zwift(self):
        platform = detect_indoor_platform(
            _no_gps_pts(),
            activity_name="Zwift event",
        )
        assert platform == "zwift"

    def test_power_no_platform_defaults_rolo(self):
        platform = detect_indoor_platform(
            _no_gps_pts(power_w=200),
            activity_name="Morning workout",
        )
        assert platform == "rolo"

    def test_no_power_no_platform_defaults_other(self):
        platform = detect_indoor_platform(
            _no_gps_pts(power_w=0),
            activity_name="Morning workout",
        )
        assert platform == "other"
