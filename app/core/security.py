from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from jose import JWTError, jwt

from app.core.config import Settings, get_settings

_ph = PasswordHasher()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return _ph.verify(hashed_password, plain_password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def hash_password(password: str) -> str:
    return _ph.hash(password)


def create_access_token(
    user_id: UUID,
    role: str,
    settings: Settings | None = None,
) -> str:
    settings = settings or get_settings()
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "user_id": str(user_id),
        "role": role,
        "iat": now,
        "exp": expires,
        "type": "access",
    }
    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "role", "exp"]},
        )
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc


def get_token_subject(token: str, settings: Settings | None = None) -> UUID:
    payload = decode_access_token(token, settings)
    return UUID(payload["sub"])
