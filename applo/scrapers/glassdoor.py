from playwright.async_api import Page
from applo.models import JobListing, JobSource, SearchCriteria
from applo.utils.logger import logger
from applo.scrapers.base import BaseScraper
from datetime import datetime, timezone
import hashlib


class GlassdoorScraper(BaseScraper):
    BASE_URL = "https://www.glassdoor.com/Job"

    async def scrape(self, criteria: SearchCriteria) -> list[JobListing]:
        listings: list[JobListing] = []

        for title in criteria.job_titles:
            for location in criteria.locations:
                logger.info(f"Glassdoor | scraping: '{title}' in '{location}'")
                page = await self.new_page()
                try:
                    results = await self._scrape_page(page, title, location)
                    listings.extend(results)
                    logger.info(f"Glassdoor | found {len(results)} listings")
                except Exception as e:
                    logger.error(f"Glassdoor | failed for '{title}' in '{location}': {e}")
                finally:
                    await page.close()
                await self.sleep()

        return listings

    async def _scrape_page(self, page: Page, title: str, location: str) -> list[JobListing]:
        location_lower = location.lower().strip()

        if location_lower == "remote":
            url = (
                f"https://www.glassdoor.com/Job/jobs.htm"
                f"?sc.keyword={title.replace(' ', '+')}"
                f"&remoteWorkType=1&sort=date_desc"
            )
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        else:
            # start with keyword only, then resolve location via dropdown
            base_url = f"https://www.glassdoor.com/Job/jobs.htm?sc.keyword={title.replace(' ', '+')}&sort=date_desc"
            await page.goto(base_url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2000)

            try:
                # clear and fill location input
                loc_input = await page.wait_for_selector("#searchBar-location", timeout=5000)
                await loc_input.click()
                await loc_input.fill("")
                await loc_input.type(location, delay=80)

                # wait for dropdown and click first suggestion
                await page.wait_for_selector("#searchBar-location-search-suggestions", timeout=5000)
                first = await page.query_selector("#searchBar-location-search-suggestions li:first-child")
                if first:
                    await first.click()
                    # wait for URL to change (location resolved) then wait for cards
                    await page.wait_for_url("**/Job/**", timeout=8000)
                    await page.wait_for_selector('[data-test="jobListing"]', timeout=10000)
                else:
                    logger.warning(f"Glassdoor | no location suggestions for '{location}', searching without location filter")
            except Exception as e:
                logger.warning(f"Glassdoor | location resolution failed for '{location}': {e}")

        await page.wait_for_timeout(3000)

        cards = await page.query_selector_all('[data-test="jobListing"]')
        listings = []

        for card in cards:
            try:
                raw_text = await card.inner_text()

                title_el = await card.query_selector('[class*="JobCard_jobTitle"]')
                company_el = await card.query_selector('[class*="EmployerProfile_compactEmployerName"]')
                location_el = await card.query_selector('[class*="JobCard_location"]')
                salary_el = await card.query_selector('[class*="JobCard_salaryEstimate"]')
                link_el = await card.query_selector('a[href*="/job-listing/"]')
                date_el = await card.query_selector('[class*="JobCard_listingAge"]')

                job_title = await title_el.inner_text() if title_el else "Unknown"
                company = await company_el.inner_text() if company_el else "Unknown"
                location_text = await location_el.inner_text() if location_el else "Unknown"
                salary_text = await salary_el.inner_text() if salary_el else ""
                href = await link_el.get_attribute("href") if link_el else ""
                job_url = f"https://www.glassdoor.com{href}" if href and href.startswith("/") else href
                posted_text = await date_el.inner_text() if date_el else ""

                logger.debug(f"Glassdoor | posted_text raw: '{posted_text}' | title: '{job_title}'")

                # date filter AFTER all fields extracted
                if posted_text and not self._is_today(posted_text):
                    logger.debug(f"Glassdoor | skipping old listing ({posted_text}): {job_title} @ {company}")
                    continue

                external_id = href.split("jobListingId=")[-1].split("&")[0] if "jobListingId=" in href else hashlib.md5(raw_text.encode()).hexdigest()[:12]
                salary_min, salary_max = self._parse_salary(salary_text)

                listings.append(JobListing(
                    source=JobSource.GLASSDOOR,
                    external_id=external_id,
                    title=job_title.strip(),
                    company=company.strip(),
                    location=location_text.strip(),
                    salary_min=salary_min,
                    salary_max=salary_max,
                    job_url=job_url,
                    raw_text=raw_text,
                    scraped_at=datetime.now(timezone.utc),
                ))
            except Exception as e:
                logger.warning(f"Glassdoor | skipping card: {e}")
                continue

        return listings
    
    def _is_today(self, posted_text: str) -> bool:
        """Allow jobs posted today or within 1 day (Glassdoor clock is imprecise)"""
        posted_text = posted_text.lower().strip()
        return any(unit in posted_text for unit in ["m ago", "h ago", "just posted", "today", "1d"])