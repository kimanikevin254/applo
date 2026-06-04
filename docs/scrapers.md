# Scraper Plugin API

Applo's scraper system is built around a self-registering plugin pattern. Any file dropped into `applo/scrapers/` is auto-discovered at startup. The file just needs to extend `BaseScraper` and register itself with `@ScraperRegistry.register`.

---

## Minimal example

```python
# applo/scrapers/mysite.py

from applo.scrapers.base import BaseScraper
from applo.scrapers.registry import ScraperRegistry
from applo.models import JobListing, SearchCriteria


@ScraperRegistry.register("mysite")
class MySiteScraper(BaseScraper):

    async def scrape(self, criteria: SearchCriteria) -> list[JobListing]:
        listings = []

        for title in criteria.job_titles:
            for location in criteria.locations:
                page = await self.new_page()
                try:
                    # your scraping logic here
                    pass
                finally:
                    await page.close()
                await self.sleep()

        return listings
```

After adding this file, restart the server. The source named `"mysite"` will appear in the scraper modal automatically.

---

## BaseScraper reference

### Methods available to your scraper

#### `await self.new_page() -> Page`

Opens a new Playwright page with a standard viewport (1280x800) and browser headers pre-configured. Always use this instead of `self.browser.new_page()` directly.

```python
page = await self.new_page()
await page.goto("https://example.com/jobs")
```

#### `await self.sleep()`

Waits `settings.scraper_delay_secs` seconds. Call this between requests to avoid rate limiting.

#### `await self.emit(event: dict)`

Sends a progress event to the UI. The UI renders these as live log lines during scraping. If your scraper is run outside the web context (e.g. in a test), `emit` is a no-op by default.

#### `self._parse_salary(salary_str: str) -> tuple[int | None, int | None]`

Parses a raw salary string like `"$80,000 - $120,000 a year"` into `(80000, 120000)`. Returns `(None, None)` if no numbers are found.

---

## Emit events

Call `await self.emit(...)` at key points in your scraper. These events power the live log in the UI.

### `start`

Called once per title/location combination before scraping begins.

```python
await self.emit({
    "type": "start",
    "source": "mysite",
    "title": title,
    "location": location,
})
```

### `found`

Called after the initial card list is loaded, before fetching individual job details.

```python
await self.emit({
    "type": "found",
    "source": "mysite",
    "count": len(cards),
})
```

### `detail`

Called for each job card as you extract its details. `index` is 1-based, `total` is the total card count.

```python
for i, card in enumerate(cards, 1):
    await self.emit({
        "type": "detail",
        "source": "mysite",
        "index": i,
        "total": len(cards),
        "title": job_title,
        "company": company,
    })
```

### `source_done`

Called when all jobs for the current title/location pair have been collected.

```python
await self.emit({
    "type": "source_done",
    "source": "mysite",
    "count": len(results),
})
```

---

## JobListing fields

Your scraper must return a list of `JobListing` objects. Required fields are marked.

```python
from applo.models import JobListing

JobListing(
    source="mysite",            # required -- must match your registry name
    external_id="abc123",       # required -- stable unique ID for this job (used for dedup)
    title="Software Engineer",  # required
    company="Acme Corp",        # required
    location="Remote",          # required
    job_url="https://...",      # required
    raw_text="full card text",  # required -- used as fallback for optimization
    description="...",          # optional -- full job description (fetched separately)
    salary_min=80000,           # optional
    salary_max=120000,          # optional
    posted_text="2 days ago",   # optional
)
```

The `external_id` is used to detect duplicates across scrape runs. Use the job board's native ID if available, or a hash of stable fields as a fallback:

```python
import hashlib
external_id = hashlib.md5(f"{title}{company}{job_url}".encode()).hexdigest()[:12]
```

---

## SearchCriteria fields

Your scraper receives a `SearchCriteria` object with the user's current settings.

```python
criteria.job_titles        # list[str] -- e.g. ["software engineer", "backend engineer"]
criteria.locations         # list[str] -- e.g. ["remote", "New York NY"]
criteria.excluded_keywords # list[str] -- post-scrape filtering (handled by JobFilter)
criteria.min_salary        # int | None -- post-scrape filtering (handled by JobFilter)
criteria.max_age_days      # int -- 1, 3, or 7 -- pass to the job board's "posted within" filter
criteria.sources           # list[str] -- sources selected in the UI for this run
```

You do not need to apply `excluded_keywords` or `min_salary` yourself. The `JobFilter` pipeline step handles those after all scrapers finish.

---

## Async context manager

`BaseScraper` is an async context manager. It launches and closes the Playwright browser automatically. You do not need to manage the browser lifecycle in your `scrape()` method.

The web app uses it like this:

```python
async with MySiteScraper() as scraper:
    scraper.emit = emit   # wire up the SSE callback
    results = await scraper.scrape(criteria)
```

---

## Tips

- Use `page.wait_for_selector(...)` rather than fixed timeouts where possible. Job board pages load dynamically and fixed timeouts are fragile.
- Log with `from applo.utils.logger import logger` so your output appears consistently with the rest of the app.
- If the job board requires authentication or has a CAPTCHA, `SCRAPER_HEADLESS=false` in `.env` lets you watch what the browser is doing.
- Test your scraper in isolation before wiring it into the UI:

```python
import asyncio
from applo.models import SearchCriteria
from applo.scrapers.mysite import MySiteScraper

async def main():
    criteria = SearchCriteria(job_titles=["software engineer"], locations=["remote"])
    async with MySiteScraper() as scraper:
        results = await scraper.scrape(criteria)
        for job in results:
            print(job.title, "@", job.company)

asyncio.run(main())
```
