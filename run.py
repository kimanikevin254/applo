import asyncio
from applo.db import init_db
from applo.scrapers import IndeedScraper, GlassdoorScraper
from applo.pipeline import JobFilter
from applo.models import SearchCriteria

async def main():
    init_db()

    criteria = SearchCriteria(
        job_titles=["software engineer"],
        locations=["remote"],
        excluded_keywords=["staff", "principal", "lead"],
        min_salary=80000,
    )

    listings = []

    async with IndeedScraper() as scraper:
        listings.extend(await scraper.scrape(criteria))

    async with GlassdoorScraper() as scraper:
        listings.extend(await scraper.scrape(criteria))

    filtered = JobFilter(criteria).run(listings)

    print(f"\n{len(filtered)} jobs passed filter:")
    for job in filtered:
        salary = f"${job.salary_min}-${job.salary_max}" if job.salary_min else "n/a"
        print(f"  [{job.source.value}] {job.title} @ {job.company} | {job.location} | {salary}")

asyncio.run(main())