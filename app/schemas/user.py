from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.models.user import UserRole


class DoctorRegister(BaseModel):
    name: str
    email: EmailStr
    password: str
    specialization: str


class UserMe(BaseModel):
    id: UUID
    name: str
    email: str
    role: UserRole
    is_approved: bool
    specialization: str | None = None

    model_config = {"from_attributes": True}


class DirectoryUserOut(BaseModel):
    """Safe user fields returned by doctor/patient directory endpoints."""

    id: UUID
    name: str
    email: str
    role: UserRole
    is_approved: bool
    specialization: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PendingDoctorOut(BaseModel):
    id: UUID
    name: str
    email: str
    specialization: str | None = None
    role: UserRole
    is_approved: bool
    created_at: datetime

    model_config = {"from_attributes": True}
