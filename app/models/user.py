from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.contact_message import ContactMessage
    from app.models.report import Report


class UserRole(StrEnum):
    ADMIN = "admin"
    PENDING_DOCTOR = "pending_doctor"
    DOCTOR = "doctor"
    PATIENT = "patient"


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(String(50), nullable=False, default=UserRole.PENDING_DOCTOR)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    specialization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Doctors explicitly request access; only then does the admin see them for approval.
    permission_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    permission_requested_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Self-referential FK: patients are linked to their doctor.
    doctor_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    dob: Mapped[date | None] = mapped_column(nullable=True)

    # Relationships
    doctor: Mapped[User | None] = relationship(
        "User",
        remote_side="User.id",
        back_populates="patients",
    )
    patients: Mapped[list[User]] = relationship(
        "User",
        back_populates="doctor",
        cascade="all, delete-orphan",
    )
    reports_as_patient: Mapped[list[Report]] = relationship(
        "Report",
        foreign_keys="Report.patient_id",
        back_populates="patient",
        cascade="all, delete-orphan",
    )
    reports_as_doctor: Mapped[list[Report]] = relationship(
        "Report",
        foreign_keys="Report.doctor_id",
        back_populates="doctor",
    )
    contact_messages: Mapped[list[ContactMessage]] = relationship(
        "ContactMessage",
        back_populates="doctor",
        cascade="all, delete-orphan",
    )
