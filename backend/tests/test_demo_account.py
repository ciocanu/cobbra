"""
API tests for the open instance: public config, payments switched off, the shared
read-only demo account, and AI quotas end to end (with a fake Anthropic client).

Run from the backend directory:
    python -m pytest tests/test_demo_account.py -v
"""

import sys
import os
from datetime import datetime
from types import SimpleNamespace

import anthropic
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import models
from auth import hash_password
from database import Base, SessionLocal, engine
from main import app


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db):
    return TestClient(app)


@pytest.fixture
def demo(db):
    user = models.User(username="demo", hashed_password="!", is_demo=True)
    db.add(user)
    db.commit()
    db.add(models.Activity(user_id=user.id, name="Demo ride", date=datetime(2026, 9, 1, 8),
                           ai_analysis="Saved analysis."))
    db.add(models.Activity(user_id=user.id, name="No analysis yet", date=datetime(2026, 9, 2, 8)))
    db.commit()
    return user


def demo_client(client):
    assert client.post("/api/auth/demo").status_code == 200
    return client


class TestPublicConfig:
    def test_defaults(self, client):
        cfg = client.get("/api/config").json()
        assert cfg == {"payments_enabled": False, "demo_available": False, "ai_available": False}

    def test_demo_available_once_seeded(self, client, demo):
        assert client.get("/api/config").json()["demo_available"] is True

    def test_payment_routes_not_mounted(self, client):
        assert client.post("/api/payments/create-checkout", json={"tier": "pro"}).status_code == 404


class TestDemoLogin:
    def test_unavailable_without_demo_user(self, client):
        assert client.post("/api/auth/demo").status_code == 404

    def test_signs_in_as_demo(self, client, demo):
        me = demo_client(client).get("/api/auth/me").json()
        assert me["username"] == "demo"
        assert me["is_demo"] is True


