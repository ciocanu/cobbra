import os
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
import models

SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY or SECRET_KEY == "velostats-dev-secret-change-in-production":
    raise RuntimeError(
        "SECRET_KEY environment variable is not set or is still the insecure default. "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 7
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_token(user_id: int, token_version: int = 1) -> str:
    expire = datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": str(user_id), "exp": expire, "ver": token_version},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def get_current_user(
    access_token: str = Cookie(default=None),
    db: Session = Depends(get_db),
):
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
    )
    if not access_token:
        raise exc
    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
        token_ver = int(payload.get("ver", 1))
    except (JWTError, KeyError, ValueError):
        raise exc
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or (user.token_version or 1) != token_ver:
        raise exc
    return user
