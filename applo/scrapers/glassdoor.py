from playwright.async_api import Page
from applo.models import JobListing, JobSource, SearchCriteria
from applo.utils.logger import logger
from applo.scrapers.base import BaseScraper
from datetime import datetime
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
        url = f"https://www.glassdoor.com/Job/jobs.htm?sc.keyword={title.replace(' ', '+')}&locT=C&locId=11047"

        await page.set_viewport_size({"width": 1280, "height": 800})
        await page.set_extra_http_headers({
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        })

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except Exception:
            # if still times out, try with whatever loaded
            pass

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

                job_title = await title_el.inner_text() if title_el else "Unknown"
                company = await company_el.inner_text() if company_el else "Unknown"
                location_text = await location_el.inner_text() if location_el else "Unknown"
                salary_text = await salary_el.inner_text() if salary_el else ""
                href = await link_el.get_attribute("href") if link_el else ""
                job_url = f"https://www.glassdoor.com{href}" if href and href.startswith("/") else href

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
                    scraped_at=datetime.utcnow(),
                ))
            except Exception as e:
                logger.warning(f"Glassdoor | skipping card: {e}")
                continue

        return listings