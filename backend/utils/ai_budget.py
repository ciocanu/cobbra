"""AI spend control: per-user quotas and a global monthly budget.

Every Claude call records its token usage with record_usage(), so the budget sees all
spend. Expensive features (ride analysis, training plans) have a monthly quota per
user; cheap one-line features (dashboard insights, note moderation) have a daily cap.
When the month's spend reaches AI_MONTHLY_BUDGET_USD, AI is switched off site-wide
until the next calendar month. The rest of the app keeps working.

Settings (environment):
    AI_MONTHLY_BUDGET_USD   default 10; 0 disables the cap
    AI_ANALYSES_PER_MONTH   default 5
    AI_PLANS_PER_MONTH      default 1
"""

import os
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

import models

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"

# USD per million tokens (input, output) — Anthropic first-party API rates
PRICES_PER_MTOK = {
    HAIKU: (1.00, 5.00),
    SONNET: (3.00, 15.00),
}

MONTHLY_FEATURES = {"analysis": "AI_ANALYSES_PER_MONTH", "plan": "AI_PLANS_PER_MONTH"}
_MONTHLY_DEFAULTS = {"analysis": 5, "plan": 1}
DAILY_LIMITS = {"ride_insight": 30, "fitness_insight": 30, "moderation": 50}


def api_key() -> str | None:
    return os.getenv("ANTHROPIC_API_KEY") or None


def monthly_budget_usd() -> float:
    return float(os.getenv("AI_MONTHLY_BUDGET_USD", "10"))


def monthly_limit(feature: str) -> int:
    return int(os.getenv(MONTHLY_FEATURES[feature], str(_MONTHLY_DEFAULTS[feature])))


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def call_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    # Unknown model: price it as Sonnet so the budget errs on the safe side
    price_in, price_out = PRICES_PER_MTOK.get(model, PRICES_PER_MTOK[SONNET])
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


def monthly_spend_usd(db: Session, now: datetime | None = None) -> float:
    since = _month_start(now or datetime.utcnow())
    total = db.query(func.sum(models.AIUsage.cost_usd)).filter(models.AIUsage.created_at >= since).scalar()
    return float(total or 0.0)


def budget_exhausted(db: Session) -> bool:
    budget = monthly_budget_usd()
    return budget > 0 and monthly_spend_usd(db) >= budget


def ai_available(db: Session) -> bool:
    return api_key() is not None and not budget_exhausted(db)


def _usage_count(db: Session, user_id: int, feature: str, since: datetime) -> int:
    return db.query(func.count(models.AIUsage.id)).filter(
        models.AIUsage.user_id == user_id,
        models.AIUsage.feature == feature,
        models.AIUsage.created_at >= since,
    ).scalar() or 0


def used_this_month(db: Session, user_id: int, feature: str) -> int:
    return _usage_count(db, user_id, feature, _month_start(datetime.utcnow()))


def check_quota(db: Session, user, feature: str) -> None:
    """Raise unless `user` may make one more `feature` call now (monthly-quota features)."""
    if user.is_demo:
        raise HTTPException(status_code=403, detail="The demo account shows saved AI results only. Create a free account to generate your own.")
    if api_key() is None:
        raise HTTPException(status_code=503, detail="AI features are not configured on this server.")
    if budget_exhausted(db):
        raise HTTPException(status_code=503, detail="AI features are paused until next month: this instance reached its monthly AI budget.")
    limit = monthly_limit(feature)
    if used_this_month(db, user.id, feature) >= limit:
        raise HTTPException(status_code=429, detail=f"Monthly AI limit reached ({limit} per month). It resets on the 1st.")


def allow_light_call(db: Session, user, feature: str) -> bool:
    """Whether a cheap, optional call may run; callers fall back to non-AI output when False."""
    if api_key() is None or budget_exhausted(db):
        return False
    since = datetime.utcnow() - timedelta(days=1)
    return _usage_count(db, user.id, feature, since) < DAILY_LIMITS[feature]


def record_usage(db: Session, user_id: int | None, feature: str, model: str, usage) -> None:
    """Store one call's token usage; `usage` is the SDK response's `.usage`."""
    input_tokens = (usage.input_tokens or 0) + (getattr(usage, "cache_creation_input_tokens", None) or 0) \
        + (getattr(usage, "cache_read_input_tokens", None) or 0)
    output_tokens = usage.output_tokens or 0
    db.add(models.AIUsage(
        user_id=user_id,
        feature=feature,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=call_cost_usd(model, input_tokens, output_tokens),
    ))
    db.commit()


def quota_status(db: Session, user) -> dict:
    """Remaining monthly AI quota, for the frontend."""
    return {
        "available": ai_available(db) and not user.is_demo,
        "features": {
            f: {"used": used_this_month(db, user.id, f), "limit": monthly_limit(f)}
            for f in MONTHLY_FEATURES
        },
    }
