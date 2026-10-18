import logging
import logging.config
import os
import sys

from dotenv import load_dotenv
load_dotenv()  # must run before any module that reads os.getenv at import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from database import engine, _is_sqlite, get_db
import models
from utils.access import payments_enabled
from utils.ai_budget import ai_available
from routes import activities, stats, auth, records, heatmap, goals, segments, settings, analysis, training, admin, payments, strava, dashboard, hydration, durability, indoor_outdoor, climbs, contact


# ── Logging ───────────────────────────────────────────────────────────────────

def _configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s %(levelname)-8s %(name)s  %(message)s",
                "datefmt": "%Y-%m-%dT%H:%M:%S",
            },
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "default",
            },
        },
        "root": {"level": level, "handlers": ["stdout"]},
        "loggers": {
            # Suppress chatty libraries — only show warnings and above
            "httpx":      {"level": "WARNING", "propagate": True},
            "httpcore":   {"level": "WARNING", "propagate": True},
            "anthropic":  {"level": "WARNING", "propagate": True},
            "stripe":     {"level": "WARNING", "propagate": True},
            "passlib":    {"level": "WARNING", "propagate": True},
        },
    })

_configure_logging()
log = logging.getLogger(__name__)


# ── Startup validation ────────────────────────────────────────────────────────

