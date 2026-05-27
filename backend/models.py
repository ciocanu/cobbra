from sqlalchemy import Column, Index, Integer, Float, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    max_hr = Column(Integer, nullable=True)
    email = Column(String, nullable=True, unique=True)
    token_version = Column(Integer, default=1, nullable=False, server_default="1")
    membership = Column(String, default="free", server_default="free", nullable=False)
    stripe_customer_id = Column(String, nullable=True, unique=True)
    subscription_start = Column(DateTime, nullable=True)
    subscription_end   = Column(DateTime, nullable=True)
    offer_token        = Column(String, nullable=True, unique=True)
    offer_expires_at   = Column(DateTime, nullable=True)
    pending_email      = Column(String, nullable=True)
    email_verify_token = Column(String, nullable=True, unique=True)
    email_verify_expires_at = Column(DateTime, nullable=True)
    # Fitness profile
    age              = Column(Integer, nullable=True)
    resting_hr       = Column(Integer, nullable=True)
    weight_kg        = Column(Float, nullable=True)
    ftp              = Column(Integer, nullable=True)  # Functional Threshold Power in watts
    experience_level = Column(String, nullable=True)  # beginner | intermediate | advanced
    bike_type        = Column(String, nullable=True)  # road | gravel | mtb | other
    # Strava integration
    strava_athlete_id       = Column(String, nullable=True)
    strava_access_token     = Column(String, nullable=True)
    strava_refresh_token    = Column(String, nullable=True)
    strava_token_expires_at = Column(DateTime, nullable=True)
    strava_last_sync_at     = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class RateAttempt(Base):
    """Persisted rate-limit log — survives server restarts."""
    __tablename__ = "rate_attempts"

    id           = Column(Integer, primary_key=True)
    ip_address   = Column(String, nullable=False)
    attempt_type = Column(String, nullable=False)   # 'login' | 'register'
    attempted_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_rate_attempts_ip_type_at", "ip_address", "attempt_type", "attempted_at"),
    )


class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    name = Column(String, nullable=False)
    date = Column(DateTime, nullable=False)
    distance_km = Column(Float, default=0)
    duration_seconds = Column(Integer, default=0)
    avg_speed_kmh = Column(Float, default=0)
    max_speed_kmh = Column(Float, default=0)
    avg_cadence_rpm = Column(Float, nullable=True)
    max_cadence_rpm = Column(Float, nullable=True)
    avg_heart_rate_bpm = Column(Float, nullable=True)
    max_heart_rate_bpm = Column(Float, nullable=True)
    elevation_gain_m = Column(Float, default=0)
    elevation_loss_m = Column(Float, default=0)
    calories = Column(Integer, nullable=True)
    avg_power_w = Column(Float, nullable=True)
    max_power_w = Column(Float, nullable=True)
    normalized_power_w = Column(Integer, nullable=True)
    tss = Column(Float, nullable=True)
    suffer_score = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    strava_id = Column(String, nullable=True, index=True)
    weather_temp_c = Column(Float, nullable=True)
    weather_wind_kmh = Column(Float, nullable=True)
    weather_desc = Column(String, nullable=True)
    ai_analysis = Column(Text, nullable=True)
    file_type = Column(String, default="gpx")
    created_at = Column(DateTime, default=datetime.utcnow)

    track_points = relationship("TrackPoint", back_populates="activity", cascade="all, delete-orphan")
    laps = relationship("Lap", back_populates="activity", cascade="all, delete-orphan")


class TrackPoint(Base):
    __tablename__ = "track_points"

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, ForeignKey("activities.id"), nullable=False)
    timestamp = Column(DateTime, nullable=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    elevation = Column(Float, nullable=True)
    speed_kmh = Column(Float, nullable=True)
    cadence_rpm = Column(Float, nullable=True)
    heart_rate_bpm = Column(Float, nullable=True)
    power_w = Column(Float, nullable=True)
    distance_m = Column(Float, nullable=True)

    activity = relationship("Activity", back_populates="track_points")


class Lap(Base):
    __tablename__ = "laps"

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, ForeignKey("activities.id"), nullable=False)
    lap_number = Column(Integer, nullable=False)
    elapsed_seconds = Column(Float, nullable=True)
    distance_m = Column(Float, nullable=True)
    avg_speed_kmh = Column(Float, nullable=True)
    avg_hr = Column(Float, nullable=True)
    avg_cadence = Column(Float, nullable=True)
    elevation_gain_m = Column(Float, nullable=True)

    activity = relationship("Activity", back_populates="laps")


class PersonalRecord(Base):
    __tablename__ = "personal_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    pr_type = Column(String, nullable=False)
    value = Column(Float, nullable=False)
    activity_id = Column(Integer, ForeignKey("activities.id"), nullable=True)
    set_at = Column(DateTime, nullable=False)


class Goal(Base):
    __tablename__ = "goals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    goal_type = Column(String, nullable=False)
    target = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Segment(Base):
    __tablename__ = "segments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    name = Column(String, nullable=False)
    start_lat = Column(Float, nullable=False)
    start_lon = Column(Float, nullable=False)
    end_lat = Column(Float, nullable=False)
    end_lon = Column(Float, nullable=False)
    distance_m = Column(Float, nullable=True)
    waypoints_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    efforts = relationship("SegmentEffort", back_populates="segment", cascade="all, delete-orphan")


class TrainingPlan(Base):
    __tablename__ = "training_plans"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    objective = Column(String, nullable=False)
    available_days = Column(Integer, nullable=False)
    training_days_json = Column(Text, nullable=True)
    event_date = Column(String, nullable=True)
    extra_notes = Column(Text, nullable=True)
    plan_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class SegmentEffort(Base):
    __tablename__ = "segment_efforts"

    id = Column(Integer, primary_key=True, index=True)
    segment_id = Column(Integer, ForeignKey("segments.id"), nullable=False)
    activity_id = Column(Integer, ForeignKey("activities.id"), nullable=False)
    elapsed_seconds = Column(Float, nullable=False)
    avg_speed_kmh = Column(Float, nullable=True)
    avg_hr = Column(Float, nullable=True)
    set_at = Column(DateTime, nullable=False)

    segment = relationship("Segment", back_populates="efforts")
