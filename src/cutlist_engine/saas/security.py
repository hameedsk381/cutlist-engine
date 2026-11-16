"""Password hashing, JWT tokens and the FastAPI auth dependency."""
from __future__ import annotations

import datetime as _dt
import hashlib
import logging
import os
import secrets

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import ApiKey, User

logger = logging.getLogger(__name__)

_JWT_ALG = "HS256"
_TOKEN_TTL = _dt.timedelta(days=7)

API_KEY_PREFIX = "ckl_"

_secret = os.environ.get("CUTLIST_JWT_SECRET", "").strip()
if not _secret:
    _secret = secrets.token_urlsafe(48)
    logger.warning(
        "CUTLIST_JWT_SECRET is not set — using an ephemeral secret. "
        "All sessions are invalidated on restart. Set it in production."
    )

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int) -> str:
    now = _dt.datetime.now(_dt.timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + _TOKEN_TTL}
    return jwt.encode(payload, _secret, algorithm=_JWT_ALG)


def decode_token(token: str) -> int | None:
    """Return the user id encoded in the token, or None if invalid/expired."""
    try:
        payload = jwt.decode(token, _secret, algorithms=[_JWT_ALG])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Password reset links
# ---------------------------------------------------------------------------

_RESET_TTL = _dt.timedelta(hours=1)


def _password_fingerprint(user: User) -> str:
    """Changes whenever the password changes, so a reset link works once."""
    return hashlib.sha256(user.password_hash.encode("utf-8")).hexdigest()[:16]


def create_reset_token(user: User) -> str:
    now = _dt.datetime.now(_dt.timezone.utc)
    payload = {"sub": str(user.id), "purpose": "reset", "pw": _password_fingerprint(user),
               "iat": now, "exp": now + _RESET_TTL}
    return jwt.encode(payload, _secret, algorithm=_JWT_ALG)


def user_for_reset_token(token: str, db: Session) -> User | None:
    """The account a valid, unused, unexpired reset link belongs to, else None."""
    try:
        payload = jwt.decode(token, _secret, algorithms=[_JWT_ALG])
        if payload.get("purpose") != "reset":
            return None
        user = db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
    if user is None or payload.get("pw") != _password_fingerprint(user):
        return None
    return user


# ---------------------------------------------------------------------------
# API keys (for CNC shops / programmatic access)
# ---------------------------------------------------------------------------

import hashlib


def _key_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Returns (raw_key, key_hash, key_prefix). Raw key is shown exactly once."""
    raw = f"{API_KEY_PREFIX}{secrets.token_urlsafe(24)}"
    return raw, _key_hash(raw), raw[:12]


def user_for_api_key(raw: str, db: Session) -> User | None:
    """Look up the owner of a raw API key (constant work, no timing oracle)."""
    from datetime import datetime, timezone

    found = db.query(ApiKey).filter(ApiKey.key_hash == _key_hash(raw)).first()
    if found is None:
        return None
    found.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return db.get(User, found.user_id)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    token = credentials.credentials

    # API keys (ckl_...) authenticate programmatic access without a session.
    if token.startswith(API_KEY_PREFIX):
        user = user_for_api_key(token, db)
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
        return user

    user_id = decode_token(token)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired — sign in again")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown account")
    return user
