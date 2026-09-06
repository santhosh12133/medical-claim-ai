import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt


ALGORITHM = "HS256"
PBKDF2_ITERATIONS = 120000


def _secret_key() -> str:
    secret = os.getenv("SECRET_KEY", "").strip()
    if not secret or secret == "change-me":
        raise RuntimeError("SECRET_KEY must be configured with a strong random value")
    if len(secret) < 32:
        raise RuntimeError("SECRET_KEY must be at least 32 characters long")
    return secret


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS)
    return digest.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    candidate_hash, _ = hash_password(password, salt)
    return hmac.compare_digest(candidate_hash, password_hash)


def create_access_token(subject: str, role: str, expires_minutes: int | None = None) -> str:
    if expires_minutes is None:
        expires_minutes = int(os.getenv("AUTH_TOKEN_EXPIRE_MINUTES", "60"))
    if expires_minutes <= 0:
        raise RuntimeError("AUTH_TOKEN_EXPIRE_MINUTES must be greater than zero")

    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
    }
    return jwt.encode(payload, _secret_key(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    return jwt.decode(token, _secret_key(), algorithms=[ALGORITHM])
