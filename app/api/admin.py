from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import require_role
from app.models.user import User, UserRole
from app.schemas.user import PendingDoctorOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get(
    "/pending-doctors",
    response_model=list[PendingDoctorOut],
    summary="List doctors awaiting admin approval",
)
async def list_pending_doctors(
    _admin: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[User]:
    result = await db.scalars(
        select(User).where(User.role == UserRole.PENDING_DOCTOR).order_by(User.created_at)
    )
    return list(result.all())


@router.patch(
    "/users/{user_id}/promote-to-doctor",
    response_model=PendingDoctorOut,
    summary="Approve a pending doctor",
)
async def promote_to_doctor(
    user_id: UUID,
    _admin: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.role != UserRole.PENDING_DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not a pending doctor",
        )

    user.role = UserRole.DOCTOR
    user.is_approved = True
    await db.commit()
    await db.refresh(user)
    return user
