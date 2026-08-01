from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token, verify_password
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse
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


@router.get(
    "/me",
    response_model=UserMe,
    summary="Current user profile",
)
async def me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    return current_user
