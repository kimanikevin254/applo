# Applo

A self-hosted job application pipeline. Applo scrapes job boards, filters results against your criteria, and uses an LLM to tailor your resume and write a cover letter for each role. Everything runs locally. Your resume and API keys never leave your machine.

![Python](https://img.shields.io/badge/python-3.11%2B-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.111%2B-009688) ![License](https://img.shields.io/badge/license-MIT-green)

---

## Features

- **Scraper plugin system**: add a new job source by dropping a single file into `applo/scrapers/`. No changes to core files required.
- **Live scraping progress**: the UI streams real-time updates via Server-Sent Events as jobs are collected.
- **Multi-provider LLM support**: works with Anthropic, OpenAI, Google Gemini, or any LiteLLM-compatible model.
- **Resume optimization**: tailors your summary, skills, and experience bullets to match each job description.
- **Cover letter generation**: writes a role-specific cover letter alongside the resume.
- **Editable output**: edit the optimized resume and cover letter directly in the UI before regenerating PDFs.
- **Manual job entry**: paste a job description without scraping to get an optimized resume for any role.
- **Configurable search criteria**: set job titles, locations, excluded keywords, and salary floor from the UI.
- **Application pipeline**: track each job through pending, optimized, approved, applied, and rejected stages.

---

## Quickstart

### 1. Clone and install

```bash
git clone https://github.com/kimanikevin254/applo.git
cd applo
python -m venv .venv
source .venv/bin/activate
pip install -e .
playwright install chromium
```

### 2. Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in your values:

```env
ANTHROPIC_API_KEY=sk-ant-...
```

See [Configuration](#configuration) for all available options.

### 3. Create the data directory

```bash
mkdir -p data/resumes data/output
```

### 4. Run

```bash
python run.py
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

### 5. Upload your resume

Click **Resume** in the header and upload your master `.docx` file. This is the base document that gets tailored for each application.

---

## Configuration

All config is read from `.env`. Copy `.env.example` to get started.

| Variable             | Required | Default                      | Description                                                     |
| -------------------- | -------- | ---------------------------- | --------------------------------------------------------------- |
| `ANTHROPIC_API_KEY`  | Yes\*    |                              | Default LLM API key. Can be overridden in the UI.               |
| `ANTHROPIC_MODEL`    | No       | `anthropic/claude-haiku-4-5` | Default model in LiteLLM format.                                |
| `DATABASE_URL`       | No       | `sqlite:///./data/applo.db`  | SQLAlchemy connection string.                                   |
| `SCRAPER_HEADLESS`   | No       | `true`                       | Run browser in headless mode. Set to `false` to watch scraping. |
| `SCRAPER_DELAY_SECS` | No       | `2`                          | Delay between page requests.                                    |
| `MASTER_RESUME_PATH` | No       | `data/resumes/master.docx`   | Path to your master resume.                                     |

\*Required only if you have not set a key via the Model modal in the UI.

The model and API key can also be changed at runtime through the **Model** button in the header. No restart needed.

---

## Adding a scraper

Applo uses a self-registering plugin system. To add a new job source:

**1. Create a file in `applo/scrapers/`**

```bash
touch applo/scrapers/linkedin.py
```

**2. Extend `BaseScraper` and register with `@ScraperRegistry.register`**

```python
from applo.scrapers.base import BaseScraper
from applo.scrapers.registry import ScraperRegistry
from applo.models import JobListing, SearchCriteria


@ScraperRegistry.register("linkedin")
class LinkedInScraper(BaseScraper):

    async def scrape(self, criteria: SearchCriteria) -> list[JobListing]:
        listings = []

        for title in criteria.job_titles:
            for location in criteria.locations:
                await self.emit({
                    "type": "start",
                    "source": "linkedin",
                    "title": title,
                    "location": location,
                })

                page = await self.new_page()
                # ... scraping logic ...
                await page.close()

                listings.extend(results)
                await self.emit({
                    "type": "source_done",
                    "source": "linkedin",
                    "count": len(results),
                })

        return listings
```

That is everything. The scraper auto-discovers on startup and appears as a selectable source in the UI.

See [docs/scrapers.md](docs/scrapers.md) for the full plugin API reference.

---

## Project structure

```
applo/
  scrapers/
    registry.py       # ScraperRegistry -- plugin registration
    base.py           # BaseScraper -- all scrapers extend this
    indeed.py         # Indeed scraper
    glassdoor.py      # Glassdoor scraper
  pipeline/
    optimizer.py      # LiteLLM resume + cover letter generation
    filter.py         # Post-scrape keyword and salary filtering
  resume/
    parser.py         # Extracts sections from master .docx
    generator.py      # Renders tailored resume and cover letter PDFs
  db/
    database.py       # SQLAlchemy models and helpers
  web/
    app.py            # FastAPI routes
    templates/        # Jinja2 HTML templates
  models.py           # Pydantic models (JobListing, SearchCriteria, etc.)
  config.py           # Settings via pydantic-settings
data/
  resumes/            # Master resume (.docx)
  output/             # Generated PDFs
  applo.db            # SQLite database
  search-config.json  # Persisted search criteria
  model-config.json   # Persisted LLM model + key
```

---

## Tech stack

| Layer              | Technology                                    |
| ------------------ | --------------------------------------------- |
| Web framework      | FastAPI                                       |
| UI                 | HTMX + Jinja2 (no build step)                 |
| Browser automation | Playwright + playwright-stealth               |
| LLM                | LiteLLM (Anthropic, OpenAI, Gemini, and more) |
| Database           | SQLite via SQLAlchemy                         |
| PDF generation     | ReportLab                                     |
| Resume parsing     | python-docx + pdfplumber                      |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

MIT
