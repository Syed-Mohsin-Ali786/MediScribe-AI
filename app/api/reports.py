from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import require_approved_doctor, require_role
from app.models.report import Report, ReportStatus
from app.models.user import User, UserRole
from app.schemas.report import (
    ApprovedReportListItem,
    ReportApprovalResponse,
    ReportOut,
    ReportUpdate,
)
from app.services.extraction import extract_clinical
from app.services.medication_validation import validate_medications
from app.services.pdf_export import generate_report_pdf
from app.services.supabase_storage import upload_audio_placeholder
from app.services.transcription import transcribe_audio

router = APIRouter(tags=["reports"])

NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
FORBIDDEN = HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


async def _fetch_report(
    report_id: UUID,
    user: User,
    db: AsyncSession,
) -> Report:
    report = await db.get(Report, report_id)
    if report is None:
        raise NOT_FOUND

    if user.role == UserRole.DOCTOR:
        if report.doctor_id != user.id:
            raise FORBIDDEN
    elif user.role == UserRole.PATIENT:
        if report.patient_id != user.id:
            raise FORBIDDEN
        if report.status != ReportStatus.APPROVED:
            raise FORBIDDEN
    else:
        raise FORBIDDEN
    return report


@router.post(
    "/generate-report",
    response_model=ReportOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload audio → transcribe → extract → validate → persist draft",
)
async def generate_report(
    patient_id: Annotated[UUID, Form()],
    audio: Annotated[UploadFile, File()],
    doctor: Annotated[User, Depends(require_approved_doctor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Report:
    patient = await db.get(User, patient_id)
    if patient is None or patient.role != UserRole.PATIENT or patient.doctor_id != doctor.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    file_bytes = await audio.read()

    transcript = await transcribe_audio(file_bytes, audio.filename or "consultation.webm")
    extraction = await extract_clinical(transcript)
    validation = await validate_medications(extraction.get("medications", []))
    audio_url = upload_audio_placeholder(file_bytes, audio.filename or "consultation.webm")

    report = Report(
        patient_id=patient.id,
        doctor_id=doctor.id,
        audio_url=audio_url,
        transcript_json=transcript,
        extraction_json=extraction,
        validation_flags=validation,
        status=ReportStatus.DRAFT_GENERATED,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report


@router.get(
    "/records/{report_id}",
    response_model=ReportOut,
    summary="Fetch a report (doctor own, or patient own approved)",
)
async def get_report(
    report_id: UUID,
    user: Annotated[User, Depends(require_role(UserRole.DOCTOR, UserRole.PATIENT))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Report:
    return await _fetch_report(report_id, user, db)


@router.patch(
    "/records/{report_id}",
    response_model=ReportOut,
    summary="Edit draft report fields (doctor only)",
)
async def update_report(
    report_id: UUID,
    payload: ReportUpdate,
    doctor: Annotated[User, Depends(require_approved_doctor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Report:
    report = await _fetch_report(report_id, doctor, db)
    if report.status == ReportStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Approved reports cannot be edited",
        )

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(report, field, value)
    await db.commit()
    await db.refresh(report)
    return report


@router.post(
    "/records/{report_id}/approve",
    response_model=ReportApprovalResponse,
    summary="Approve and finalize a draft report",
)
async def approve_report(
    report_id: UUID,
    doctor: Annotated[User, Depends(require_approved_doctor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReportApprovalResponse:
    report = await _fetch_report(report_id, doctor, db)
    report.approve()
    await db.commit()
    await db.refresh(report)
    return ReportApprovalResponse(
        id=report.id,
        status=report.status,
        approved_at=report.approved_at,
    )


@router.get(
    "/records/{report_id}/pdf",
    summary="Export an approved report as PDF",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def export_report_pdf(
    report_id: UUID,
    user: Annotated[User, Depends(require_role(UserRole.DOCTOR, UserRole.PATIENT))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    report = await _fetch_report(report_id, user, db)
    if report.status != ReportStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Report must be approved before PDF export",
        )

    patient = await db.get(User, report.patient_id)
    doctor = await db.get(User, report.doctor_id)
    pdf = generate_report_pdf(report, patient, doctor)

    return Response(
        content=pdf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="report-{report.id}.pdf"'},
    )


@router.get(
    "/patient/reports",
    response_model=list[ApprovedReportListItem],
    summary="List own approved reports (patient only)",
)
async def list_patient_reports(
    patient: Annotated[User, Depends(require_role(UserRole.PATIENT))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Report]:
    from sqlalchemy import select

    result = await db.scalars(
        select(Report)
        .where(Report.patient_id == patient.id, Report.status == ReportStatus.APPROVED)
        .order_by(Report.approved_at)
    )
    return list(result.all())
