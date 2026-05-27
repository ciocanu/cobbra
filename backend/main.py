import os
from dotenv import load_dotenv
load_dotenv()  # must run before any module that reads os.getenv at import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from sqlalchemy import text
from database import engine
import models
from routes import activities, stats, auth, records, heatmap, goals, segments, settings, analysis, training, admin, payments, strava, dashboard


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
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

app = FastAPI(title="Cycling Tracker API", version="2.0.0")

app.add_middleware(SecurityHeadersMiddleware)

origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
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
app.include_router(payments.router,   prefix="/api/payments",   tags=["payments"])
app.include_router(strava.router,     prefix="/api/strava",     tags=["strava"])
app.include_router(dashboard.router,  prefix="/api/dashboard",  tags=["dashboard"])


@app.get("/health")
def health():
    return {"status": "ok"}
