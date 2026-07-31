from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: UUID
    role: str
    is_approved: bool | None = None
