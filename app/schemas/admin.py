from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.models.user import UserRole


class AdminStats(BaseModel):
    """Platform-wide counts for the admin console."""

    total_users: int
    doctors: int
    pending_doctors: int
    patients: int
    reports: int
    approved_reports: int
    draft_reports: int


class AdminUserOut(BaseModel):
    """Directory entry for an admin-managed user (doctors + patients)."""

    id: UUID
    name: str
    email: str
    role: UserRole
    is_approved: bool
    specialization: str | None = None
    doctor_id: UUID | None = None
    doctor_name: str | None = None
    report_count: int = 0
    created_at: datetime


class IntegrationOut(BaseModel):
    configured: bool
    status: Literal["ok", "error", "unconfigured"]
    detail: str | None = None


class IntegrationsStatus(BaseModel):
    """Live status of the external services the pipeline depends on."""

    database: IntegrationOut
    mistral: IntegrationOut
    gemini: IntegrationOut
    supabase: IntegrationOut
    rxnorm: IntegrationOut
    checked_at: datetime


class DailyReportPoint(BaseModel):
    date: str
    generated: int
    approved: int


class DailyUserPoint(BaseModel):
    date: str
    new_users: int
    doctors: int
    patients: int


class DoctorReportBreakdown(BaseModel):
    doctor_name: str
    total: int
    approved: int


class AdminAnalytics(BaseModel):
    """Time-series + breakdowns for the admin analytics dashboard."""

    reports_over_time: list[DailyReportPoint]
    users_over_time: list[DailyUserPoint]
    reports_by_doctor: list[DoctorReportBreakdown]
    totals: AdminStats
    approval_rate: float
