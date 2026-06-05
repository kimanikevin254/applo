from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path
import json

class Settings(BaseSettings):
    # Anthropic
    anthropic_api_key: str
    anthropic_model: str = "anthropic/claude-haiku-4-5"

    # App
    app_env: str = "development"
    secret_key: str = "change_me_in_production"

    # Database
    database_url: str = "sqlite:///./data/applo.db"

    # Scraping
    scraper_headless: bool = True
    scraper_delay_secs: int = 2
    glassdoor_auth_modal_timeout: int = 2000

    # Resume
    master_resume_path: Path = Path("data/resumes/master.docx")

    # Search criteria
    job_titles: list[str] = Field(default=["software engineer", "backend_engineer"])
    locations: list[str] = Field(default=["remote"])
    excluded_keywords: list[str] = Field(default=["senior", "staff", "principal"])
    min_salary: int | None = None
    scraper_max_age_days: int = 1

    # Gotenberg
    gotenberg_url: str = "http://localhost:3000"

    # Google
    google_credentials_path: Path = Path("data/google_credentials.json")
    google_token_path: Path = Path("data/token.json")
    google_sheet_id: str = ""
    google_drive_folder_id: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

settings = Settings()

SEARCH_CONFIG_PATH = Path("data/search-config.json")
MODEL_CONFIG_PATH = Path("data/model-config.json")


def load_model_config() -> dict:
    if MODEL_CONFIG_PATH.exists():
        return json.loads(MODEL_CONFIG_PATH.read_text())
    return {
        "model": settings.anthropic_model,
        "api_key": settings.anthropic_api_key,
    }