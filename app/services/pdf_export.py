# pyright: reportArgumentType=false, reportCallIssue=false
from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)
from reportlab.platypus.flowables import Flowable

from app.models.report import Report
from app.models.user import User

BLUE = colors.HexColor("#2563eb")
GREY = colors.HexColor("#666666")


def _bullet_list(items: list[str] | None, style: ParagraphStyle) -> ListFlowable | None:
    if not items:
        return None
    return ListFlowable(
        [ListItem(Paragraph(item, style), leftIndent=18, value="\u2022") for item in items],
        bulletType="bullet",
        start="\u2022",
    )


def _medication_lines(medications: list[dict[str, Any]] | None, style: ParagraphStyle) -> ListFlowable | None:
    if not medications:
        return None
    lines: list[ListItem] = []
    for med in medications:
        name = med.get("name", "Unknown")
        details = " \u2014 ".join(
            str(med[k]) for k in ("dosage", "frequency", "duration") if med.get(k)
        )
        lines.append(ListItem(Paragraph(f"{name} ({details})" if details else name, style)))
    return ListFlowable(lines, bulletType="bullet", start="\u2022")


def generate_report_pdf(report: Report, patient: User, doctor: User) -> BytesIO:
    extraction: dict[str, Any] = report.extraction_json or {}
    soap: dict[str, str] = extraction.get("soap", {})
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitleX", parent=styles["Title"], fontSize=20, textColor=BLUE, spaceAfter=4
    )
    sub_style = ParagraphStyle(
        "SubtitleX", parent=styles["Normal"], fontSize=10, textColor=GREY, alignment=TA_CENTER
    )
    meta_style = ParagraphStyle("MetaX", parent=styles["Normal"], fontSize=10, spaceAfter=2)
    section_style = ParagraphStyle(
        "SectionX", parent=styles["Heading2"], fontSize=13, textColor=BLUE, spaceBefore=16
    )
    body_style = ParagraphStyle("BodyX", parent=styles["Normal"], fontSize=10, leading=14)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.9 * inch,
        leftMargin=0.9 * inch,
        topMargin=0.9 * inch,
        bottomMargin=0.9 * inch,
        title=f"MediScribe Report {report.id}",
    )

    approved_at = (report.approved_at or datetime.now(UTC)).strftime("%Y-%m-%d %H:%M UTC")

    story: list[Flowable] = [
        Paragraph("MediScribe AI \u2014 Medical Consultation Report", title_style),
        Paragraph("AI-generated draft, reviewed and approved by the attending physician", sub_style),
        Spacer(1, 10),
        HRFlowable(width="100%", thickness=1.2, color=BLUE),
        Spacer(1, 12),
        Paragraph(f"<b>Report ID:</b> {report.id}", meta_style),
        Paragraph(f"<b>Patient:</b> {patient.name}", meta_style),
        Paragraph(
            f"<b>Doctor:</b> {doctor.name}"
            + (f" ({doctor.specialization})" if doctor.specialization else ""),
            meta_style,
        ),
        Paragraph(f"<b>Approved at:</b> {approved_at}", meta_style),
        Spacer(1, 8),
    ]

    story.append(Paragraph("SOAP Note", section_style))
    for label in ("subjective", "objective", "assessment", "plan"):
        value = soap.get(label, "N/A")
        story.append(Paragraph(f"<b>{label.capitalize()}:</b><br/>{value}", body_style))
        story.append(Spacer(1, 4))

    story.append(Paragraph("Diagnosis", section_style))
    story.append(Paragraph(str(extraction.get("diagnosis", "N/A")), body_style))

    def add_section(title: str, items: ListFlowable | None) -> None:
        if items is not None:
            story.append(Paragraph(title, section_style))
            story.append(items)

    add_section("Symptoms", _bullet_list(extraction.get("symptoms"), body_style))
    add_section("Medical History", _bullet_list(extraction.get("medical_history"), body_style))
    add_section("Medications", _medication_lines(extraction.get("medications"), body_style))
    add_section("Recommendations", _bullet_list(extraction.get("recommendations"), body_style))

    highlights = _bullet_list(extraction.get("highlights"), body_style)
    follow_up = _bullet_list(extraction.get("follow_up_points"), body_style)
    if highlights or follow_up:
        story.append(Paragraph("Highlights & Follow-up", section_style))
        if highlights:
            story.append(Paragraph("<b>Highlights:</b>", body_style))
            story.append(highlights)
            story.append(Spacer(1, 4))
        if follow_up:
            story.append(Paragraph("<b>Follow-up points:</b>", body_style))
            story.append(follow_up)

    flags: list[dict[str, str]] = extraction.get("confidence_flags") or []
    if flags:
        story.append(Paragraph("Confidence flags", section_style))
        flag_lines = _bullet_list(
            [f"{f.get('field')}: {f.get('reason')}" for f in flags], body_style
        )
        if flag_lines:
            story.append(flag_lines)

    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.8, color=GREY))
    story.append(
        Paragraph(
            "Generated by MediScribe AI. This report was reviewed and approved by the "
            "attending physician.",
            ParagraphStyle("FooterX", parent=styles["Normal"], fontSize=9, textColor=GREY),
        )
    )

    doc.build(story)
    buffer.seek(0)
    return buffer
