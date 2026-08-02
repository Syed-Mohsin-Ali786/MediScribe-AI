# pyright: reportArgumentType=false, reportCallIssue=false
from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import Flowable

from app.models.report import Report
from app.models.user import User

PAGE_W, PAGE_H = A4

DEEP_NAVY = colors.HexColor("#0f172a")
TEAL = colors.HexColor("#0d9488")
SLATE = colors.HexColor("#475569")
SLATE_LIGHT = colors.HexColor("#94a3b8")
BORDER = colors.HexColor("#e2e8f0")
AMBER = colors.HexColor("#d97706")
ROSE = colors.HexColor("#e11d48")
GREEN = colors.HexColor("#16a34a")

MARGIN = 0.7 * inch


class _StripeBar(Flowable):
    """A full-width coloured bar."""

    def __init__(self, width: float, height: float, color: colors.Color):
        Flowable.__init__(self)
        self.width = width
        self.height = height
        self._color = color

    def draw(self) -> None:
        self.canv.setFillColor(self._color)
        self.canv.rect(0, 0, self.width, self.height, fill=1, stroke=0)


def _hrule(width: float, color: colors.Color, thickness: float = 0.6) -> HRFlowable:
    return HRFlowable(width="100%", thickness=thickness, color=color, spaceAfter=0, spaceBefore=0)


def _styled_table(data: list[list[Any]], col_widths: list[float] | None = None) -> Table:
    t = Table(data, colWidths=col_widths, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, BORDER),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ]
        )
    )
    return t


