"""Shared DB-backed rate limiting used by auth and upload routes."""

import random
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

import models

# (window_seconds, max_attempts, error_message)
_LIMITS: dict[str, tuple[int, int, str]] = {
    "login":    (300,  10, "Too many login attempts. Try again in 5 minutes."),
    "register": (3600,  5, "Too many registration attempts. Try again later."),
    "upload":   (3600, 30, "Upload limit reached (30 per hour). Try again later."),
    "demo":     (300,  20, "Too many demo sign-ins. Try again in 5 minutes."),
}


def check_rate_limit(ip: str, attempt_type: str, db: Session) -> None:
    """Raise HTTP 429 if ip has exceeded the rate limit for attempt_type."""
    window_secs, max_attempts, retry_msg = _LIMITS[attempt_type]
    window_start = datetime.utcnow() - timedelta(seconds=window_secs)

    count = (
        db.query(models.RateAttempt)
        .filter(
            models.RateAttempt.ip_address == ip,
            models.RateAttempt.attempt_type == attempt_type,
            models.RateAttempt.attempted_at >= window_start,
        )
        .count()
    )

    if count >= max_attempts:
        raise HTTPException(status_code=429, detail=retry_msg)

    db.add(models.RateAttempt(ip_address=ip, attempt_type=attempt_type))
    db.commit()

    # Probabilistic cleanup — 5% chance per request; avoids a background thread
    if random.random() < 0.05:
        cutoff = datetime.utcnow() - timedelta(hours=2)
        db.query(models.RateAttempt).filter(models.RateAttempt.attempted_at < cutoff).delete()
        db.commit()
