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

class SettingsIn(BaseModel):
    max_hr: Optional[int] = None
    age: Optional[int] = None
    resting_hr: Optional[int] = None
    weight_kg: Optional[float] = None
    ftp: Optional[int] = None
    experience_level: Optional[str] = None
    bike_type: Optional[str] = None


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
