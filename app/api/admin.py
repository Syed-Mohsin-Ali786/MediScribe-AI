from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import require_role
from app.models.report import Report, ReportStatus
from app.models.user import User, UserRole
from app.schemas.admin import (
    AdminAnalytics,
    AdminStats,
    AdminUserOut,
    DailyReportPoint,
    DailyUserPoint,
    DoctorReportBreakdown,
    IntegrationsStatus,
)
from app.schemas.user import PendingDoctorOut
from app.services.integrations import check_integrations

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
            doctor_id=u.doctor_id,
            doctor_name=doctor_names.get(u.doctor_id),
            report_count=int(counts.get(u.id, 0) or 0),
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
