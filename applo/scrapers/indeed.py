from playwright.async_api import Page
from applo.models import JobListing, SearchCriteria
from applo.utils.logger import logger
from applo.scrapers.base import BaseScraper
from applo.scrapers.registry import ScraperRegistry
from datetime import datetime, timezone
import hashlib
import asyncio


@ScraperRegistry.register("indeed")
class IndeedScraper(BaseScraper):
    BASE_URL = "https://www.indeed.com/jobs"

    async def scrape(self, criteria: SearchCriteria) -> list[JobListing]:
        listings: list[JobListing] = []
        for title in criteria.job_titles:
            for location in criteria.locations:
                logger.info(f"Indeed | scraping: '{title}' in '{location}'")
                await self.emit({"type": "start", "source": "indeed", "title": title, "location": location})
                page = await self.new_page()
                try:
                    results = await self._scrape_page(page, title, location, criteria.max_age_days)
                    listings.extend(results)
                    logger.info(f"Indeed | found {len(results)} listings")
                    await self.emit({"type": "source_done", "source": "indeed", "count": len(results)})
                except Exception as e:
                    logger.error(f"Indeed | failed for '{title}' in '{location}': {e}")
                finally:
                    await page.close()
                await self.sleep()
        return listings

    async def _scrape_page(self, page: Page, title: str, location: str, max_age_days: int) -> list[JobListing]:
        params = f"?q={title.replace(' ', '+')}&l={location.replace(' ', '+')}&fromage={max_age_days}&sort=date"
        await page.goto(self.BASE_URL + params, wait_until="networkidle")
        await page.wait_for_timeout(2000)

        cards = await page.query_selector_all('[class*="job_seen_beacon"]')
        await self.emit({"type": "found", "source": "indeed", "count": len(cards)})

        # PASS 1: extract metadata from all cards
        card_data = []
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
                external_id = href.split("jk=")[-1].split("&")[0] if "jk=" in href else hashlib.md5(raw_text.encode()).hexdigest()[:12]

                card_data.append({
                    "raw_text": raw_text,
                    "job_title": job_title,
                    "company": company,
                    "location_text": location_text,
                    "salary_text": salary_text,
                    "href": href,
                    "job_url": job_url,
                    "external_id": external_id,
                })
            except Exception as e:
                logger.warning(f"Indeed | skipping card metadata: {e}")
                continue

        # PASS 2: click each card and extract JD from right panel
        listings = []
        cards = await page.query_selector_all('[class*="job_seen_beacon"]')
        total = len(card_data)

        for i, data in enumerate(card_data, 1):
            await self.emit({"type": "detail", "source": "indeed", "index": i, "total": total, "title": data["job_title"], "company": data["company"]})
            description = ""
            try:
                for card in cards:
                    link_el = await card.query_selector('a[id^="job_"]')
                    if link_el:
                        href = await link_el.get_attribute("href")
                        if href == data["href"]:
                            await card.click()
                            await page.wait_for_selector('#jobsearch-ViewjobPaneWrapper', timeout=5000)

                            jd_selectors = [
                                '#jobDescriptionText',
                                '#mosaic-vjJobDetails',
                                '[class*="jobsearch-embeddedBody"]',
                            ]
                            for sel in jd_selectors:
                                jd_el = await page.query_selector(sel)
                                if jd_el:
                                    description = (await jd_el.inner_text()).strip()
                                    break
                            await asyncio.sleep(1)
                            break
            except Exception as e:
                logger.debug(f"Indeed | right panel JD failed for {data['job_title']}: {e}")

            salary_min, salary_max = self._parse_salary(data["salary_text"])

            listings.append(JobListing(
                source="indeed",
                external_id=data["external_id"],
                title=data["job_title"].strip(),
                company=data["company"].strip(),
                location=data["location_text"].strip(),
                salary_min=salary_min,
                salary_max=salary_max,
                job_url=data["job_url"],
                description=description,
                raw_text=data["raw_text"],
                posted_text=None,
                scraped_at=datetime.now(timezone.utc),
            ))

        return listings