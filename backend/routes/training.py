import json
from datetime import date, timedelta, datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from database import get_db
from auth import get_current_user
import models
import anthropic
from utils.access import has_full_access
from utils.ai_budget import SONNET, api_key, check_quota, monthly_limit, record_usage, unavailable_reason

router = APIRouter()

ALL_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class PlanRequest(BaseModel):
    objective: str
    training_days: List[str]   # e.g. ["Monday", "Wednesday", "Friday"]
    event_date: Optional[str] = None
    extra_notes: Optional[str] = None
    lang: Optional[str] = "en"


def _next_generation_date(plan_date: datetime) -> str:
    """First day of the month after plan_date."""
    if plan_date.month == 12:
        return date(plan_date.year + 1, 1, 1).isoformat()
    return date(plan_date.year, plan_date.month + 1, 1).isoformat()


def _plans_this_month(db: Session, user_id: int) -> int:
    today = date.today()
    return (
        db.query(models.TrainingPlan)
        .filter(
            models.TrainingPlan.user_id == user_id,
            models.TrainingPlan.created_at >= date(today.year, today.month, 1),
        )
        .count()
    )



def _build_prompt(request: PlanRequest, user: models.User, db: Session) -> str:
    # ── Last 8 weeks of rides ─────────────────────────────────────────────────
    eight_weeks_ago = datetime.utcnow() - timedelta(weeks=8)
    activities = (
        db.query(models.Activity)
        .filter(models.Activity.user_id == user.id, models.Activity.date >= eight_weeks_ago)
        .order_by(models.Activity.date)
        .all()
    )

    # Weekly summaries
    weekly: dict[str, dict] = {}
    for a in activities:
        week_start = (a.date.date() - timedelta(days=a.date.weekday())).isoformat()
        if week_start not in weekly:
            weekly[week_start] = {"rides": 0, "distance_km": 0.0, "elevation_m": 0.0,
                                   "duration_s": 0, "suffer": 0}
        weekly[week_start]["rides"] += 1
        weekly[week_start]["distance_km"] += a.distance_km
        weekly[week_start]["elevation_m"] += a.elevation_gain_m
        weekly[week_start]["duration_s"] += a.duration_seconds
        weekly[week_start]["suffer"] += a.suffer_score or 0

    n_weeks = max(len(weekly), 1)
    avg_weekly_km    = sum(w["distance_km"] for w in weekly.values()) / n_weeks
    avg_weekly_elev  = sum(w["elevation_m"]  for w in weekly.values()) / n_weeks
    avg_weekly_suffer = sum(w["suffer"]      for w in weekly.values()) / n_weeks
    total_rides      = sum(w["rides"]        for w in weekly.values())

    # ── Phase 2: Richer single-ride stats ────────────────────────────────────
    n_act = max(len(activities), 1)

    longest_ride_km  = max((a.distance_km        for a in activities), default=0.0)
    longest_ride_min = max((a.duration_seconds    for a in activities), default=0) // 60
    avg_ride_km      = sum(a.distance_km          for a in activities) / n_act
    avg_ride_min     = (sum(a.duration_seconds    for a in activities) // n_act) // 60

    # Effort distribution by suffer score bands
    easy     = sum(1 for a in activities if (a.suffer_score or 0) < 20)
    moderate = sum(1 for a in activities if 20 <= (a.suffer_score or 0) <= 50)
    hard     = sum(1 for a in activities if (a.suffer_score or 0) > 50)
    effort_pct = (
        f"Easy {easy * 100 // n_act}%  /  Moderate {moderate * 100 // n_act}%  /  Hard {hard * 100 // n_act}%"
        if activities else "No data"
    )

    # 8-week load trend — linear regression slope (km/week)
    sorted_week_keys = sorted(weekly.keys())
    km_series = [weekly[w]["distance_km"] for w in sorted_week_keys]
    trend_str = "Insufficient data (fewer than 3 weeks)"
    if len(km_series) >= 3:
        n = len(km_series)
        xs = list(range(n))
        sx, sy = sum(xs), sum(km_series)
        sxy = sum(x * y for x, y in zip(xs, km_series))
        sxx = sum(x * x for x in xs)
        denom = n * sxx - sx * sx
        if denom:
            slope = (n * sxy - sx * sy) / denom
            if slope > 2:
                trend_str = f"Improving  (+{slope:.1f} km/week)"
            elif slope < -2:
                trend_str = f"Declining  ({slope:.1f} km/week)"
            else:
                trend_str = f"Stable  ({slope:+.1f} km/week)"

    # ── Current fitness (CTL/ATL/TSB) ────────────────────────────────────────
    all_activities = (
        db.query(models.Activity)
        .filter(models.Activity.user_id == user.id)
        .order_by(models.Activity.date)
        .all()
    )
    daily_load: dict[date, float] = {}
    for a in all_activities:
        d = a.date.date()
        daily_load[d] = daily_load.get(d, 0) + (a.suffer_score or 0)

    today = date.today()
    ctl, atl = 0.0, 0.0
    cur = today - timedelta(days=84)
    while cur <= today:
        load = daily_load.get(cur, 0)
        ctl += (load - ctl) / 42
        atl += (load - atl) / 7
        cur += timedelta(days=1)
    tsb = ctl - atl

    # ── Phase 3: Server-side HR zone calculation ──────────────────────────────
    _ZONE_DEFS = [
        ("Z1 Recovery",  0.50, 0.60),
        ("Z2 Endurance", 0.60, 0.70),
        ("Z3 Tempo",     0.70, 0.80),
        ("Z4 Threshold", 0.80, 0.90),
        ("Z5 VO2 Max",   0.90, 1.00),
    ]
    max_hr    = user.max_hr
    resting_hr = user.resting_hr
    hr_zone_lines: list[str] = []
    hr_method = None

    if max_hr:
        if resting_hr:
            hrr = max_hr - resting_hr
            hr_method = f"Karvonen / heart rate reserve  (max {max_hr} bpm, resting {resting_hr} bpm)"
            for name, lo, hi in _ZONE_DEFS:
                hr_zone_lines.append(f"  {name}: {round(resting_hr + hrr * lo)}–{round(resting_hr + hrr * hi)} bpm")
        else:
            hr_method = f"% of max HR  (max {max_hr} bpm)"
            for name, lo, hi in _ZONE_DEFS:
                hr_zone_lines.append(f"  {name}: {round(max_hr * lo)}–{round(max_hr * hi)} bpm")

    # ── PRs ──────────────────────────────────────────────────────────────────
    prs = db.query(models.PersonalRecord).filter(models.PersonalRecord.user_id == user.id).all()
    pr_lines = []
    label_map = {
        "fastest_400m": "400m", "fastest_1km": "1km", "fastest_5km": "5km",
        "fastest_10km": "10km", "fastest_20km": "20km", "fastest_40km": "40km",
    }
    for pr in prs:
        label = label_map.get(pr.pr_type, pr.pr_type)
        secs = int(pr.value)
        m, s = divmod(secs, 60)
        h, m = divmod(m, 60)
        t = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
        pr_lines.append(f"  {label}: {t}")

    # ── Phase 4: Build prompt ─────────────────────────────────────────────────
    day_order   = {d: i for i, d in enumerate(ALL_DAYS)}
    sorted_days = sorted(request.training_days, key=lambda d: day_order.get(d, 99))
    rest_days   = [d for d in ALL_DAYS if d not in request.training_days]

    # Hard caps derived from actual rider data
    session_cap_min = (longest_ride_min + 20) if longest_ride_min > 0 else None
    week1_cap_km    = (avg_weekly_km * 1.05)  if avg_weekly_km  > 0 else None

    lang = request.lang or "en"
    lang_instruction = (
        "Write entirely in European Portuguese (Portugal). Use natural PT-PT phrasing."
        if lang.startswith("pt") else
        "Write entirely in English."
    )

    lines: list[str] = [
        f"You are an expert cycling coach. {lang_instruction} Create a personalised 4-week training plan for the rider below.",
        "",
        "══════════════════════════════════════════════════════════",
        "ANTI-HALLUCINATION RULES — read before generating anything",
        "══════════════════════════════════════════════════════════",
        "1. Every session duration and distance MUST be grounded in the rider's actual recent ride data.",
        "   If the rider's longest recent ride is 60 min, do not suggest 90-min sessions.",
        "2. Use ONLY the pre-computed HR zone ranges provided in this prompt.",
        "   Do NOT recalculate, adjust, or invent bpm values.",
        "3. If you are uncertain about any value, use the rider's actual data as the reference.",
        "   Do not generate plausible-sounding numbers that are not grounded in the data provided.",
        "4. The 80/20 rule is non-negotiable: 80% of sessions per week must be Z1/Z2 (easy aerobic).",
        "",
        "══════════════════════════════════════════════════════════",
        "HARD CONSTRAINTS — never violate these",
        "══════════════════════════════════════════════════════════",
    ]

    if session_cap_min:
        lines.append(f"• Maximum single session length: {session_cap_min} min  (rider's longest recent ride + 20 min buffer)")
    if week1_cap_km:
        lines.append(f"• Week 1 total distance cap: {week1_cap_km:.0f} km  (rider's current weekly average × 1.05)")
    lines += [
        "• Weekly load increase: ≤10% per week across the 4-week block",
        "• Training days: ONLY schedule sessions on the days listed in the rider profile. All other days = Rest.",
        "• Intensity split: ≥80% of weekly sessions at Z1/Z2. Max 20% at Z3 or above.",
        "",
        "══════════════════════════════════════════════════════════",
        "FORMAT RULES — follow exactly",
        "══════════════════════════════════════════════════════════",
        "1. Start each week with: ## Week N — [Theme]",
        "2. Immediately after the heading, a markdown table with these exact columns:",
        "   | Day | Session | Duration | Intensity | Why |",
        "   |-----|---------|----------|-----------|-----|",
        "   Day      — full name (Monday … Sunday)",
        "   Session  — short type: Z2 Endurance, Threshold Intervals, Rest, Active Recovery, etc.",
        "   Duration — e.g. 55 min or 38 km  |  use '—' for rest",
        "   Intensity — exact bpm range from the HR Zones section, e.g. '130–148 bpm (Z3)'  |  use '—' for rest",
        "   Why      — one sentence: the physiological purpose  |  use '—' for rest",
        "3. Every day Monday–Sunday must appear.",
        "4. After the table: '**Coach notes:**' — 2–3 sentences on the week's theme, cues, recovery.",
        "5. End the plan with '## Key Principles' — 3–5 bullet points.",
        "",
        "══════════════════════════════════════════════════════════",
        "RIDER PROFILE",
        "══════════════════════════════════════════════════════════",
        f"Objective:            {request.objective}",
        f"Experience level:     {user.experience_level or 'Not specified'}",
        f"Bike type:            {user.bike_type or 'Not specified'}",
        f"Age:                  {user.age or 'Not specified'}",
        f"Weight:               {f'{user.weight_kg} kg' if user.weight_kg else 'Not specified'}",
        f"FTP:                  {f'{user.ftp} W  ({round(user.ftp / user.weight_kg, 2)} w/kg)' if user.ftp and user.weight_kg else (f'{user.ftp} W' if user.ftp else 'Not specified — use RPE/HR zones')}",
        f"Training days:        {', '.join(sorted_days)}",
        f"Rest days:            {', '.join(rest_days)}",
        f"Target event / date:  {request.event_date or 'None specified'}",
        f"Extra notes:          {request.extra_notes or 'None'}",
        "",
        "══════════════════════════════════════════════════════════",
        "CURRENT FITNESS  (last 8 weeks)",
        "══════════════════════════════════════════════════════════",
        f"Total rides:          {total_rides}",
        f"Avg weekly distance:  {avg_weekly_km:.1f} km",
        f"Avg weekly elevation: {avg_weekly_elev:.0f} m",
        f"Avg weekly suffer:    {avg_weekly_suffer:.0f}  (scale: <20 easy, 20–50 moderate, 50+ hard)",
        f"Longest single ride:  {longest_ride_km:.1f} km  /  {longest_ride_min} min",
        f"Avg single ride:      {avg_ride_km:.1f} km  /  {avg_ride_min} min",
        f"Effort distribution:  {effort_pct}",
        f"8-week load trend:    {trend_str}",
        f"Fitness (CTL):        {ctl:.1f}  (higher = fitter)",
        f"Fatigue (ATL):        {atl:.1f}  (higher = more tired)",
        f"Form (TSB):           {tsb:.1f}  (positive = fresh, negative = fatigued)",
        "",
    ]

    if weekly:
        lines.append("══════════════════════════════════════════════════════════")
        lines.append("WEEKLY LOAD HISTORY  (last 8 weeks)")
        lines.append("══════════════════════════════════════════════════════════")
        for week, w in sorted(weekly.items())[-8:]:
            h = w["duration_s"] // 3600
            m = (w["duration_s"] % 3600) // 60
            lines.append(
                f"  w/c {week}: {w['rides']} rides, {w['distance_km']:.0f} km, "
                f"{w['elevation_m']:.0f} m elev, {h}h{m:02d}, suffer {w['suffer']}"
            )
        lines.append("")

    if hr_zone_lines:
        lines.append("══════════════════════════════════════════════════════════")
        lines.append(f"HR ZONES  ({hr_method})")
        lines.append("══════════════════════════════════════════════════════════")
        lines.append("USE THESE EXACT VALUES in the Intensity column. Do not recalculate.")
        lines.extend(hr_zone_lines)
        lines.append("")
    else:
        lines.append("══════════════════════════════════════════════════════════")
        lines.append("HR ZONES")
        lines.append("══════════════════════════════════════════════════════════")
        lines.append("Max HR not set — use RPE 1–10 for intensity.")
        lines.append("  Z1 Recovery:  RPE 2–3")
        lines.append("  Z2 Endurance: RPE 4–5")
        lines.append("  Z3 Tempo:     RPE 6–7")
        lines.append("  Z4 Threshold: RPE 8")
        lines.append("  Z5 VO2 Max:   RPE 9–10")
        lines.append("")

    if pr_lines:
        lines.append("══════════════════════════════════════════════════════════")
        lines.append("PERSONAL RECORDS")
        lines.append("══════════════════════════════════════════════════════════")
        lines.extend(pr_lines)
        lines.append("")

    return "\n".join(lines)


@router.get("/plan")
def get_plan(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    is_free = not has_full_access(current_user)
    plan = (
        db.query(models.TrainingPlan)
        .filter(models.TrainingPlan.user_id == current_user.id)
        .order_by(models.TrainingPlan.created_at.desc())
        .first()
    )

    limit = monthly_limit("plan")
    used_this_month = _plans_this_month(db, current_user.id)
    ai_reason = "demo" if current_user.is_demo else unavailable_reason(db)
    ai_on = ai_reason is None
    can_gen = (not is_free) and ai_on and used_this_month < limit
    next_date = None
    if not is_free and used_this_month >= limit and plan:
        next_date = _next_generation_date(plan.created_at)

    meta = {
        "can_generate": can_gen,
        "next_generation_date": next_date,
        "plans_used": used_this_month,
        "plans_limit": limit,
        "is_free": is_free,
        "ai_available": ai_on,
        "ai_unavailable_reason": ai_reason,
    }

    if not plan:
        return {"plan": None, **meta}

    training_days = json.loads(plan.training_days_json) if plan.training_days_json else []
    return {
        "plan": {
            "id": plan.id,
            "objective": plan.objective,
            "available_days": plan.available_days,
            "training_days": training_days,
            "event_date": plan.event_date,
            "extra_notes": plan.extra_notes,
            "plan_text": plan.plan_text,
            "created_at": plan.created_at.isoformat(),
        },
        **meta,
    }


@router.post("/plan")
def generate_plan(
    body: PlanRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not has_full_access(current_user):
        raise HTTPException(status_code=403, detail="AI training plans are a Pro feature. Upgrade to generate personalised plans.")

    limit = monthly_limit("plan")
    used_this_month = _plans_this_month(db, current_user.id)
    if used_this_month >= limit:
        existing = (
            db.query(models.TrainingPlan)
            .filter(models.TrainingPlan.user_id == current_user.id)
            .order_by(models.TrainingPlan.created_at.desc())
            .first()
        )
        next_date = _next_generation_date(existing.created_at) if existing else None
        raise HTTPException(
            status_code=429,
            detail=f"You can generate up to {limit} plans per month. Next generation available on {next_date}."
        )
    check_quota(db, current_user, "plan")

    prompt = _build_prompt(body, current_user, db)

    try:
        client = anthropic.Anthropic(api_key=api_key())
        message = client.messages.create(
            model=SONNET,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        plan_text = message.content[0].text
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {str(e)}")
    record_usage(db, current_user.id, "plan", SONNET, message.usage)

    plan = models.TrainingPlan(
        user_id=current_user.id,
        objective=body.objective,
        available_days=len(body.training_days),
        training_days_json=json.dumps(body.training_days),
        event_date=body.event_date,
        extra_notes=body.extra_notes,
        plan_text=plan_text,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    return {
        "plan": {
            "id": plan.id,
            "objective": plan.objective,
            "available_days": plan.available_days,
            "training_days": body.training_days,
            "event_date": plan.event_date,
            "extra_notes": plan.extra_notes,
            "plan_text": plan.plan_text,
            "created_at": plan.created_at.isoformat(),
        },
        "can_generate": False,
        "next_generation_date": _next_generation_date(plan.created_at),
    }
