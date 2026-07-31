from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class PatientCreate(BaseModel):
    name: str
    email: EmailStr
    dob: date | None = None
    temporary_password: str | None = None


class PatientOut(BaseModel):
    id: UUID
    name: str
    email: str
    dob: date | None = None
    doctor_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class PatientInviteResponse(BaseModel):
    id: UUID
    name: str
    email: str
    temporary_password: str | None = None
    message: str = "Patient account created. Share the temporary password offline for demo."
