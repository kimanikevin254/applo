from fastapi import FastAPI, Request, Form, UploadFile, File, Query, Response
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, StreamingResponse
from pathlib import Path
from applo.db import init_db, get_session, JobListingORM, ApplicationORM, save_optimization, save_listings
from applo.models import ApplicationStatus, SearchCriteria
from applo.utils.logger import logger
from applo.config import settings
from applo.pipeline.optimizer import ResumeOptimizer
from applo.pipeline.filter import JobFilter
from applo.resume.generator import ResumeGenerator
from applo.resume.parser import load_or_parse_resume
from applo.scrapers import ScraperRegistry
from applo.config import SEARCH_CONFIG_PATH, MODEL_CONFIG_PATH, load_model_config
from sqlalchemy.orm import joinedload
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated
import uvicorn
import asyncio
import json

BASE_DIR = Path(__file__).parent

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="Applo", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, status: str = "all"):
    with get_session() as session:
        query = (
            session.query(JobListingORM)
            .outerjoin(ApplicationORM)
            .options(joinedload(JobListingORM.application))
            .order_by(JobListingORM.scraped_at.desc())
        )

        if status == "all":
            # exclude not_interested by default
            query = query.filter(
                (ApplicationORM.status != ApplicationStatus.NOT_INTERESTED) |
                (ApplicationORM.id == None)
            )
        elif status == "pending":
            # pending = no application record yet OR status is pending
            query = query.filter(
                (ApplicationORM.id == None) |
                (ApplicationORM.status == ApplicationStatus.PENDING)
            )
        else:
            query = query.filter(ApplicationORM.status == status)

        jobs = query.all()

    with get_session() as session:
        all_apps = session.query(ApplicationORM).all()
        stats = {s.value: 0 for s in ApplicationStatus}
        for a in all_apps:
            stats[a.status.value] = stats.get(a.status.value, 0) + 1
        # jobs with no application record are implicitly pending
        total_jobs = session.query(JobListingORM).count()
        jobs_with_app = session.query(ApplicationORM).count()
        stats["pending"] += total_jobs - jobs_with_app

    return templates.TemplateResponse(
        request=request, name="index.html",
        context={
            "jobs": jobs,
            "current_status": status,
            "statuses": [s.value for s in ApplicationStatus],
            "stats": stats,
            "scrapers": list(ScraperRegistry.list_all().keys()),
        }
    )


def load_search_config() -> dict:
    if SEARCH_CONFIG_PATH.exists():
        return json.loads(SEARCH_CONFIG_PATH.read_text())
    return {
        "job_titles": settings.job_titles,
        "locations": settings.locations,
        "excluded_keywords": settings.excluded_keywords,
        "min_salary": settings.min_salary,
        "max_age_days": settings.scraper_max_age_days,
    }


@app.get("/search-config")
async def get_search_config():
    return JSONResponse(load_search_config())


@app.post("/search-config")
async def save_search_config(request: Request):
    body = await request.json()
    criteria = SearchCriteria(sources=["indeed"], **body)
    data = {k: v for k, v in criteria.model_dump().items() if k != "sources"}
    SEARCH_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEARCH_CONFIG_PATH.write_text(json.dumps(data, indent=2))
    return JSONResponse({"ok": True})


@app.get("/model-config")
async def get_model_config():
    cfg = load_model_config()
    masked_key = ("•••" + cfg["api_key"][-6:]) if cfg.get("api_key") else ""
    return JSONResponse({**cfg, "api_key": masked_key})


@app.post("/model-config")
async def save_model_config(request: Request):
    body = await request.json()
    model = body.get("model", "").strip()
    api_key = body.get("api_key", "").strip()
    if not model:
        return JSONResponse({"ok": False, "error": "model is required"}, status_code=400)
    if api_key.startswith("•"):
        api_key = load_model_config().get("api_key", "")
    MODEL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODEL_CONFIG_PATH.write_text(json.dumps({"model": model, "api_key": api_key}, indent=2))
    return JSONResponse({"ok": True})


