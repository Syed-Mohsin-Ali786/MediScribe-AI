from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import hash_password
from app.dependencies.auth import require_role
from app.models.report import Report, ReportStatus
from app.models.user import User, UserRole
from app.schemas.admin import (
    AdminAnalytics,
    AdminDoctorCreate,
    AdminStats,
    AdminUserOut,
    AdminUserUpdate,
    DailyReportPoint,
    DailyUserPoint,
    DoctorReportBreakdown,
    IntegrationsStatus,
)
from app.schemas.user import PendingDoctorOut
from app.services.avatar import save_avatar
from app.services.integrations import check_integrations

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get(
    "/pending-doctors",
    response_model=list[PendingDoctorOut],
    summary="List doctors awaiting admin approval (who requested permission)",
)
async def list_pending_doctors(
    _admin: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[User]:
    result = await db.scalars(
        select(User)
        .where(
            User.role == UserRole.PENDING_DOCTOR,
            User.permission_requested.is_(True),
        )
        .order_by(User.created_at)
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


@router.delete(
    "/users/{user_id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reject a pending doctor",
)
async def reject_doctor(
    user_id: UUID,
    _admin: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.role != UserRole.PENDING_DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not a pending doctor",
        )

    await db.delete(user)
    await db.commit()


@router.post(
    "/users/{user_id}/avatar",
    response_model=AdminUserOut,
    summary="Upload a profile photo for a doctor (admin-managed)",
)
async def upload_user_avatar(
    user_id: UUID,
    file: Annotated[UploadFile, "Profile photo (jpg/png/webp/gif, max 5 MB)"],
    _admin: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminUserOut:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.role not in {UserRole.DOCTOR, UserRole.PENDING_DOCTOR}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only doctors can have a profile photo",
        )
    try:
        user.avatar_url = save_avatar(file, str(user.id))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(user)
    return AdminUserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        is_approved=user.is_approved,
        specialization=user.specialization,
        avatar_url=user.avatar_url,
        permission_requested=user.permission_requested,
        doctor_id=user.doctor_id,
        report_count=0,
        dob=user.dob,
        created_at=user.created_at,
    )


@router.post(
    "/doctors",
    response_model=AdminUserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a doctor directly (admin onboarding — no self-registration)",
)
async def create_doctor(
    payload: AdminDoctorCreate,
    _admin: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminUserOut:
    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    doctor = User(
        name=payload.name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        specialization=payload.specialization,
        role=UserRole.DOCTOR,
        is_approved=True,
    )
    db.add(doctor)
    await db.commit()
    await db.refresh(doctor)
    return AdminUserOut(
        id=doctor.id,
        name=doctor.name,
        email=doctor.email,
        role=doctor.role,
        is_approved=doctor.is_approved,
        specialization=doctor.specialization,
        avatar_url=doctor.avatar_url,
        permission_requested=doctor.permission_requested,
        created_at=doctor.created_at,
    )


@router.patch(
    "/users/{user_id}",
    response_model=AdminUserOut,
    summary="Edit a doctor (name, email, specialization, password)",
)
async def update_user(
    user_id: UUID,
    payload: AdminUserUpdate,
    _admin: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminUserOut:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.role != UserRole.DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only doctors can be edited — patients are managed by their doctor",
        )

    if payload.email is not None and payload.email != user.email:
        clash = await db.scalar(select(User).where(User.email == payload.email))
        if clash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already in use",
            )
        user.email = payload.email
    if payload.name is not None:
        user.name = payload.name
    if payload.specialization is not None:
        user.specialization = payload.specialization or None
    if payload.password:
        user.hashed_password = hash_password(payload.password)

    await db.commit()
    await db.refresh(user)

    doctor_name: str | None = None
    if user.doctor_id:
        linked = await db.get(User, user.doctor_id)
        doctor_name = linked.name if linked else None
    report_count = (
        await db.scalar(
            select(func.count()).select_from(Report).where(Report.doctor_id == user.id)
        )
        or 0
    )
    return AdminUserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        is_approved=user.is_approved,
        specialization=user.specialization,
        avatar_url=user.avatar_url,
        permission_requested=user.permission_requested,
        doctor_id=user.doctor_id,
        doctor_name=doctor_name,
        report_count=int(report_count),
        dob=user.dob,
        created_at=user.created_at,
    )


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a doctor or patient",
)
async def delete_user(
    user_id: UUID,
    _admin: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.role not in {UserRole.DOCTOR, UserRole.PATIENT}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only doctors and patients can be deleted",
        )

    if user.role == UserRole.DOCTOR:
        linked_patients = (
            await db.scalar(select(func.count()).select_from(User).where(User.doctor_id == user.id))
            or 0
        )
        if linked_patients:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Doctor has linked patients — delete or reassign them first",
            )
        doctor_reports = (
            await db.scalar(
                select(func.count()).select_from(Report).where(Report.doctor_id == user.id)
            )
            or 0
        )
        if doctor_reports:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Doctor has reports — delete them first",
            )

    await db.delete(user)
    await db.commit()


