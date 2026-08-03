from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.contact_message import ContactMessage
from app.models.user import User, UserRole
from app.schemas.message import ContactMessageCreate, ContactMessageOut
from app.schemas.user import DirectoryUserOut

router = APIRouter(prefix="/public", tags=["public"])


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
    summary="Send a contact message to a doctor (public landing-page form)",
)
async def send_contact_message(
    payload: ContactMessageCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ContactMessage:
    """Persist a message from the landing-page "Contact Now" form.

    Public endpoint — no auth required. If a valid doctor ID is provided, the
    message is linked to that doctor; otherwise it is stored as a generic inbox
    message and can be viewed by admins.
    """
    doctor_id = payload.doctor_id
    doctor = None
    if doctor_id is not None:
        doctor = await db.get(User, doctor_id)
        if doctor is None or doctor.role != UserRole.DOCTOR or not doctor.is_approved:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Doctor not found",
            )

    message = ContactMessage(
        doctor_id=doctor.id if doctor is not None else None,
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

