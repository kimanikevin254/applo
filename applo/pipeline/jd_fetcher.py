from playwright.async_api import Browser, Page
from applo.models import JobListing, JobSource
from applo.utils.logger import logger
from applo.config import settings
import asyncio


class JDFetcher:
    """Fetches full JDs using an existing browser session (avoids Cloudflare re-check)."""

    def __init__(self, browser: Browser):
        self.browser = browser

    async def fetch_all(self, listings: list[JobListing]) -> list[JobListing]:
        results = []
        for job in listings:
            page = await self.browser.new_page()
            await page.set_viewport_size({"width": 1280, "height": 800})
            await page.set_extra_http_headers({
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            })
            try:
                description = await self._fetch_one(page, job)
                job.description = description
                logger.info(f"JD | fetched: {job.title} @ {job.company} ({len(description)} chars)")
            except Exception as e:
                logger.warning(f"JD | failed for {job.title} @ {job.company}: {e}")
            finally:
                await page.close()
            results.append(job)
            await asyncio.sleep(settings.scraper_delay_secs)
        return results

    async def _fetch_one(self, page: Page, job: JobListing) -> str:
        if job.source == JobSource.INDEED:
            return await self._fetch_indeed(page, job.job_url)
        elif job.source == JobSource.GLASSDOOR:
            return await self._fetch_glassdoor(page, job.job_url)
        return ""

    async def _fetch_indeed(self, page: Page, url: str) -> str:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        selectors = [
            '#jobDescriptionText',
            '[class*="jobsearch-jobDescriptionText"]',
            '[class*="job-description"]',
        ]
        for selector in selectors:
            el = await page.query_selector(selector)
            if el:
                return (await el.inner_text()).strip()

        logger.warning(f"JD | Indeed: no description selector matched for {url}")
        return ""

    async def _fetch_glassdoor(self, page: Page, url: str) -> str:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        try:
            await page.wait_for_selector('[class*="JobDetails_jobDetailsContainer"]', timeout=8000)
        except Exception:
            pass

        show_more = await page.query_selector('[class*="JobDetails_showMore"]')
        if show_more:
            await show_more.click()
            await page.wait_for_timeout(1000)

        selectors = [
            '[class*="JobDetails_jobDetailsContainer"]',
            '[class*="TwoColumnJobView_columnLeft"]',
            '[class*="JobViewPage_sectionContainer"]',
        ]
        for selector in selectors:
            el = await page.query_selector(selector)
            if el:
                return (await el.inner_text()).strip()

        logger.warning(f"JD | Glassdoor: no description selector matched for {url}")
        return ""