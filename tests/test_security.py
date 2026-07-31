from __future__ import annotations

from uuid import uuid4

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

settings = get_settings()


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("S3cret!pass")
    assert hashed != "S3cret!pass"
    assert verify_password("S3cret!pass", hashed)
    assert not verify_password("wrong", hashed)


def test_access_token_roundtrip() -> None:
    user_id = uuid4()
    token = create_access_token(user_id=user_id, role="doctor")
    payload = decode_access_token(token)

    assert payload["sub"] == str(user_id)
    assert payload["user_id"] == str(user_id)
    assert payload["role"] == "doctor"


def test_access_token_rejects_bad_token() -> None:
    try:
        decode_access_token("not.a.jwt")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for malformed token")
