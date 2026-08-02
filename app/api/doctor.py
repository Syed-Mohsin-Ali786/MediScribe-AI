from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import hash_password
from app.dependencies.auth import require_approved_doctor, require_role
from app.models.contact_message import ContactMessage
from app.models.user import User, UserRole
from app.schemas.message import ContactMessageOut
from app.schemas.patient import PatientCreate, PatientInviteResponse, PatientOut
from app.schemas.user import DoctorProfileUpdate, UserMe
from app.services.avatar import save_avatar

router = APIRouter(prefix="/doctor", tags=["doctor"])


@router.post(
    "/patients",
    response_model=PatientInviteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create and invite a patient (doctor-owned)",
)
async def create_patient(
    payload: PatientCreate,
    doctor: Annotated[User, Depends(require_approved_doctor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PatientInviteResponse:
    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    patient = User(
        name=payload.name,
        email=payload.email,
        dob=payload.dob,
        hashed_password=hash_password(payload.password),
        role=UserRole.PATIENT,
        is_approved=True,
        doctor_id=doctor.id,
    )
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    return PatientInviteResponse(
        id=patient.id,
        name=patient.name,
        email=patient.email,
        role=patient.role,
        is_approved=patient.is_approved,
        dob=patient.dob,
        doctor_id=doctor.id,
        created_at=patient.created_at,
    )


@router.get(
    "/patients",
    response_model=list[PatientOut],
    summary="List patients linked to the current doctor",
)
async def list_patients(
    doctor: Annotated[User, Depends(require_approved_doctor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[User]:
    result = await db.scalars(
        select(User)
        .where(User.doctor_id == doctor.id, User.role == UserRole.PATIENT)
        .order_by(User.created_at)
    )
    return list(result.all())


@router.get(
    "/patients/search",
    response_model=list[PatientOut],
    summary="Search patients linked to the current doctor",
)
async def search_patients(
    q: Annotated[str, Query(min_length=1, max_length=100)],
    doctor: Annotated[User, Depends(require_approved_doctor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[User]:
    search_term = q.strip()
    if not search_term:
        return []

    result = await db.scalars(
        select(User)
        .where(
            User.doctor_id == doctor.id,
            User.role == UserRole.PATIENT,
            or_(User.name.ilike(f"%{search_term}%"), User.email.ilike(f"%{search_term}%")),
        )
        .order_by(User.name)
        .limit(25)
    )
    return list(result.all())


@router.patch(
    "/profile",
    response_model=UserMe,
    summary="Update the current doctor's own profile",
)
async def update_profile(
    payload: DoctorProfileUpdate,
    doctor: Annotated[User, Depends(require_approved_doctor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if payload.name is not None:
        doctor.name = payload.name.strip()
    if payload.specialization is not None:
        doctor.specialization = payload.specialization.strip() or None
    if payload.avatar_url is not None:
        doctor.avatar_url = payload.avatar_url or None
    await db.commit()
    await db.refresh(doctor)
    return doctor


@router.post(
    "/profile/avatar",
    response_model=UserMe,
    summary="Upload a profile photo for the current doctor",
)
async def upload_avatar(
    file: Annotated[UploadFile, "Profile photo (jpg/png/webp/gif, max 5 MB)"],
    doctor: Annotated[User, Depends(require_role(UserRole.DOCTOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    try:
        doctor.avatar_url = save_avatar(file, str(doctor.id))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(doctor)
    return doctor


@router.get(
    "/messages",
    response_model=list[ContactMessageOut],
    summary="List contact messages sent to the current doctor",
)
async def list_messages(
    doctor: Annotated[User, Depends(require_approved_doctor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    unread_only: Annotated[bool, Query()] = False,
) -> list[ContactMessage]:
    stmt = select(ContactMessage).where(ContactMessage.doctor_id == doctor.id)
    if unread_only:
        stmt = stmt.where(ContactMessage.read.is_(False))
    result = await db.scalars(stmt.order_by(ContactMessage.created_at.desc()))
    return list(result.all())


@router.patch(
    "/messages/{message_id}/read",
    response_model=ContactMessageOut,
    summary="Mark a contact message as read",
)
async def mark_message_read(
    message_id: UUID,
    doctor: Annotated[User, Depends(require_approved_doctor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ContactMessage:
    message = await db.get(ContactMessage, message_id)
    if message is None or message.doctor_id != doctor.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )
    message.read = True
    await db.commit()
    await db.refresh(message)
    return message
