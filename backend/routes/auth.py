from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from database import get_db
import models
import schemas
from auth import verify_password, hash_password, create_token, get_current_user, TOKEN_EXPIRE_DAYS, COOKIE_SECURE

from utils.ai_budget import quota_status
from utils.rate_limit import check_rate_limit as _check_rate_limit

router = APIRouter()


# ── Cookie helper ────────────────────────────────────────────────────────────

def _set_auth_cookie(response: JSONResponse, token: str):
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="strict",
        secure=COOKIE_SECURE,
        max_age=TOKEN_EXPIRE_DAYS * 24 * 3600,
        path="/",
    )


# ── Routes ───────────────────────────────────────────────────────────────────

_REGISTER_ERROR = "Could not create account. The username may be unavailable or your details are invalid."


@router.post("/register")
def register(request: Request, data: schemas.RegisterRequest, db: Session = Depends(get_db)):
    # Honeypot — bots fill this in, real browsers leave it empty
    if data.website:
        return JSONResponse({"token_type": "bearer"})

    _check_rate_limit(request.client.host, "register", db)

    email = data.email.strip().lower()
    if not data.username.strip() or len(data.password) < 6 or "@" not in email:
        raise HTTPException(status_code=400, detail=_REGISTER_ERROR)

    # Generic 400 (not 409) so status code can't be used to enumerate existing usernames/emails
    existing = db.query(models.User).filter(
        (models.User.username == data.username.strip()) | (models.User.email == email)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=_REGISTER_ERROR)

    user = models.User(username=data.username.strip(), email=email, hashed_password=hash_password(data.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_token(user.id, user.token_version or 1)
    response = JSONResponse({"token_type": "bearer"})
    _set_auth_cookie(response, token)
    return response


@router.post("/login")
def login(request: Request, data: schemas.LoginRequest, db: Session = Depends(get_db)):
    _check_rate_limit(request.client.host, "login", db)
    user = db.query(models.User).filter(models.User.username == data.username).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_token(user.id, user.token_version or 1)
    response = JSONResponse({"token_type": "bearer"})
    _set_auth_cookie(response, token)
    return response


@router.post("/demo")
def demo_login(request: Request, db: Session = Depends(get_db)):
    """Sign in to the shared read-only demo account (created by scripts/seed_demo.py)."""
    _check_rate_limit(request.client.host, "demo", db)
    user = db.query(models.User).filter(models.User.is_demo.is_(True)).first()
    if not user:
        raise HTTPException(status_code=404, detail="The demo is not available on this server.")
    token = create_token(user.id, user.token_version or 1)
    response = JSONResponse({"token_type": "bearer"})
    _set_auth_cookie(response, token)
    return response


@router.post("/logout")
def logout(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    # Bumping token_version signs out every session; the demo account is shared,
    # so one visitor leaving must not sign everyone else out.
    if not current_user.is_demo:
        current_user.token_version = (current_user.token_version or 1) + 1
        db.commit()
    response = JSONResponse({"ok": True})
    response.delete_cookie(key="access_token", path="/")
    return response


@router.get("/me", response_model=schemas.UserOut)
def me(current_user=Depends(get_current_user)):
    return current_user


@router.get("/ai-quota")
def ai_quota(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return quota_status(db, current_user)


@router.get("/setup")
def setup_status(db: Session = Depends(get_db)):
    return {"needs_setup": db.query(models.User).count() == 0}
