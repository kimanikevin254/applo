# Architecture

A high-level walkthrough of how Applo is structured and why the key design decisions were made.

---

## Overview

```
Browser (HTMX + SSE)
        |
   FastAPI (app.py)
        |
   +---------+----------+-----------+
   |         |          |           |
Scrapers  Optimizer  Resume      Database
(Playwright) (LiteLLM) (ReportLab) (SQLite)
```

The web layer is thin. Routes in `app.py` mostly coordinate between the scraper, optimizer, and database layers. Business logic lives in the individual modules.

---

## Scraper plugin system

Scrapers self-register using a decorator pattern. `ScraperRegistry` is a class-level dict:

```python
# applo/scrapers/registry.py

class ScraperRegistry:
    _registry: dict[str, type] = {}

    @classmethod
    def register(cls, name: str):
        def decorator(scraper_cls):
            cls._registry[name] = scraper_cls
            return scraper_cls
        return decorator
```

Each scraper file decorates its class with `@ScraperRegistry.register("name")`. The `__init__.py` for the scrapers package auto-discovers all `.py` files in the directory and imports them:

```python
# applo/scrapers/__init__.py

for _f in Path(__file__).parent.glob("*.py"):
    if _f.stem not in ("__init__", "base", "registry"):
        importlib.import_module(f"applo.scrapers.{_f.stem}")
```

This means adding a new scraper requires no changes to any existing file. The import triggers the decorator, which registers the class. The web app then reads `ScraperRegistry.list_all()` to populate the source checkboxes in the UI.

---

## Live progress with Server-Sent Events

When the user clicks "Run Scraper", the browser opens an `EventSource` connection to `/scrape-stream`. The server runs all selected scrapers as concurrent `asyncio` tasks and streams progress events back as they happen.

The key is an `asyncio.Queue` shared between the scraper tasks and the SSE generator:

```python
queue: asyncio.Queue = asyncio.Queue()

async def emit(event: dict):
    await queue.put(json.dumps(event))

# Scrapers call scraper.emit = emit before running.
# The generator drains the queue while waiting for tasks:

while pending:
    while not queue.empty():
        yield f"data: {queue.get_nowait()}\n\n"
    done, pending = await asyncio.wait(pending, timeout=0.05)
```

This gives you real-time progress without threads or external message brokers.

The browser side uses a plain `EventSource`:

```javascript
const es = new EventSource('/scrape-stream?sources=indeed&sources=glassdoor');
es.onmessage = (ev) => { /* render log line */ };
```

HTMX is not used for the scraping flow specifically because `EventSource` handles SSE natively and HTMX's SSE extension adds unnecessary complexity for this case.

---

## LLM integration via LiteLLM

The optimizer uses [LiteLLM](https://github.com/BerriAI/litellm) as a unified interface so the user can swap providers without changing any application code:

```python
response = litellm.completion(
    model=cfg["model"],   # e.g. "anthropic/claude-haiku-4-5" or "openai/gpt-4o"
    messages=[{"role": "user", "content": prompt}]
)
```

The model and API key are stored in `data/model-config.json` and loaded fresh on each optimization call. This means the user can change the model in the UI and the next optimization will use it immediately without a restart.

The model string follows LiteLLM's `provider/model-name` convention. Any model supported by LiteLLM works, including Anthropic, OpenAI, Google Gemini, Ollama, and Cohere.

---

## Resume optimization flow

1. User clicks "Optimize" on a job.
2. The route sets application status to `optimizing` and returns immediately (the UI shows a spinner).
3. `ResumeOptimizer.optimize()` runs in a thread executor to avoid blocking the async event loop.
4. The optimizer builds a prompt with the job description and the user's parsed resume sections, then calls the LLM.
5. The LLM returns a JSON object with rewritten summary, skills, experience bullets, and a cover letter.
6. `ResumeGenerator` applies the optimized sections to the master `.docx` structure and renders two PDFs (resume + cover letter) via ReportLab.
7. The optimization JSON, cover letter text, and PDF paths are saved to the database.
8. Status updates to `optimized` and the page refreshes.

The raw optimization JSON is stored so the user can edit any field and regenerate PDFs without re-running the LLM.

---

## Configuration

Settings are managed by `pydantic-settings` in `applo/config.py`. Values are read from the environment (or `.env` file) and validated at startup. Runtime config (model selection, search criteria) is stored in JSON files under `data/` and loaded on each request, so changes take effect without a restart.

```
.env                      # environment-level secrets and defaults
data/model-config.json    # active model + API key (set via UI)
data/search-config.json   # active search criteria (set via UI)
```

---

## Database

SQLite via SQLAlchemy ORM. Two tables:

- `job_listings` -- one row per scraped or manually entered job
- `applications` -- one row per job that has been acted on (status, resume path, cover letter, etc.)

The tables are created on startup via `Base.metadata.create_all()`. There is no migration framework in place; schema changes require a manual `ALTER TABLE` or deleting and recreating the database.

---

## Frontend

The UI uses [HTMX](https://htmx.org) for partial page updates (status changes, action buttons, job list refresh after scraping). There is no JavaScript build step. All templates are Jinja2 rendered server-side.

Lucide icons are loaded from a CDN script tag. All styles are inline in `base.html` -- one file, no stylesheet to manage.

The scraping flow is the one exception to HTMX: it uses a native `EventSource` for the SSE stream, with vanilla JS to render log lines and trigger an HTMX reload of the job list when scraping completes.
