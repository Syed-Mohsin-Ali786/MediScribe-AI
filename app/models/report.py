from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONBCompat, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User


class ReportStatus(StrEnum):
    DRAFT_GENERATED = "draft_generated"
    APPROVED = "approved"


class Report(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "reports"

    patient_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    doctor_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    audio_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    transcript_json: Mapped[dict | None] = mapped_column(JSONBCompat, nullable=True)
    extraction_json: Mapped[dict | None] = mapped_column(JSONBCompat, nullable=True)
    validation_flags: Mapped[dict | None] = mapped_column(JSONBCompat, nullable=True)
    status: Mapped[ReportStatus] = mapped_column(
        String(50),
        nullable=False,
        default=ReportStatus.DRAFT_GENERATED,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    patient: Mapped[User] = relationship(
        "User",
        foreign_keys=[patient_id],
        back_populates="reports_as_patient",
    )
    doctor: Mapped[User] = relationship(
        "User",
        foreign_keys=[doctor_id],
        back_populates="reports_as_doctor",
    )

    def approve(self) -> None:
        self.status = ReportStatus.APPROVED
        self.approved_at = datetime.now(UTC)
