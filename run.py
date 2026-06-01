import asyncio
from applo.db import init_db, get_session, save_listings
from applo.scrapers import IndeedScraper, GlassdoorScraper
from applo.pipeline import JobFilter, JDFetcher
from applo.models import SearchCriteria
from applo.utils.logger import logger

async def main():
    init_db()

    criteria = SearchCriteria(
        job_titles=["software engineer"],
        locations=["remote"],
        excluded_keywords=["staff", "principal", "lead"],
        min_salary=80000,
        max_age_days=7,
    )

    listings = []

    # async with IndeedScraper() as indeed_scraper:
    #     indeed_listings = await indeed_scraper.scrape(criteria)
    #     listings.extend(indeed_listings)
    #     # fetch Indeed JDs while browser session is alive
    #     indeed_fetcher = JDFetcher(indeed_scraper.browser)
    #     indeed_listings = await indeed_fetcher.fetch_all(indeed_listings)

    async with GlassdoorScraper() as gd_scraper:
        gd_listings = await gd_scraper.scrape(criteria)
        # no separate JD fetch — already scraped from side panel

    all_listings = gd_listings
    filtered = JobFilter(criteria).run(all_listings)

    for job in filtered:
        desc_preview = job.description[:150] if job.description else "NO DESCRIPTION"
        print(f"\n[{job.source.value}] {job.title} @ {job.company}")
        print(f"  {desc_preview}...")

    with get_session() as session:
        saved, skipped = save_listings(session, filtered)
        logger.info(f"DB | saved: {saved} | skipped duplicates: {skipped}")

asyncio.run(main())