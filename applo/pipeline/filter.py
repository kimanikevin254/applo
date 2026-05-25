from applo.models import JobListing, SearchCriteria
from applo.utils.logger import logger

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
        """Remove duplicates by external_id within current batch"""
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

        # salary filter (only if job has salary data)
        if self.criteria.min_salary and job.salary_max:
            if job.salary_max < self.criteria.min_salary:
                logger.debug(f"Filter | below min salary: {job.title} @ {job.company}")
                return False

        return True
