import asyncio
from applo.db import init_db
from applo.scrapers import IndeedScraper, GlassdoorScraper
from applo.models import SearchCriteria

async def main():
    init_db()

    criteria = SearchCriteria(
        job_titles=["software engineer"],
        locations=["remote"],
    )

    async with IndeedScraper() as scraper:
        indeed_jobs = await scraper.scrape(criteria)
        print(f"Indeed: {len(indeed_jobs)} jobs")
        for job in indeed_jobs[:2]:
            print(f"  - {job.title} @ {job.company} | {job.location}")

    async with GlassdoorScraper() as scraper:
        gd_jobs = await scraper.scrape(criteria)
        print(f"Glassdoor: {len(gd_jobs)} jobs")
        for job in gd_jobs[:2]:
            print(f"  - {job.title} @ {job.company} | {job.location}")

asyncio.run(main())