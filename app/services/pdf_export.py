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
    NextPageTemplate,
    PageBreak,
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

COVER_MARGIN = 0.6 * inch
BODY_MARGIN = 0.7 * inch


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


def _build_cover_story(
    report: Report,
    patient: User,
    doctor: User,
    extraction: dict[str, Any],
    soap: dict[str, str],
    styles: dict[str, ParagraphStyle],
) -> list[Flowable]:
    """Page 1: cover page with SOAP note as the hero."""

    avail = PAGE_W - 2 * COVER_MARGIN
    story: list[Flowable] = []

    # Top accent bar
    story.append(_StripeBar(avail, 4, TEAL))
    story.append(Spacer(1, 14))

    # MediScribe wordmark + tagline
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
    story.append(Spacer(1, 18))
    story.append(_hrule(avail, BORDER))
    story.append(Spacer(1, 16))

    # Patient & Doctor info cards
    approved_at = (report.approved_at or datetime.now(UTC)).strftime("%d %B %Y, %H:%M UTC")
    report_date = (report.created_at or datetime.now(UTC)).strftime("%d %B %Y")

    info_data = [
        [
            _label_cell("Patient", styles["label"]),
            _label_cell("Attending Physician", styles["label"]),
        ],
        [
            Paragraph(patient.name, styles["body"]),
            Paragraph(doctor.name, styles["body"]),
        ],
        [
            Paragraph(f"<font color='{SLATE}'>{patient.email}</font>", styles["body"]),
            Paragraph(
                f"<font color='{SLATE}'>{doctor.specialization or 'General Practice'}</font>",
                styles["body"],
            ),
        ],
        [
            Paragraph(
                f"<font color='{SLATE_LIGHT}'>DOB: {patient.dob.strftime('%d %B %Y') if patient.dob else '—'}</font>",
                styles["small"],
            ),
            Paragraph(f"<font color='{SLATE_LIGHT}'>{doctor.email}</font>", styles["small"]),
        ],
    ]
    story.append(Paragraph("Report Details", styles["section"]))
    story.append(Spacer(1, 8))
    story.append(_styled_table(info_data, [avail * 0.48, avail * 0.48]))
    story.append(Spacer(1, 10))

    meta_data = [
        [
            _label_cell("Report ID", styles["label"]),
            _label_cell("Generated", styles["label"]),
            _label_cell("Approved", styles["label"]),
            _label_cell("Status", styles["label"]),
        ],
        [
            Paragraph(str(report.id)[:8] + "…", styles["small"]),
            Paragraph(report_date, styles["small"]),
            Paragraph(approved_at, styles["small"]),
            Paragraph(
                f"<font color='{GREEN}'>● Approved</font>",
                styles["small"],
            ),
        ],
    ]
    story.append(_styled_table(meta_data, [avail * 0.28, avail * 0.24, avail * 0.28, avail * 0.16]))
    story.append(Spacer(1, 22))

    # ── SOAP Note block ──
    story.append(_StripeBar(avail, 3, TEAL))
    story.append(Spacer(1, 14))
    story.append(Paragraph("SOAP Note", styles["section"]))
    story.append(Spacer(1, 12))

    soap_sections = [
        ("S", "Subjective", soap.get("subjective", "N/A")),
        ("O", "Objective", soap.get("objective", "N/A")),
        ("A", "Assessment", soap.get("assessment", "N/A")),
        ("P", "Plan", soap.get("plan", "N/A")),
    ]

    for letter, title, body in soap_sections:
        left = avail * 0.08
        right = avail - left - 6
        data = [
            [
                Paragraph(
                    f'<font fontName="Helvetica-Bold" color="{TEAL}" size="18">{letter}</font>',
                    ParagraphStyle("SoapL", fontSize=18, leading=20),
                ),
                Paragraph(
                    f'<font fontName="Helvetica-Bold" size="10">{title}</font><br/>'
                    f'<font color="{SLATE}" size="9">{body}</font>',
                    ParagraphStyle("SoapR", fontSize=9, leading=13),
                ),
            ]
        ]
        t = Table(data, colWidths=[left, right], hAlign="LEFT")
        t.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (0, 0), 0),
                    ("LEFTPADDING", (1, 0), (1, 0), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, BORDER),
                ]
            )
        )
        story.append(t)

    story.append(Spacer(1, 18))

    # Diagnosis highlight
    diagnoses = extraction.get("diagnosis") or []
    if diagnoses:
        story.append(Paragraph("Primary Diagnosis", styles["section"]))
        story.append(Spacer(1, 6))
        for d in diagnoses:
            story.append(
                Paragraph(
                    f'<font color="{TEAL}" size="9">●</font>  '
                    f'<font color="{DEEP_NAVY}" size="10">{d}</font>',
                    ParagraphStyle("DiagItem", parent=styles["body"], fontSize=10, leading=14),
                )
            )
            story.append(Spacer(1, 2))

    story.append(Spacer(1, 14))
    story.append(
        Paragraph(
            "This report was generated by AI, reviewed by the attending physician, "
            "and approved for patient access.",
            ParagraphStyle(
                "Disclaimer", parent=styles["body"], fontSize=7.5, textColor=SLATE_LIGHT
            ),
        )
    )

    return story


