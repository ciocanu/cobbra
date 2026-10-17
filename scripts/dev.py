#!/usr/bin/env python3
"""Run Cobbra locally with one command: backend + frontend + a ready test account.

    python scripts/dev.py                         # start (installs deps on first run)
    python scripts/dev.py --reset                 # wipe the local dev database first
    python scripts/dev.py --import strava_Data/activities --limit 30
                                                  # also load your own .gpx/.fit(.gz) rides

Opens http://localhost:5173 — log in as  dev / devpassword
Ctrl+C stops everything.

Uses only the Python standard library, so it runs before the backend venv exists.
Data lives in backend/data/dev.db (git-ignored) and never touches production.
Values in backend/.env (e.g. ANTHROPIC_API_KEY) are still picked up, except the
ones this script sets below.
"""
import argparse
import gzip
import hashlib
import http.cookiejar
import json
import math
import os
import random
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
DATA_DIR = BACKEND / "data"
DB_PATH = DATA_DIR / "dev.db"

BACKEND_PORT = 8000
FRONTEND_PORT = 5173
API = f"http://127.0.0.1:{BACKEND_PORT}"

DEV_USER = "dev"
DEV_PASSWORD = "devpassword"

IS_WINDOWS = os.name == "nt"


def log(msg):
    print(f"[dev] {msg}", flush=True)


def die(msg):
    print(f"[dev] ERROR: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── Dependencies ─────────────────────────────────────────────────────────────

def venv_python():
    # Reuse a venv created by the README instructions (backend/venv) if present.
    venv = BACKEND / "venv" if (BACKEND / "venv").exists() else BACKEND / ".venv"
    py = venv / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")
    if not py.exists():
        log(f"Creating Python venv in {venv.relative_to(ROOT)} ...")
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    marker = venv / ".cobbra-requirements.sha256"
    wanted = file_hash(BACKEND / "requirements.txt")
    if not marker.exists() or marker.read_text().strip() != wanted:
        log("Installing backend requirements (first run or requirements.txt changed) ...")
        subprocess.run([str(py), "-m", "pip", "install", "-q", "-r", str(BACKEND / "requirements.txt")], check=True)
        marker.write_text(wanted)
    return py


def npm_cmd():
    npm = shutil.which("npm")
    if not npm:
        die("npm not found. Install Node.js 18+ from https://nodejs.org and re-run.")
    marker = FRONTEND / "node_modules" / ".cobbra-lock.sha256"
    wanted = file_hash(FRONTEND / "package-lock.json")
    if not marker.exists() or marker.read_text().strip() != wanted:
        log("Installing frontend packages (first run or package-lock.json changed) ...")
        subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=FRONTEND, check=True)
        marker.write_text(wanted)
    return npm


def port_in_use(port):
    import socket
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


# ── Backend setup ────────────────────────────────────────────────────────────

def backend_env():
    env = os.environ.copy()
    env.update({
        "DATABASE_URL": f"sqlite:///{DB_PATH.as_posix()}",
        "SECRET_KEY": "local-dev-only-not-a-secret-0123456789abcdef",
        "COOKIE_SECURE": "false",
        "ADMIN_USERNAME": DEV_USER,
        "CORS_ORIGINS": f"http://localhost:{FRONTEND_PORT},http://127.0.0.1:{FRONTEND_PORT}",
        "APP_URL": f"http://localhost:{FRONTEND_PORT}",
        "PYTHONUNBUFFERED": "1",
    })
    return env


# Creates the tables and an admin user whose profile already passes the
# onboarding gate (age, weight, experience, bike type), so the app opens
# straight on the dashboard.
SEED_USER = f"""
import models
from database import SessionLocal, engine
from auth import hash_password
models.Base.metadata.create_all(bind=engine)
db = SessionLocal()
u = db.query(models.User).filter(models.User.username == {DEV_USER!r}).first()
created = u is None
if created:
    u = models.User(username={DEV_USER!r}, email="dev@localhost")
    db.add(u)
u.hashed_password = hash_password({DEV_PASSWORD!r})
for k, v in dict(age=34, weight_kg=72.0, resting_hr=52, max_hr=186, max_hr_source="user",
                 ftp=250, experience_level="intermediate", bike_type="road").items():
    if getattr(u, k) is None:
        setattr(u, k, v)
db.commit()
print("created" if created else "exists")
"""


def seed_user(py, env):
    out = subprocess.run([str(py), "-c", SEED_USER], cwd=BACKEND, env=env,
                         capture_output=True, text=True)
    if out.returncode != 0:
        print(out.stdout, out.stderr, file=sys.stderr)
        die("Could not create the dev user (see error above).")
    log(f"Test account {'created' if 'created' in out.stdout else 'ready'}: {DEV_USER} / {DEV_PASSWORD}")


# ── Sample data ──────────────────────────────────────────────────────────────

def synthetic_gpx():
    """A deterministic ~32 km loop west of Lisbon with elevation, HR, cadence, power and temperature.

    Sensor tags follow real exports: HR/cadence/temperature in Garmin's TrackPointExtension
    (<gpxtpx:hr>, <gpxtpx:cad>, <gpxtpx:atemp>) and power as Strava's flat <power>.
    """
    rnd = random.Random(42)
    clat, clon = 38.715, -9.255
    r_lat, r_lon = 0.046, 0.059                       # ~5 km radius
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
        return 85 + 55 * math.sin(2 * math.pi * 2 * x) + 22 * math.sin(2 * math.pi * 5 * x + 1)

    start = (datetime.now(timezone.utc) - timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
    pts, s, t, j, hr = [], 0.0, 0, 0, 118.0
    while s < total:
        grade = (ele(s + 10) - ele(s)) / 10
        v = max(3.5, min(13.5, 8.6 - 55 * grade + rnd.uniform(-0.4, 0.4)))     # m/s
        hr += ((max(105, min(178, 138 + 650 * grade + t / 300))) - hr) * 0.06 + rnd.uniform(-1, 1)
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
        "<trk><name>Volta de teste (dev)</name><type>cycling</type><trkseg>"
        + "".join(pts)
        + "</trkseg></trk></gpx>"
    ).encode()


