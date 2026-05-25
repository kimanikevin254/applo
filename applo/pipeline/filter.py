from applo.models import JobListing, SearchCriteria
from applo.utils.logger import logger
import re


class JobFilter:
    def __init__(self, criteria: SearchCriteria):
        self.criteria = criteria

    def run(self, listings: list[JobListing]) -> list[JobListing]:
        before = len(listings)
        listings = self._deduplicate(listings)
        listings = self._apply_criteria(listings)
        after = len(listings)
        logger.info(f"Filter | {before} listings → {after} after dedup + filtering")
        return listings

    def _deduplicate(self, listings: list[JobListing]) -> list[JobListing]:
        seen: set[str] = set()
        unique = []
        for job in listings:
            key = f"{job.source}:{job.external_id}"
            if key not in seen:
                seen.add(key)
                unique.append(job)
            else:
                logger.debug(f"Filter | duplicate skipped: {job.title} @ {job.company}")
        return unique

    def _apply_criteria(self, listings: list[JobListing]) -> list[JobListing]:
        return [job for job in listings if self._passes(job)]

    def _passes(self, job: JobListing) -> bool:
        text = f"{job.title} {job.company} {job.raw_text}".lower()

        # excluded keywords
        for kw in self.criteria.excluded_keywords:
            if kw.lower() in text:
                logger.debug(f"Filter | excluded keyword '{kw}': {job.title} @ {job.company}")
                return False

        # salary filter
        if self.criteria.min_salary and job.salary_max:
            if job.salary_max < self.criteria.min_salary:
                logger.debug(f"Filter | below min salary: {job.title} @ {job.company}")
                return False

        # date safety net. catches promoted listings that ignore fromAge
        if job.posted_text and not self._is_recent(job.posted_text, self.criteria.max_age_days):
            logger.debug(f"Filter | promoted/old listing ({job.posted_text}): {job.title} @ {job.company}")
            return False

        return True

    def _is_recent(self, posted_text: str, max_age_days: int) -> bool:
        text = posted_text.lower().strip()
        if any(u in text for u in ["m ago", "h ago", "just posted", "today"]):
            return True
        match = re.search(r"(\d+)d", text)
        if match:
            return int(match.group(1)) <= max_age_days
        return True  # unknown format, don't exclude