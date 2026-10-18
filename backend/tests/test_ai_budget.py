"""
Tests for utils/ai_budget.py and utils/access.py — AI quotas, the monthly budget,
and feature access when payments are switched off.

Run from the backend directory:
    python -m pytest tests/test_ai_budget.py -v
"""

import sys
import os
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import models
from database import Base, SessionLocal, engine
from utils import ai_budget
from utils.access import has_full_access, payments_enabled


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def user(db):
    u = models.User(username="rider", hashed_password="x")
    db.add(u)
    db.commit()
    return u


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")


def usage(input_tokens, output_tokens):
    return SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens,
                           cache_creation_input_tokens=None, cache_read_input_tokens=None)


def add_spend(db, user_id, feature, cost_usd, created_at=None):
    db.add(models.AIUsage(user_id=user_id, feature=feature, model=ai_budget.HAIKU,
                          cost_usd=cost_usd, created_at=created_at or datetime.utcnow()))
    db.commit()


# ── Cost ───────────────────────────────────────────────────────────────────

class TestCallCost:
    def test_haiku(self):
        # 1M input at $1 + 1M output at $5
        assert ai_budget.call_cost_usd(ai_budget.HAIKU, 1_000_000, 1_000_000) == pytest.approx(6.0)

    def test_sonnet(self):
        assert ai_budget.call_cost_usd(ai_budget.SONNET, 2000, 4000) == pytest.approx(0.066)

    def test_unknown_model_priced_as_sonnet(self):
        assert ai_budget.call_cost_usd("claude-unknown", 1000, 1000) == \
            ai_budget.call_cost_usd(ai_budget.SONNET, 1000, 1000)

    def test_record_usage_stores_cost(self, db, user):
        ai_budget.record_usage(db, user.id, "analysis", ai_budget.HAIKU, usage(3000, 800))
        row = db.query(models.AIUsage).one()
        assert (row.input_tokens, row.output_tokens) == (3000, 800)
        assert row.cost_usd == pytest.approx(0.007)


# ── Monthly budget ─────────────────────────────────────────────────────────

class TestBudget:
    def test_spend_counts_only_this_month(self, db, user):
        add_spend(db, user.id, "analysis", 2.0)
        add_spend(db, user.id, "analysis", 5.0, created_at=datetime.utcnow().replace(day=1) - timedelta(days=1))
        assert ai_budget.monthly_spend_usd(db) == pytest.approx(2.0)

    def test_exhausted_at_budget(self, db, user, monkeypatch):
        monkeypatch.setenv("AI_MONTHLY_BUDGET_USD", "3")
        add_spend(db, user.id, "plan", 2.99)
        assert not ai_budget.budget_exhausted(db)
        add_spend(db, user.id, "plan", 0.01)
        assert ai_budget.budget_exhausted(db)

    def test_zero_budget_means_no_cap(self, db, user, monkeypatch):
        monkeypatch.setenv("AI_MONTHLY_BUDGET_USD", "0")
        add_spend(db, user.id, "plan", 500)
        assert not ai_budget.budget_exhausted(db)

    def test_ai_unavailable_without_key(self, db):
        assert not ai_budget.ai_available(db)


# ── Quotas ─────────────────────────────────────────────────────────────────

class TestCheckQuota:
    def test_allows_within_quota(self, db, user, with_key):
        ai_budget.check_quota(db, user, "analysis")

    def test_monthly_limit(self, db, user, with_key, monkeypatch):
        monkeypatch.setenv("AI_ANALYSES_PER_MONTH", "2")
        add_spend(db, user.id, "analysis", 0.01)
        ai_budget.check_quota(db, user, "analysis")
        add_spend(db, user.id, "analysis", 0.01)
        with pytest.raises(HTTPException) as e:
            ai_budget.check_quota(db, user, "analysis")
        assert e.value.status_code == 429

    def test_quotas_are_per_feature_and_per_user(self, db, user, with_key, monkeypatch):
        monkeypatch.setenv("AI_PLANS_PER_MONTH", "1")
        other = models.User(username="other", hashed_password="x")
        db.add(other)
        db.commit()
        add_spend(db, other.id, "plan", 0.05)
        add_spend(db, user.id, "analysis", 0.01)
        ai_budget.check_quota(db, user, "plan")

    def test_demo_cannot_generate(self, db, user, with_key):
        user.is_demo = True
        with pytest.raises(HTTPException) as e:
            ai_budget.check_quota(db, user, "analysis")
        assert e.value.status_code == 403

    def test_no_key(self, db, user):
        with pytest.raises(HTTPException) as e:
            ai_budget.check_quota(db, user, "analysis")
        assert e.value.status_code == 503

    def test_budget_exhausted(self, db, user, with_key, monkeypatch):
        monkeypatch.setenv("AI_MONTHLY_BUDGET_USD", "1")
        add_spend(db, None, "moderation", 1.0)
        with pytest.raises(HTTPException) as e:
            ai_budget.check_quota(db, user, "analysis")
        assert e.value.status_code == 503


class TestLightCalls:
    def test_daily_cap(self, db, user, with_key):
        cap = ai_budget.DAILY_LIMITS["ride_insight"]
        for _ in range(cap - 1):
            add_spend(db, user.id, "ride_insight", 0.0001)
        assert ai_budget.allow_light_call(db, user, "ride_insight")
        add_spend(db, user.id, "ride_insight", 0.0001)
        assert not ai_budget.allow_light_call(db, user, "ride_insight")

    def test_old_calls_do_not_count(self, db, user, with_key):
        yesterday = datetime.utcnow() - timedelta(days=1, minutes=1)
        for _ in range(ai_budget.DAILY_LIMITS["moderation"]):
            add_spend(db, user.id, "moderation", 0.0001, created_at=yesterday)
        assert ai_budget.allow_light_call(db, user, "moderation")

    def test_off_without_key(self, db, user):
        assert not ai_budget.allow_light_call(db, user, "fitness_insight")


# ── Access ─────────────────────────────────────────────────────────────────

class TestAccess:
    def test_everyone_has_access_without_payments(self):
        assert not payments_enabled()
        assert has_full_access(SimpleNamespace(membership="free"))

    def test_free_users_gated_with_payments(self, monkeypatch):
        monkeypatch.setenv("PAYMENTS_ENABLED", "true")
        assert not has_full_access(SimpleNamespace(membership="free"))
        assert has_full_access(SimpleNamespace(membership="pro"))