def _build_detail_story(
    extraction: dict[str, Any],
    transcript: list[dict[str, Any]] | None,
    styles: dict[str, ParagraphStyle],
) -> list[Flowable]:
    """Page 2+: all clinical detail."""
    avail = PAGE_W - 2 * BODY_MARGIN
    story: list[Flowable] = []

    # Page 2 header
    story.append(_StripeBar(avail, 3, TEAL))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Clinical Details & Supporting Data", styles["section"]))
    story.append(Spacer(1, 8))

    # Medications table — detailed
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
                    Paragraph(m.get("name", ""), styles["body"]),
                    Paragraph(m.get("dosage", "—"), styles["body"]),
                    Paragraph(m.get("frequency", "—"), styles["body"]),
                    Paragraph(f"{badge}<br/><font size='7' color='{SLATE_LIGHT}'>{note}</font>", styles["small"]),
                ]
            )
        story.append(
            _styled_table(med_rows, [avail * 0.28, avail * 0.22, avail * 0.22, avail * 0.24])
        )
        story.append(Spacer(1, 16))

    # Symptoms / History / Recommendations in two-column
    symptoms = extraction.get("symptoms") or []
    history = extraction.get("medical_history") or []
    recs = extraction.get("recommendations") or []

    col_data: list[list[Flowable]] = []
    col_data.append(
        [
            Paragraph("<b>Symptoms</b>", styles["body"]),
            Paragraph("<b>Medical History</b>", styles["body"]),
        ]
    )
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
    story.append(
        _styled_table(col_data, [avail * 0.48, avail * 0.48])
    )
    story.append(Spacer(1, 16))

    if recs:
        story.append(Paragraph("Recommendations", styles["subsection"]))
        story.append(Spacer(1, 4))
        rec_rows: list[list[Flowable]] = []
        for r in recs:
            rec_rows.append([Paragraph(f'<font size="9">● {r}</font>', styles["small"])])
        story.append(_styled_table(rec_rows, [avail * 0.96]))
        story.append(Spacer(1, 16))

    # Highlights + Follow-up
    highlights = extraction.get("highlights") or []
    follow_up = extraction.get("follow_up_points") or []
    if highlights or follow_up:
        story.append(Paragraph("Clinical Summary", styles["subsection"]))
        story.append(Spacer(1, 4))
        hl_fu_data: list[list[Flowable]] = []
        hl_fu_data.append(
            [
                _label_cell("Key Highlights", styles["label"]),
                _label_cell("Follow-up Points", styles["label"]),
            ]
        )
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
            level = f.get("level", "—")
            level_color = {"high": GREEN, "medium": AMBER, "low": ROSE}.get(level, SLATE)
            flag_rows.append(
                [
                    Paragraph(f.get("field", ""), styles["small"]),
                    Paragraph(f'<font color="{level_color}">{level.upper()}</font>', styles["small"]),
                    Paragraph(f.get("note", ""), styles["small"]),
                ]
            )
        story.append(_styled_table(flag_rows, [avail * 0.22, avail * 0.16, avail * 0.58]))
        story.append(Spacer(1, 12))

    # Transcript excerpt
    if transcript:
        story.append(Paragraph("Transcript Excerpt", styles["subsection"]))
        story.append(Spacer(1, 4))
        shown = transcript[:12] if len(transcript) > 12 else transcript
        for seg in shown:
            speaker = seg.get("speaker", "Unknown")
            text = seg.get("text", "")
            time_s = seg.get("time", 0)
            mins, secs = divmod(int(time_s), 60)
            color = TEAL if speaker.lower() == "doctor" else AMBER
            story.append(
                Paragraph(
                    f'<font color="{color}" size="9"><b>[{speaker}]</b></font> '
                    f'<font color="{SLATE}" size="9">({mins:02d}:{secs:02d})</font> '
                    f'<font size="9">{text}</font>',
                    ParagraphStyle(
                        "TxLine", parent=styles["body"], fontSize=9, leading=13, leftIndent=8
                    ),
                )
            )
            story.append(Spacer(1, 2))
        if len(transcript) > 12:
            story.append(
                Paragraph(
                    f'<i><font color="{SLATE_LIGHT}">… {len(transcript) - 12} more segments — see full transcript in the application</font></i>',
                    styles["small"],
                )
            )

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


