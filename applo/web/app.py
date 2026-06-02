from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pathlib import Path
from applo.db import init_db, get_session, JobListingORM, ApplicationORM, save_optimization
from applo.models import ApplicationStatus
from applo.utils.logger import logger
from applo.config import settings
from applo.pipeline.optimizer import ResumeOptimizer
from applo.resume.generator import ResumeGenerator
from applo.resume.parser import load_or_parse_resume
from sqlalchemy.orm import joinedload
from contextlib import asynccontextmanager
from datetime import datetime
import uvicorn
import asyncio

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
        context={"jobs": jobs, "current_status": status, "statuses": [s.value for s in ApplicationStatus], "stats": stats}
    )


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
        context={"job": job}
    )


@app.post("/job/{job_id}/status", response_class=HTMLResponse)
async def update_status(request: Request, job_id: int, status: str = Form(...)):
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

    return templates.TemplateResponse(
        request=request, name="partials/job_row.html",
        context={"job": job}
    )


@app.post("/job/{job_id}/optimize", response_class=HTMLResponse)
async def optimize(request: Request, job_id: int):
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
        return templates.TemplateResponse(
            request=request, name="partials/job_row.html",
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

    return templates.TemplateResponse(
        request=request, name="partials/job_row.html",
        context={"job": job}
    )

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