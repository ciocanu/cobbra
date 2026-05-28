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
    # Hydration & heat
    sweat_rate_ml_per_hour  = Column(Float, nullable=True)    # calibrated via sweat test
    heat_adaptation_level   = Column(String, nullable=True)   # "low" | "moderate" | "high"
    heat_rides_last_14d     = Column(Integer, default=0)
    # Power calibration (Phase B)
    calibrated_crr          = Column(Float, nullable=True)
    calibrated_cda          = Column(Float, nullable=True)
    calibration_source      = Column(String, nullable=True)
    bike_weight_kg          = Column(Float, nullable=True)
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
    # Hydration input (entered by user post-ride)
    hydration_ml = Column(Integer, nullable=True)
    # Open-Meteo extras fetched at upload
    weather_humidity_pct = Column(Float, nullable=True)
    # Durability profiling
    durability_index = Column(Float, nullable=True)
    # Indoor/outdoor classification
    ride_environment        = Column(String, nullable=True)  # "indoor" | "outdoor" | "unknown"
    ride_environment_source = Column(String, nullable=True)  # "auto_detected" | "user_override" | "strava"
    indoor_platform         = Column(String, nullable=True)  # "zwift" | "trainerroad" | "wahoo" | "mywhoosh" | "rolo" | "other"
    power_correction_factor = Column(Float, nullable=True)   # e.g. 1.08 = indoor power adjusted +8%
    hr_correction_factor    = Column(Float, nullable=True)   # e.g. 0.95 = indoor HR adjusted -5%
    corrected_tss           = Column(Float, nullable=True)   # TSS after indoor/outdoor correction
    # Adjusted decoupling (Phase A)
    decoupling_raw              = Column(Float, nullable=True)   # Coggan-style raw Pw:HR or Pa:HR drift
    decoupling_adjusted         = Column(Float, nullable=True)   # terrain+heat+hydration-corrected drift
    decoupling_components_json  = Column(Text, nullable=True)    # breakdown JSON
    decoupling_quality          = Column(String, nullable=True)  # "high" | "medium" | "low"
    decoupling_warning          = Column(String, nullable=True)  # null or human-readable caveat
    # Climb summary (Phase B)
    total_climbing_power_avg_w = Column(Float, nullable=True)
    total_climbing_wkg_avg     = Column(Float, nullable=True)
    climb_count                = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    track_points = relationship("TrackPoint", back_populates="activity", cascade="all, delete-orphan")
    laps = relationship("Lap", back_populates="activity", cascade="all, delete-orphan")
    hydration_analysis = relationship("HydrationAnalysis", back_populates="activity", uselist=False, cascade="all, delete-orphan")
    durability_analysis = relationship("DurabilityAnalysis", back_populates="activity", uselist=False, cascade="all, delete-orphan")
    climb_detections = relationship("ClimbDetection", back_populates="activity", cascade="all, delete-orphan")
    # indoor_outdoor relationship is accessed via IndoorOutdoorProfile.user_id, not per-activity


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


class HydrationAnalysis(Base):
    __tablename__ = "hydration_analyses"

    id          = Column(Integer, primary_key=True)
    activity_id = Column(Integer, ForeignKey("activities.id", ondelete="CASCADE"), unique=True, nullable=False)

    # Conditions
    avg_temperature_c  = Column(Float)
    max_temperature_c  = Column(Float, nullable=True)
    humidity_pct       = Column(Float, nullable=True)
    wind_speed_kmh     = Column(Float, nullable=True)

    # Sweat loss estimates
    estimated_sweat_rate_ml_h = Column(Float)
    estimated_total_sweat_ml  = Column(Float)

    # User intake (mirrors activity.hydration_ml, kept here for query convenience)
    reported_intake_ml = Column(Integer, nullable=True)

    # Deficit
    deficit_ml        = Column(Float, nullable=True)
    deficit_body_pct  = Column(Float, nullable=True)

    # HR impact
    estimated_hr_drift_heat_bpm         = Column(Float)
    estimated_hr_drift_dehydration_bpm  = Column(Float, nullable=True)
    estimated_performance_loss_pct      = Column(Float, nullable=True)

    # Classification
    risk_level        = Column(String)           # "low" | "moderate" | "high" | "critical"
    analysis_quality  = Column(String)           # "high" | "medium" | "low"

    # Recommendations JSON
    recommendations_json = Column(Text, nullable=True)

    activity = relationship("Activity", back_populates="hydration_analysis")


