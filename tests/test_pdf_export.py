from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO

from app.models.report import Report, ReportStatus
from app.models.user import User
from app.services.pdf_export import generate_report_pdf


def _sample_report() -> Report:
    return Report(
        id="12345678-1234-1234-1234-123456789012",
        patient_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        doctor_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        audio_url="local://audio/demo.webm",
        extraction_json={
            "symptoms": ["sore throat", "fever"],
            "diagnosis": "Acute pharyngitis",
            "medications": [
                {
                    "name": "acetaminophen",
                    "dosage": "500 mg",
                    "frequency": "every 6 hours",
                    "duration": "3 days",
                }
            ],
            "recommendations": ["Rest", "Hydration"],
            "soap": {
                "subjective": "Sore throat and fever for two days.",
                "objective": "No exam data.",
                "assessment": "Acute pharyngitis.",
                "plan": "Acetaminophen and rest.",
            },
            "highlights": ["Fever present"],
            "follow_up_points": ["Return if fever persists"],
            "confidence_flags": [{"field": "objective", "reason": "No exam data"}],
        },
        status=ReportStatus.APPROVED,
        approved_at=datetime.now(UTC),
    )


def test_generate_report_pdf_returns_pdf() -> None:
    patient = User(
        id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        name="Jamie Morgan",
        email="patient@mediscribe.ai",
        hashed_password="",
        role="patient",
        is_approved=True,
    )
    doctor = User(
        id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        name="Dr. Alex Rivera",
        email="doctor@mediscribe.ai",
        hashed_password="",
        role="doctor",
        is_approved=True,
        specialization="General Practice",
    )

    result = generate_report_pdf(_sample_report(), patient, doctor)
    assert isinstance(result, BytesIO)
    data = result.getvalue()
    assert data.startswith(b"%PDF")