@app.post("/scrape", response_class=HTMLResponse)
async def run_scrape(request: Request, sources: Annotated[list[str], Form()] = []):
    if not sources:
        return HTMLResponse(
            '<tbody id="job-list"><tr><td colspan="4" class="empty"><p>Select at least one source.</p></td></tr></tbody>'
        )

    criteria = SearchCriteria(sources=sources, **load_search_config())

    async def run_scraper(name: str):
        scraper_cls = ScraperRegistry.get(name)
        async with scraper_cls() as scraper:
            return await scraper.scrape(criteria)

    results = await asyncio.gather(*[run_scraper(s) for s in sources], return_exceptions=True)

    all_listings = []
    for name, result in zip(sources, results):
        if isinstance(result, Exception):
            logger.error(f"Scrape | {name} failed: {result}")
        else:
            all_listings.extend(result)

    filtered = JobFilter(criteria).run(all_listings)
    with get_session() as session:
        saved, skipped = save_listings(session, filtered)

    logger.info(f"Scrape | saved={saved} skipped={skipped}")

    with get_session() as session:
        jobs = (
            session.query(JobListingORM)
            .outerjoin(ApplicationORM)
            .options(joinedload(JobListingORM.application))
            .filter(
                (ApplicationORM.status != ApplicationStatus.NOT_INTERESTED) |
                (ApplicationORM.id == None)
            )
            .order_by(JobListingORM.scraped_at.desc())
            .all()
        )

    return templates.TemplateResponse(
        request=request, name="partials/job_list.html",
        context={"jobs": jobs}
    )


@app.get("/scrape-stream")
async def scrape_stream(sources: list[str] = Query(...)):
    async def generate():
        queue: asyncio.Queue = asyncio.Queue()

        async def emit(event: dict):
            await queue.put(json.dumps(event))

        criteria = SearchCriteria(sources=sources, **load_search_config())

        async def run_one(name: str) -> list:
            scraper_cls = ScraperRegistry.get(name)
            async with scraper_cls() as scraper:
                scraper.emit = emit
                return await scraper.scrape(criteria)

        tasks = [asyncio.create_task(run_one(s)) for s in sources]
        all_listings = []
        pending = set(tasks)

        while pending:
            while not queue.empty():
                yield f"data: {queue.get_nowait()}\n\n"
            done, pending = await asyncio.wait(pending, timeout=0.05)
            for t in done:
                try:
                    all_listings.extend(t.result())
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        while not queue.empty():
            yield f"data: {queue.get_nowait()}\n\n"

        filtered = JobFilter(criteria).run(all_listings)
        with get_session() as session:
            saved, skipped = save_listings(session, filtered)

        yield f"data: {json.dumps({'type': 'done', 'saved': saved, 'skipped': skipped})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/job/{job_id}", response_class=HTMLResponse)
async def job_detail(request: Request, job_id: int):
    with get_session() as session:
        job = (
            session.query(JobListingORM)
            .options(joinedload(JobListingORM.application))
            .filter(JobListingORM.id == job_id)
            .first()
        )
        if not job:
            return HTMLResponse("Job not found", status_code=404)

        # force load the relationship while session is open
        _ = job.application
        if job.application:
            _ = job.application.status
            _ = job.application.tailored_resume_path
            _ = job.application.cover_letter
            _ = job.application.optimization_notes

    return templates.TemplateResponse(
        request=request, name="job_detail.html",
        context={"job": job, "scrapers": list(ScraperRegistry.list_all().keys())}
    )


@app.post("/job/{job_id}/status", response_class=HTMLResponse)
async def update_status(request: Request, job_id: int, status: str = Form(...), source: str = Form(default="list")):
    with get_session() as session:
        app_record = session.query(ApplicationORM).filter(ApplicationORM.job_id == job_id).first()

        if not app_record:
            app_record = ApplicationORM(job_id=job_id, status=status)
            session.add(app_record)
        else:
            app_record.status = status
        session.commit()
        session.refresh(app_record)

        job = (
            session.query(JobListingORM)
            .options(joinedload(JobListingORM.application))
            .filter(JobListingORM.id == job_id)
            .first()
        )

    partial = "partials/job_actions.html" if source == "detail" else "partials/job_row.html"
    return templates.TemplateResponse(request=request, name=partial, context={"job": job})


