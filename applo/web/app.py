from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pathlib import Path
from applo.db import init_db, get_session, JobListingORM, ApplicationORM
from applo.models import ApplicationStatus
from applo.utils.logger import logger
from sqlalchemy.orm import joinedload
from contextlib import asynccontextmanager
import uvicorn

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
        if status != "all":
            query = query.filter(ApplicationORM.status == status)
        else:
            # exclude not_interested by default
            query = query.filter(
                (ApplicationORM.status != ApplicationStatus.NOT_INTERESTED) |
                (ApplicationORM.id == None)
            )
        jobs = query.all()

    return templates.TemplateResponse(
        request=request, name="index.html",
        context={"jobs": jobs, "current_status": status, "statuses": [s.value for s in ApplicationStatus]}
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
    return templates.TemplateResponse(
        request=request, name="job_detail.html",
        context={"job": job}
    )


@app.post("/job/{job_id}/status", response_class=HTMLResponse)
async def update_status(request: Request, job_id: int, status: str = Form(...)):
    with get_session() as session:
        app_record = session.query(ApplicationORM).filter_by(job_id=job_id).first()
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
        app_record = session.query(ApplicationORM).filter_by(job_id=job_id).first()
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

    # TODO: trigger optimizer here (next step)
    logger.info(f"Optimize requested for job {job_id}: {job.title} @ {job.company}")

    return templates.TemplateResponse(
        request=request, name="partials/job_row.html",
        context={"job": job}
    )


if __name__ == "__main__":
    uvicorn.run("applo.web.app:app", host="0.0.0.0", port=8000, reload=True)