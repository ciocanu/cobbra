"""
Tests for parsers/gpx_parser.py — per-point sensor data from GPX extensions.

Covers: Garmin TrackPointExtension (hr, cad, atemp), Strava-style flat <power>,
Garmin PowerExtension (PowerInWatts), legacy <cadence>, and files without extensions.

Run from the backend directory:
    python -m pytest tests/test_gpx_parser.py -v
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from parsers.gpx_parser import parse_gpx


# ── Helpers ────────────────────────────────────────────────────────────────

NAMESPACES = (
    'xmlns="http://www.topografix.com/GPX/1/1" '
    'xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1" '
    'xmlns:gpxpx="http://www.garmin.com/xmlschemas/PowerExtension/v1"'
)


def make_gpx(extensions):
    """One trkpt per entry in `extensions` (inner XML of <extensions>, or None), 1 s apart."""
    pts = []
    for i, ext in enumerate(extensions):
        ext_xml = f"<extensions>{ext}</extensions>" if ext is not None else ""
        pts.append(
            f'<trkpt lat="{38.7 + i * 0.0001:.4f}" lon="-9.25"><ele>{100 + i}</ele>'
            f"<time>2026-05-01T08:00:{i:02d}Z</time>{ext_xml}</trkpt>"
        )
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="test" {NAMESPACES}>'
        f"<trk><name>Test</name><trkseg>{''.join(pts)}</trkseg></trk></gpx>"
    ).encode()


def tpx(hr=None, cad=None, atemp=None):
    inner = ""
    if hr is not None:
        inner += f"<gpxtpx:hr>{hr}</gpxtpx:hr>"
    if cad is not None:
        inner += f"<gpxtpx:cad>{cad}</gpxtpx:cad>"
    if atemp is not None:
        inner += f"<gpxtpx:atemp>{atemp}</gpxtpx:atemp>"
    return f"<gpxtpx:TrackPointExtension>{inner}</gpxtpx:TrackPointExtension>"


def column(data, key):
    return [p[key] for p in data["track_points"]]


# ── Garmin TrackPointExtension ─────────────────────────────────────────────

class TestGarminTrackPointExtension:
    def setup_method(self):
        self.data = parse_gpx(make_gpx([
            tpx(hr=120, cad=80, atemp=18.0),
            tpx(hr=140, cad=90, atemp=20.0),
            tpx(hr=160, cad=0, atemp=22.0),
        ]))

    def test_cadence_read_from_cad(self):
        assert column(self.data, "cadence_rpm") == [80.0, 90.0, 0.0]
        assert self.data["max_cadence_rpm"] == 90.0

    def test_heart_rate(self):
        assert column(self.data, "heart_rate_bpm") == [120.0, 140.0, 160.0]
        assert self.data["avg_heart_rate_bpm"] == 140.0
        assert self.data["max_heart_rate_bpm"] == 160.0

    def test_temperature(self):
        assert self.data["avg_temperature_c"] == 20.0
        assert self.data["max_temperature_c"] == 22.0

    def test_no_power(self):
        assert column(self.data, "power_w") == [None, None, None]
        assert self.data["avg_power_w"] is None
        assert self.data["max_power_w"] is None

    def test_legacy_cadence_tag_still_read(self):
        data = parse_gpx(make_gpx(["<gpxtpx:TrackPointExtension><gpxtpx:cadence>85</gpxtpx:cadence></gpxtpx:TrackPointExtension>"]))
        assert column(data, "cadence_rpm") == [85.0]


# ── Power ──────────────────────────────────────────────────────────────────

class TestStravaFlatPower:
    def setup_method(self):
        # Strava export: <power> directly under <extensions>, next to the TrackPointExtension
        self.data = parse_gpx(make_gpx([
            "<power>200</power>" + tpx(hr=130, cad=85),
            "<power>300</power>" + tpx(hr=135, cad=88),
            "<power>0</power>" + tpx(hr=128, cad=0),
        ]))

    def test_power_per_point(self):
        # Zeros are kept per point (coasting) — same as the FIT parser
        assert column(self.data, "power_w") == [200.0, 300.0, 0.0]

    def test_power_summary_excludes_zeros(self):
        assert self.data["avg_power_w"] == 250.0
        assert self.data["max_power_w"] == 300.0

    def test_other_sensors_alongside_flat_power(self):
        assert column(self.data, "heart_rate_bpm") == [130.0, 135.0, 128.0]
        assert column(self.data, "cadence_rpm") == [85.0, 88.0, 0.0]


class TestGarminPowerExtension:
    def test_power_in_watts(self):
        data = parse_gpx(make_gpx([
            f"<gpxpx:PowerExtension><gpxpx:PowerInWatts>{w}</gpxpx:PowerInWatts></gpxpx:PowerExtension>"
            for w in (180, 220, 260)
        ]))
        assert column(data, "power_w") == [180.0, 220.0, 260.0]
        assert data["avg_power_w"] == 220.0
        assert data["max_power_w"] == 260.0

    def test_watts_tag(self):
        data = parse_gpx(make_gpx(["<watts>210</watts>"]))
        assert column(data, "power_w") == [210.0]


class TestFlatExtensions:
    def test_flat_hr_and_cadence(self):
        data = parse_gpx(make_gpx(["<hr>150</hr><cad>92</cad>"]))
        assert column(data, "heart_rate_bpm") == [150.0]
        assert column(data, "cadence_rpm") == [92.0]

    def test_tcx_style_heart_rate_value(self):
        data = parse_gpx(make_gpx(["<HeartRateBpm><Value>142</Value></HeartRateBpm>"]))
        assert column(data, "heart_rate_bpm") == [142.0]

    def test_non_numeric_value_ignored(self):
        data = parse_gpx(make_gpx(["<power></power><cad>n/a</cad>"]))
        assert column(data, "power_w") == [None]
        assert column(data, "cadence_rpm") == [None]


# ── No extensions ──────────────────────────────────────────────────────────

class TestNoExtensions:
    def setup_method(self):
        self.data = parse_gpx(make_gpx([None, None, None]))

    def test_sensor_fields_empty(self):
        for key in ("cadence_rpm", "heart_rate_bpm", "power_w"):
            assert column(self.data, key) == [None, None, None]
        for key in ("avg_cadence_rpm", "max_cadence_rpm", "avg_heart_rate_bpm", "max_heart_rate_bpm",
                    "avg_power_w", "max_power_w", "avg_temperature_c", "max_temperature_c"):
            assert self.data[key] is None

    def test_track_still_parsed(self):
        assert len(self.data["track_points"]) == 3
        assert self.data["duration_seconds"] == 2
        assert self.data["distance_km"] > 0
        # Speed falls back to distance / time between points
        assert self.data["track_points"][1]["speed_kmh"] is not None


def test_output_shape_matches_fit_parser_point_keys():
    data = parse_gpx(make_gpx(["<power>200</power>"]))
    assert set(data["track_points"][0]) == {
        "timestamp", "lat", "lon", "elevation", "speed_kmh",
        "cadence_rpm", "heart_rate_bpm", "power_w", "distance_m",
    }
