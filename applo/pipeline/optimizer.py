import anthropic
import json
from pathlib import Path
from applo.config import settings
from applo.resume.parser import load_or_parse_resume
from applo.utils.logger import logger


class ResumeOptimizer:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.resume_data = load_or_parse_resume(settings.master_resume_path)

    def optimize(self, job_title: str, company: str, jd_text: str) -> dict:
        """
        Targeted rewrite of summary, skills, top 3 experience bullets.
        Returns dict with optimized sections + cover letter.
        """
        logger.info(f"Optimizer | optimizing for: {job_title} @ {company}")

        prompt = self._build_prompt(job_title, company, jd_text)
        response = self.client.messages.create(
            model=settings.anthropic_model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = response.content[0].text
        result = self._parse_response(raw)
        logger.info(f"Optimizer | done. Tokens used — input: {response.usage.input_tokens}, output: {response.usage.output_tokens}")
        return result

    def _build_prompt(self, job_title: str, company: str, jd_text: str) -> str:
        resume = self.resume_data["sections"]

        return f"""You are an expert resume writer. Your task is to tailor a candidate's resume for a specific job.

## Job Details
Title: {job_title}
Company: {company}

## Job Description
{jd_text[:3000]}

## Current Resume Sections

### Professional Summary
{resume.get("professional summary", "")}

### Skills
{resume.get("skills", "")}

### Professional Experience
{resume.get("professional experience", "")}

## Instructions
Perform a TARGETED rewrite only. Do NOT invent experience or skills the candidate doesn't have.

1. Rewrite the Professional Summary (3-4 sentences) to align with this specific role and company.
2. Reorder and highlight the most relevant skills from the existing skills list. Do not add new skills.
3. Pick the single most relevant job from the experience section. Rewrite up to 3 of its bullet points to better match the JD language and requirements. Do not change bullets from other jobs.
4. Write a concise cover letter (3 paragraphs) for this role.

Respond ONLY with valid JSON in this exact format, no preamble or markdown:
{{
  "summary": "rewritten summary here",
  "skills": "rewritten skills section here",
  "experience_bullets": {{
    "job_title": "exact job title from the resume",
    "company": "exact company name from the resume",
    "bullets": [
      "rewritten bullet 1",
      "rewritten bullet 2",
      "rewritten bullet 3"
    ]
  }},
  "cover_letter": "full cover letter text here",
  "optimization_notes": "brief explanation of what was changed and why"
}}"""

    def _parse_response(self, raw: str) -> dict:
        try:
            # strip markdown fences if present
            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            return json.loads(clean.strip())
        except json.JSONDecodeError as e:
            logger.error(f"Optimizer | failed to parse response: {e}")
            logger.debug(f"Optimizer | raw response: {raw}")
            return {}