@app.post("/job/{job_id}/optimize", response_class=HTMLResponse)
async def optimize(request: Request, job_id: int, source: str = Form(default="list")):
    with get_session() as session:
        app_record = session.query(ApplicationORM).filter(ApplicationORM.job_id == job_id).first()

        if not app_record:
            app_record = ApplicationORM(
                job_id=job_id,
                status=ApplicationStatus.OPTIMIZING
            )
            session.add(app_record)
        else:
            app_record.status = ApplicationStatus.OPTIMIZING
        session.commit()

        job = (
            session.query(JobListingORM)
            .options(joinedload(JobListingORM.application))
            .filter(JobListingORM.id == job_id)
            .first()
        )
        job_title = job.title
        company = job.company
        description = job.description or job.raw_text

    if not description or not description.strip():
        logger.warning(f"Optimize | no description for job {job_id}, aborting")
        with get_session() as session:
            job = (
                session.query(JobListingORM)
                .options(joinedload(JobListingORM.application))
                .filter(JobListingORM.id == job_id)
                .first()
            )
        partial = "partials/job_actions.html" if source == "detail" else "partials/job_row.html"
        return templates.TemplateResponse(
            request=request, name=partial,
            context={"job": job, "error": "No job description available — cannot optimize."}
        )

    logger.info(f"Optimize | starting for job {job_id}: {job.title} @ {job.company}")

    try:
        # run optimizer in thread to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        optimizer = ResumeOptimizer()
        result = await loop.run_in_executor(
            None,
            lambda: optimizer.optimize(job_title, company, description)
        )

        if not result:
            raise ValueError("Optimizer returned empty result")

        # generate PDFs
        resume_data = load_or_parse_resume(settings.master_resume_path)
        generator = ResumeGenerator()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_company = company.replace(" ", "_").replace("/", "_")[:30]

        resume_path = f"data/output/{job_id}_{safe_company}_{timestamp}_resume.pdf"
        cover_path = f"data/output/{job_id}_{safe_company}_{timestamp}_cover.pdf"

        await loop.run_in_executor(
            None,
            lambda: generator.generate(
                output_path=resume_path,
                master_docx_path=settings.master_resume_path,
                resume_data=resume_data,
                optimized=result,
            )
        )
        await loop.run_in_executor(
            None,
            lambda: generator.generate_cover_letter(
                output_path=cover_path,
                cover_letter_text=result.get("cover_letter", ""),
                candidate_name=resume_data["sections"].get("header", "").split("\n")[0].strip(),
            )
        )

        # save to DB
        with get_session() as session:
            save_optimization(
                session=session,
                job_id=job_id,
                tailored_resume_path=resume_path,
                cover_letter=result.get("cover_letter", ""),
                notes=result.get("optimization_notes", ""),
            )

        logger.info(f"Optimize | complete for job {job_id}")

    except Exception as e:
        logger.error(f"Optimize | failed for job {job_id}: {e}")
        # revert status to pending on failure
        with get_session() as session:
            app_record = session.query(ApplicationORM).filter(ApplicationORM.job_id == job_id).first()

            if app_record:
                app_record.status = ApplicationStatus.PENDING
                session.commit()

    # return updated row
    with get_session() as session:
        job = (
            session.query(JobListingORM)
            .options(joinedload(JobListingORM.application))
            .filter(JobListingORM.id == job_id)
            .first()
        )

    partial = "partials/job_actions.html" if source == "detail" else "partials/job_row.html"
    return templates.TemplateResponse(request=request, name=partial, context={"job": job})

