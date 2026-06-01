from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field, field_validator
from typing import Optional

class JobSource(str, Enum):
    INDEED = "indeed"
    GLASSDOOR = "glassdoor"

class ApplicationStatus(str, Enum):
    PENDING = "pending"           # scraped, awaiting user review
    OPTIMIZING = "optimizing"     # Claude is generating tailored resume
    OPTIMIZED = "optimized"       # resume ready, awaiting user approval
    APPROVED = "approved"         # user approved, ready to send
    APPLIED = "applied"           # sent
    NOT_INTERESTED = "not_interested"  # dismissed, reversible
    REJECTED = "rejected"         # company rejected (post-application)

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
    posted_text: Optional[str] = None
    scraped_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    is_duplicate: bool = False

class Application(BaseModel):
    id: Optional[int] = None
    job_id: int
    status: ApplicationStatus = ApplicationStatus.PENDING
    tailored_resume_path: Optional[str] = None
    cover_letter: Optional[str] = None
    optimization_notes: Optional[str] = None  # what Claude changed and why
    created_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    applied_at: Optional[datetime] = None

class SearchCriteria(BaseModel):
    job_titles: list[str] = ["software engineer"]
    locations: list[str] = ["remote"]
    excluded_keywords: list[str] = []
    min_salary: Optional[int] = None
    sources: list[JobSource] = [JobSource.INDEED, JobSource.GLASSDOOR]
    max_age_days: int = 1

    @field_validator("max_age_days")
    @classmethod
    def validate_max_age_days(cls, v:int) -> int:
        if v not in [1, 3, 7]:
            raise ValueError("max_age_days must be 1, 3 , or 7")
        return v