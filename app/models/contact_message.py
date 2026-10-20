from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User


class ContactMessage(Base, UUIDMixin, TimestampMixin):
    """A message sent from the public landing-page contact form.

    ``intent`` records *why* the message exists and therefore where it is routed:

    - ``patient_to_doctor`` — a patient contacted a specific doctor. ``doctor_id`` is set, so
      the message shows up in that doctor's inbox.
    - ``doctor_to_us`` — a doctor wants to register with the platform. ``doctor_id`` is NULL, so
      the message shows up in the admin inbox instead.
    - ``general`` — legacy rows that predate the intent split (generic enquiries).
    """

    __tablename__ = "contact_messages"

    INTENT_PATIENT_TO_DOCTOR = "patient_to_doctor"
    INTENT_DOCTOR_TO_US = "doctor_to_us"
    INTENT_GENERAL = "general"

    doctor_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    intent: Mapped[str] = mapped_column(String(32), default=INTENT_GENERAL, nullable=False)
    subject: Mapped[str | None] = mapped_column(String(120), nullable=True)
    specialization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    doctor: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[doctor_id],
        back_populates="contact_messages",
    )
