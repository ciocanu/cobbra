"""Deterministic synthetic GPX rides for local development and the demo account.

Standard library only: scripts/dev.py imports this before the backend venv exists.
"""

import math
import random
from datetime import datetime, timedelta, timezone


def synthetic_gpx(seed=42, start=None, name="Volta de teste (dev)", size=1.0, hills=1.0, effort=1.0,
                  center=(38.715, -9.255)):
    """A loop west of Lisbon with elevation, HR, cadence, power and temperature.

    The defaults give a ~37 km ride; `size` scales the loop radius, `hills` the
    elevation, and `effort` the rider's speed, heart rate and power.

    Sensor tags follow real exports: HR/cadence/temperature in Garmin's TrackPointExtension
    (<gpxtpx:hr>, <gpxtpx:cad>, <gpxtpx:atemp>) and power as Strava's flat <power>.
    """
    rnd = random.Random(seed)
    clat, clon = center
    r_lat, r_lon = 0.046 * size, 0.059 * size          # ~5 km radius at size 1
    poly = []
    for i in range(4000):
        a = 2 * math.pi * i / 4000
        k = 1 + 0.22 * math.sin(3 * a) + 0.08 * math.sin(7 * a)
        poly.append((clat + r_lat * k * math.sin(a), clon + r_lon * k * math.cos(a)))
    poly.append(poly[0])

    def dist(p, q):
        dy = (q[0] - p[0]) * 111_320
        dx = (q[1] - p[1]) * 111_320 * math.cos(math.radians(p[0]))
        return math.hypot(dx, dy)

    cum = [0.0]
    for p, q in zip(poly, poly[1:]):
        cum.append(cum[-1] + dist(p, q))
    total = cum[-1]

    def ele(s):
        x = s / total
        return 85 + hills * (55 * math.sin(2 * math.pi * 2 * x) + 22 * math.sin(2 * math.pi * 5 * x + 1))

    if start is None:
        start = (datetime.now(timezone.utc) - timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
    pts, s, t, j, hr = [], 0.0, 0, 0, 118.0
    while s < total:
        grade = (ele(s + 10) - ele(s)) / 10
        v = max(3.5, min(13.5, 8.6 * effort - 55 * grade + rnd.uniform(-0.4, 0.4)))     # m/s
        hr += ((max(105, min(178, 138 + 60 * (effort - 1) + 650 * grade + t / 300))) - hr) * 0.06 + rnd.uniform(-1, 1)
        cad = 0 if grade < -0.035 else max(62, min(102, 88 - 160 * grade + rnd.uniform(-3, 3)))
        # 80 kg rider+bike, Crr 0.005, CdA 0.32 m², 97 % drivetrain; no pedalling when coasting
        watts = 0 if cad == 0 else max(0, (80 * 9.81 * v * (grade + 0.005) + 0.5 * 1.2 * 0.32 * v ** 3) / 0.97
                                         + rnd.uniform(-15, 15))
        while j < len(cum) - 2 and cum[j + 1] < s:
            j += 1
        f = (s - cum[j]) / max(cum[j + 1] - cum[j], 1e-9)
        lat = poly[j][0] + (poly[j + 1][0] - poly[j][0]) * f
        lon = poly[j][1] + (poly[j + 1][1] - poly[j][1]) * f
        ts = (start + timedelta(seconds=t)).strftime("%Y-%m-%dT%H:%M:%SZ")
        pts.append(
            f'<trkpt lat="{lat:.6f}" lon="{lon:.6f}"><ele>{ele(s):.1f}</ele><time>{ts}</time>'
            f"<extensions><power>{round(watts)}</power><gpxtpx:TrackPointExtension><gpxtpx:hr>{round(hr)}</gpxtpx:hr>"
            f"<gpxtpx:cad>{round(cad)}</gpxtpx:cad><gpxtpx:atemp>{19 + 4 * t / 4000:.1f}</gpxtpx:atemp>"
            f"</gpxtpx:TrackPointExtension></extensions></trkpt>"
        )
        s += v * 5
        t += 5
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx version="1.1" creator="cobbra-dev" xmlns="http://www.topografix.com/GPX/1/1" '
        'xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">'
        f"<trk><name>{name}</name><type>cycling</type><trkseg>"
        + "".join(pts)
        + "</trkseg></trk></gpx>"
    ).encode()
