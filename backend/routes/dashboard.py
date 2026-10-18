import time
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from auth import get_current_user
from database import get_db
import anthropic
from pydantic import BaseModel
from utils.ai_budget import HAIKU, allow_light_call, api_key, record_usage

router = APIRouter()

# Insights only call the API when the user asks (use_ai); identical prompts are
# answered from memory instead of calling the API again.
_CACHE_TTL_S = 12 * 3600
_CACHE_MAX = 2000
_insight_cache: dict[str, tuple[float, str]] = {}


def _cached_insight(prompt: str) -> str | None:
    hit = _insight_cache.get(prompt)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    return None


def _store_insight(prompt: str, insight: str) -> None:
    if len(_insight_cache) >= _CACHE_MAX:
        now = time.monotonic()
        for key in [k for k, (exp, _) in _insight_cache.items() if exp <= now]:
            del _insight_cache[key]
        if len(_insight_cache) >= _CACHE_MAX:
            _insight_cache.clear()
    _insight_cache[prompt] = (time.monotonic() + _CACHE_TTL_S, insight)


def _one_line_insight(db: Session, user, feature: str, prompt: str, max_tokens: int) -> str | None:
    """Cached, budget-checked one-sentence insight; None means use the fallback text."""
    cached = _cached_insight(prompt)
    if cached is not None:
        return cached
    if not allow_light_call(db, user, feature):
        return None
    try:
        client = anthropic.Anthropic(api_key=api_key())
        msg = client.messages.create(
            model=HAIKU,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        return None
    record_usage(db, user.id, feature, HAIKU, msg.usage)
    insight = msg.content[0].text.strip().strip('"\'')
    _store_insight(prompt, insight)
    return insight


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
    lang: str = "en"
    use_ai: bool = False                   # only when the user asks (privacy policy: consent by click)


class FitnessInsightRequest(BaseModel):
    ctl: float
    atl: float
    tsb: float
    ctl_7d_ago: float | None = None
    atl_7d_ago: float | None = None
    lang: str = "en"
    use_ai: bool = False                   # only when the user asks (privacy policy: consent by click)


def _fallback_ride_insight(req: RideInsightRequest) -> dict:
    pt = req.lang.startswith("pt")
    if req.avg_distance_km and req.avg_distance_km > 0:
        pct = ((req.ride_distance_km - req.avg_distance_km) / req.avg_distance_km) * 100
        sign = "+" if pct >= 0 else ""
        if pt:
            return {"insight": f"{sign}{pct:.0f}% da distância vs média das últimas 4 semanas."}
        return {"insight": f"{sign}{pct:.0f}% distance vs 4-week average."}
    if pt:
        return {"insight": f"{req.ride_distance_km:.1f} km concluídos."}
    return {"insight": f"{req.ride_distance_km:.1f} km completed."}


def _fallback_fitness_insight(tsb: float, lang: str = "en") -> str:
    pt = lang.startswith("pt")
    if tsb < -20:
        return "Fadiga significativa acumulada — prioriza dias fáceis." if pt else "Carrying significant fatigue — prioritise easy days."
    if tsb < -5:
        return "Carga de treino normal com fadiga moderada." if pt else "Normal training load with moderate fatigue."
    if tsb < 5:
        return "Forma equilibrada — boa base para trabalho consistente." if pt else "Balanced form — solid baseline for steady work."
    return "Descansado e pronto — bom momento para intensidade." if pt else "Fresh and ready — good window for intensity."


@router.post("/ride-insight")
def get_ride_insight(req: RideInsightRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if not req.use_ai:
        return _fallback_ride_insight(req)
    lang_instruction = "Write in European Portuguese (PT-PT)." if req.lang.startswith("pt") else "Write in English."

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

    prompt = f"""You are a cycling coach. {lang_instruction} Write ONE sentence, max 12 words, about this ride.

Rules:
- Combine: the most notable finding + the most likely reason or implication
- No acronyms. No filler ("it seems", "you may", "overall").
- Format: "<what happened> — <why or so what>."
- If TSB is available and negative, consider fatigue as a contributing factor.
- If temperature is high (>28°C), consider heat as a factor.
- Be specific with numbers when they strengthen the insight.

THIS RIDE:
{chr(10).join(ride_lines)}{avg_section}

Respond with ONLY the sentence. No quotes, no period at the end unless natural."""

    insight = _one_line_insight(db, current_user, "ride_insight", prompt, max_tokens=80)
    return {"insight": insight} if insight else _fallback_ride_insight(req)


@router.post("/fitness-insight")
def get_fitness_insight(req: FitnessInsightRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if not req.use_ai:
        return {"insight": _fallback_fitness_insight(req.tsb, req.lang)}
    lang_instruction = "Write in European Portuguese (PT-PT)." if req.lang.startswith("pt") else "Write in English."

    ctl_trend = ""
    if req.ctl_7d_ago is not None:
        delta = req.ctl - req.ctl_7d_ago
        ctl_trend = f"\nCTL changed {'+' if delta >= 0 else ''}{delta:.1f} over the last 7 days."

    prompt = f"""You are a cycling coach. {lang_instruction} Write ONE sentence (max 12 words) about the athlete's current training state.
Be direct. No jargon acronyms. Action-oriented when appropriate.

CTL (Fitness, 42-day load): {req.ctl:.0f}
ATL (Fatigue, 7-day load): {req.atl:.0f}
TSB (Form = CTL minus ATL): {req.tsb:.0f}{ctl_trend}

TSB guide: below -20 = significant fatigue, -20 to -5 = training load, -5 to +5 = balanced, above +5 = fresh.

Respond with ONLY the sentence. No quotes, no explanation."""

    insight = _one_line_insight(db, current_user, "fitness_insight", prompt, max_tokens=60)
    return {"insight": insight or _fallback_fitness_insight(req.tsb, req.lang)}
