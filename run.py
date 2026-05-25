import asyncio
from applo.db import init_db, get_session, save_listings
from applo.scrapers import IndeedScraper, GlassdoorScraper
from applo.pipeline import JobFilter
from applo.models import SearchCriteria
from applo.utils.logger import logger

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

    with get_session() as session:
        saved, skipped = save_listings(session, filtered)
        logger.info(f"DB | saved: {saved} | skipped duplicates: {skipped}")

    print(f"\n{len(filtered)} jobs passed filter, {saved} saved to DB, {skipped} duplicates skipped")

asyncio.run(main())