class Api:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method, path, body=None, headers=None, timeout=30):
        req = urllib.request.Request(API + path, data=body, method=method, headers=headers or {})
        with self.opener.open(req, timeout=timeout) as r:
            return json.loads(r.read() or b"null")

    def login(self):
        self.call("POST", "/api/auth/login", json.dumps({"username": DEV_USER, "password": DEV_PASSWORD}).encode(),
                  {"Content-Type": "application/json"})

    def activity_count(self):
        data = self.call("GET", "/api/activities/?limit=1")
        return data.get("total", len(data.get("items", []))) if isinstance(data, dict) else len(data)

    def upload(self, filename, content):
        boundary = uuid.uuid4().hex
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        return self.call("POST", "/api/activities/upload", body,
                         {"Content-Type": f"multipart/form-data; boundary={boundary}"}, timeout=300)


def seed_activities(import_dir, limit):
    api = Api()
    api.login()
    if import_dir:
        files = sorted(p for p in Path(import_dir).expanduser().iterdir()
                       if p.name.lower().endswith((".gpx", ".fit", ".gpx.gz", ".fit.gz")))
        files = files[-limit:]                      # newest by name (Strava exports are numbered)
        log(f"Importing {len(files)} ride(s) from {import_dir} ...")
        ok = 0
        for p in files:
            name, content = p.name, p.read_bytes()
            if name.lower().endswith(".gz"):
                name, content = name[:-3], gzip.decompress(content)
            try:
                api.upload(name, content)
                ok += 1
            except urllib.error.HTTPError as e:
                log(f"  skipped {p.name}: HTTP {e.code} {e.read()[:120].decode(errors='replace')}")
        log(f"Imported {ok}/{len(files)}.")
    elif api.activity_count() == 0:
        log("No rides yet — uploading a synthetic sample ride ...")
        a = api.upload("volta-de-teste.gpx", synthetic_gpx())
        log(f"Sample ride ready: {a.get('distance_km', 0):.1f} km (activity #{a.get('id')})")


# ── Process management ───────────────────────────────────────────────────────

def start(cmd, cwd, env=None):
    kwargs = {"cwd": cwd, "env": env}
    if IS_WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)


def stop(proc):
    if proc.poll() is not None:
        return
    if IS_WINDOWS:   # npm.cmd → node, uvicorn reloader → worker: kill the whole tree
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def wait_for_backend(proc, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            die("Backend exited during startup (see the log above).")
        try:
            urllib.request.urlopen(API + "/health", timeout=2)
            return
        except OSError:
            time.sleep(0.5)
    die(f"Backend did not answer on {API}/health within {timeout}s.")


def main():
    ap = argparse.ArgumentParser(description="Run Cobbra locally (backend + frontend + test account).")
    ap.add_argument("--reset", action="store_true", help="delete the local dev database before starting")
    ap.add_argument("--import", dest="import_dir", metavar="DIR",
                    help="upload .gpx/.fit(.gz) files from DIR, e.g. a Strava export's activities/ folder")
    ap.add_argument("--limit", type=int, default=20, help="max files to import with --import (default 20)")
    args = ap.parse_args()

    if sys.version_info < (3, 10):
        die(f"Python 3.10+ required (this is {sys.version.split()[0]}).")
    for port, what in ((BACKEND_PORT, "backend"), (FRONTEND_PORT, "frontend")):
        if port_in_use(port):
            die(f"Port {port} ({what}) is already in use — stop whatever is running there first.")

    if args.reset:
        for suffix in ("", "-wal", "-shm"):
            Path(f"{DB_PATH}{suffix}").unlink(missing_ok=True)
        log("Local dev database wiped.")
    DATA_DIR.mkdir(exist_ok=True)

    py = venv_python()
    npm = npm_cmd()
    env = backend_env()
    seed_user(py, env)

    # Children run in their own process group/session (so Ctrl+C reaches only us
    # and we shut them down in order). Treat termination signals like Ctrl+C so
    # closing the terminal doesn't leave uvicorn/vite holding the ports.
    def _interrupt(*_):
        raise KeyboardInterrupt
    for name in ("SIGTERM", "SIGHUP"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), _interrupt)

    procs = []
    try:
        log(f"Starting backend on {API} ...")
        backend = start([str(py), "-m", "uvicorn", "main:app", "--host", "127.0.0.1",
                         "--port", str(BACKEND_PORT), "--reload"], BACKEND, env)
        procs.append(backend)
        wait_for_backend(backend)
        seed_activities(args.import_dir, args.limit)

        log("Starting frontend ...")
        procs.append(start([npm, "run", "dev", "--", "--port", str(FRONTEND_PORT), "--strictPort"], FRONTEND))

        print(
            f"\n  Cobbra is running:  http://localhost:{FRONTEND_PORT}\n"
            f"  Login:              {DEV_USER} / {DEV_PASSWORD}   (admin)\n"
            f"  API docs:           {API}/docs\n"
            f"  Ctrl+C to stop.\n",
            flush=True,
        )
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
        die("A process exited unexpectedly (see the log above).")
    except KeyboardInterrupt:
        print()
        log("Stopping ...")
    finally:
        for p in reversed(procs):
            stop(p)


if __name__ == "__main__":
    main()
