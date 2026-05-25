from pathlib import Path
from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean,
    DateTime, Enum as SAEnum, Text, ForeignKey
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship
from sqlalchemy.sql import func
from datetime import datetime, timezone
from applo.config import settings
from applo.models import JobSource, ApplicationStatus

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