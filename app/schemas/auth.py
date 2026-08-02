from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: UUID
    role: str
    is_approved: bool | None = None


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=6, max_length=255)
    specialization: str | None = Field(default=None, max_length=255)


class RegisterResponse(BaseModel):
    access_token: str = ""
    token_type: str = "bearer"
    user_id: UUID
    role: str
    is_approved: bool

