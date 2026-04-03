"""
JWT-based authentication for the price monitoring API.

Design:
  - HS256 signed access tokens (short-lived: 60 min default)
  - Optional refresh token support via /auth/refresh
  - Password hashing with bcrypt (via passlib)
  - Users stored in config (demo) — swap _USERS for a DB lookup in prod

Environment variables:
  JWT_SECRET_KEY   – signing secret (REQUIRED in production)
  JWT_EXPIRE_MINS  – token lifetime in minutes (default 60)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

SECRET_KEY  = os.getenv("JWT_SECRET_KEY", "DEV_ONLY_CHANGE_IN_PRODUCTION_abc123xyz")
ALGORITHM   = "HS256"
EXPIRE_MINS = int(os.getenv("JWT_EXPIRE_MINS", "60"))

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── In-memory user store (replace with DB in production) ──────────────────────
# Format: { username: { "hashed_password": ..., "role": ... } }
_USERS: dict[str, dict] = {
    "admin": {
        "hashed_password": _pwd_ctx.hash("admin123"),
        "role": "admin",
    },
    "viewer": {
        "hashed_password": _pwd_ctx.hash("viewer123"),
        "role": "viewer",
    },
}

# ── Public API ─────────────────────────────────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


def get_password_hash(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def authenticate_user(username: str, password: str) -> dict | None:
    """Return user dict if credentials are valid, else None."""
    user = _USERS.get(username)
    if user and verify_password(password, user["hashed_password"]):
        return {"username": username, **user}
    return None


def create_access_token(
    data: dict,
    expires_delta: timedelta | None = None,
) -> str:
    """Sign and return a JWT access token."""
    payload = data.copy()
    expire  = datetime.now(tz=timezone.utc) + (expires_delta or timedelta(minutes=EXPIRE_MINS))
    payload.update({"exp": expire, "iat": datetime.now(tz=timezone.utc)})
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    logger.debug("Issued token for sub=%s exp=%s", data.get("sub"), expire)
    return token


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT.
    Raises HTTP 401 on any failure.
    """
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exc
        return {"username": username, "role": payload.get("role", "viewer")}
    except JWTError as exc:
        logger.warning("JWT decode failed: %s", exc)
        raise credentials_exc
