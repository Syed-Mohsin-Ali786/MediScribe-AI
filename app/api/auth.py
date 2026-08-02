from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.dependencies.auth import get_current_user
from app.models.user import User, UserRole
from app.schemas.auth import LoginRequest, LoginResponse, RegisterRequest, RegisterResponse
from app.schemas.user import UserMe

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Login, returns JWT with role and user_id claims",
)
async def login(
    payload: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoginResponse:
    user = await db.scalar(select(User).where(User.email == payload.email))
    if user is None or not user.hashed_password or not verify_password(
        payload.password, user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    role_str = user.role.value if hasattr(user.role, "value") else user.role
    access_token = create_access_token(user_id=user.id, role=role_str)
    return LoginResponse(
        access_token=access_token,
        user_id=user.id,
        role=role_str,
        is_approved=user.is_approved,
    )


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Self-register as a doctor — an approval request is sent to the admin immediately",
)
async def register(
    payload: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RegisterResponse:
    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists. Please sign in.",
        )

    doctor = User(
        name=payload.name.strip(),
        email=str(payload.email).lower(),
        hashed_password=hash_password(payload.password),
        specialization=payload.specialization.strip() if payload.specialization else None,
        role=UserRole.PENDING_DOCTOR,
        is_approved=False,
        # Registering immediately requests admin approval — no separate button needed.
        permission_requested=True,
        permission_requested_at=datetime.now(UTC),
    )
    db.add(doctor)
    await db.commit()
    await db.refresh(doctor)

    # No session/token — the doctor must wait for approval, then sign in.
    return RegisterResponse(
        access_token="",
        user_id=doctor.id,
        role=doctor.role.value if hasattr(doctor.role, "value") else doctor.role,
        is_approved=doctor.is_approved,
    )


@router.post(
    "/request-permission",
    response_model=UserMe,
    summary="Pending doctor explicitly requests access from the admin",
)
async def request_permission(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if current_user.role != UserRole.PENDING_DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending doctors can request permission",
        )
    if current_user.permission_requested:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Permission already requested — please wait for the admin",
        )

    current_user.permission_requested = True
    current_user.permission_requested_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.get(
    "/me",
    response_model=UserMe,
    summary="Current user profile",
)
async def me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    return current_user
