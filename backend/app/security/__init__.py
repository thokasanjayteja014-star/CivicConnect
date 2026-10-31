"""Password hashing, JWT handling and role/permission checks."""
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from app.core.config import get_settings
from app.core.errors import err

_hasher = PasswordHasher()
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, Exception):
        return False


def _secret() -> str:
    secret = get_settings().AUTH_SECRET
    if not secret or len(secret) < 32:
        raise RuntimeError("AUTH_SECRET must be set to a random value of at least 32 characters.")
    return secret


def create_access_token(user_id: uuid.UUID, role: str) -> tuple[str, datetime]:
    expires = datetime.now(timezone.utc) + timedelta(minutes=get_settings().ACCESS_TOKEN_TTL_MINUTES)
    payload = {
        "sub": str(user_id),
        "role": role,
        "typ": "access",
        "jti": secrets.token_hex(16),
        "exp": expires,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM), expires


def decode_token(token: str, expected_type: str = "access") -> dict:
    try:
        payload = jwt.decode(token, _secret(), algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise err("UNAUTHENTICATED")
    if payload.get("typ") != expected_type:
        raise err("UNAUTHENTICATED")
    return payload


def create_media_token(media_id: uuid.UUID, user_id: uuid.UUID | None) -> tuple[str, datetime]:
    """Short-lived signed link for an already-authorized media read."""
    expires = datetime.now(timezone.utc) + timedelta(seconds=get_settings().MEDIA_LINK_TTL_SECONDS)
    payload = {"typ": "media", "mid": str(media_id), "sub": str(user_id) if user_id else None, "exp": expires}
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM), expires
