import gspread
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from pathlib import Path
from applo.config import settings
from applo.utils.logger import logger

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = [
    "ID", "Job Title", "Company", "Location", "Salary",
    "Source", "Status", "Optimization Notes", "Job URL",
    "Scraped Date", "Resume Link", "Cover Letter Link",
    "Applied Date", "Interview Stage", "Notes",
]

# Columns Applo owns — never overwrite user-owned columns (Applied Date, Interview Stage, Notes)
APPLO_COLUMNS = list(range(1, 13))  # columns 1–12 (1-indexed)


def get_credentials() -> Credentials | None:
    """Load saved OAuth credentials, refreshing if expired. Returns None if not authed."""
    token_path = settings.google_token_path
    if not token_path.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_path.write_text(creds.to_json())
        except Exception as e:
            logger.warning(f"Google | token refresh failed: {e}")
            return None
    return creds if creds.valid else None


def is_connected() -> bool:
    return get_credentials() is not None


# Store flow between auth redirect and callback (single-user tool)
_pending_flow: Flow | None = None


def get_auth_url(redirect_uri: str) -> str:
    """Generate the Google OAuth consent URL and stash the flow for the callback."""
    global _pending_flow
    _pending_flow = Flow.from_client_secrets_file(
        str(settings.google_credentials_path),
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )
    auth_url, _ = _pending_flow.authorization_url(access_type="offline", prompt="consent")
    return auth_url


def exchange_code(code: str, redirect_uri: str) -> None:
    """Exchange auth code for tokens using the stashed flow and save to token.json."""
    global _pending_flow
    if _pending_flow is None:
        raise RuntimeError("No pending OAuth flow — start auth from /auth/google first")
    _pending_flow.redirect_uri = redirect_uri
    _pending_flow.fetch_token(code=code)
    creds = _pending_flow.credentials
    _pending_flow = None
    settings.google_token_path.parent.mkdir(parents=True, exist_ok=True)
    settings.google_token_path.write_text(creds.to_json())
    logger.info("Google | OAuth token saved")


def disconnect() -> None:
    """Delete the saved token."""
    if settings.google_token_path.exists():
        settings.google_token_path.unlink()
    logger.info("Google | disconnected")


def job_to_row(job: dict) -> list:
    salary = ""
    if job.get("salary_min") and job.get("salary_max"):
        salary = f"${job['salary_min']:,} – ${job['salary_max']:,}"
    return [
        job.get("id", ""),
        job.get("title", ""),
        job.get("company", ""),
        job.get("location", ""),
        salary,
        job.get("source", ""),
        job.get("status", ""),
        job.get("optimization_notes", ""),
        job.get("job_url", ""),
        job.get("scraped_at", ""),
        job.get("resume_link", ""),
        job.get("cover_letter_link", ""),
        "", "", "",
    ]


class SheetsSync:
    def __init__(self):
        creds = get_credentials()
        if not creds:
            raise RuntimeError("Google account not connected")
        self.client = gspread.authorize(creds)
        self.sheet = self.client.open_by_key(settings.google_sheet_id).sheet1

    def sync_one(self, job: dict) -> None:
        """Upsert a single job row. Used for auto-sync on status change."""
        self._ensure_headers()
        existing = self.sheet.get_all_values()
        id_to_row = {str(row[0]): i for i, row in enumerate(existing[1:], start=2) if row}

        job_id = str(job["id"])
        row_data = job_to_row(job)

        if job_id in id_to_row:
            row_num = id_to_row[job_id]
            for col in APPLO_COLUMNS:
                self.sheet.update_cell(row_num, col, row_data[col - 1])
        else:
            self.sheet.append_row(row_data, value_input_option="USER_ENTERED")

    def sync_stale(self, jobs: list[dict]) -> int:
        """Upsert only stale/unsynced jobs. Returns number of rows written."""
        self._ensure_headers()
        existing = self.sheet.get_all_values()
        id_to_row = {str(row[0]): i for i, row in enumerate(existing[1:], start=2) if row}

        written = 0
        for job in jobs:
            job_id = str(job["id"])
            row_data = job_to_row(job)
            if job_id in id_to_row:
                row_num = id_to_row[job_id]
                for col in APPLO_COLUMNS:
                    self.sheet.update_cell(row_num, col, row_data[col - 1])
            else:
                self.sheet.append_row(row_data, value_input_option="USER_ENTERED")
            written += 1

        logger.info(f"Sheets | force-synced {written} stale jobs")
        return written

    def _ensure_headers(self):
        first_row = self.sheet.row_values(1)
        if first_row != HEADERS:
            self.sheet.insert_row(HEADERS, index=1)
            self.sheet.format("1:1", {"textFormat": {"bold": True}})


class DriveUpload:
    def __init__(self):
        creds = get_credentials()
        if not creds:
            raise RuntimeError("Google account not connected")
        self.service = build("drive", "v3", credentials=creds)
        self.folder_id = settings.google_drive_folder_id

    def upload(self, file_path: str | Path, filename: str) -> str:
        """Upload a file to the Drive folder. Returns a shareable link."""
        file_path = Path(file_path)
        media = MediaFileUpload(str(file_path), mimetype="application/pdf")
        metadata = {"name": filename, "parents": [self.folder_id]}
        uploaded = self.service.files().create(
            body=metadata, media_body=media, fields="id"
        ).execute()

        file_id = uploaded["id"]
        self.service.permissions().create(
            fileId=file_id,
            body={"role": "reader", "type": "anyone"},
        ).execute()

        link = f"https://drive.google.com/file/d/{file_id}/view"
        logger.info(f"Drive | uploaded {filename} → {link}")
        return link
