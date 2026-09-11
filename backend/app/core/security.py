"""Password hashing and session tokens.

The password format is deliberately unchanged from the TypeScript version
(`pbkdf2$<saltHex>$<hashHex>`, PBKDF2-HMAC-SHA256, 100k iterations, 32 bytes),
so user rows migrated from the old database keep working.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

from .config import settings

ITERATIONS = 100_000
_ALGO = "HS256"


def _derive(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS, dklen=32).hex()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    return f"pbkdf2${salt.hex()}${_derive(password, salt)}"


def verify_password(password: str, stored: str) -> bool:
    parts = (stored or "").split("$")
    if len(parts) != 3 or parts[0] != "pbkdf2":
        return False
    _, salt_hex, hash_hex = parts
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    return hmac.compare_digest(_derive(password, salt), hash_hex)


def _secret() -> str:
    raw = settings.auth_secret
    if len(raw) < 32 and os.getenv("ENV", "development") == "production":
        raise RuntimeError("AUTH_SECRET must be at least 32 characters in production.")
    return raw


def create_session_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=settings.session_days)).timestamp()),
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGO)


def verify_session_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, _secret(), algorithms=[_ALGO])
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) else None