def _label_cell(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(f"<b>{text}</b>", style)


def _norm_list(value: Any) -> list[str]:
    """Normalize a list field that may be a single string, a list, or None."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(x) for x in value]


def _details_table(patient: User, doctor: User, report: Report, styles: dict[str, ParagraphStyle], avail: float) -> Table:
    """A clean label → value table (Name / Email / DOB / …) for patient, doctor and report metadata."""

    approved_at = (report.approved_at or datetime.now(UTC)).strftime("%d %B %Y, %H:%M UTC")
    report_date = (report.created_at or datetime.now(UTC)).strftime("%d %B %Y")
    report_id = str(report.id)
    dob = patient.dob.strftime("%d %B %Y") if patient.dob else "—"

    def row(label: str, value: str) -> list[Flowable]:
        return [
            _label_cell(label, styles["label"]),
            Paragraph(value, styles["body"]),
        ]

    # Two side-by-side boxes: patient info | doctor info. Each box has 2 columns
    # (label | value), with the section header spanning both.
    def box_rows(header: str, pairs: list[tuple[str, str]]) -> list[list[Flowable]]:
        rows: list[list[Flowable]] = [[_label_cell(header, styles["section"])]]
        for label, value in pairs:
            rows.append(row(label, value))
        return rows

    left_rows = box_rows(
        "PATIENT",
        [("Name", patient.name), ("Email", patient.email), ("DOB", dob)],
    )
    right_rows = box_rows(
        "ATTENDING PHYSICIAN",
        [
            ("Name", doctor.name),
            ("Email", doctor.email),
            ("Specialization", doctor.specialization or "General Practice"),
        ],
    )

    def boxed(rows: list[list[Flowable]], width: float) -> Table:
        t = Table(rows, colWidths=[width * 0.32, width * 0.68], hAlign="LEFT")
        t.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("SPAN", (0, 0), (1, 0)),
                    ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, BORDER),
                ]
            )
        )
        return t

    # Patient + doctor tables side by side.
    side = Table(
        [[boxed(left_rows, avail * 0.5), boxed(right_rows, avail * 0.5)]],
        colWidths=[avail * 0.5, avail * 0.5],
        hAlign="LEFT",
    )
    side.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 8)]))

    # Report metadata below, full width (2-col label|value, header spanning).
    meta_rows = box_rows(
        "REPORT DETAILS",
        [
            ("Report ID", report_id),
            ("Generated", report_date),
            ("Approved", approved_at),
            ("Status", "Approved"),
        ],
    )
    meta = boxed(meta_rows, avail)

    outer = Table(
        [[side], [meta]],
        colWidths=[avail],
        hAlign="LEFT",
    )
    outer.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return outer


def _build_story(
    report: Report,
    patient: User,
    doctor: User,
    extraction: dict[str, Any],
    soap: dict[str, str],
    styles: dict[str, ParagraphStyle],
) -> list[Flowable]:
    """One continuous story: header → report details → SOAP → primary diagnosis → all clinical detail."""

    avail = PAGE_W - 2 * MARGIN
    story: list[Flowable] = []

    # ── Header ──
    story.append(_StripeBar(avail, 4, TEAL))
    story.append(Spacer(1, 14))
    story.append(
        Paragraph(
            "MediScribe AI",
            ParagraphStyle(
                "Wordmark",
                parent=styles["h1"],
                fontSize=11,
                fontName="Helvetica-Bold",
                textColor=DEEP_NAVY,
                letterSpacing=2.5,
            ),
        )
    )
    story.append(Spacer(1, 2))
    story.append(
        Paragraph(
            "Clinical Consultation Report",
            ParagraphStyle(
                "CoverTag",
                parent=styles["body"],
                fontSize=22,
                fontName="Helvetica-Bold",
                textColor=DEEP_NAVY,
                leading=26,
            ),
        )
    )
    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            "AI-generated draft, reviewed and approved by the attending physician",
            ParagraphStyle("CoverSub", parent=styles["body"], fontSize=9, textColor=SLATE_LIGHT),
        )
    )
    story.append(Spacer(1, 14))
    story.append(_hrule(avail, BORDER))
    story.append(Spacer(1, 14))

    # ── Report Details (label → value) ──
    story.append(_details_table(patient, doctor, report, styles, avail))
    story.append(Spacer(1, 18))

    # ── Primary Diagnosis highlight box ──
    diagnoses = _norm_list(extraction.get("diagnosis"))
    if diagnoses:
        diag_block: list[Flowable] = [_StripeBar(avail, 3, AMBER)]
        diag_block.append(Spacer(1, 8))
        diag_block.append(
            Paragraph(
                "PRIMARY DIAGNOSIS",
                ParagraphStyle(
                    "DiagHdr",
                    parent=styles["label"],
                    fontSize=10.5,
                    leading=13,
                    fontName="Helvetica-Bold",
                    textColor=DEEP_NAVY,
                    letterSpacing=1.5,
                ),
            )
        )
        diag_block.append(Spacer(1, 4))
        for i, d in enumerate(diagnoses):
            diag_block.append(
                Paragraph(
                    f'<font color="{DEEP_NAVY}" size="10"><b>●</b> {d}</font>',
                    ParagraphStyle(f"DiagItem{i}", fontSize=10, leading=15),
                )
            )
        diag_block.append(Spacer(1, 2))
        diag_block.append(_hrule(avail, AMBER))
        story.append(KeepTogether(diag_block))
        story.append(Spacer(1, 16))

    # ── SOAP Note block ──
    story.append(_StripeBar(avail, 3, TEAL))
    story.append(Spacer(1, 12))
    story.append(Paragraph("SOAP Note", styles["section"]))
    story.append(Spacer(1, 10))

    soap_sections = [
        ("S", "Subjective", soap.get("subjective", "N/A")),
        ("O", "Objective", soap.get("objective", "N/A")),
        ("A", "Assessment", soap.get("assessment", "N/A")),
        ("P", "Plan", soap.get("plan", "N/A")),
    ]
    supporting = {
        "S": "symptoms",
        "O": "medical_history",
        "A": "diagnosis",
        "P": "recommendations",
    }

    for letter, title, body in soap_sections:
        extra_items = _norm_list(extraction.get(supporting[letter]))
        body_lines = [line.strip() for line in body.splitlines() if line.strip()] if body != "N/A" else []

        inner: list[Flowable] = []
        inner.append(
            Paragraph(
                f'<font fontName="Helvetica-Bold" color="{DEEP_NAVY}" size="9.5">{title}</font>',
                ParagraphStyle(f"SoapTitle{letter}", fontSize=9.5, leading=12),
            )
        )
        inner.append(Spacer(1, 3))
        if body_lines:
            inner.append(
                Paragraph(
                    f'<font color="{SLATE}" size="9">{body}</font>',
                    ParagraphStyle(f"SoapBody{letter}", fontSize=9, leading=13),
                )
            )
        for item in extra_items:
            inner.append(Spacer(1, 2))
            inner.append(
                Paragraph(
                    f'<font color="{TEAL}" size="8.5">•</font>  '
                    f'<font color="{SLATE}" size="8.5">{item}</font>',
                    ParagraphStyle(f"SoapExtra{letter}", fontSize=8.5, leading=12),
                )
            )

        data = [
            [
                Paragraph(
                    f'<font fontName="Helvetica-Bold" color="white" size="13">{letter}</font>',
                    ParagraphStyle(f"SoapChip{letter}", fontSize=13, leading=16, alignment=TA_CENTER),
                ),
                inner,
            ]
        ]
        chip_w = avail * 0.07
        t = Table(data, colWidths=[chip_w, avail - chip_w], hAlign="LEFT")
        t.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
                    ("VALIGN", (1, 0), (1, 0), "TOP"),
                    ("BACKGROUND", (0, 0), (0, 0), TEAL),
                    ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#f8fafc")),
                    ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
                    ("INNERGRID", (0, 0), (0, 0), 0.6, BORDER),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (0, 0), 0),
                    ("RIGHTPADDING", (0, 0), (0, 0), 0),
                    ("LEFTPADDING", (1, 0), (1, 0), 10),
                    ("RIGHTPADDING", (1, 0), (1, 0), 10),
                ]
            )
        )
        story.append(KeepTogether(t))
        story.append(Spacer(1, 8))

    story.append(Spacer(1, 14))

    # ── Clinical Details & Supporting Data ──
    story.append(_StripeBar(avail, 3, TEAL))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Clinical Details & Supporting Data", styles["section"]))
    story.append(Spacer(1, 8))

    # Medications table
    medications: list[dict[str, Any]] = extraction.get("medications") or []
    if medications:
        story.append(Paragraph("Medications", styles["subsection"]))
        story.append(Spacer(1, 4))
        med_rows = [
            [
                _label_cell("Medication", styles["label"]),
                _label_cell("Dosage", styles["label"]),
                _label_cell("Frequency", styles["label"]),
                _label_cell("RxNorm", styles["label"]),
            ]
        ]
        for m in medications:
            status = m.get("rxnorm_status", "—")
            badge = {
                "valid": f'<font color="{GREEN}">✓ valid</font>',
                "unrecognized": f'<font color="{ROSE}">✗ unrecognized</font>',
                "warning": f'<font color="{AMBER}">⚠ review</font>',
            }.get(status, f'<font color="{SLATE_LIGHT}">—</font>')
            note = m.get("rxnorm_note", "")
            med_rows.append(
                [
                    Paragraph(str(m.get("name", "")), styles["body"]),
                    Paragraph(str(m.get("dosage", "—")), styles["body"]),
                    Paragraph(str(m.get("frequency", "—")), styles["body"]),
                    Paragraph(f"{badge}<br/><font size='7' color='{SLATE_LIGHT}'>{note}</font>", styles["small"]),
                ]
            )
        story.append(
            _styled_table(med_rows, [avail * 0.28, avail * 0.22, avail * 0.22, avail * 0.24])
        )
        story.append(Spacer(1, 16))

    # Symptoms / History / Recommendations in two-column
    symptoms = _norm_list(extraction.get("symptoms"))
    history = _norm_list(extraction.get("medical_history"))
    recs = _norm_list(extraction.get("recommendations"))

    col_data: list[list[Flowable]] = [
        [
            Paragraph("<b>Symptoms</b>", styles["body"]),
            Paragraph("<b>Medical History</b>", styles["body"]),
        ]
    ]
    max_rows = max(len(symptoms), len(history), 1)
    for i in range(max_rows):
        s = symptoms[i] if i < len(symptoms) else ""
        h = history[i] if i < len(history) else ""
        col_data.append(
            [
                Paragraph(f'<font size="9">● {s}</font>' if s else "", styles["small"]),
                Paragraph(f'<font size="9">● {h}</font>' if h else "", styles["small"]),
            ]
        )
    story.append(_styled_table(col_data, [avail * 0.48, avail * 0.48]))
    story.append(Spacer(1, 16))

    add_section("Symptoms", _bullet_list(extraction.get("symptoms"), body_style))
    add_section("Medical History", _bullet_list(extraction.get("medical_history"), body_style))
    add_section("Medications", _medication_lines(extraction.get("medications"), body_style))
    add_section("Recommendations", _bullet_list(extraction.get("recommendations"), body_style))

    # Highlights + Follow-up
    highlights = _norm_list(extraction.get("highlights"))
    follow_up = _norm_list(extraction.get("follow_up_points"))
    if highlights or follow_up:
        story.append(Paragraph("Clinical Summary", styles["subsection"]))
        story.append(Spacer(1, 4))
        hl_fu_data: list[list[Flowable]] = [
            [
                _label_cell("Key Highlights", styles["label"]),
                _label_cell("Follow-up Points", styles["label"]),
            ]
        ]
        max_hl = max(len(highlights), len(follow_up), 1)
        for i in range(max_hl):
            hl = highlights[i] if i < len(highlights) else ""
            fu = follow_up[i] if i < len(follow_up) else ""
            hl_fu_data.append(
                [
                    Paragraph(f'<font size="9">● {hl}</font>' if hl else "", styles["small"]),
                    Paragraph(f'<font size="9">● {fu}</font>' if fu else "", styles["small"]),
                ]
            )
        story.append(_styled_table(hl_fu_data, [avail * 0.48, avail * 0.48]))
        story.append(Spacer(1, 16))

    # Confidence flags
    flags: list[dict[str, Any]] = extraction.get("confidence_flags") or []
    if flags:
        story.append(Paragraph("AI Confidence Flags", styles["subsection"]))
        story.append(Spacer(1, 4))
        flag_rows: list[list[Flowable]] = [
            [_label_cell("Field", styles["label"]), _label_cell("Level", styles["label"]), _label_cell("Note", styles["label"])]
        ]
        for f in flags:
            level = str(f.get("level", "—"))
            level_color = {"high": GREEN, "medium": AMBER, "low": ROSE}.get(level, SLATE)
            flag_rows.append(
                [
                    Paragraph(str(f.get("field", "")), styles["small"]),
                    Paragraph(f'<font color="{level_color}">{level.upper()}</font>', styles["small"]),
                    Paragraph(str(f.get("note", "")), styles["small"]),
                ]
            )
        story.append(_styled_table(flag_rows, [avail * 0.22, avail * 0.16, avail * 0.58]))
        story.append(Spacer(1, 12))

    # Footer
    story.append(Spacer(1, 20))
    story.append(_hrule(avail, BORDER))
    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            "Generated by MediScribe AI — Clinical Documentation Platform — "
            "For demonstration only. No real patient data.",
            ParagraphStyle(
                "FooterX", parent=styles["body"], fontSize=7, textColor=SLATE_LIGHT, alignment=TA_CENTER
            ),
        )
    )

    return story


def _page_footer(canvas, doc) -> None:  # type: ignore[no-untyped-def]
    canvas.saveState()
    canvas.setFillColor(SLATE_LIGHT)
    canvas.setFont("Helvetica", 6)
    canvas.drawRightString(PAGE_W - MARGIN, 20, f"MediScribe AI · page {doc.page}")
    canvas.restoreState()


def generate_report_pdf(report: Report, patient: User, doctor: User) -> BytesIO:
    extraction: dict[str, Any] = report.extraction_json or {}
    soap: dict[str, str] = extraction.get("soap", {})

    base_styles = getSampleStyleSheet()
    styles: dict[str, ParagraphStyle] = {
        "h1": ParagraphStyle("H1x", parent=base_styles["Normal"], fontSize=18, leading=22, fontName="Helvetica-Bold", textColor=DEEP_NAVY),
        "body": ParagraphStyle("BodyX", parent=base_styles["Normal"], fontSize=9.5, leading=14, textColor=SLATE),
        "small": ParagraphStyle("SmallX", parent=base_styles["Normal"], fontSize=8.5, leading=12, textColor=SLATE),
        "label": ParagraphStyle("LabelX", parent=base_styles["Normal"], fontSize=8.5, leading=12, fontName="Helvetica-Bold", textColor=DEEP_NAVY),
        "section": ParagraphStyle("SecX", parent=base_styles["Normal"], fontSize=13, leading=16, fontName="Helvetica-Bold", textColor=DEEP_NAVY),
        "subsection": ParagraphStyle("SubX", parent=base_styles["Normal"], fontSize=10.5, leading=14, fontName="Helvetica-Bold", textColor=DEEP_NAVY),
    }

    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        title=f"MediScribe Report {report.id}",
        author=doctor.name,
        subject=f"Clinical report for {patient.name}",
    )

    frame = Frame(MARGIN, MARGIN, PAGE_W - 2 * MARGIN, PAGE_H - 2 * MARGIN, id="body")
    doc.addPageTemplates([PageTemplate(id="Body", frames=[frame], onPage=_page_footer)])

    story: list[Flowable] = _build_story(report, patient, doctor, extraction, soap, styles)
    doc.build(story)
    buffer.seek(0)
    return buffer
