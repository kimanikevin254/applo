# Applo

A self-hosted job application pipeline. Applo scrapes job boards, filters results against your criteria, and uses an LLM to tailor your resume and write a cover letter for each role. Optionally syncs your pipeline to Google Sheets and backs up documents to Google Drive.

![Python](https://img.shields.io/badge/python-3.11%2B-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.111%2B-009688) ![License](https://img.shields.io/badge/license-MIT-green)

---

## Features

- **Scraper plugin system** — add a new job source by dropping a single file into `applo/scrapers/`. No changes to core files required.
- **Live scraping progress** — the UI streams real-time updates via Server-Sent Events as jobs are collected.
- **Multi-provider LLM support** — works with Anthropic, OpenAI, Google Gemini, or any LiteLLM-compatible model.
- **DOCX-based resume pipeline** — parses your master `.docx` resume, surgically patches optimized sections in-place, and exports to PDF via Gotenberg. Your original formatting is fully preserved.
- **Resume optimization** — tailors your summary, skills, and experience bullets to match each job description.
- **Cover letter generation** — writes a role-specific cover letter alongside the resume.
- **Editable output** — edit the optimized resume and cover letter directly in the UI before regenerating PDFs.
- **Manual job entry** — paste a job description without scraping to get an optimized resume for any role.
- **Configurable search criteria** — set job titles, locations, excluded keywords, and salary floor from the UI.
- **Application pipeline** — track each job through pending, optimized, approved, applied, and rejected stages.
- **Google integration (optional)** — connect your Google account to back up PDFs to Drive and auto-sync your pipeline to Sheets for tracking.

---

## Quickstart

### Docker (recommended)

The easiest way to run Applo. No local dependencies needed beyond Docker.

```bash
git clone https://github.com/kimanikevin254/applo.git
cd applo
cp .env.example .env
# fill in at minimum your LLM API key
mkdir -p data/resumes data/output
docker compose up
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

Applo runs alongside [Gotenberg](https://gotenberg.dev) — a self-hosted document conversion service used for PDF export. Both start automatically via `docker compose`.

### Local development

```bash
git clone https://github.com/kimanikevin254/applo.git
cd applo
uv sync
playwright install chromium
cp .env.example .env
mkdir -p data/resumes data/output
```

Gotenberg must be running separately for PDF export:

```bash
docker run -p 3000:3000 gotenberg/gotenberg:8
```

Then start the app:

```bash
python run.py
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

### Upload your resume

Click **Resume** in the header and upload your master `.docx` file. This is the base document that gets tailored for each application.

---

## Configuration

All config is read from `.env`. Copy `.env.example` to get started.

| Variable                  | Required | Default                        | Description                                                        |
| ------------------------- | -------- | ------------------------------ | ------------------------------------------------------------------ |
| `ANTHROPIC_API_KEY`       | Yes\*    |                                | Default LLM API key. Can be overridden in the UI.                  |
| `ANTHROPIC_MODEL`         | No       | `anthropic/claude-haiku-4-5`   | Default model in LiteLLM format.                                   |
| `DATABASE_URL`            | No       | `sqlite:///./data/applo.db`    | SQLAlchemy connection string.                                      |
| `SCRAPER_HEADLESS`        | No       | `true`                         | Run browser in headless mode. Set to `false` to watch scraping.    |
| `SCRAPER_DELAY_SECS`      | No       | `2`                            | Delay between page requests.                                       |
| `MASTER_RESUME_PATH`      | No       | `data/resumes/master.docx`     | Path to your master resume.                                        |
| `GOTENBERG_URL`           | No       | `http://localhost:3000`        | URL of the Gotenberg service. Set automatically in Docker.         |
| `GOOGLE_CREDENTIALS_PATH` | No       | `data/google_credentials.json` | OAuth 2.0 client secret from Google Cloud Console.                 |
| `GOOGLE_TOKEN_PATH`       | No       | `data/token.json`              | Where the OAuth token is saved after connecting.                   |
| `GOOGLE_SHEET_ID`         | No       |                                | ID of the Google Sheet to sync your pipeline to.                   |
| `GOOGLE_DRIVE_FOLDER_ID`  | No       |                                | ID of the Drive folder to upload resumes and cover letters to.     |

\*Required only if you have not set a key via the Model modal in the UI.

---

## Google Integration (optional)

Applo can sync your job pipeline to Google Sheets and back up generated PDFs to Google Drive. This is entirely optional — without it, files are saved locally and Sheets sync is unavailable.

### Setup

1. Create a Google Cloud project and enable the **Google Sheets API** and **Google Drive API**
2. Create an **OAuth 2.0 Client ID** (Desktop app) and download the JSON as `data/google_credentials.json`
3. Configure the OAuth consent screen (External, add yourself as a test user)
4. Create a Google Sheet and a Drive folder — copy their IDs into `.env`
5. Start Applo — a modal will prompt you to connect your Google account on first load
6. Click **Connect Google Account** and complete the OAuth flow in your browser

Once connected, resumes and cover letters are uploaded to Drive automatically on optimization, and job status changes sync to Sheets in the background. The **Sync to Sheets** button in the header force-syncs any stale rows.

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
    registry.py         # ScraperRegistry -- plugin registration
    base.py             # BaseScraper -- all scrapers extend this
    indeed.py           # Indeed scraper
    glassdoor.py        # Glassdoor scraper
  pipeline/
    optimizer.py        # LiteLLM resume + cover letter generation
    filter.py           # Post-scrape keyword, salary, and description filtering
  resume/
    parser.py           # Extracts sections and paragraph map from master .docx
    generator.py        # Patches optimized sections in-place, exports PDF via Gotenberg
  integrations/
    google.py           # OAuth flow, SheetsSync, DriveUpload
  db/
    database.py         # SQLAlchemy models and helpers
  web/
    app.py              # FastAPI routes
    templates/          # Jinja2 HTML templates
  models.py             # Pydantic models (JobListing, SearchCriteria, etc.)
  config.py             # Settings via pydantic-settings
data/
  resumes/              # Master resume (.docx) and parse cache (.json)
  output/               # Generated PDFs (.docx intermediates + final PDFs)
  applo.db              # SQLite database
  search-config.json    # Persisted search criteria
  model-config.json     # Persisted LLM model + key
  token.json            # Google OAuth token (auto-managed)
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
| Resume parsing     | python-docx                                   |
| PDF export         | Gotenberg (self-hosted, via Docker)           |
| Google integration | google-auth-oauthlib + gspread                |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

MIT
