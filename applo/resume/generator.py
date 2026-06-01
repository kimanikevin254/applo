from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from pathlib import Path
from applo.utils.logger import logger


class ResumeGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_styles()

    def _setup_styles(self):
        self.title_style = ParagraphStyle(
            "Title",
            parent=self.styles["Normal"],
            fontSize=18,
            fontName="Helvetica-Bold",
            textColor=HexColor("#1a1a2e"),
            alignment=TA_CENTER,
            spaceAfter=4,
        )
        self.contact_style = ParagraphStyle(
            "Contact",
            parent=self.styles["Normal"],
            fontSize=9,
            textColor=HexColor("#555555"),
            alignment=TA_CENTER,
            spaceAfter=12,
        )
        self.section_header_style = ParagraphStyle(
            "SectionHeader",
            parent=self.styles["Normal"],
            fontSize=11,
            fontName="Helvetica-Bold",
            textColor=HexColor("#1a1a2e"),
            spaceBefore=12,
            spaceAfter=4,
        )
        self.body_style = ParagraphStyle(
            "Body",
            parent=self.styles["Normal"],
            fontSize=10,
            leading=14,
            spaceAfter=4,
        )
        self.bullet_style = ParagraphStyle(
            "Bullet",
            parent=self.styles["Normal"],
            fontSize=10,
            leading=14,
            leftIndent=16,
            spaceAfter=3,
        )
        self.job_title_style = ParagraphStyle(
            "JobTitle",
            parent=self.styles["Normal"],
            fontSize=10,
            fontName="Helvetica-Bold",
            spaceAfter=2,
        )

    def generate(
        self,
        output_path: str | Path,
        resume_data: dict,
        optimized: dict,
    ) -> Path:
        """
        Generate tailored PDF resume.
        Uses optimized sections where available, falls back to original.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            leftMargin=0.75 * inch,
            rightMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
        )

        story = []
        sections = resume_data.get("sections", {})

        # --- Contact Header ---
        header = sections.get("header", "")
        lines = [l.strip() for l in header.split("\n") if l.strip()]
        if lines:
            story.append(Paragraph(lines[0], self.title_style))  # name
        if len(lines) > 1:
            story.append(Paragraph(" · ".join(lines[1:]), self.contact_style))

        story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#1a1a2e")))

        # --- Professional Summary ---
        story.append(Paragraph("Professional Summary", self.section_header_style))
        summary = optimized.get("summary") or sections.get("professional summary", "")
        story.append(Paragraph(summary, self.body_style))

        # --- Skills ---
        story.append(Paragraph("Skills", self.section_header_style))
        skills = optimized.get("skills") or sections.get("skills", "")
        for line in skills.split("\n"):
            if line.strip():
                story.append(Paragraph(line.strip(), self.body_style))

        # --- Professional Experience ---
        story.append(Paragraph("Professional Experience", self.section_header_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor("#dddddd")))

        experience_text = sections.get("professional experience", "")
        optimized_bullets = optimized.get("experience_bullets", [])
        story.extend(self._render_experience(experience_text, optimized_bullets))

        # --- Education ---
        story.append(Paragraph("Education", self.section_header_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor("#dddddd")))
        education = sections.get("education", "")
        for line in education.split("\n"):
            if line.strip():
                story.append(Paragraph(line.strip(), self.body_style))

        doc.build(story)
        logger.info(f"Generator | PDF saved to {output_path}")
        return output_path

    def _render_experience(self, experience_text: str, optimized_bullets: list) -> list:
        story = []
        bullet_count = 0
        lines = experience_text.split("\n")
        bullet_chars = ("●", "•", "-", "*")

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            if any(stripped.startswith(c) for c in bullet_chars):
                if bullet_count < len(optimized_bullets):
                    text = f"• {optimized_bullets[bullet_count]}"
                    bullet_count += 1
                else:
                    text = f"• {stripped.lstrip('●•-* ').strip()}"
                story.append(Paragraph(text, self.bullet_style))
            else:
                story.append(Paragraph(stripped, self.job_title_style))

        return story

    def generate_cover_letter(
        self,
        output_path: str | Path,
        cover_letter_text: str,
        candidate_name: str,
    ) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            leftMargin=inch,
            rightMargin=inch,
            topMargin=inch,
            bottomMargin=inch,
        )

        story = []
        story.append(Paragraph(candidate_name, self.title_style))
        story.append(Spacer(1, 0.3 * inch))

        for para in cover_letter_text.split("\n\n"):
            if para.strip():
                story.append(Paragraph(para.strip(), self.body_style))
                story.append(Spacer(1, 0.15 * inch))

        doc.build(story)
        logger.info(f"Generator | Cover letter saved to {output_path}")
        return output_path