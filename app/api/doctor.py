from __future__ import annotations

import secrets
import string
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import hash_password
from app.dependencies.auth import require_approved_doctor
from app.models.user import User, UserRole
from app.schemas.patient import PatientCreate, PatientInviteResponse, PatientOut

router = APIRouter(prefix="/doctor", tags=["doctor"])


def _generate_temporary_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(12))


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

    temporary_password = payload.temporary_password or _generate_temporary_password()
    patient = User(
        name=payload.name,
        email=payload.email,
        dob=payload.dob,
        hashed_password=hash_password(temporary_password),
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
        temporary_password=temporary_password,
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
