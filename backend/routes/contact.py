import time
import threading
import os
from collections import defaultdict
from fastapi import APIRouter, Request, HTTPException
from email_service import send_contact_message

router = APIRouter()

_rate_lock = threading.Lock()
_submissions: dict[str, list[float]] = defaultdict(list)
_WINDOW = 3600   # 1 hour
_MAX    = 3      # max submissions per IP per window
_MIN_T  = 5      # minimum seconds on form before submitting


def _check_rate(ip: str) -> None:
    now = time.time()
    with _rate_lock:
        _submissions[ip] = [t for t in _submissions[ip] if now - t < _WINDOW]
        if len(_submissions[ip]) >= _MAX:
            raise HTTPException(status_code=429, detail="Too many messages. Try again later.")
        _submissions[ip].append(now)


@router.post("/contact")
async def contact(request: Request, body: dict):
    # Honeypot — bots fill hidden fields, humans don't
    if body.get("website"):
        return {"ok": True}

    # Time-on-form check — bots submit instantly
    rendered_at = body.get("rendered_at") or 0
    if time.time() - float(rendered_at) < _MIN_T:
        raise HTTPException(status_code=400, detail="Please take a moment to fill out the form.")

    ip = (request.client.host if request.client else "unknown")
    _check_rate(ip)

    name    = (body.get("name")    or "").strip()
    email   = (body.get("email")   or "").strip()
    subject = (body.get("subject") or "").strip() or "No subject"
    message = (body.get("message") or "").strip()

    if not name or not email or not message:
        raise HTTPException(status_code=400, detail="Name, email and message are required.")
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Invalid email address.")
    if len(message) > 5000:
        raise HTTPException(status_code=400, detail="Message too long (max 5000 characters).")

    send_contact_message(name=name, from_email=email, subject=subject, message=message)
    return {"ok": True}
