from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

# Which destination a submitted message is routed to.
#   patient_to_doctor — the patient contacted a specific doctor (that doctor's inbox).
#   doctor_to_us      — the doctor wants to register with the platform (admin inbox).
ContactIntent = Literal["patient_to_doctor", "doctor_to_us"]


class ContactMessageCreate(BaseModel):
    intent: ContactIntent
    doctor_id: UUID | None = None
    doctor_email: EmailStr | None = None
    subject: str | None = Field(default=None, max_length=120)
    specialization: str | None = Field(default=None, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    phone: str = Field(min_length=7, max_length=20, pattern=r"^\+?[0-9\s\-()]+$")
    age: int | None = Field(default=None, ge=1, le=120)
    message: str = Field(min_length=1, max_length=5000)


class ContactMessageOut(BaseModel):
    id: UUID
    doctor_id: UUID | None = None
    intent: str
    subject: str | None = None
    specialization: str | None = None
    name: str
    email: str
    phone: str
    age: int | None = None
    message: str
    read: bool
    created_at: datetime

    model_config = {"from_attributes": True}