@router.get(
    "/stats",
    response_model=AdminStats,
    summary="Platform-wide live counts",
)
async def platform_stats(
    _admin: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminStats:
    total_users = await db.scalar(select(func.count()).select_from(User)) or 0
    doctors = (
        await db.scalar(
            select(func.count()).select_from(User).where(User.role == UserRole.DOCTOR)
        )
        or 0
    )
    pending = (
        await db.scalar(
            select(func.count()).select_from(User).where(User.role == UserRole.PENDING_DOCTOR)
        )
        or 0
    )
    patients = (
        await db.scalar(
            select(func.count()).select_from(User).where(User.role == UserRole.PATIENT)
        )
        or 0
    )
    reports = await db.scalar(select(func.count()).select_from(Report)) or 0
    approved = (
        await db.scalar(
            select(func.count()).select_from(Report).where(Report.status == ReportStatus.APPROVED)
        )
        or 0
    )
    draft = (
        await db.scalar(
            select(func.count()).select_from(Report).where(Report.status == ReportStatus.DRAFT_GENERATED)
        )
        or 0
    )
    return AdminStats(
        total_users=total_users,
        doctors=doctors,
        pending_doctors=pending,
        patients=patients,
        reports=reports,
        approved_reports=approved,
        draft_reports=draft,
    )


@router.get(
    "/users",
    response_model=list[AdminUserOut],
    summary="Directory of all doctors and patients",
)
async def list_all_users(
    _admin: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AdminUserOut]:
    result = await db.scalars(
        select(User)
        .where(User.role.in_([UserRole.DOCTOR, UserRole.PATIENT, UserRole.PENDING_DOCTOR]))
        .order_by(User.created_at.desc())
    )
    users = list(result.all())

    doctor_names = {u.id: u.name for u in users if u.role == UserRole.DOCTOR}
    counts = dict(
        (await db.execute(select(Report.doctor_id, func.count(Report.id)).group_by(Report.doctor_id)))
        .all()
    )
    return [
        AdminUserOut(
            id=u.id,
            name=u.name,
            email=u.email,
            role=u.role,
            is_approved=u.is_approved,
            specialization=u.specialization,
            avatar_url=u.avatar_url,
            permission_requested=u.permission_requested,
            doctor_id=u.doctor_id,
            doctor_name=doctor_names.get(u.doctor_id),
            report_count=int(counts.get(u.id, 0) or 0),
            dob=u.dob,
            created_at=u.created_at,
        )
        for u in users
    ]


@router.get(
    "/integrations",
    response_model=IntegrationsStatus,
    summary="Live status of external API keys and services",
)
async def integration_status(
    _admin: Annotated[User, Depends(require_role(UserRole.ADMIN))],
) -> IntegrationsStatus:
    return IntegrationsStatus(**await check_integrations())


@router.get(
    "/analytics",
    response_model=AdminAnalytics,
    summary="Time-series analytics for the admin dashboard",
)
async def platform_analytics(
    _admin: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminAnalytics:
    reports = list((await db.scalars(select(Report))).all())
    users = list((await db.scalars(select(User))).all())

    today = datetime.now(UTC).date()
    days = [today - timedelta(days=i) for i in range(13, -1, -1)]

    report_buckets = {d.isoformat(): {"generated": 0, "approved": 0} for d in days}
    for r in reports:
        key = r.created_at.date().isoformat()
        if key in report_buckets:
            report_buckets[key]["generated"] += 1
        if r.status == ReportStatus.APPROVED and r.approved_at:
            akey = r.approved_at.date().isoformat()
            if akey in report_buckets:
                report_buckets[akey]["approved"] += 1

    user_buckets = {d.isoformat(): {"new_users": 0} for d in days}
    for u in users:
        key = u.created_at.date().isoformat()
        if key in user_buckets:
            user_buckets[key]["new_users"] += 1

    doctor_count = sum(1 for u in users if u.role == UserRole.DOCTOR)
    patient_count = sum(1 for u in users if u.role == UserRole.PATIENT)
    users_over_time: list[DailyUserPoint] = []
    for d in days:
        key = d.isoformat()
        users_over_time.append(
            DailyUserPoint(
                date=key,
                new_users=user_buckets[key]["new_users"],
                doctors=sum(1 for u in users if u.role == UserRole.DOCTOR and u.created_at.date() <= d),
                patients=sum(1 for u in users if u.role == UserRole.PATIENT and u.created_at.date() <= d),
            )
        )

    by_doctor: dict[UUID, DoctorReportBreakdown] = {}
    doctor_names: dict[UUID, str] = {}
    for u in users:
        if u.role == UserRole.DOCTOR:
            doctor_names[u.id] = u.name
    for r in reports:
        entry = by_doctor.setdefault(
            r.doctor_id,
            DoctorReportBreakdown(doctor_name=doctor_names.get(r.doctor_id, "Unknown"), total=0, approved=0),
        )
        entry.total += 1
        if r.status == ReportStatus.APPROVED:
            entry.approved += 1

    approved_count = sum(1 for r in reports if r.status == ReportStatus.APPROVED)
    draft_count = sum(1 for r in reports if r.status == ReportStatus.DRAFT_GENERATED)
    approval_rate = round((approved_count / len(reports) * 100) if reports else 0.0, 1)

    return AdminAnalytics(
        reports_over_time=[
            DailyReportPoint(date=k, **v) for k, v in report_buckets.items()
        ],
        users_over_time=users_over_time,
        reports_by_doctor=sorted(by_doctor.values(), key=lambda b: b.total, reverse=True),
        totals=AdminStats(
            total_users=len(users),
            doctors=doctor_count,
            pending_doctors=sum(1 for u in users if u.role == UserRole.PENDING_DOCTOR),
            patients=patient_count,
            reports=len(reports),
            approved_reports=approved_count,
            draft_reports=draft_count,
        ),
        approval_rate=approval_rate,
    )