def _cover_page(canvas, doc) -> None:  # type: ignore[no-untyped-def]
    canvas.saveState()
    # subtle watermark-style footer
    canvas.setFillColor(BORDER)
    canvas.setFont("Helvetica", 6)
    canvas.drawRightString(PAGE_W - COVER_MARGIN, 20, "MediScribe AI · page 1")
    canvas.restoreState()


def _body_page(canvas, doc) -> None:  # type: ignore[no-untyped-def]
    canvas.saveState()
    canvas.setFillColor(SLATE_LIGHT)
    canvas.setFont("Helvetica", 6)
    canvas.drawRightString(PAGE_W - BODY_MARGIN, 20, f"MediScribe AI · page {doc.page}")
    canvas.restoreState()


def generate_report_pdf(report: Report, patient: User, doctor: User) -> BytesIO:
    extraction: dict[str, Any] = report.extraction_json or {}
    soap: dict[str, str] = extraction.get("soap", {})

    # Parse transcript from report for detail page
    transcript = None
    raw_tx = report.transcript_json
    if isinstance(raw_tx, list):
        transcript = raw_tx
    elif isinstance(raw_tx, dict):
        transcript = raw_tx.get("segments") or raw_tx.get("transcript") or []

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

    # Cover frame (page 1)
    cover_frame = Frame(
        COVER_MARGIN, COVER_MARGIN, PAGE_W - 2 * COVER_MARGIN, PAGE_H - 2 * COVER_MARGIN, id="cover"
    )
    # Body frame (page 2+)
    body_frame = Frame(
        BODY_MARGIN, BODY_MARGIN, PAGE_W - 2 * BODY_MARGIN, PAGE_H - 2 * BODY_MARGIN, id="body"
    )

    cover_template = PageTemplate(id="Cover", frames=[cover_frame], onPage=_cover_page)
    body_template = PageTemplate(id="Body", frames=[body_frame], onPage=_body_page)

    doc.addPageTemplates([cover_template, body_template])

    story: list[Flowable] = []

    # Page 1: Cover
    story.extend(_build_cover_story(report, patient, doctor, extraction, soap, styles))
    story.append(NextPageTemplate("Body"))
    story.append(PageBreak())

    # Page 2+: Details
    story.extend(_build_detail_story(extraction, transcript, styles))

    doc.build(story)
    buffer.seek(0)
    return buffer