class TestDemoIsReadOnly:
    def test_reads_work(self, client, demo):
        c = demo_client(client)
        assert c.get("/api/activities/").status_code == 200

    @pytest.mark.parametrize("method,path,body", [
        ("post", "/api/goals/", {"type": "distance", "target": 100}),
        ("patch", "/api/settings/", {"max_hr": 190}),
        ("delete", "/api/settings/account", None),
    ])
    def test_writes_rejected(self, client, demo, method, path, body):
        c = demo_client(client)
        resp = getattr(c, method)(path, json=body) if body is not None else getattr(c, method)(path)
        assert resp.status_code == 403
        assert "read-only" in resp.json()["detail"]

    def test_cannot_delete_rides(self, client, demo, db):
        c = demo_client(client)
        act = db.query(models.Activity).filter_by(user_id=demo.id).first()
        assert c.delete(f"/api/activities/{act.id}").status_code == 403
        assert c.delete(f"/api/activities/{act.id}/analysis").status_code == 403

    def test_dashboard_insights_still_answer(self, client, demo):
        c = demo_client(client)
        resp = c.post("/api/dashboard/fitness-insight", json={"ctl": 50, "atl": 60, "tsb": -10})
        assert resp.status_code == 200
        assert resp.json()["insight"]

    def test_saved_analysis_is_served(self, client, demo, db):
        c = demo_client(client)
        act = db.query(models.Activity).filter_by(name="Demo ride").one()
        resp = c.get(f"/api/activities/{act.id}/analysis")
        assert resp.status_code == 200
        assert resp.json() == {"analysis": "Saved analysis.", "cached": True}

    def test_cannot_generate_new_analysis(self, client, demo, db, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        c = demo_client(client)
        act = db.query(models.Activity).filter_by(name="No analysis yet").one()
        resp = c.get(f"/api/activities/{act.id}/analysis")
        assert resp.status_code == 403

    def test_logout_keeps_other_visitors_signed_in(self, client, demo, db):
        other = TestClient(app)
        demo_client(other)
        c = demo_client(client)
        assert c.post("/api/auth/logout").status_code == 200
        assert other.get("/api/auth/me").status_code == 200
        db.refresh(demo)
        assert demo.token_version == 1


# ── AI calls end to end, with a fake Anthropic client ─────────────────────

class _FakeMessages:
    def create(self, **kwargs):
        return SimpleNamespace(
            content=[SimpleNamespace(text=f"Fake {kwargs['model']} reply.")],
            usage=SimpleNamespace(input_tokens=2000, output_tokens=500,
                                  cache_creation_input_tokens=None, cache_read_input_tokens=None),
        )


class _FakeAnthropic:
    def __init__(self, api_key=None):
        self.messages = _FakeMessages()


@pytest.fixture
def fake_ai(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr(anthropic, "Anthropic", _FakeAnthropic)


@pytest.fixture
def rider_client(client, db):
    db.add(models.User(username="rider", hashed_password=hash_password("pw123456")))
    db.commit()
    assert client.post("/api/auth/login", json={"username": "rider", "password": "pw123456"}).status_code == 200
    return client


def _rider_activity(db, name):
    user = db.query(models.User).filter_by(username="rider").one()
    act = models.Activity(user_id=user.id, name=name, date=datetime(2026, 9, 1, 8))
    db.add(act)
    db.commit()
    return act.id


class TestAnalysisQuota:
    def test_generation_records_spend_and_stops_at_quota(self, rider_client, db, fake_ai, monkeypatch):
        monkeypatch.setenv("AI_ANALYSES_PER_MONTH", "2")
        ids = [_rider_activity(db, f"Ride {i}") for i in range(3)]

        for activity_id in ids[:2]:
            resp = rider_client.get(f"/api/activities/{activity_id}/analysis")
            assert resp.status_code == 200
            assert resp.json()["cached"] is False

        rows = db.query(models.AIUsage).all()
        assert [r.feature for r in rows] == ["analysis", "analysis"]
        assert rows[0].cost_usd == pytest.approx(0.0045)   # 2000 in + 500 out on Haiku

        assert rider_client.get(f"/api/activities/{ids[2]}/analysis").status_code == 429
        quota = rider_client.get("/api/auth/ai-quota").json()
        assert quota["features"]["analysis"] == {"used": 2, "limit": 2}
        assert quota["available"] is True and quota["reason"] is None

    def test_quota_reports_why_ai_is_off(self, rider_client, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        quota = rider_client.get("/api/auth/ai-quota").json()
        assert quota["available"] is False and quota["reason"] == "not_configured"

    def test_regenerating_counts_against_quota(self, rider_client, db, fake_ai, monkeypatch):
        monkeypatch.setenv("AI_ANALYSES_PER_MONTH", "1")
        activity_id = _rider_activity(db, "Ride")
        assert rider_client.get(f"/api/activities/{activity_id}/analysis").status_code == 200
        assert rider_client.delete(f"/api/activities/{activity_id}/analysis").status_code == 200
        assert rider_client.get(f"/api/activities/{activity_id}/analysis").status_code == 429

    def test_refused_regeneration_keeps_saved_analysis(self, rider_client, db, fake_ai, monkeypatch):
        monkeypatch.setenv("AI_ANALYSES_PER_MONTH", "2")
        activity_id = _rider_activity(db, "Ride")
        first = rider_client.get(f"/api/activities/{activity_id}/analysis").json()["analysis"]
        assert rider_client.get(f"/api/activities/{activity_id}/analysis",
                                params={"regenerate": True}).json()["cached"] is False
        resp = rider_client.get(f"/api/activities/{activity_id}/analysis", params={"regenerate": True})
        assert resp.status_code == 429
        assert rider_client.get(f"/api/activities/{activity_id}/analysis").json() == {"analysis": first, "cached": True}


class TestSeedDemo:
    def test_works_with_production_secure_cookies(self, db, monkeypatch):
        # Production sets COOKIE_SECURE=true; a client on http:// would never send the cookie back
        from scripts import seed_demo
        import routes.activities
        import routes.auth

        async def no_weather(*_args):
            return {}
        monkeypatch.setattr(routes.activities, "_fetch_weather", no_weather)
        monkeypatch.setattr(routes.auth, "COOKIE_SECURE", True)
        monkeypatch.setattr(sys, "argv", ["seed_demo.py", "--no-ai"])
        seed_demo.main()

        demo = db.query(models.User).filter_by(username="demo").one()
        assert db.query(models.Activity).filter_by(user_id=demo.id).count() == len(seed_demo.RIDES)

    def test_builds_demo_with_saved_ai_results(self, db, fake_ai, monkeypatch):
        from scripts import seed_demo
        import routes.activities

        async def no_weather(*_args):
            return {}
        monkeypatch.setattr(routes.activities, "_fetch_weather", no_weather)
        monkeypatch.setenv("AI_ANALYSES_PER_MONTH", "5")   # restored after the seed overrides it
        monkeypatch.setenv("AI_PLANS_PER_MONTH", "1")
        monkeypatch.setattr(sys, "argv", ["seed_demo.py"])
        seed_demo.main()

        demo = db.query(models.User).filter_by(username="demo").one()
        assert demo.is_demo is True
        rides = db.query(models.Activity).filter_by(user_id=demo.id).all()
        assert len(rides) == len(seed_demo.RIDES)
        assert all(r.ai_analysis for r in rides)
        assert all(r.avg_power_w and r.avg_cadence_rpm for r in rides)
        assert db.query(models.TrainingPlan).filter_by(user_id=demo.id).count() == 1
        assert db.query(models.AIUsage).count() == len(seed_demo.RIDES) + 1


class TestAccountDeletion:
    def test_deletes_rides_with_personal_records_when_fks_are_enforced(self, client, db):
        # SQLite skips FK checks unless asked; PostgreSQL (production) always checks them
        from sqlalchemy import event

        def enforce_fks(dbapi_conn, _record):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        event.listen(engine, "connect", enforce_fks)
        engine.dispose()
        try:
            db.add(models.User(username="leaver", hashed_password=hash_password("pw123456")))
            db.commit()
            user = db.query(models.User).filter_by(username="leaver").one()
            ride = models.Activity(user_id=user.id, name="Ride", date=datetime(2026, 9, 1, 8))
            db.add(ride)
            db.commit()
            db.add(models.PersonalRecord(user_id=user.id, activity_id=ride.id, pr_type="1km",
                                         value=90, set_at=datetime(2026, 9, 1, 8)))
            db.commit()

            c = TestClient(app)
            assert c.post("/api/auth/login", json={"username": "leaver", "password": "pw123456"}).status_code == 200
            resp = c.request("DELETE", "/api/settings/account", json={"password": "pw123456"})
            assert resp.status_code == 200
            db.expire_all()
            assert db.query(models.User).filter_by(username="leaver").count() == 0
        finally:
            event.remove(engine, "connect", enforce_fks)
            engine.dispose()


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def text_stream(self):
        async def gen():
            for c in self._chunks:
                yield c
        return gen()

    async def get_final_message(self):
        return SimpleNamespace(usage=SimpleNamespace(input_tokens=1000, output_tokens=300,
                                                     cache_creation_input_tokens=None, cache_read_input_tokens=None))


class _FakeAsyncAnthropic:
    def __init__(self, api_key=None):
        self.messages = SimpleNamespace(stream=lambda **kw: _FakeStream(["Strong ", "ride."]))


class TestStreamingAnalysis:
    def test_stream_saves_text_and_records_usage(self, rider_client, db, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
        activity_id = _rider_activity(db, "Ride")

        body = rider_client.get(f"/api/activities/{activity_id}/analysis/stream").text
        assert '"done": true' in body

        db.expire_all()
        assert db.get(models.Activity, activity_id).ai_analysis == "Strong ride."
        row = db.query(models.AIUsage).one()
        assert (row.feature, row.input_tokens, row.output_tokens) == ("analysis", 1000, 300)

    def test_stream_refused_over_quota(self, rider_client, db, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("AI_ANALYSES_PER_MONTH", "0")
        monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
        activity_id = _rider_activity(db, "Ride")
        assert rider_client.get(f"/api/activities/{activity_id}/analysis/stream").status_code == 429


class TestDashboardInsights:
    BODY = {"ctl": 50, "atl": 60, "tsb": -10}

    def test_no_ai_unless_asked(self, rider_client, db, fake_ai):
        resp = rider_client.post("/api/dashboard/fitness-insight", json=self.BODY)
        assert resp.status_code == 200
        assert "Fake" not in resp.json()["insight"]
        assert db.query(models.AIUsage).count() == 0

    def test_ai_when_asked(self, rider_client, db, fake_ai):
        resp = rider_client.post("/api/dashboard/fitness-insight", json={**self.BODY, "use_ai": True})
        assert resp.json()["insight"].startswith("Fake")
        assert db.query(models.AIUsage).one().feature == "fitness_insight"