class DurabilityAnalysis(Base):
    __tablename__ = "durability_analyses"

    id          = Column(Integer, primary_key=True)
    activity_id = Column(Integer, ForeignKey("activities.id", ondelete="CASCADE"), unique=True, nullable=False)

    # Method used for the calculation
    method   = Column(String, nullable=False)   # "power" | "hr_speed" | "climbing_power"

    # Main metric
    durability_index    = Column(Float, nullable=True)   # 0-100
    durability_category = Column(String, nullable=True)  # "excellent"|"good"|"moderate"|"poor"|"very_poor"

    # Per-quarter output values
    q1_output   = Column(Float, nullable=True)
    q2_output   = Column(Float, nullable=True)
    q3_output   = Column(Float, nullable=True)
    q4_output   = Column(Float, nullable=True)
    output_unit = Column(String, nullable=True)  # "watts" | "speed_hr_ratio" | "vam"

    # Fade
    fade_rate_pct_per_hour = Column(Float, nullable=True)

    # Context
    total_work_kj      = Column(Float, nullable=True)
    tsb_at_start       = Column(Float, nullable=True)
    temperature_avg_c  = Column(Float, nullable=True)

    # Full JSON breakdown
    analysis_json = Column(Text, nullable=True)

    # Confidence
    quality        = Column(String, nullable=True)   # "high" | "medium" | "low"
    quality_reason = Column(String, nullable=True)

    activity = relationship("Activity", back_populates="durability_analysis")


class ClimbDetection(Base):
    __tablename__ = "climb_detections"

    id = Column(Integer, primary_key=True)
    activity_id = Column(Integer, ForeignKey("activities.id", ondelete="CASCADE"), nullable=False)

    # Location in ride
    start_trackpoint_idx = Column(Integer)
    end_trackpoint_idx   = Column(Integer)
    start_distance_m     = Column(Float)
    end_distance_m       = Column(Float)

    # Climb metrics
    distance_m        = Column(Float)
    elevation_gain_m  = Column(Float)
    avg_gradient_pct  = Column(Float)
    max_gradient_pct  = Column(Float)
    duration_seconds  = Column(Integer)

    # Speed & HR
    avg_speed_kmh  = Column(Float)
    avg_heart_rate = Column(Integer, nullable=True)
    max_heart_rate = Column(Integer, nullable=True)

    # VAM
    vam_m_per_hour = Column(Float)

    # Power estimation
    estimated_power_w      = Column(Float, nullable=True)
    estimated_power_low_w  = Column(Float, nullable=True)
    estimated_power_high_w = Column(Float, nullable=True)
    estimated_wkg          = Column(Float, nullable=True)
    estimation_quality     = Column(String, nullable=True)
    estimation_method      = Column(String, default="physics")

    # Pacing
    pacing_type        = Column(String, nullable=True)
    first_half_speed   = Column(Float, nullable=True)
    second_half_speed  = Column(Float, nullable=True)

    activity = relationship("Activity", back_populates="climb_detections")


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


class IndoorOutdoorProfile(Base):
    __tablename__ = "indoor_outdoor_profiles"

    id      = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)

    # Calculated gap
    power_gap_pct        = Column(Float, nullable=True)   # e.g. -10.0 = indoor 10% below outdoor
    hr_gap_bpm           = Column(Float, nullable=True)   # e.g. +7.0 = indoor 7 bpm higher
    power_gap_confidence = Column(String, nullable=True)  # "high" | "medium" | "low" | "insufficient_data"

    # Z3 reference values used for calculation
    indoor_avg_wkg_z3  = Column(Float, nullable=True)
    outdoor_avg_wkg_z3 = Column(Float, nullable=True)
    indoor_avg_hr_z3   = Column(Float, nullable=True)
    outdoor_avg_hr_z3  = Column(Float, nullable=True)

    # Ride counts used
    indoor_rides_analyzed  = Column(Integer, default=0)
    outdoor_rides_analyzed = Column(Integer, default=0)

    # Manual calibration override
    manual_power_gap_pct = Column(Float, nullable=True)
    calibration_date     = Column(DateTime, nullable=True)
    calibration_method   = Column(String, nullable=True)  # "same_route_test" | "ftp_comparison" | "manual"

    # Metadata
    last_calculated  = Column(DateTime, nullable=True)
    calculation_json = Column(Text, nullable=True)
