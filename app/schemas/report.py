from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.report import ReportStatus


class ReportUpdate(BaseModel):
    transcript_json: dict | None = None
    extraction_json: dict | None = None
    validation_flags: list[dict] | None = None


class ReportOut(BaseModel):
    id: UUID
    patient_id: UUID
    doctor_id: UUID
    audio_url: str
    transcript_json: dict | None = None
    extraction_json: dict | None = None
    validation_flags: list[dict] | None = None
    status: ReportStatus
    created_at: datetime
    approved_at: datetime | None = None

    model_config = {"from_attributes": True}


class AppointmentHistoryItem(BaseModel):
    """The only report data a patient may see: when and with whom the visit happened."""

    id: UUID
    doctor_id: UUID
    doctor_name: str
    specialization: str | None = None
    appointment_at: datetime
    status: ReportStatus

    model_config = {"from_attributes": True}


class DoctorReportListItem(BaseModel):
    id: UUID
    patient_id: UUID
    patient_name: str
    patient_email: str
    audio_url: str
    extraction_json: dict | None = None
    validation_flags: list[dict] | None = None
    status: ReportStatus
    created_at: datetime
    approved_at: datetime | None = None

    model_config = {"from_attributes": True}