@app.post("/jobs/manual")
async def add_manual_job(
    request: Request,
    title: str = Form(...),
    company: str = Form(...),
    location: str = Form(default=""),
    description: str = Form(default=""),
):
    import hashlib
    external_id = "manual_" + hashlib.md5(f"{title}{company}{description[:100]}".encode()).hexdigest()[:12]

    with get_session() as session:
        from applo.db.database import JobListingORM
        job = JobListingORM(
            source="manual",
            external_id=external_id,
            title=title.strip(),
            company=company.strip(),
            location=location.strip(),
            job_url="",
            raw_text=description.strip(),
            description=description.strip(),
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id

    return Response(status_code=303, headers={"Location": f"/job/{job_id}"})


@app.get("/preview/{job_id}/resume")
async def preview_resume(job_id: int):
    with get_session() as session:
        app_record = session.query(ApplicationORM).filter(ApplicationORM.job_id == job_id).first()
        if not app_record or not app_record.tailored_resume_path:
            return HTMLResponse("Resume not found", status_code=404)
        path = app_record.tailored_resume_path
    return FileResponse(path, media_type="application/pdf", headers={"Content-Disposition": "inline"})


@app.get("/preview/{job_id}/cover")
async def preview_cover(job_id: int):
    with get_session() as session:
        app_record = session.query(ApplicationORM).filter(ApplicationORM.job_id == job_id).first()
        if not app_record or not app_record.tailored_resume_path:
            return HTMLResponse("Cover letter not found", status_code=404)
        cover_path = app_record.tailored_resume_path.replace("_resume.pdf", "_cover.pdf")
    return FileResponse(cover_path, media_type="application/pdf", headers={"Content-Disposition": "inline"})


@app.get("/download/{job_id}/resume")
async def download_resume(job_id: int):
    with get_session() as session:
        app_record = session.query(ApplicationORM).filter(ApplicationORM.job_id == job_id).first()

        if not app_record or not app_record.tailored_resume_path:
            return HTMLResponse("Resume not found", status_code=404)
        path = app_record.tailored_resume_path
    return FileResponse(path, media_type="application/pdf", filename=Path(path).name)


@app.get("/download/{job_id}/cover")
async def download_cover(job_id: int):
    with get_session() as session:
        app_record = session.query(ApplicationORM).filter(ApplicationORM.job_id == job_id).first()

        if not app_record or not app_record.tailored_resume_path:
            return HTMLResponse("Cover letter not found", status_code=404)
        # derive cover letter path from resume path
        resume_path = app_record.tailored_resume_path
        cover_path = resume_path.replace("_resume.pdf", "_cover.pdf")
    return FileResponse(cover_path, media_type="application/pdf", filename=Path(cover_path).name)

@app.get("/resume/preview")
async def resume_preview():
    master = settings.master_resume_path
    if not master.exists():
        return HTMLResponse("No master resume uploaded.", status_code=404)

    preview_pdf = master.with_name("master_preview.pdf")

    if not preview_pdf.exists():
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: _convert_docx_to_preview(master, preview_pdf))

    return FileResponse(preview_pdf, media_type="application/pdf", filename="master_resume_preview.pdf")


def _convert_docx_to_preview(docx_path: Path, pdf_path: Path):
    import subprocess
    result = subprocess.run(
        ["libreoffice", "--headless", "--convert-to", "pdf",
         "--outdir", str(pdf_path.parent), str(docx_path)],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice conversion failed: {result.stderr}")
    converted = pdf_path.parent / (docx_path.stem + ".pdf")
    if converted != pdf_path:
        converted.rename(pdf_path)


@app.get("/resume/status")
async def resume_status():
    exists = settings.master_resume_path.exists()
    name = settings.master_resume_path.name if exists else None
    return JSONResponse({"exists": exists, "name": name})


@app.post("/resume/upload", response_class=HTMLResponse)
async def resume_upload(request: Request, file: UploadFile = File(...)):
    if not file.filename.endswith(".docx"):
        return HTMLResponse(
            '<span id="upload-status" style="color:#dc3545;">Only .docx files are supported.</span>',
            status_code=400,
        )

    dest = settings.master_resume_path
    dest.parent.mkdir(parents=True, exist_ok=True)

    contents = await file.read()
    dest.write_bytes(contents)

    # Bust parse cache and preview cache so they regenerate from the new file
    for stale in [dest.with_suffix(".json"), dest.with_name("master_preview.pdf")]:
        if stale.exists():
            stale.unlink()

    logger.info(f"Resume | uploaded new master: {file.filename}")
    return HTMLResponse('<span id="upload-status" style="color:#28a745;">Resume uploaded successfully.</span>')


if __name__ == "__main__":
    uvicorn.run("applo.web.app:app", host="0.0.0.0", port=8000, reload=True)