import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt


ALGORITHM = "HS256"


def _secret_key() -> str:
    return os.getenv("SECRET_KEY", "change-me")


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return digest.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    candidate_hash, _ = hash_password(password, salt)
    return candidate_hash == password_hash


def create_access_token(subject: str, role: str, expires_minutes: int = 480) -> str:
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