def _validate_env() -> None:
    """Fail fast on missing critical env vars; warn on disabled optional features."""
    fatal: list[str] = []
    warnings: list[str] = []

    if not os.getenv("SECRET_KEY"):
        fatal.append(
            "SECRET_KEY is required. "
            "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    db_url = os.getenv("DATABASE_URL", "sqlite:///./cycling.db")
    is_production = os.getenv("COOKIE_SECURE", "false").lower() == "true"

    if is_production and db_url.startswith("sqlite"):
        fatal.append(
            "DATABASE_URL must point to PostgreSQL when COOKIE_SECURE=true. "
            "SQLite is not suitable for production (no concurrent writers, no network access)."
        )

    if not os.getenv("ADMIN_USERNAME"):
        warnings.append("ADMIN_USERNAME not set — admin panel will be inaccessible")
    if not os.getenv("ANTHROPIC_API_KEY"):
        warnings.append("ANTHROPIC_API_KEY not set — AI analysis, training plans, and moderation disabled")
    if payments_enabled() and not os.getenv("STRIPE_SECRET_KEY"):
        warnings.append("PAYMENTS_ENABLED=true but STRIPE_SECRET_KEY not set — payment checkout disabled")
    if not payments_enabled():
        log.info("Payments disabled (PAYMENTS_ENABLED unset) — every account gets every feature")
    if not os.getenv("SMTP_HOST"):
        warnings.append("SMTP_HOST not set — email (verification, lifetime offer) disabled")

    cors = os.getenv("CORS_ORIGINS", "")
    if is_production and "localhost" in cors:
        warnings.append(
            "CORS_ORIGINS contains 'localhost' but COOKIE_SECURE=true — "
            "remove localhost origins before deploying to production"
        )

    for w in warnings:
        log.warning("Config: %s", w)

    if fatal:
        for msg in fatal:
            log.critical("Startup aborted: %s", msg)
        sys.exit(1)

_validate_env()


# ── Security headers middleware ───────────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        h = response.headers
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["X-XSS-Protection"] = "1; mode=block"
        h["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # HSTS — tells browsers to use HTTPS for the next 2 years.
        # Nginx also emits this header; having it here is defence-in-depth for
        # environments where the app is accessed directly (health checks, staging).
        h["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        # Tight CSP for API-only (JSON) responses — no resources need to load.
        # The SPA HTML CSP is set in nginx/nginx.conf at the server level.
        h["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        )
        return response

models.Base.metadata.create_all(bind=engine)

# Run safe migrations for columns added after initial setup
_MIGRATIONS = [
    "ALTER TABLE activities ADD COLUMN avg_power_w FLOAT",
    "ALTER TABLE activities ADD COLUMN max_power_w FLOAT",
    "ALTER TABLE activities ADD COLUMN suffer_score INTEGER",
    "ALTER TABLE track_points ADD COLUMN power_w FLOAT",
    "ALTER TABLE activities ADD COLUMN notes TEXT",
    "ALTER TABLE activities ADD COLUMN weather_temp_c FLOAT",
    "ALTER TABLE activities ADD COLUMN weather_wind_kmh FLOAT",
    "ALTER TABLE activities ADD COLUMN weather_desc VARCHAR",
    "ALTER TABLE users ADD COLUMN max_hr INTEGER",
    "ALTER TABLE segments ADD COLUMN waypoints_json TEXT",
    "ALTER TABLE activities ADD COLUMN ai_analysis TEXT",
    "ALTER TABLE training_plans ADD COLUMN training_days_json TEXT",
    # Multi-user: per-user ownership columns
    "ALTER TABLE activities ADD COLUMN user_id INTEGER REFERENCES users(id)",
    "ALTER TABLE personal_records ADD COLUMN user_id INTEGER REFERENCES users(id)",
    "ALTER TABLE goals ADD COLUMN user_id INTEGER REFERENCES users(id)",
    "ALTER TABLE segments ADD COLUMN user_id INTEGER REFERENCES users(id)",
    # Token revocation support
    "ALTER TABLE users ADD COLUMN token_version INTEGER DEFAULT 1",
    # Membership tier
    "ALTER TABLE users ADD COLUMN membership VARCHAR DEFAULT 'free'",
    # Email for notifications
    "ALTER TABLE users ADD COLUMN email VARCHAR",
    # Stripe & subscription tracking
    "ALTER TABLE users ADD COLUMN stripe_customer_id VARCHAR",
    "ALTER TABLE users ADD COLUMN subscription_start DATETIME",
    "ALTER TABLE users ADD COLUMN subscription_end DATETIME",
    # Lifetime invite offer
    "ALTER TABLE users ADD COLUMN offer_token VARCHAR",
    "ALTER TABLE users ADD COLUMN offer_expires_at DATETIME",
    # Email verification
    "ALTER TABLE users ADD COLUMN pending_email VARCHAR",
    "ALTER TABLE users ADD COLUMN email_verify_token VARCHAR",
    "ALTER TABLE users ADD COLUMN email_verify_expires_at DATETIME",
    # Fitness profile
    "ALTER TABLE users ADD COLUMN age INTEGER",
    "ALTER TABLE users ADD COLUMN resting_hr INTEGER",
    "ALTER TABLE users ADD COLUMN weight_kg FLOAT",
    "ALTER TABLE users ADD COLUMN experience_level VARCHAR",
    "ALTER TABLE users ADD COLUMN bike_type VARCHAR",
    "ALTER TABLE users ADD COLUMN ftp INTEGER",
    "ALTER TABLE activities ADD COLUMN normalized_power_w INTEGER",
    "ALTER TABLE activities ADD COLUMN tss FLOAT",
    # Strava integration
    "ALTER TABLE users ADD COLUMN strava_athlete_id VARCHAR",
    "ALTER TABLE users ADD COLUMN strava_access_token VARCHAR",
    "ALTER TABLE users ADD COLUMN strava_refresh_token VARCHAR",
    "ALTER TABLE users ADD COLUMN strava_token_expires_at DATETIME",
    "ALTER TABLE users ADD COLUMN strava_last_sync_at DATETIME",
    "ALTER TABLE activities ADD COLUMN strava_id VARCHAR",
    # Hydration & heat — Activity
    "ALTER TABLE activities ADD COLUMN hydration_ml INTEGER",
    "ALTER TABLE activities ADD COLUMN weather_humidity_pct FLOAT",
    # Sensor temperature from activity file (atemp/temperature field — more accurate than weather API)
    "ALTER TABLE activities ADD COLUMN sensor_temp_avg_c FLOAT",
    "ALTER TABLE activities ADD COLUMN sensor_temp_max_c FLOAT",
    # Wall-clock elapsed time for FIT files (duration_seconds is moving/timer time)
    "ALTER TABLE activities ADD COLUMN elapsed_seconds INTEGER",
    # Hydration analysis accuracy engine v2 columns
    "ALTER TABLE hydration_analyses ADD COLUMN effective_temp_c FLOAT",
    "ALTER TABLE hydration_analyses ADD COLUMN wind_cooling_c FLOAT",
    "ALTER TABLE hydration_analyses ADD COLUMN population_sweat_rate_ml_h FLOAT",
    "ALTER TABLE hydration_analyses ADD COLUMN model_method VARCHAR",
    # Hydration & heat — User
    "ALTER TABLE users ADD COLUMN sweat_rate_ml_per_hour FLOAT",
    "ALTER TABLE users ADD COLUMN heat_adaptation_level VARCHAR",
    "ALTER TABLE users ADD COLUMN heat_rides_last_14d INTEGER DEFAULT 0",
    # hydration_analyses table
    """CREATE TABLE IF NOT EXISTS hydration_analyses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        activity_id INTEGER NOT NULL UNIQUE REFERENCES activities(id) ON DELETE CASCADE,
        avg_temperature_c FLOAT,
        max_temperature_c FLOAT,
        humidity_pct FLOAT,
        wind_speed_kmh FLOAT,
        estimated_sweat_rate_ml_h FLOAT,
        estimated_total_sweat_ml FLOAT,
        reported_intake_ml INTEGER,
        deficit_ml FLOAT,
        deficit_body_pct FLOAT,
        estimated_hr_drift_heat_bpm FLOAT,
        estimated_hr_drift_dehydration_bpm FLOAT,
        estimated_performance_loss_pct FLOAT,
        risk_level VARCHAR,
        analysis_quality VARCHAR,
        recommendations_json TEXT
    )""",
    # Durability profiling — Activity field
    "ALTER TABLE activities ADD COLUMN durability_index FLOAT",
    # Durability profiling — analysis table
    """CREATE TABLE IF NOT EXISTS durability_analyses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        activity_id INTEGER NOT NULL UNIQUE REFERENCES activities(id) ON DELETE CASCADE,
        method VARCHAR NOT NULL,
        durability_index FLOAT,
        durability_category VARCHAR,
        q1_output FLOAT,
        q2_output FLOAT,
        q3_output FLOAT,
        q4_output FLOAT,
        output_unit VARCHAR,
        fade_rate_pct_per_hour FLOAT,
        total_work_kj FLOAT,
        tsb_at_start FLOAT,
        temperature_avg_c FLOAT,
        analysis_json TEXT,
        quality VARCHAR,
        quality_reason VARCHAR
    )""",
    # Indoor/outdoor reconciliation — activity columns
    "ALTER TABLE activities ADD COLUMN ride_environment VARCHAR",
    "ALTER TABLE activities ADD COLUMN ride_environment_source VARCHAR",
    "ALTER TABLE activities ADD COLUMN indoor_platform VARCHAR",
    "ALTER TABLE activities ADD COLUMN power_correction_factor FLOAT",
    "ALTER TABLE activities ADD COLUMN hr_correction_factor FLOAT",
    "ALTER TABLE activities ADD COLUMN corrected_tss FLOAT",
    # Indoor/outdoor reconciliation — per-user profile table
    """CREATE TABLE IF NOT EXISTS indoor_outdoor_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
        power_gap_pct FLOAT,
        hr_gap_bpm FLOAT,
        power_gap_confidence VARCHAR,
        indoor_avg_wkg_z3 FLOAT,
        outdoor_avg_wkg_z3 FLOAT,
        indoor_avg_hr_z3 FLOAT,
        outdoor_avg_hr_z3 FLOAT,
        indoor_rides_analyzed INTEGER DEFAULT 0,
        outdoor_rides_analyzed INTEGER DEFAULT 0,
        manual_power_gap_pct FLOAT,
        calibration_date DATETIME,
        calibration_method VARCHAR,
        last_calculated DATETIME,
        calculation_json TEXT
    )""",
    # Climb summary on Activity (Phase B)
    "ALTER TABLE activities ADD COLUMN total_climbing_power_avg_w FLOAT",
    "ALTER TABLE activities ADD COLUMN total_climbing_wkg_avg FLOAT",
    "ALTER TABLE activities ADD COLUMN climb_count INTEGER DEFAULT 0",
    # Power calibration on User (Phase B)
    "ALTER TABLE users ADD COLUMN calibrated_crr FLOAT",
    "ALTER TABLE users ADD COLUMN calibrated_cda FLOAT",
    "ALTER TABLE users ADD COLUMN calibration_source VARCHAR",
    "ALTER TABLE users ADD COLUMN bike_weight_kg FLOAT",
    # climb_detections table (Phase B)
    """CREATE TABLE IF NOT EXISTS climb_detections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
        start_trackpoint_idx INTEGER,
        end_trackpoint_idx INTEGER,
        start_distance_m FLOAT,
        end_distance_m FLOAT,
        distance_m FLOAT,
        elevation_gain_m FLOAT,
        avg_gradient_pct FLOAT,
        max_gradient_pct FLOAT,
        duration_seconds INTEGER,
        avg_speed_kmh FLOAT,
        avg_heart_rate INTEGER,
        max_heart_rate INTEGER,
        vam_m_per_hour FLOAT,
        estimated_power_w FLOAT,
        estimated_power_low_w FLOAT,
        estimated_power_high_w FLOAT,
        estimated_wkg FLOAT,
        estimation_quality VARCHAR,
        estimation_method VARCHAR DEFAULT 'physics',
        pacing_type VARCHAR,
        first_half_speed FLOAT,
        second_half_speed FLOAT
    )""",
    # Onboarding: track whether max HR came from the user or was auto-estimated
    "ALTER TABLE users ADD COLUMN max_hr_source VARCHAR",
    # Shared read-only demo account
    "ALTER TABLE users ADD COLUMN is_demo BOOLEAN NOT NULL DEFAULT 0",
]

# Assign all legacy (pre-multi-user) records to user id=1
_DATA_MIGRATIONS = [
    "UPDATE activities SET user_id = 1 WHERE user_id IS NULL",
    "UPDATE personal_records SET user_id = 1 WHERE user_id IS NULL",
    "UPDATE goals SET user_id = 1 WHERE user_id IS NULL",
    "UPDATE segments SET user_id = 1 WHERE user_id IS NULL",
    # Recompute avg cadence excluding zeros (coasting / downhill)
    """
    UPDATE activities SET avg_cadence_rpm = (
        SELECT ROUND(AVG(cadence_rpm), 1)
        FROM track_points
        WHERE track_points.activity_id = activities.id
          AND cadence_rpm IS NOT NULL
          AND cadence_rpm > 0
    ) WHERE EXISTS (
        SELECT 1 FROM track_points
        WHERE track_points.activity_id = activities.id
          AND cadence_rpm IS NOT NULL
          AND cadence_rpm > 0
    )
    """,
]

# training_plans table is created automatically by SQLAlchemy above

# SQLite-only migration shims: add columns that were introduced after the
# initial schema.  On PostgreSQL (and any fresh database) these are skipped
# entirely — create_all() above already emits the full correct schema via
# SQLAlchemy's dialect-aware DDL generator.
if _is_sqlite:
    with engine.connect() as _conn:
        for _sql in _MIGRATIONS:
            try:
                _conn.execute(text(_sql))
                _conn.commit()
            except Exception:
                pass
        for _sql in _DATA_MIGRATIONS:
            try:
                _conn.execute(text(_sql))
                _conn.commit()
            except Exception:
                pass

_is_production = os.getenv("COOKIE_SECURE", "false").lower() == "true"

app = FastAPI(
    title="Cobbra API",
    version="2.0.0",
    # Hide interactive docs in production — they expose the full API surface
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)

log.info("Starting Cobbra API (production=%s)", _is_production)

app.add_middleware(SecurityHeadersMiddleware)

_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",") if o.strip()]
log.info("CORS allowed origins: %s", _cors_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,       prefix="/api/auth",       tags=["auth"])
app.include_router(activities.router, prefix="/api/activities", tags=["activities"])
app.include_router(stats.router,      prefix="/api/stats",      tags=["stats"])
app.include_router(records.router,    prefix="/api/records",    tags=["records"])
app.include_router(heatmap.router,    prefix="/api/heatmap",    tags=["heatmap"])
app.include_router(goals.router,      prefix="/api/goals",      tags=["goals"])
app.include_router(segments.router,   prefix="/api/segments",   tags=["segments"])
app.include_router(settings.router,   prefix="/api/settings",   tags=["settings"])
app.include_router(analysis.router,   prefix="/api/activities", tags=["analysis"])
app.include_router(training.router,   prefix="/api/training",   tags=["training"])
app.include_router(admin.router,      prefix="/api/admin",      tags=["admin"])
if payments_enabled():
    app.include_router(payments.router, prefix="/api/payments", tags=["payments"])
app.include_router(strava.router,     prefix="/api/strava",     tags=["strava"])
app.include_router(dashboard.router,  prefix="/api/dashboard",  tags=["dashboard"])
app.include_router(hydration.router,      prefix="/api",  tags=["hydration"])
app.include_router(durability.router,     prefix="/api",  tags=["durability"])
app.include_router(indoor_outdoor.router, prefix="/api",  tags=["indoor_outdoor"])
app.include_router(climbs.router,         prefix="/api",  tags=["climbs"])
app.include_router(contact.router,        prefix="/api",  tags=["contact"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/config")
def public_config(db: Session = Depends(get_db)):
    """What this instance offers, so the frontend can hide what is switched off."""
    return {
        "payments_enabled": payments_enabled(),
        "demo_available": db.query(models.User.id).filter(models.User.is_demo.is_(True)).first() is not None,
        "ai_available": ai_available(db),
    }
