import json
import os
from fastapi import APIRouter, Depends
from auth import get_current_user
import anthropic
from pydantic import BaseModel

router = APIRouter()


class RideInsightRequest(BaseModel):
    ride_distance_km: float
    ride_duration_seconds: int
    ride_avg_speed_kmh: float
    ride_elevation_m: float
    ride_avg_hr: float | None = None
    ride_suffer_score: float | None = None
    ride_tsb: float | None = None          # form at time of ride (CTL − ATL)
    ride_temperature_c: float | None = None
    avg_distance_km: float | None = None   # per-ride average over last 4 complete weeks
    avg_elevation_m: float | None = None
    avg_hr_bpm: float | None = None        # avg HR over last 4 weeks (if available)


class FitnessInsightRequest(BaseModel):
    ctl: float
    atl: float
    tsb: float
    ctl_7d_ago: float | None = None
    atl_7d_ago: float | None = None


def _fallback_ride_insight(req: RideInsightRequest) -> dict:
    if req.avg_distance_km and req.avg_distance_km > 0:
        pct = ((req.ride_distance_km - req.avg_distance_km) / req.avg_distance_km) * 100
        sign = "+" if pct >= 0 else ""
        return {"insight": f"{sign}{pct:.0f}% distance vs 4-week average."}
    return {"insight": f"{req.ride_distance_km:.1f} km completed."}


def _fallback_fitness_insight(tsb: float) -> str:
    if tsb < -20:
        return "Carrying significant fatigue — prioritise easy days."
    if tsb < -5:
        return "Normal training load with moderate fatigue."
    if tsb < 5:
        return "Balanced form — solid baseline for steady work."
    return "Fresh and ready — good window for intensity."


@router.post("/ride-insight")
def get_ride_insight(req: RideInsightRequest, current_user=Depends(get_current_user)):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return _fallback_ride_insight(req)

    h = req.ride_duration_seconds // 3600
    m = (req.ride_duration_seconds % 3600) // 60

    ride_lines = [
        f"  Distance: {req.ride_distance_km:.1f} km",
        f"  Duration: {h}h {m}m",
        f"  Avg speed: {req.ride_avg_speed_kmh:.1f} km/h",
        f"  Elevation: {req.ride_elevation_m:.0f} m",
    ]
    if req.ride_avg_hr:
        ride_lines.append(f"  Avg HR: {req.ride_avg_hr:.0f} bpm")
    if req.ride_suffer_score:
        ride_lines.append(f"  Suffer score: {req.ride_suffer_score:.0f}")
    if req.ride_tsb is not None:
        ride_lines.append(f"  TSB (form): {req.ride_tsb:.0f}  (negative = carrying fatigue, positive = fresh)")
    if req.ride_temperature_c is not None:
        ride_lines.append(f"  Temperature: {req.ride_temperature_c:.0f}°C")

    avg_lines = []
    if req.avg_distance_km is not None:
        avg_lines.append(f"  Avg distance per ride: {req.avg_distance_km:.1f} km")
    if req.avg_elevation_m is not None:
        avg_lines.append(f"  Avg elevation per ride: {req.avg_elevation_m:.0f} m")
    if req.avg_hr_bpm is not None:
        avg_lines.append(f"  Avg HR per ride: {req.avg_hr_bpm:.0f} bpm")

    avg_section = ("\n\n4-WEEK PER-RIDE AVERAGES:\n" + "\n".join(avg_lines)) if avg_lines else ""

    prompt = f"""You are a cycling coach. Write ONE sentence, max 12 words, about this ride.

Rules:
- Combine: the most notable finding + the most likely reason or implication
- Use plain English. No acronyms. No filler ("it seems", "you may", "overall").
- Format: "<what happened> — <why or so what>."
- If TSB is available and negative, consider fatigue as a contributing factor.
- If temperature is high (>28°C), consider heat as a factor.
- Be specific with numbers when they strengthen the insight.

Good examples:
  "HR 8 bpm above average for this distance — TSB suggests accumulated fatigue."
  "Best pace-to-elevation ratio this month despite tired legs."
  "Speed 2 km/h below average — 200m more climbing than usual."

THIS RIDE:
{chr(10).join(ride_lines)}{avg_section}

Respond with ONLY the sentence. No quotes, no period at the end unless natural."""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            messages=[{"role": "user", "content": prompt}],
        )
        insight = msg.content[0].text.strip().strip('"\'')
        return {"insight": insight}
    except Exception:
        return _fallback_ride_insight(req)


@router.post("/fitness-insight")
def get_fitness_insight(req: FitnessInsightRequest, current_user=Depends(get_current_user)):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {"insight": _fallback_fitness_insight(req.tsb)}

    ctl_trend = ""
    if req.ctl_7d_ago is not None:
        delta = req.ctl - req.ctl_7d_ago
        ctl_trend = f"\nCTL changed {'+' if delta >= 0 else ''}{delta:.1f} over the last 7 days."

    prompt = f"""You are a cycling coach. Write ONE sentence (max 12 words) about the athlete's current training state.
Be direct. No jargon acronyms. Plain English. Action-oriented when appropriate.

CTL (Fitness, 42-day load): {req.ctl:.0f}
ATL (Fatigue, 7-day load): {req.atl:.0f}
TSB (Form = CTL minus ATL): {req.tsb:.0f}{ctl_trend}

TSB guide: below -20 = significant fatigue, -20 to -5 = training load, -5 to +5 = balanced, above +5 = fresh.

Respond with ONLY the sentence. No quotes, no explanation."""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=60,
            messages=[{"role": "user", "content": prompt}],
        )
        insight = msg.content[0].text.strip().strip('"\'')
        return {"insight": insight}
    except Exception:
        return {"insight": _fallback_fitness_insight(req.tsb)}
