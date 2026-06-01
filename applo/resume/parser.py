import pdfplumber
import json
import re
from pathlib import Path
from applo.utils.logger import logger

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

        return {
            "raw_text": text,
            "lines": lines,
            "sections": self._extract_sections(text),
        }
    
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