from playwright.async_api import Page
from applo.models import JobListing, JobSource, SearchCriteria
from applo.utils.logger import logger
from applo.scrapers.base import BaseScraper
from datetime import datetime
import hashlib


class IndeedScraper(BaseScraper):
    BASE_URL = "https://www.indeed.com/jobs"

    async def scrape(self, criteria: SearchCriteria) -> list[JobListing]:
        listings: list[JobListing] = []

        for title in criteria.job_titles:
            for location in criteria.locations:
                logger.info(f"Indeed | scraping: '{title}' in '{location}'")
                page = await self.new_page()
                try:
                    results = await self._scrape_page(page, title, location)
                    listings.extend(results)
                    logger.info(f"Indeed | found {len(results)} listings")
                except Exception as e:
                    logger.error(f"Indeed | failed for '{title}' in '{location}': {e}")
                finally:
                    await page.close()
                await self.sleep()

        return listings

    async def _scrape_page(self, page: Page, title: str, location: str) -> list[JobListing]:
        params = f"?q={title.replace(' ', '+')}&l={location.replace(' ', '+')}&fromage=1&sort=date"
        await page.goto(self.BASE_URL + params, wait_until="networkidle")
        await page.wait_for_timeout(2000)

        cards = await page.query_selector_all('[class*="job_seen_beacon"]')
        listings = []

        for card in cards:
            try:
                raw_text = await card.inner_text()

                title_el = await card.query_selector('[class*="jobTitle"]')
                company_el = await card.query_selector('[data-testid="company-name"]')
                location_el = await card.query_selector('[data-testid="text-location"]')
                salary_el = await card.query_selector('[class*="salary"]')
                link_el = await card.query_selector('a[id^="job_"]')

                job_title = await title_el.inner_text() if title_el else "Unknown"
                company = await company_el.inner_text() if company_el else "Unknown"
                location_text = await location_el.inner_text() if location_el else "Unknown"
                salary_text = await salary_el.inner_text() if salary_el else ""
                href = await link_el.get_attribute("href") if link_el else ""
                job_url = f"https://www.indeed.com{href}" if href else ""

                # stable unique id from url or fallback to hash
                external_id = href.split("jk=")[-1].split("&")[0] if "jk=" in href else hashlib.md5(raw_text.encode()).hexdigest()[:12]

                salary_min, salary_max = self._parse_salary(salary_text)

                listings.append(JobListing(
                    source=JobSource.INDEED,
                    external_id=external_id,
                    title=job_title.strip(),
                    company=company.strip(),
                    location=location_text.strip(),
                    salary_min=salary_min,
                    salary_max=salary_max,
                    job_url=job_url,
                    raw_text=raw_text,
                    scraped_at=datetime.utcnow(),
                ))
            except Exception as e:
                logger.warning(f"Indeed | skipping card: {e}")
                continue

        return listings