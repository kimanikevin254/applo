# Contributing

Thanks for your interest in contributing to Applo. Adding a new job board scraper is the most impactful thing you can do, and the plugin system was built to make that as straightforward as possible.

---

## Dev setup

```bash
git clone https://github.com/kimanikevin254/applo.git
cd applo
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
cp .env.example .env
# fill in your ANTHROPIC_API_KEY
mkdir -p data/resumes data/output
python run.py
```

The app runs at [http://localhost:8000](http://localhost:8000).

---

## Adding a scraper

This is the main extension point. Read [docs/scrapers.md](docs/scrapers.md) for a full walkthrough of the plugin API. The short version:

1. Create `applo/scrapers/yoursite.py`
2. Extend `BaseScraper`, decorate with `@ScraperRegistry.register("yoursite")`
3. Implement `async def scrape(self, criteria: SearchCriteria) -> list[JobListing]`
4. Call `await self.emit(...)` at key points so the UI shows live progress

No other files need to be touched. The scraper auto-discovers on the next startup.

---

## Project layout

```
applo/scrapers/    # Drop new scrapers here
applo/pipeline/    # Resume optimization and filtering logic
applo/resume/      # .docx parsing and PDF generation
applo/web/         # FastAPI app and Jinja2 templates
applo/db/          # SQLAlchemy ORM and session helpers
applo/config.py    # All settings (pydantic-settings, reads from .env)
applo/models.py    # Shared Pydantic models
```

---

## Running tests

```bash
pytest
```

Tests live in `tests/`. When adding a scraper, a basic test that instantiates the class and checks its registration is appreciated but not required.

---

## Pull request guidelines

- Keep PRs focused. A scraper for one job board, a bug fix, or a single feature per PR.
- Test your scraper against a real search before submitting. Include a note in the PR description about what search terms and location you tested with.
- Do not commit your `.env` file or any keys.
- The `data/` directory is gitignored. Do not commit database files or generated PDFs.

---

## Reporting issues

Open an issue on GitHub. If it is a scraper that stopped working, include the job board URL and the error from the server log (`--log-level debug` helps).
