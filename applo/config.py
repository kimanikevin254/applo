from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path

class Settings(BaseSettings):
    # Anthropic
    anthropic_api_key: str
    anthropic_model: str = "claude-haiku-4-5"

    # App
    app_env: str = "development"
    secret_key: str = "change_me_in_production"

    # Database
    database_url: str = "sqlite:///./data/applo.db"

    # Scraping
    scraper_headless: bool = True
    scraper_delay_secs: int = 2

    # Resume
    master_resume_path: Path = Path("data/resumes/master.pdf")

    # Search criteria
    job_titles: list[str] = Field(default=["software engineer", "backend_engineer"])
    locations: list[str] = Field(default=["remote"])
    excluded_keywords: list[str] = Field(default=["senior", "staff", "principal"])
    min_salary: int | None = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

settings = Settings()