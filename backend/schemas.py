from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


# ── Auth ────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    website: Optional[str] = None   # honeypot — must be empty on legitimate requests

class LoginRequest(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    membership: str = "free"
    subscription_start: Optional[datetime] = None
    subscription_end: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── Track points & activities ────────────────────────────────────────────────

class TrackPointOut(BaseModel):
    id: int
    timestamp: Optional[datetime]
    lat: Optional[float]
    lon: Optional[float]
    elevation: Optional[float]
    speed_kmh: Optional[float]
    cadence_rpm: Optional[float]
    heart_rate_bpm: Optional[float]
    power_w: Optional[float]
    distance_m: Optional[float]

    class Config:
        from_attributes = True


class LapOut(BaseModel):
    id: int
    lap_number: int
    elapsed_seconds: Optional[float]
    distance_m: Optional[float]
    avg_speed_kmh: Optional[float]
    avg_hr: Optional[float]
    avg_cadence: Optional[float]
    elevation_gain_m: Optional[float]

    class Config:
        from_attributes = True


class ActivityOut(BaseModel):
    id: int
    name: str
    date: datetime
    distance_km: float
    duration_seconds: int
    avg_speed_kmh: float
    max_speed_kmh: float
    avg_cadence_rpm: Optional[float]
    max_cadence_rpm: Optional[float]
    avg_heart_rate_bpm: Optional[float]
    max_heart_rate_bpm: Optional[float]
    elevation_gain_m: float
    elevation_loss_m: float
    calories: Optional[int]
    avg_power_w: Optional[float]
    max_power_w: Optional[float]
    suffer_score: Optional[int]
    notes: Optional[str]
    weather_temp_c: Optional[float]
    weather_wind_kmh: Optional[float]
    weather_desc: Optional[str]
    file_type: str
    created_at: datetime
    tss: Optional[float] = None
    intensity_factor: Optional[float] = None
    ride_environment:        Optional[str] = None
    ride_environment_source: Optional[str] = None
    indoor_platform:         Optional[str] = None
    power_correction_factor: Optional[float] = None
    hr_correction_factor:    Optional[float] = None
    corrected_tss:           Optional[float] = None
    decoupling_raw:             Optional[float] = None
    decoupling_adjusted:        Optional[float] = None
    decoupling_components_json: Optional[str]   = None
    decoupling_quality:         Optional[str]   = None
    decoupling_warning:         Optional[str]   = None

    class Config:
        from_attributes = True


class ActivityDetail(ActivityOut):
    track_points: List[TrackPointOut]
    laps: List[LapOut]

    class Config:
        from_attributes = True


# ── Stats ────────────────────────────────────────────────────────────────────

class StatsOut(BaseModel):
    total_activities: int
    total_distance_km: float
    total_duration_seconds: int
    total_elevation_gain_m: float
    avg_speed_kmh: float
    best_avg_speed_kmh: float
    longest_ride_km: float


# ── Personal Records ─────────────────────────────────────────────────────────

class PROut(BaseModel):
    pr_type: str
    value: float
    activity_id: Optional[int]
    set_at: datetime

    class Config:
        from_attributes = True


# ── Goals ────────────────────────────────────────────────────────────────────

class GoalIn(BaseModel):
    goal_type: str
    target: float

class GoalOut(BaseModel):
    id: int
    goal_type: str
    target: float
    created_at: datetime

    class Config:
        from_attributes = True


# ── Segments ─────────────────────────────────────────────────────────────────

class SettingsOut(BaseModel):
    max_hr: Optional[int] = None
    age: Optional[int] = None
    resting_hr: Optional[int] = None
    weight_kg: Optional[float] = None
    ftp: Optional[int] = None
    experience_level: Optional[str] = None
    bike_type: Optional[str] = None
    bike_weight_kg: Optional[float] = None
    calibrated_cda: Optional[float] = None
    calibrated_crr: Optional[float] = None
    calibration_source: Optional[str] = None

class SettingsIn(BaseModel):
    max_hr: Optional[int] = None
    age: Optional[int] = None
    resting_hr: Optional[int] = None
    weight_kg: Optional[float] = None
    ftp: Optional[int] = None
    experience_level: Optional[str] = None
    bike_type: Optional[str] = None
    bike_weight_kg: Optional[float] = None


class ClimbDetectionOut(BaseModel):
    id: int
    activity_id: int
    start_trackpoint_idx: Optional[int]
    end_trackpoint_idx: Optional[int]
    start_distance_m: Optional[float]
    end_distance_m: Optional[float]
    distance_m: Optional[float]
    elevation_gain_m: Optional[float]
    avg_gradient_pct: Optional[float]
    max_gradient_pct: Optional[float]
    duration_seconds: Optional[int]
    avg_speed_kmh: Optional[float]
    avg_heart_rate: Optional[int]
    max_heart_rate: Optional[int]
    vam_m_per_hour: Optional[float]
    estimated_power_w: Optional[float]
    estimated_power_low_w: Optional[float]
    estimated_power_high_w: Optional[float]
    estimated_wkg: Optional[float]
    estimation_quality: Optional[str]
    estimation_method: Optional[str]
    pacing_type: Optional[str]
    first_half_speed: Optional[float]
    second_half_speed: Optional[float]

    class Config:
        from_attributes = True


# ── Hydration ────────────────────────────────────────────────────────────────

class HydrationAnalysisOut(BaseModel):
    id: int
    activity_id: int
    avg_temperature_c: Optional[float]
    max_temperature_c: Optional[float]
    effective_temp_c: Optional[float]
    wind_cooling_c: Optional[float]
    humidity_pct: Optional[float]
    wind_speed_kmh: Optional[float]
    estimated_sweat_rate_ml_h: float
    population_sweat_rate_ml_h: Optional[float]
    model_method: Optional[str]
    estimated_total_sweat_ml: float
    reported_intake_ml: Optional[int]
    deficit_ml: Optional[float]
    deficit_body_pct: Optional[float]
    estimated_hr_drift_heat_bpm: float
    estimated_hr_drift_dehydration_bpm: Optional[float]
    estimated_performance_loss_pct: Optional[float]
    risk_level: str
    analysis_quality: str
    recommendations_json: Optional[str]

    class Config:
        from_attributes = True


class HeatProfileOut(BaseModel):
    heat_adaptation_level: Optional[str]
    heat_rides_last_14d: int
    sweat_rate_ml_per_hour: Optional[float]
    has_calibrated_rate: bool


class SweatTestIn(BaseModel):
    weight_before_kg: float
    weight_after_kg: float
    intake_ml_during: int
    duration_h: float


# ── Durability ────────────────────────────────────────────────────────────────

class DurabilityAnalysisOut(BaseModel):
    id: int
    activity_id: int
    method: str
    durability_index: Optional[float]
    durability_category: Optional[str]
    q1_output: Optional[float]
    q2_output: Optional[float]
    q3_output: Optional[float]
    q4_output: Optional[float]
    output_unit: Optional[str]
    fade_rate_pct_per_hour: Optional[float]
    total_work_kj: Optional[float]
    tsb_at_start: Optional[float]
    temperature_avg_c: Optional[float]
    analysis_json: Optional[str]
    quality: Optional[str]
    quality_reason: Optional[str]

    class Config:
        from_attributes = True


class DurabilityTrendOut(BaseModel):
    weekly_averages: List[dict]
    trend: str
    trend_slope: float
    current_avg: Optional[float]
    best_ever: Optional[float]
    best_ever_date: Optional[str]


class DurabilityCompareIn(BaseModel):
    activity_ids: List[int]


class DurabilityCompareOut(BaseModel):
    rides: List[dict]
    best_ride_id: Optional[int]
    comparison_note: str


# ── Indoor / Outdoor ─────────────────────────────────────────────────────────

class IndoorOutdoorProfileOut(BaseModel):
    power_gap_pct:          Optional[float]
    hr_gap_bpm:             Optional[float]
    power_gap_confidence:   Optional[str]
    indoor_avg_wkg_z3:      Optional[float]
    outdoor_avg_wkg_z3:     Optional[float]
    indoor_avg_hr_z3:       Optional[float]
    outdoor_avg_hr_z3:      Optional[float]
    indoor_rides_analyzed:  int = 0
    outdoor_rides_analyzed: int = 0
    manual_power_gap_pct:   Optional[float]
    calibration_date:       Optional[datetime]
    calibration_method:     Optional[str]
    last_calculated:        Optional[datetime]
    # Effective gap used for corrections (manual overrides calculated)
    effective_power_gap_pct: Optional[float] = None

    class Config:
        from_attributes = True


class CalibrateIn(BaseModel):
    method: str                                # "ftp_comparison" | "dual_test"
    indoor_ftp: Optional[float]  = None        # for ftp_comparison
    outdoor_ftp: Optional[float] = None        # for ftp_comparison
    indoor_activity_id:  Optional[int] = None  # for dual_test
    outdoor_activity_id: Optional[int] = None  # for dual_test


class CalibrateOut(BaseModel):
    power_gap_pct:         Optional[float]
    hr_gap_bpm:            Optional[float]
    indoor_ftp_estimated:  Optional[float]
    outdoor_ftp_estimated: Optional[float]
    interpretation:        str
    recommendation:        str


class EnvironmentOverrideIn(BaseModel):
    environment: str               # "indoor" | "outdoor" | "unknown"
    platform:    Optional[str] = None  # "zwift" | "trainerroad" | …


class TrainingLoadComparisonOut(BaseModel):
    original:   dict
    corrected:  dict
    difference: dict


class SegmentIn(BaseModel):
    name: str
    waypoints: List[List[float]]  # [[lat, lon], ...] — minimum 2 points

class SegmentEffortOut(BaseModel):
    id: int
    segment_id: int
    activity_id: int
    elapsed_seconds: float
    avg_speed_kmh: Optional[float]
    avg_hr: Optional[float]
    set_at: datetime

    class Config:
        from_attributes = True
