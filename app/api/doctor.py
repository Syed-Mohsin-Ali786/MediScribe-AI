from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import hash_password
from app.dependencies.auth import require_approved_doctor
from app.models.user import User, UserRole
from app.schemas.patient import PatientCreate, PatientInviteResponse, PatientOut

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
