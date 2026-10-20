from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.contact_message import ContactMessage
from app.models.user import User, UserRole
from app.schemas.message import ContactMessageCreate, ContactMessageOut
from app.schemas.user import DirectoryUserOut

router = APIRouter(prefix="/public", tags=["public"])
legacy_router = APIRouter(tags=["public"])

DOCTOR_NOT_FOUND_MESSAGE = "We couldn't find a doctor with that email address."


async def _resolve_target_doctor(
    db: AsyncSession,
    doctor_id: UUID | None,
    doctor_email: str | None,
) -> User | None:
    """Find the approved doctor a patient is trying to reach.

    The patient may supply the doctor's id (the per-doctor form knows it) or
    the doctor's email address (typed into the general landing-page form).
    Only approved doctors can be contacted.
    """
    if doctor_id is not None:
        doctor = await db.get(User, doctor_id)
    elif doctor_email:
        doctor = await db.scalar(select(User).where(User.email == doctor_email.strip().lower()))
    else:
        return None

    if doctor is None or doctor.role != UserRole.DOCTOR or not doctor.is_approved:
        return None
    return doctor


async def _persist_contact_message(
    payload: ContactMessageCreate,
    db: AsyncSession,
) -> ContactMessage:
    """Persist a public contact message and route it by the sender's intent.

    - ``patient_to_doctor`` — must resolve to an approved doctor; the message
      is stored against that doctor so it lands in their inbox.
    - ``doctor_to_us`` — the sender wants to register with the platform; the
      message is stored without a doctor so it lands in the admin inbox.
    """
    doctor: User | None = None

    if payload.intent == ContactMessage.INTENT_PATIENT_TO_DOCTOR:
        if payload.doctor_id is None and not payload.doctor_email:
            raise HTTPException(
                status_code=422,
                detail="Tell us which doctor you want to reach — enter their email address.",
            )
        doctor = await _resolve_target_doctor(db, payload.doctor_id, payload.doctor_email)
        if doctor is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=DOCTOR_NOT_FOUND_MESSAGE,
            )

    message = ContactMessage(
        intent=payload.intent,
        doctor_id=doctor.id if doctor is not None else None,
        subject=payload.subject.strip() if payload.subject else None,
        specialization=payload.specialization.strip() if payload.specialization else None,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        age=payload.age,
        message=payload.message,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


@router.get(
    "/doctors",
    response_model=list[DirectoryUserOut],
    summary="List approved doctors (public landing-page directory)",
)
async def list_public_doctors(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[User]:
    """Public, read-only directory of approved doctors for the landing page.

    Only doctors (role == doctor, is_approved) are exposed. No PII beyond the
    name, email and specialization a doctor chose to share.
    """
    result = await db.scalars(
        select(User)
        .where(User.role == UserRole.DOCTOR, User.is_approved.is_(True))
        .order_by(User.created_at)
    )
    return list(result.all())


@router.post(
    "/contact",
    response_model=ContactMessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Send a contact message from the public landing-page form",
)
async def send_contact_message(
    payload: ContactMessageCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ContactMessage:
    """Send a message from the landing-page contact form.

    Public endpoint — no auth required. The sender's intent decides where the
    message is routed: a patient contacting a doctor lands in that doctor's
    inbox, a doctor asking to register lands in the admin inbox.
    """
    return await _persist_contact_message(payload, db)


@legacy_router.post(
    "/contact",
    response_model=ContactMessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Compatibility endpoint for public contact submissions",
)
async def send_contact_message_legacy(
    payload: ContactMessageCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ContactMessage:
    """Legacy compatibility route for the public contact form."""
    return await _persist_contact_message(payload, db)
