from playwright.async_api import Page
from applo.models import JobListing, SearchCriteria
from applo.utils.logger import logger
from applo.scrapers.base import BaseScraper
from applo.scrapers.registry import ScraperRegistry
from applo.config import settings
from datetime import datetime, timezone
import hashlib
import asyncio
import re


@ScraperRegistry.register("glassdoor")
class GlassdoorScraper(BaseScraper):
    BASE_URL = "https://www.glassdoor.com/Job/jobs.htm"

    async def scrape(self, criteria: SearchCriteria) -> list[JobListing]:
        listings: list[JobListing] = []
        for title in criteria.job_titles:
            for location in criteria.locations:
                logger.info(f"Glassdoor | scraping: '{title}' in '{location}'")
                page = await self.new_page()
                try:
                    results = await self._scrape_page(page, title, location, criteria.max_age_days)
                    listings.extend(results)
                    logger.info(f"Glassdoor | found {len(results)} listings")
                except Exception as e:
                    logger.error(f"Glassdoor | failed for '{title}' in '{location}': {e}")
                finally:
                    await page.close()
                await self.sleep()
        return listings

    async def _scrape_page(self, page: Page, title: str, location: str, max_age_days: int) -> list[JobListing]:
        location_lower = location.lower().strip()

        if location_lower == "remote":
            url = (
                f"{self.BASE_URL}"
                f"?sc.keyword={title.replace(' ', '+')}"
                f"&remoteWorkType=1&fromAge={max_age_days}&sortBy=date_desc"
            )
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        else:
            base_url = (
                f"{self.BASE_URL}"
                f"?sc.keyword={title.replace(' ', '+')}"
                f"&fromAge={max_age_days}&sortBy=date_desc"
            )
            await page.goto(base_url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2000)

            try:
                loc_input = await page.wait_for_selector("#searchBar-location", timeout=5000)
                await loc_input.click()
                await loc_input.fill("")
                await loc_input.type(location, delay=80)
                await page.wait_for_selector("#searchBar-location-search-suggestions", timeout=5000)
                first = await page.query_selector("#searchBar-location-search-suggestions li:first-child")
                if first:
                    await first.click()
                    await page.wait_for_url("**/Job/**", timeout=8000)
                    await page.wait_for_selector('[data-test="jobListing"]', timeout=10000)
                else:
                    logger.warning(f"Glassdoor | no location suggestions for '{location}'")
            except Exception as e:
                logger.warning(f"Glassdoor | location resolution failed for '{location}': {e}")

        await page.wait_for_timeout(3000)

        cards = await page.query_selector_all('[data-test="jobListing"]')

        # PASS 1: extract metadata from all cards first
        card_data = []
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

                if posted_text and not self._is_recent(posted_text, max_age_days):
                    logger.debug(f"Glassdoor | skipping old listing ({posted_text}): {job_title} @ {company}")
                    continue

                card_data.append({
                    "raw_text": raw_text,
                    "job_title": job_title,
                    "company": company,
                    "location_text": location_text,
                    "salary_text": salary_text,
                    "href": href,
                    "job_url": job_url,
                    "posted_text": posted_text,
                })
            except Exception as e:
                logger.warning(f"Glassdoor | skipping card metadata: {e}")
                continue

        # PASS 2: click each card and extract JD from side panel
        listings = []
        cards = await page.query_selector_all('[data-test="jobListing"]')

        for data in card_data:
            description = ""
            try:
                # find matching card by href and click it
                for card in cards:
                    link_el = await card.query_selector('a[href*="/job-listing/"]')
                    if link_el:
                        href = await link_el.get_attribute("href")
                        if href == data["href"]:
                            await card.click()
                            await self._dismiss_auth_modal(page)
                            await page.wait_for_selector(
                                '[class*="JobDetails_jobDetailsContainer"]', timeout=5000
                            )
                            # try specific selectors first, fall back to container
                            jd_selectors = [
                                '[class*="JobDetails_jobDescription"]',
                                '[data-test="jobDescriptionContent"]',
                                '[class*="JobDetails_jobDetailsContainer"]',
                            ]
                            for sel in jd_selectors:
                                jd_el = await page.query_selector(sel)
                                if jd_el:
                                    description = (await jd_el.inner_text()).strip()
                                    break
                            await asyncio.sleep(1)
                            break
            except Exception as e:
                logger.debug(f"Glassdoor | side panel JD failed for {data['job_title']}: {e}")

            href = data["href"]
            external_id = (
                href.split("jobListingId=")[-1].split("&")[0]
                if "jobListingId=" in href
                else hashlib.md5(data["raw_text"].encode()).hexdigest()[:12]
            )
            salary_min, salary_max = self._parse_salary(data["salary_text"])

            listings.append(JobListing(
                source="glassdoor",
                external_id=external_id,
                title=data["job_title"].strip(),
                company=data["company"].strip(),
                location=data["location_text"].strip(),
                salary_min=salary_min,
                salary_max=salary_max,
                job_url=data["job_url"],
                description=description,
                raw_text=data["raw_text"],
                posted_text=data["posted_text"] or None,
                scraped_at=datetime.now(timezone.utc),
            ))

        return listings

    def _is_recent(self, posted_text: str, max_age_days: int) -> bool:
        text = posted_text.lower().strip()
        if any(u in text for u in ["m ago", "h ago", "just posted", "today"]):
            return True
        match = re.search(r"(\d+)d", text)
        if match:
            return int(match.group(1)) <= max_age_days
        return True
    
    async def _dismiss_auth_modal(self, page: Page) -> None:
        try:
            close_btn = await page.wait_for_selector(
                '[data-test="auth-modal-close-button"]', timeout=settings.glassdoor_auth_modal_timeout
            )
            if close_btn:
                await close_btn.click()
                await page.wait_for_timeout(500)
                logger.debug("Glassdoor | auth modal dismissed")
        except Exception:
            pass # modal did not appear