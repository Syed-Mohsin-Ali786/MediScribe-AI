from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User, UserRole

security = HTTPBearer(auto_error=False)


credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

role_exception = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Insufficient permissions",
)

approval_exception = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Doctor account is pending admin approval",
)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if not credentials:
        raise credentials_exception

    try:
        payload = decode_access_token(credentials.credentials)
    except ValueError as exc:
        raise credentials_exception from exc

    user_id = payload.get("user_id") or payload.get("sub")
    if not user_id:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    return current_user


def require_role(*allowed_roles: UserRole):
    async def role_checker(
        current_user: Annotated[User, Depends(get_current_active_user)],
    ) -> User:
        if current_user.role not in allowed_roles:
            raise role_exception
        return current_user

    return role_checker


async def require_approved_doctor(
    current_user: Annotated[User, Depends(require_role(UserRole.DOCTOR))],
) -> User:
    if not current_user.is_approved:
        raise approval_exception
    return current_user


async def require_doctor_or_admin(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    if current_user.role not in {UserRole.DOCTOR, UserRole.ADMIN}:
        raise role_exception
    return current_user
