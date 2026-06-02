from docx import Document
from pathlib import Path
import json
from applo.utils.logger import logger


SECTION_NAMES = [
    "professional summary", "summary", "objective", "profile",
    "professional experience", "work experience", "experience", "employment",
    "education", "skills", "technical skills",
    "certifications", "projects", "awards",
    "languages", "interests", "references",
]

_SECTION_LOOKUP = sorted(SECTION_NAMES, key=len, reverse=True)


def _detect_section(para) -> str | None:
    text = para.text.strip().lower()
    if not text:
        return None
    style_name = (para.style.name or "").lower()
    is_heading = "heading" in style_name
    for name in _SECTION_LOOKUP:
        if text == name or (is_heading and name in text):
            return name
    return None


class DocxResumeParser:
    def __init__(self, docx_path: str | Path):
        self.docx_path = Path(docx_path)

    def parse(self) -> dict:
        doc = Document(self.docx_path)
        paragraphs = doc.paragraphs

        sections: dict[str, str] = {}
        paragraph_map: dict[str, list[int]] = {}

        current_section = "header"
        current_text: list[str] = []
        current_indices: list[int] = []

        for i, para in enumerate(paragraphs):
            section_name = _detect_section(para)
            if section_name:
                sections[current_section] = "\n".join(current_text).strip()
                paragraph_map[current_section] = current_indices
                current_section = section_name
                current_text = []
                current_indices = []
            else:
                current_text.append(para.text)
                current_indices.append(i)

        sections[current_section] = "\n".join(current_text).strip()
        paragraph_map[current_section] = current_indices

        return {
            "raw_text": "\n".join(p.text for p in paragraphs),
            "sections": sections,
            "paragraph_map": paragraph_map,
        }


def load_or_parse_resume(docx_path: str | Path) -> dict:
    """Parse DOCX resume and cache as JSON alongside it."""
    docx_path = Path(docx_path)
    json_path = docx_path.with_suffix(".json")

    if json_path.exists():
        logger.info(f"Resume | loading cached JSON from {json_path}")
        return json.loads(json_path.read_text())

    logger.info(f"Resume | parsing DOCX: {docx_path}")
    data = DocxResumeParser(docx_path).parse()
    json_path.write_text(json.dumps(data, indent=2))
    logger.info(f"Resume | cached to {json_path}")
    return data
