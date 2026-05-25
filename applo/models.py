from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional

class JobSource(str, Enum):
    INDEED = "indeed"
    GLASSDOOR = "glassdoor"

class ApplicationStatus(str, Enum):
    PENDING = "pending"        # scraped, not yet optimized
    OPTIMIZED = "optimized"    # resume tailored, awaiting review
    APPROVED = "approved"      # user approved, ready to send
    APPLIED = "applied"        # sent
    REJECTED = "rejected"      # user dismissed

class JobListing(BaseModel):
    id: Optional[int] = None
    source: JobSource
    external_id: str                        # indeed/glassdoor job id
    title: str
    company: str
    location: str
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    job_url: str
    description: Optional[str] = None      # fetched separately
    raw_text: str                           # full card text as scraped
    scraped_at: datetime = Field(default_factory=datetime.now(datetime.timezone.utc))
    is_duplicate: bool = False

class Application(BaseModel):
    id: Optional[int] = None
    job_id: int
    status: ApplicationStatus = ApplicationStatus.PENDING
    tailored_resume_path: Optional[str] = None
    cover_letter: Optional[str] = None
    optimization_notes: Optional[str] = None  # what Claude changed and why
    created_at: datetime = Field(default_factory=datetime.now(datetime.timezone.utc))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.timezone.utc))
    applied_at: Optional[datetime] = None

class SearchCriteria(BaseModel):
    job_titles: list[str] = ["software engineer"]
    locations: list[str] = ["remote"]
    excluded_keywords: list[str] = []
    min_salary: Optional[int] = None
    sources: list[JobSource] = [JobSource.INDEED, JobSource.GLASSDOOR]