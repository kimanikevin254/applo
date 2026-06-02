from abc import ABC, abstractmethod
from playwright.async_api import async_playwright, Browser, Page
from playwright_stealth import Stealth
from applo.models import JobListing, SearchCriteria
from applo.config import settings
from applo.utils.logger import logger
from typing import Callable, Awaitable
import asyncio


async def _noop_emit(event: dict) -> None:
    pass


class BaseScraper(ABC):
    def __init__(self):
        self.browser: Browser | None = None
        self.delay = settings.scraper_delay_secs
        self._stealth_ctx = None
        self._playwright = None
        self.emit: Callable[[dict], Awaitable[None]] = _noop_emit

    async def __aenter__(self):
        self._stealth_ctx = Stealth().use_async(async_playwright())
        self._playwright = await self._stealth_ctx.__aenter__()
        self.browser = await self._playwright.chromium.launch(
            headless=settings.scraper_headless
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()
        if self._stealth_ctx:
            await self._stealth_ctx.__aexit__(exc_type, exc_val, exc_tb)

    async def new_page(self) -> Page:
        page = await self.browser.new_page()
        await page.set_viewport_size({"width": 1280, "height": 800})
        await page.set_extra_http_headers({
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        })
        return page

    async def sleep(self):
        await asyncio.sleep(self.delay)

    @abstractmethod
    async def scrape(self, criteria: SearchCriteria) -> list[JobListing]:
        pass

    def _parse_salary(self, salary_str: str) -> tuple[int | None, int | None]:
        import re
        if not salary_str:
            return None, None
        numbers = re.findall(r"[\d,]+", salary_str.replace("K", "000"))
        numbers = [int(n.replace(",", "")) for n in numbers]
        if len(numbers) == 0:
            return None, None
        if len(numbers) == 1:
            return numbers[0], numbers[0]
        return numbers[0], numbers[1]