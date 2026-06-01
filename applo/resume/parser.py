import pdfplumber
import json
import re
from pathlib import Path
from applo.utils.logger import logger
import re


class ResumeParser:
    def __init__(self, pdf_path: str | Path):
        self.pdf_path = Path(pdf_path)

    def parse(self) -> dict:
        """Extract resume text and structure it into JSON."""
        text = self._extract_text()
        structured = self._structure(text)
        return structured

    def _extract_text(self) -> str:
        text = ""
        with pdfplumber.open(self.pdf_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() + "\n"
        return text.strip()
    
    def _structure(self, text: str) -> dict:
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        sections = self._extract_sections(text)
        
        # post-process experience to join wrapped bullet lines
        if "professional experience" in sections:
            sections["professional experience"] = self._join_wrapped_lines(
                sections["professional experience"]
            )
        # also handle other common experience section names
        for key in ["experience", "work experience", "employment"]:
            if key in sections:
                sections[key] = self._join_wrapped_lines(sections[key])

        return {
            "raw_text": text,
            "lines": lines,
            "sections": sections,
        }

    def _join_wrapped_lines(self, text: str) -> str:
        """
        Join continuation lines back into their parent line.
        A continuation line is one that:
        - doesn't start with a bullet (●•-)
        - doesn't look like a job header (contains | or matches date pattern)
        - doesn't start with a known section keyword
        """
        lines = text.split("\n")
        result = []
        date_pattern = re.compile(
            r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|"
            r"March|April|June|July|August|September|October|November|December)"
            r"|\d{4}"
        )
        bullet_chars = ("●", "•", "-", "*")

        for line in lines:
            stripped = line.strip()
            if not stripped:
                result.append("")
                continue

            is_bullet = any(stripped.startswith(c) for c in bullet_chars)
            is_job_header = "|" in stripped or date_pattern.search(stripped)

            if is_bullet or is_job_header or not result:
                result.append(stripped)
            else:
                # continuation line — append to previous
                if result:
                    result[-1] = result[-1] + " " + stripped
                else:
                    result.append(stripped)

        return "\n".join(line for line in result if line.strip())
    
    def _extract_sections(self, text: str) -> dict:
        section_patterns = [
            "professional summary", "summary", "objective", "profile",
            "professional experience", "work experience", "experience", "employment",
            "education", "skills", "technical skills",
            "certifications", "projects", "awards",
            "languages", "interests", "references",
        ]

        # sort by length descending so "professional summary" matches before "summary"
        section_patterns.sort(key=len, reverse=True)

        pattern = r"(?i)^(" + "|".join(re.escape(p) for p in section_patterns) + r")\s*$"
        sections = {}
        current_section = "header"
        current_content = []

        for line in text.split("\n"):
            if re.match(pattern, line.strip()):
                sections[current_section] = "\n".join(current_content).strip()
                current_section = line.strip().lower()
                current_content = []
            else:
                current_content.append(line)

        sections[current_section] = "\n".join(current_content).strip()
        return sections
    
def load_or_parse_resume(pdf_path: str | Path) -> dict:
    """Parse resume PDF and cache as JSON alongside it."""
    pdf_path = Path(pdf_path)
    json_path = pdf_path.with_suffix(".json")

    if json_path.exists():
        logger.info(f"Resume | loading cached JSON from {json_path}")
        return json.loads(json_path.read_text())

    logger.info(f"Resume | parsing PDF: {pdf_path}")
    parser = ResumeParser(pdf_path)
    data = parser.parse()
    json_path.write_text(json.dumps(data, indent=2))
    logger.info(f"Resume | saved to {json_path}")
    return data