from pathlib import Path
from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean,
    DateTime, Enum as SAEnum, Text, ForeignKey
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship
from sqlalchemy.sql import func
from datetime import datetime, timezone
from applo.config import settings
from applo.models import JobSource, ApplicationStatus, JobListing
from applo.utils.logger import logger

engine = create_engine(
    url=settings.database_url,
    connect_args={"check_same_thread": False} # TODO: for sqlite only. remove for postgres
)

class Base(DeclarativeBase):
    pass

class JobListingORM(Base):
    __tablename__  = "job_listings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(SAEnum(JobSource), nullable=False)
    external_id = Column(String, nullable=False)
    title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    location = Column(String, nullable=False)
    salary_min = Column(Integer, nullable=True)
    salary_max = Column(Integer, nullable=True)
    job_url = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    raw_text = Column(Text, nullable=False)
    posted_text = Column(String, nullable=True)
    scraped_at = Column(DateTime, default=datetime.now(timezone.utc))
    is_duplicate = Column(Boolean, default=False)

    application = relationship("ApplicationORM", back_populates="job", uselist=False)

class ApplicationORM(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("job_listings.id"), nullable=False)
    status = Column(SAEnum(ApplicationStatus), default=ApplicationStatus.PENDING)
    tailored_resume_path = Column(String, nullable=True)
    cover_letter = Column(Text, nullable=True)
    optimization_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=datetime.now(timezone.utc), onupdate=func.now())
    applied_at = Column(DateTime, nullable=True)

    job = relationship("JobListingORM", back_populates="application")

def init_db() -> None:
    """Create all tables. Safe to call multiple times"""
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=engine)

def get_session() -> Session:
    return Session(engine)

def is_duplicate(session: Session, source: str, external_id: str) -> bool:
    """Check if job already exists in DB by source + external_id."""
    from applo.models import JobSource
    result = session.query(JobListingORM).filter_by(
        source=source,
        external_id=external_id,
    ).first()
    return result is not None


def save_listings(session: Session, listings: list[JobListing]) -> tuple[int, int]:
    """Save listings to DB, skipping duplicates. Returns (saved, skipped)."""
    saved, skipped = 0, 0
    for job in listings:
        if is_duplicate(session, job.source, job.external_id):
            logger.debug(f"DB | duplicate skipped: {job.title} @ {job.company}")
            skipped += 1
            continue
        orm = JobListingORM(
            source=job.source,
            external_id=job.external_id,
            title=job.title,
            company=job.company,
            location=job.location,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            job_url=job.job_url,
            description=job.description,
            raw_text=job.raw_text,
            posted_text=job.posted_text,
            scraped_at=job.scraped_at,
        )
        session.add(orm)
        saved += 1
    session.commit()
    return saved, skipped