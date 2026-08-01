from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.models.user import UserRole


class PatientCreate(BaseModel):
    name: str
    email: EmailStr
    dob: date | None = None
    password: str


class PatientOut(BaseModel):
    id: UUID
    name: str
    email: str
    role: UserRole
    is_approved: bool
    dob: date | None = None
    doctor_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class PatientInviteResponse(BaseModel):
    id: UUID
    name: str
    email: str
    role: UserRole
    is_approved: bool
    dob: date | None = None
    doctor_id: UUID
    created_at: datetime
    message: str = "Patient account created. Share the password with the patient."
