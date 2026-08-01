from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.user import UserRole


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


class DoctorProfileUpdate(BaseModel):
    """Editable fields on the doctor's own profile. Omitted fields are left
    unchanged; an empty specialization string clears it."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    specialization: str | None = Field(default=None, max_length=255)


class PendingDoctorOut(BaseModel):
    id: UUID
    name: str
    email: str
    specialization: str | None = None
    role: UserRole
    is_approved: bool
    created_at: datetime

    model_config = {"from_attributes": True}
