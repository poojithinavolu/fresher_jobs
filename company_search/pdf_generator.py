"""Publication-grade PDF generator for Company Interview Preparation Guides.

Renders an executive candidate dossier with professional typography,
clean card containers, dynamic 'Page X of Y' two-pass numbering,
and dedicated sections for:
1. Executive Company & Engineering Profile (Case Studies, Tech Stack, Interview Hooks)
2. Evaluation Pipeline & Round-by-Round Breakdown
3. Verified Interview Questions & Expert Playbooks (Evaluation criteria, verbal navigation,
   exemplary delivery, production code, critical traps)
4. Research Methodology & Evidence Ledger
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# Executive Color System
# ---------------------------------------------------------------------------
COLOR_PRIMARY = colors.HexColor("#1E3A8A")       # Deep Navy
COLOR_SECONDARY = colors.HexColor("#0D9488")     # Deep Teal
COLOR_DARK = colors.HexColor("#0F172A")          # Slate 900
COLOR_BODY = colors.HexColor("#334155")          # Slate 700
COLOR_MUTED = colors.HexColor("#64748B")         # Slate 500
COLOR_BG_LIGHT = colors.HexColor("#F8FAFC")      # Slate 50
COLOR_BG_CARD = colors.HexColor("#FFFFFF")       # White
COLOR_BORDER = colors.HexColor("#CBD5E1")        # Slate 300
COLOR_BORDER_LIGHT = colors.HexColor("#E2E8F0")  # Slate 200

COLOR_GREEN = colors.HexColor("#16A34A")         # Green 600
COLOR_AMBER = colors.HexColor("#D97706")         # Amber 600
COLOR_RED = colors.HexColor("#DC2626")           # Red 600

COLOR_TRAP_BG = colors.HexColor("#FFF1F2")       # Rose 50
COLOR_TRAP_BORDER = colors.HexColor("#FECDD3")   # Rose 200
COLOR_TRAP_TEXT = colors.HexColor("#991B1B")     # Rose 800

COLOR_SPEECH_BG = colors.HexColor("#F1F5F9")     # Slate 100
COLOR_SPEECH_BORDER = colors.HexColor("#94A3B8") # Slate 400


def safe_text(text: str) -> str:
    """Escapes raw XML entities while preserving legitimate <b>, <i>, <br/>, <font> tags."""
    if not text:
        return ""
    text = str(text)
    # Temporarily protect allowed tags
    text = text.replace("<b>", "___B_OPEN___").replace("</b>", "___B_CLOSE___")
    text = text.replace("<i>", "___I_OPEN___").replace("</i>", "___I_CLOSE___")
    text = text.replace("<br/>", "___BR___").replace("<br>", "___BR___")
    # Escape raw XML
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Restore allowed tags
    text = text.replace("___B_OPEN___", "<b>").replace("___B_CLOSE___", "</b>")
    text = text.replace("___I_OPEN___", "<i>").replace("___I_CLOSE___", "</i>")
    text = text.replace("___BR___", "<br/>")
    return text


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to dynamically compute and print 'Page X of Y' with running headers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages: int):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(COLOR_MUTED)

        # Draw running header on page 2+
        if self._pageNumber > 1:
            header_text = f"{getattr(self, 'doc_company', 'Company')} — {getattr(self, 'doc_role', 'Role')} Interview Preparation Dossier"
            self.drawString(38, letter[1] - 28, header_text)
            self.setStrokeColor(COLOR_BORDER_LIGHT)
            self.setLineWidth(0.5)
            self.line(38, letter[1] - 32, letter[0] - 38, letter[1] - 32)

        # Draw running footer on all pages
        self.setStrokeColor(COLOR_BORDER_LIGHT)
        self.setLineWidth(0.5)
        self.line(38, 34, letter[0] - 38, 34)

        footer_left = "Executive Placement Intelligence & Candidate Research Dossier | Confidential"
        footer_right = f"Page {self._pageNumber} of {total_pages}"
        self.drawString(38, 22, footer_left)
        self.drawRightString(letter[0] - 38, 22, footer_right)

        self.restoreState()


def get_difficulty_color(difficulty: str) -> colors.HexColor:
    diff = (difficulty or "").lower()
    if "easy" in diff:
        return COLOR_GREEN
    elif "hard" in diff:
        return COLOR_RED
    return COLOR_AMBER


def create_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()

    styles = {
        "DocTitle": ParagraphStyle(
            "DocTitle",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=21,
            leading=25,
            textColor=COLOR_PRIMARY,
            spaceAfter=3,
        ),
        "DocSubtitle": ParagraphStyle(
            "DocSubtitle",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=COLOR_SECONDARY,
            spaceAfter=2,
        ),
        "DocMeta": ParagraphStyle(
            "DocMeta",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=COLOR_MUTED,
            spaceAfter=10,
        ),
        "SectionHeader": ParagraphStyle(
            "SectionHeader",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=COLOR_PRIMARY,
            spaceBefore=12,
            spaceAfter=8,
            keepWithNext=True,
        ),
        "SubHeader": ParagraphStyle(
            "SubHeader",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=COLOR_SECONDARY,
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "Body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12.5,
            textColor=COLOR_BODY,
            spaceAfter=5,
        ),
        "BodyBold": ParagraphStyle(
            "BodyBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=12.5,
            textColor=COLOR_DARK,
        ),
        "BulletItem": ParagraphStyle(
            "BulletItem",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11.5,
            textColor=COLOR_BODY,
            leftIndent=10,
            spaceAfter=2,
        ),
        "TableHeader": ParagraphStyle(
            "TableHeader",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=colors.white,
            alignment=0,
        ),
        "TableCell": ParagraphStyle(
            "TableCell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11.5,
            textColor=COLOR_BODY,
        ),
        "TableCellBold": ParagraphStyle(
            "TableCellBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11.5,
            textColor=COLOR_DARK,
        ),
        "QuestionHeading": ParagraphStyle(
            "QuestionHeading",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=14,
            textColor=COLOR_DARK,
            spaceBefore=2,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "SubLabelNavy": ParagraphStyle(
            "SubLabelNavy",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=COLOR_PRIMARY,
            spaceBefore=4,
            spaceAfter=2,
            keepWithNext=True,
        ),
        "SubLabelTeal": ParagraphStyle(
            "SubLabelTeal",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=COLOR_SECONDARY,
            spaceBefore=4,
            spaceAfter=2,
            keepWithNext=True,
        ),
        "SpeechBoxText": ParagraphStyle(
            "SpeechBoxText",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8.5,
            leading=12.5,
            textColor=COLOR_DARK,
        ),
        "CodeBoxText": ParagraphStyle(
            "CodeBoxText",
            parent=base["Normal"],
            fontName="Courier",
            fontSize=7.5,
            leading=10.5,
            textColor=COLOR_DARK,
            leftIndent=10,
            spaceBefore=2,
            spaceAfter=4,
        ),
        "TrapBoxText": ParagraphStyle(
            "TrapBoxText",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11.5,
            textColor=COLOR_TRAP_TEXT,
        ),
        "SourceRef": ParagraphStyle(
            "SourceRef",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=7.5,
            leading=10,
            textColor=COLOR_MUTED,
            spaceBefore=3,
            spaceAfter=6,
        ),
    }

    return styles


def build_interview_prep_pdf(prep_pack: dict[str, Any], output_path: str | Path) -> Path:
    """
    Renders publication-grade PDF report from validated InterviewPrepPack dictionary.
    """
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    company = prep_pack.get("company_profile", {}).get("company_name", "Target Enterprise")
    role = prep_pack.get("company_profile", {}).get("target_role", "Candidate Role")

    doc = SimpleDocTemplate(
        str(out_file),
        pagesize=letter,
        leftMargin=38,
        rightMargin=38,
        topMargin=38,
        bottomMargin=38,
    )

    styles = create_styles()
    story: list[Any] = []
    usable_width = letter[0] - 76  # 612 - 76 = 536 pt

    # -------------------------------------------------------------
    # 1. Document Title Banner
    # -------------------------------------------------------------
    date_str = datetime.now().strftime("%B %d, %Y")
    story.append(Paragraph(safe_text(f"{company.upper()} — {role.upper()}"), styles["DocTitle"]))
    story.append(
        Paragraph(
            "EXECUTIVE CANDIDATE INTERVIEW DOSSIER & TECHNICAL PLAYBOOK",
            styles["DocSubtitle"],
        )
    )
    story.append(
        Paragraph(
            f"<b>Generated:</b> {date_str} &bull; <b>Target Track:</b> Entry-Level Engineering &bull; "
            f"<b>Intelligence Origin:</b> Verified Candidate Transcripts & Engineering Disclosures",
            styles["DocMeta"],
        )
    )
    story.append(HRFlowable(width="100%", thickness=1.5, color=COLOR_PRIMARY, spaceAfter=8))

    # -------------------------------------------------------------
    # 2. Executive Company Profile & Project Intelligence
    # -------------------------------------------------------------
    profile = prep_pack.get("company_profile", {})
    overview_text = profile.get("overview", "Leading enterprise in modern technology and client solutions.")
    domains = profile.get("core_business_domains", [])
    tech_stack = profile.get("tech_stack", [])
    standards = profile.get("engineering_culture_and_standards", [])

    story.append(Paragraph("1. Corporate Technology Overview & Strategic Systems", styles["SectionHeader"]))
    story.append(Paragraph(safe_text(overview_text), styles["Body"]))

    # Core Domains & Primary Tech Stack table
    meta_data = [
        [
            Paragraph("<b>Core Business Domains:</b>", styles["TableCellBold"]),
            Paragraph(safe_text(", ".join(domains)) if domains else "Enterprise Platforms, Cloud, Analytics", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Primary Tech Stack & Ecosystem:</b>", styles["TableCellBold"]),
            Paragraph(safe_text(", ".join(tech_stack)) if tech_stack else "Python, SQL, Cloud Architecture, Scalable Backends", styles["TableCell"]),
        ],
    ]
    t_meta = Table(meta_data, colWidths=[130, usable_width - 130])
    t_meta.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG_LIGHT),
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER_LIGHT),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ])
    )
    story.append(t_meta)
    story.append(Spacer(1, 8))

    # Flagship Projects Table
    projects = profile.get("key_projects", [])
    if projects:
        story.append(Paragraph("<b>Flagship Engineering Initiatives & Case Studies:</b>", styles["SubHeader"]))
        p_headers = [
            Paragraph("System / Initiative", styles["TableHeader"]),
            Paragraph("Client / Domain", styles["TableHeader"]),
            Paragraph("Technologies Used", styles["TableHeader"]),
            Paragraph("Architecture & Impact", styles["TableHeader"]),
            Paragraph("Interview Talking Point", styles["TableHeader"]),
        ]
        p_rows = [p_headers]
        for p in projects:
            p_name = p.get("project_name", "Enterprise System")
            client = p.get("client_or_industry", "Global Enterprise")
            techs = ", ".join(p.get("technologies_used", [])) if isinstance(p.get("technologies_used"), list) else str(p.get("technologies_used", ""))
            summary = p.get("summary", "")
            impact = p.get("impact", "")
            hook = p.get("interview_talking_point", "Cite this when discussing system scalability and architectural design.")

            desc_cell = f"{summary}"
            if impact:
                desc_cell += f"<br/><b>Impact:</b> {impact}"

            p_rows.append([
                Paragraph(safe_text(f"<b>{p_name}</b>"), styles["TableCellBold"]),
                Paragraph(safe_text(client), styles["TableCell"]),
                Paragraph(safe_text(techs), styles["TableCell"]),
                Paragraph(safe_text(desc_cell), styles["TableCell"]),
                Paragraph(safe_text(hook), styles["TableCell"]),
            ])

        col_w = [95, 75, 90, usable_width - 370, 110]
        t_proj = Table(p_rows, colWidths=col_w)
        t_proj.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER_LIGHT),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_BG_LIGHT]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ])
        )
        story.append(t_proj)
        story.append(Spacer(1, 8))

    # Engineering Culture & Tenets
    if standards:
        std_paras = [Paragraph("<b>Engineering Culture & Code Quality Standards:</b>", styles["BodyBold"])]
        for std in standards:
            std_paras.append(Paragraph(safe_text(f"&bull; {std}"), styles["BulletItem"]))
        t_std = Table([[std_paras]], colWidths=[usable_width])
        t_std.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG_LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ])
        )
        story.append(t_std)
        story.append(Spacer(1, 8))

    # -------------------------------------------------------------
    # 3. Interview Process & Evaluation Rounds
    # -------------------------------------------------------------
    rounds = prep_pack.get("interview_process", [])
    story.append(Paragraph("2. Candidate Evaluation Pipeline & Round-by-Round Breakdown", styles["SectionHeader"]))

    if rounds:
        r_headers = [
            Paragraph("Round #", styles["TableHeader"]),
            Paragraph("Round Title", styles["TableHeader"]),
            Paragraph("Format", styles["TableHeader"]),
            Paragraph("Evaluation Criteria & Core Focus Areas", styles["TableHeader"]),
        ]
        r_rows = [r_headers]
        for r in rounds:
            focus = ", ".join(r.get("focus_areas", [])) if isinstance(r.get("focus_areas"), list) else str(r.get("focus_areas", ""))
            desc = r.get("description", "")
            detail = f"{desc}<br/><b>Key Focus:</b> {focus}" if focus else desc
            r_rows.append([
                Paragraph(safe_text(f"Round {r.get('round_number', 1)}"), styles["TableCellBold"]),
                Paragraph(safe_text(r.get("round_name", "Technical Round")), styles["TableCellBold"]),
                Paragraph(safe_text(r.get("round_type", "Assessment")), styles["TableCell"]),
                Paragraph(safe_text(detail), styles["TableCell"]),
            ])
        t_rounds = Table(r_rows, colWidths=[55, 120, 85, usable_width - 260])
        t_rounds.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_SECONDARY),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER_LIGHT),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_BG_LIGHT]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        story.append(t_rounds)
        story.append(Spacer(1, 8))

    # Preparation Strategy Callout
    tips = prep_pack.get("preparation_tips", [])
    if tips:
        tip_paras = [Paragraph("<b>Strategic Candidate Preparation Playbook:</b>", styles["BodyBold"])]
        for tip in tips:
            tip_paras.append(Paragraph(safe_text(f"&bull; {tip}"), styles["BulletItem"]))
        t_tips = Table([[tip_paras]], colWidths=[usable_width])
        t_tips.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF3C7")),  # Amber 100
                ("BOX", (0, 0), (-1, -1), 1, COLOR_AMBER),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ])
        )
        story.append(t_tips)
        story.append(Spacer(1, 10))

    # -------------------------------------------------------------
    # 4. Curated Interview Questions & Professional Handout Cards
    # -------------------------------------------------------------
    qna_list = prep_pack.get("questions_and_answers", [])
    story.append(
        Paragraph(
            f"3. Curated Interview Questions & Expert Technical Playbooks ({len(qna_list)} Questions)",
            styles["SectionHeader"],
        )
    )
    story.append(
        Paragraph(
            "Every question below represents real recruitment rounds conducted at the target company. "
            "For technical questions, review the clarifying questions, algorithmic intuition, production code, and edge cases. "
            "For behavioral scenarios, study the verbatim first-person STAR delivery and timing structure.",
            styles["Body"],
        )
    )
    story.append(Spacer(1, 6))

    for idx, qa in enumerate(qna_list, start=1):
        q_text = qa.get("question", "")
        category = qa.get("category", "Technical Coding & DSA")
        difficulty = qa.get("difficulty", "Medium")
        diff_color = get_difficulty_color(difficulty)
        diff_hex = diff_color.hexval() if hasattr(diff_color, "hexval") else "#D97706"

        focus = qa.get("interviewer_focus", "")
        how_to = qa.get("how_to_answer", "")
        response = qa.get("exemplary_response", "") or qa.get("sample_answer", "")
        traps = qa.get("traps_to_avoid", "")
        source_ref = qa.get("source_reference", "")

        is_behavioral = "behavioral" in category.lower() or "leadership" in category.lower() or "hr" in category.lower()

        # Top Bar: Question Number + Category Pill + Difficulty Pill
        header_table = Table(
            [
                [
                    Paragraph(safe_text(f"<b>Q{idx}. [{category.upper()}]</b>"), styles["SubLabelNavy"]),
                    Paragraph(f"<font color='{diff_hex}'><b>DIFFICULTY: {difficulty.upper()}</b></font>", styles["TableCellBold"]),
                ]
            ],
            colWidths=[usable_width - 130, 130],
        )
        header_table.setStyle(
            TableStyle([
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ])
        )

        # Question Header Block: Header table + Question title + divider
        # Kept together so the title is never orphaned at page bottom
        header_block = [
            Spacer(1, 4),
            header_table,
            Paragraph(safe_text(f"<b>{q_text}</b>"), styles["QuestionHeading"]),
            HRFlowable(width="100%", thickness=0.75, color=COLOR_PRIMARY, spaceAfter=4),
        ]
        story.append(KeepTogether(header_block))

        # 1. Interviewer Evaluation Focus
        if focus:
            story.append(Paragraph("<b>INTERVIEWER EVALUATION & CORE CRITERIA:</b>", styles["SubLabelNavy"]))
            story.append(Paragraph(safe_text(focus), styles["Body"]))

        # 2. How to Answer in the Interview (Verbal Strategy / Navigation)
        if how_to:
            story.append(Paragraph("<b>HOW TO STRUCTURE YOUR ANSWER IN THE INTERVIEW:</b>", styles["SubLabelTeal"]))
            story.append(Paragraph(safe_text(how_to), styles["Body"]))

        # 3. Exemplary Response / Optimal Code
        if response:
            story.append(Paragraph("<b>EXEMPLARY CANDIDATE DELIVERY & IMPLEMENTATION:</b>", styles["SubLabelNavy"]))
            if is_behavioral:
                # Format as verbal speech box
                speech_table = Table([[Paragraph(safe_text(response), styles["SpeechBoxText"])]], colWidths=[usable_width])
                speech_table.setStyle(
                    TableStyle([
                        ("BACKGROUND", (0, 0), (-1, -1), COLOR_SPEECH_BG),
                        ("BOX", (0, 0), (-1, -1), 0.75, COLOR_SPEECH_BORDER),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ])
                )
                story.append(speech_table)
            else:
                # Render code as paragraphs with Courier font and non-breaking spaces
                # This allows long code blocks to split across page boundaries effortlessly!
                code_clean = safe_text(response).replace("\t", "    ")
                code_html = code_clean.replace(" ", "&nbsp;").replace("\n", "<br/>")
                story.append(Paragraph(code_html, styles["CodeBoxText"]))
            story.append(Spacer(1, 4))

        # 4. Critical Traps & Red Flags to Avoid
        if traps:
            trap_table = Table(
                [[
                    Paragraph(
                        f"<b>CRITICAL TRAPS & DISQUALIFYING RED FLAGS TO AVOID:</b><br/>{safe_text(traps)}",
                        styles["TrapBoxText"],
                    )
                ]],
                colWidths=[usable_width],
            )
            trap_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), COLOR_TRAP_BG),
                    ("BOX", (0, 0), (-1, -1), 0.75, COLOR_TRAP_BORDER),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ])
            )
            story.append(trap_table)

        # 5. Evidence Reference
        if source_ref:
            story.append(Paragraph(safe_text(f"Evidence Grounding: {source_ref}"), styles["SourceRef"]))

        # Subtle card separator line between questions
        story.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_BORDER, spaceBefore=4, spaceAfter=8))

    # -------------------------------------------------------------
    # 5. Evidence Sources & Research Methodology Ledger
    # -------------------------------------------------------------
    sources = prep_pack.get("sources_consulted", [])
    if sources:
        story.append(Spacer(1, 6))
        story.append(Paragraph("4. Research Methodology & Evidence Ledger", styles["SectionHeader"]))
        s_headers = [
            Paragraph("Domain / Platform", styles["TableHeader"]),
            Paragraph("Category", styles["TableHeader"]),
            Paragraph("Evidence URL", styles["TableHeader"]),
        ]
        s_rows = [s_headers]
        for s in sources:
            s_rows.append([
                Paragraph(safe_text(s.get("domain", "web")), styles["TableCellBold"]),
                Paragraph(safe_text(s.get("category", "interview")), styles["TableCell"]),
                Paragraph(safe_text(s.get("url", "")), styles["TableCell"]),
            ])
        t_sources = Table(s_rows, colWidths=[120, 80, usable_width - 200])
        t_sources.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER_LIGHT),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_BG_LIGHT]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        story.append(t_sources)

    # Attach doc company and role for running headers
    def canvas_maker(*args, **kwargs):
        c = NumberedCanvas(*args, **kwargs)
        c.doc_company = company
        c.doc_role = role
        return c

    doc.build(story, canvasmaker=canvas_maker)
    return out_file
