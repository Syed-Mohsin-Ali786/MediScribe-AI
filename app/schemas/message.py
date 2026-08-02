from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class ContactMessageCreate(BaseModel):
    doctor_id: UUID
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    phone: str = Field(min_length=7, max_length=20, pattern=r"^\+?[0-9\s\-()]+$")
    age: int | None = Field(default=None, ge=1, le=120)
    message: str = Field(min_length=1, max_length=5000)


class ContactMessageOut(BaseModel):
    id: UUID
    doctor_id: UUID
    name: str
    email: str
    phone: str
    age: int | None = None
    message: str
    read: bool
    created_at: datetime

    model_config = {"from_attributes": True}
