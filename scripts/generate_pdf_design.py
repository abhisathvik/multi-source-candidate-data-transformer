"""Script to generate the 1-page Technical Design PDF for Eightfold Assignment."""

from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def build_pdf(filename: str = "Technical_Design_Eightfold.pdf") -> None:
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=18,
        textColor=colors.HexColor("#1E3A8A"),
        spaceAfter=2,
    )

    subtitle_style = ParagraphStyle(
        "SubtitleStyle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=12,
        textColor=colors.HexColor("#3B82F6"),
        spaceAfter=6,
    )

    h2_style = ParagraphStyle(
        "H2Style",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=13,
        textColor=colors.HexColor("#1E3A8A"),
        spaceBefore=4,
        spaceAfter=2,
    )

    body_style = ParagraphStyle(
        "BodyStyle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=10.5,
        textColor=colors.HexColor("#1F2937"),
        spaceAfter=3,
    )

    bullet_style = ParagraphStyle(
        "BulletStyle",
        parent=body_style,
        leftIndent=10,
        spaceAfter=2,
    )

    table_text = ParagraphStyle(
        "TableText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#1F2937"),
    )

    table_header = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.white,
    )

    story = []

    story.append(Paragraph("Technical Design: Multi-Source Candidate Data Transformer", title_style))
    story.append(Paragraph("Eightfold Internship Assignment | Stage 1 Specification", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1E3A8A"), spaceAfter=6))

    story.append(Paragraph("1. System Architecture & Pipeline Breakdown", h2_style))
    story.append(
        Paragraph(
            "The transformer uses a modular six-stage deterministic pipeline designed for idempotence and complete explainability:",
            body_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Detect & Extract:</b> Ingests structured (CSV, ATS JSON) and unstructured (PDF via pdfminer.six, TXT notes) files. Identifies headers, contact sections, and metadata phrases.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Normalize:</b> Standardizes emails (lowercased/trimmed), phone numbers (E.164 via libphonenumber), countries (ISO 3166-1 alpha-2), dates (ISO 8601 YYYY-MM-DD), and skills (canonical taxonomy dictionary).",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Merge & Entity Resolution:</b> Links candidate records using exact matching on normalized email and phone keys, alongside secondary context fuzzy matching (name compatibility + country/skill overlap). Resolves field conflicts deterministically using fixed source trust hierarchy (ATS &gt; CSV &gt; Resume &gt; Notes).",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Confidence & Provenance:</b> Assigns dynamic confidence scores (0.0–1.0) based on source reliability and multi-source agreement, tracking source tags (e.g., <code>ATS:ats.json#1</code>) per field.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Project & Validate:</b> Maps canonical records into custom output JSON schemas via runtime config (supporting field remapping, array indexing e.g. <code>emails[0]</code>, and missing data policies: null/omit/error). Validates final structure using Pydantic.",
            bullet_style,
        )
    )

    story.append(Paragraph("2. Canonical Schema & Merge Rules", h2_style))

    table_data = [
        [
            Paragraph("Canonical Field", table_header),
            Paragraph("Target Format", table_header),
            Paragraph("Merge Policy & Winner Heuristic", table_header),
            Paragraph("Confidence Model", table_header),
        ],
        [
            Paragraph("<b>full_name</b>", table_text),
            Paragraph("Title-Case String", table_text),
            Paragraph("Longest, most complete name string across sources.", table_text),
            Paragraph("0.95 if 3+ sources match; 0.62–0.82 based on priority.", table_text),
        ],
        [
            Paragraph("<b>email</b>", table_text),
            Paragraph("RFC-5322 Lowercase", table_text),
            Paragraph("Case-insensitive match; plus-addressing alias resolving.", table_text),
            Paragraph("0.95 multi-source match; 0.90 for primary trust.", table_text),
        ],
        [
            Paragraph("<b>phone</b>", table_text),
            Paragraph("E.164 String", table_text),
            Paragraph("Valid E.164 number with highest source priority.", table_text),
            Paragraph("0.95 multi-source match; 0.85 validated single source.", table_text),
        ],
        [
            Paragraph("<b>country</b>", table_text),
            Paragraph("ISO 3166-1 Alpha-2", table_text),
            Paragraph("Standardized alias lookup (e.g., 'U.S.A.' &rarr; 'US').", table_text),
            Paragraph("0.95 multi-source confirmation.", table_text),
        ],
        [
            Paragraph("<b>skills</b>", table_text),
            Paragraph("Canonical List[str]", table_text),
            Paragraph("Union across all sources, taxonomy deduplication, sorted.", table_text),
            Paragraph("0.85 (3+ sources), 0.75 (2 sources), 0.60 (1 source).", table_text),
        ],
        [
            Paragraph("<b>experience_yrs</b>", table_text),
            Paragraph("Float Number", table_text),
            Paragraph("Maximum valid experience value reported across sources.", table_text),
            Paragraph("0.82 primary trust source agreement.", table_text),
        ],
    ]

    col_widths = [1.1 * inch, 1.2 * inch, 3.2 * inch, 2.0 * inch]
    t = Table(table_data, colWidths=col_widths)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 4))

    story.append(Paragraph("3. Edge Case Handling & Scoping Trade-offs", h2_style))
    story.append(
        Paragraph(
            "<b>1. Conflicting Attributes across Sources:</b> Discrepancies (e.g., country US vs. GB) are resolved deterministically using fixed source weights (ATS=100, CSV=80, Resume=60, Notes=40), logging exact provenance.",
            body_style,
        )
    )
    story.append(
        Paragraph(
            "<b>2. Freeform Recruiter Notes:</b> Prevents creation of false orphan candidates by validating name candidates against non-name phrases (e.g., 'Candidate goes by Jon.') and extracting preferred aliases for record linkage.",
            body_style,
        )
    )
    story.append(
        Paragraph(
            "<b>3. Unparseable / Garbage Inputs:</b> Missing files or malformed rows emit logging warnings and degrade gracefully to <code>null</code> without crashing the execution pipeline.",
            body_style,
        )
    )
    story.append(
        Paragraph(
            "<b>Scoping Trade-offs under time pressure:</b> External LLM API dependencies and complex full-page neural OCR were deliberately excluded in favor of fast, deterministic local extraction (Pydantic, phonenumbers, pdfminer.six) to guarantee sub-second execution speed, idempotence, and offline operational reliability.",
            body_style,
        )
    )

    doc.build(story)
    print(f"Successfully generated {filename}")


if __name__ == "__main__":
    build_pdf()
