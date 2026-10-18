"""
Create (or rebuild) the shared read-only demo account behind "Try the demo".

The rides go through the real upload endpoint in-process, so the demo shows exactly
what a real upload produces. With ANTHROPIC_API_KEY set, it also saves an AI analysis
for every ride and one training plan; visitors only ever read these saved results.
Ride dates are relative to today, so re-run with --reset every few weeks to keep the
dashboard current.

Usage (run from the backend directory, with the same environment as the server):
    python scripts/seed_demo.py [--reset] [--no-ai] [--lang en|pt]

    # production
    docker compose -f docker-compose.prod.yml exec backend python scripts/seed_demo.py --reset

Options:
    --reset   Delete the existing demo account and its data first
    --no-ai   Skip AI analyses and the training plan (no API spend)
    --lang    Language of the saved AI texts (default: en)
"""

from __future__ import annotations
import argparse
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from fastapi.testclient import TestClient

import models
from auth import hash_password
from database import SessionLocal
from main import app
from scripts.sample_rides import synthetic_gpx
from utils.ai_budget import api_key

DEMO_USERNAME = "demo"

# (days ago, name, seed, size, hills, effort, center)
RIDES = [
    (2,  "Recovery spin",    101, 0.6, 0.5, 0.85, (38.715, -9.255)),
    (4,  "Tempo loop",       102, 1.0, 1.0, 1.05, (38.740, -9.200)),
    (6,  "Long Sunday ride", 103, 1.8, 1.2, 0.95, (38.700, -9.300)),
    (9,  "Hill repeats",     104, 0.9, 2.0, 1.00, (38.760, -9.330)),
    (12, "Endurance",        105, 1.4, 0.8, 0.95, (38.715, -9.255)),
    (16, "Group ride",       106, 1.2, 1.0, 1.08, (38.740, -9.200)),
]

PROFILE = dict(age=34, weight_kg=72.0, ftp=250, max_hr=186, max_hr_source="user", resting_hr=52,
               experience_level="intermediate", bike_type="road")


def _login(client: TestClient, password: str) -> None:
    resp = client.post("/api/auth/login", json={"username": DEMO_USERNAME, "password": password})
    resp.raise_for_status()


def _reset(db, client: TestClient) -> None:
    user = db.query(models.User).filter(models.User.username == DEMO_USERNAME).first()
    if not user:
        return
    if not user.is_demo:
        sys.exit(f"User '{DEMO_USERNAME}' exists and is not the demo account; refusing to delete it.")
    # Unlock the account and delete it through the normal erasure path
    password = secrets.token_urlsafe(24)
    user.is_demo = False
    user.hashed_password = hash_password(password)
    db.commit()
    try:
        _login(client, password)
        client.request("DELETE", "/api/settings/account", json={"password": password}).raise_for_status()
    except Exception:
        db.rollback()
        user.is_demo = True     # leave the old demo in place rather than a half-unlocked account
        db.commit()
        raise
    client.cookies.clear()
    print("Deleted the previous demo account.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--no-ai", action="store_true")
    parser.add_argument("--lang", default="en", choices=["en", "pt"])
    args = parser.parse_args()

    # The seed is the only caller allowed past the per-user AI quotas; the monthly budget still applies.
    os.environ["AI_ANALYSES_PER_MONTH"] = "1000"
    os.environ["AI_PLANS_PER_MONTH"] = "1000"

    db = SessionLocal()
    # https: production sets Secure cookies, which a client on http:// never sends back
    client = TestClient(app, base_url="https://testserver")
    if args.reset:
        _reset(db, client)
    if db.query(models.User).filter(models.User.username == DEMO_USERNAME).first():
        sys.exit(f"User '{DEMO_USERNAME}' already exists. Use --reset to rebuild the demo.")

    # Nobody ever signs in with this password; visitors use POST /api/auth/demo
    password = secrets.token_urlsafe(24)
    user = models.User(username=DEMO_USERNAME, hashed_password=hash_password(password), **PROFILE)
    db.add(user)
    db.commit()
    _login(client, password)

    today = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    activity_ids = []
    for days_ago, name, seed, size, hills, effort, center in RIDES:
        start = (today - timedelta(days=days_ago)).replace(hour=7 + seed % 3)
        gpx = synthetic_gpx(seed=seed, start=start, name=name, size=size, hills=hills, effort=effort, center=center)
        resp = client.post("/api/activities/upload", files={"file": (f"{name}.gpx", gpx, "application/gpx+xml")})
        resp.raise_for_status()
        ride = resp.json()
        activity_ids.append(ride["id"])
        print(f"Uploaded {name}: {ride['distance_km']:.1f} km")

    client.post("/api/goals/", json={"goal_type": "weekly_distance_km", "target": 150}).raise_for_status()

    if args.no_ai:
        print("Skipping AI (--no-ai).")
    elif not api_key():
        print("ANTHROPIC_API_KEY not set — the demo has no saved AI analyses or plan.")
    else:
        for activity_id in activity_ids:
            client.get(f"/api/activities/{activity_id}/analysis", params={"lang": args.lang}).raise_for_status()
        print(f"Saved {len(activity_ids)} AI ride analyses.")
        client.post("/api/training/plan", json={
            "objective": "Build endurance for a 120 km gran fondo",
            "training_days": ["Tuesday", "Thursday", "Saturday", "Sunday"],
            "lang": args.lang,
        }).raise_for_status()
        print("Saved an AI training plan.")

    db.refresh(user)
    user.is_demo = True
    db.commit()
    db.close()
    print(f"Demo account ready ({len(activity_ids)} rides). Visitors reach it with the 'Try the demo' button.")


if __name__ == "__main__":
    main()
