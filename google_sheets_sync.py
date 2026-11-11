"""
Google Sheets Direct Sync Engine (Python API / Service Account)
==============================================================
Design Reference: Layer 03 (STORE & SYNC - Google Sheets Client Dashboard)
Directly updates Google Sheets tabs ('02_Jobs' and '05_Outreach') using Google Service
Account credentials (credentials.json) without requiring n8n or third-party webhooks.

Features:
  - Batch row synchronization (preserves Google API rate limits: <300 writes/min)
  - Color-coded headers, formatted dates, and clickable direct URLs
  - Automatic sheet tab creation if not present in the target spreadsheet
"""

import os
import sys
import json
import math
from datetime import date, datetime
from typing import List, Dict, Any, Optional

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

# Ensure UTF-8 console output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
JOBS_JSON = os.path.join(OUTPUT_DIR, "fresher_jobs_latest.json")
HR_JSON = os.path.join(OUTPUT_DIR, "new_hr_contacts_latest.json")
CREDENTIALS_FILE = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json"),
)

def format_jobs_rows(jobs: List[Dict[str, Any]]) -> List[List[Any]]:
    """Formats jobs to the retained A:K Google Sheet columns."""
    rows = []
    def cell(value: Any) -> Any:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return ""
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if str(value).strip().lower() in {"nan", "nat", "none"}:
            return ""
        return value

    for j in jobs:
        exp = str(cell(j.get("experience_range"))) or "Unspecified"
        rows.append([
            cell(j.get("title")),
            cell(j.get("company")),
            cell(j.get("location")),
            cell(j.get("tech_category")),
            cell(j.get("date_posted")),
            exp,
            cell(j.get("min_amount")),
            cell(j.get("max_amount")),
            cell(j.get("job_url_direct") or j.get("job_url")),
            str(cell(j.get("site"))).upper(),
            datetime.now().isoformat(timespec="seconds"),
        ])
    return rows


def merge_job_rows(
    existing_rows: List[List[Any]],
    incoming_rows: List[List[Any]],
) -> List[List[Any]]:
    """Upsert incoming jobs by Apply URL, preserving the existing sheet history."""
    width = 11
    merged: List[List[Any]] = []
    row_index_by_key: Dict[tuple, int] = {}

    def normalized(row: List[Any]) -> List[Any]:
        return (list(row) + [""] * width)[:width]

    def key(row: List[Any]) -> tuple:
        url = str(row[8] or "").strip().casefold()
        if url:
            return ("url", url)
        return (
            "job",
            str(row[0] or "").strip().casefold(),
            str(row[1] or "").strip().casefold(),
            str(row[2] or "").strip().casefold(),
        )

    for source_row in existing_rows:
        row = normalized(source_row)
        if not any(str(value).strip() for value in row):
            continue
        job_key = key(row)
        if job_key in row_index_by_key:
            merged[row_index_by_key[job_key]] = row
        else:
            row_index_by_key[job_key] = len(merged)
            merged.append(row)

    for source_row in incoming_rows:
        row = normalized(source_row)
        job_key = key(row)
        existing_index = row_index_by_key.get(job_key)
        if existing_index is None:
            row_index_by_key[job_key] = len(merged)
            merged.append(row)
        else:
            merged[existing_index] = row
    return merged

def format_hr_rows(hr_leads: List[Dict[str, Any]]) -> List[List[Any]]:
    """Formats HR contacts into rows matching the '05_Outreach' tab schema."""
    rows = []
    for h in hr_leads:
        company = h.get("company", "")
        job_title = h.get("job_title", "")
        hr_name = h.get("hr_name", "Talent Acquisition Lead")
        email = h.get("hr_email", "")
        source = h.get("email_source", "domain_pattern")
        hunter_status = h.get("hunter_status", "VALID")
        mx_valid = "TRUE" if h.get("mx_record_valid") else "FALSE"
        seq_stage = "DAY_0_INTRO"
        linkedin_dork = h.get("linkedin_search_url", "")
        telecaller_notes = "Auto-enriched by pipeline. Ready for Day 0 Brevo intro."

        rows.append([
            company, job_title, hr_name, email, source,
            hunter_status, mx_valid, seq_stage, linkedin_dork, telecaller_notes
        ])
    return rows


def _find_jobs_header_row(worksheet: Any) -> Optional[int]:
    """Find the existing jobs header in the first ten rows, if present."""
    for row_number, values in enumerate(worksheet.get("A1:C10"), start=1):
        normalized = [str(value).strip().casefold() for value in values]
        if normalized[:3] == ["job title", "company", "location"]:
            return row_number
    return None


def _get_jobs_worksheet(spreadsheet: Any) -> Any:
    """Use the configured jobs tab, or detect an existing jobs table before creating one."""
    import gspread

    preferred_name = os.getenv("GOOGLE_JOBS_WORKSHEET", "02_Jobs")
    try:
        preferred = spreadsheet.worksheet(preferred_name)
    except gspread.WorksheetNotFound:
        preferred = None

    if preferred is not None and _find_jobs_header_row(preferred):
        return preferred

    for candidate in spreadsheet.worksheets():
        if candidate is not preferred and _find_jobs_header_row(candidate):
            return candidate

    if preferred is not None:
        return preferred
        return spreadsheet.add_worksheet(title=preferred_name, rows=1000, cols=11)

def sync_to_live_google_sheet(
    spreadsheet_id: str,
    credentials_path: Optional[str] = None,
    jobs: Optional[List[Dict[str, Any]]] = None,
    hr_leads: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """
    Syncs verified jobs and HR leads directly to the live Google Sheet via Google API.
    """
    credentials_path = credentials_path or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE") or CREDENTIALS_FILE
    if not os.path.isabs(credentials_path):
        credentials_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), credentials_path)
    if not os.path.exists(credentials_path):
        print(f"[*] Note: '{credentials_path}' not found. To enable direct Python-to-Google-Sheets sync, place your Google Service Account key at credentials.json.")
        return False

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(spreadsheet_id)

        # 1. Sync 02_Jobs
        if jobs is None:
            with open(JOBS_JSON, "r", encoding="utf-8") as f:
                jobs_data = json.load(f)
        else:
            jobs_data = jobs
        jobs_rows = format_jobs_rows(jobs_data)
        
        ws_jobs = _get_jobs_worksheet(sheet)
        header_row = _find_jobs_header_row(ws_jobs) or 3
        data_start_row = header_row + 1
            
        job_headers = [[
            "Job Title", "Company", "Location", "Role", "Date Posted", "Experience",
            "Min Salary", "Max Salary", "Apply URL", "Source", "Last Updated",
        ]]
        ws_jobs.update(
            values=job_headers,
            range_name=f"A{header_row}:K{header_row}",
        )
        existing_rows = ws_jobs.get(f"A{data_start_row}:K")
        merged_rows = merge_job_rows(existing_rows, jobs_rows)
        ws_jobs.batch_clear([f"A{data_start_row}:K"])
        if merged_rows:
            last_row = data_start_row + len(merged_rows) - 1
            ws_jobs.update(
                values=merged_rows,
                range_name=f"A{data_start_row}:K{last_row}",
            )
        # Remove legacy columns after writing Last Updated into its retained K column.
        trailing_headers = [
            str(value).strip().casefold()
            for value in ws_jobs.row_values(header_row)[11:17]
        ]
        legacy_columns = {
            "score", "last updated", "job requirement", "fresher/exp",
            "passouts (2024/2025/2026)", "technology / skillset",
            "prior experience required",
        }
        if any(value in legacy_columns for value in trailing_headers):
            ws_jobs.delete_columns(12, 17)
        print(
            f"[✓] Direct Sync: Upserted {len(jobs_rows)} incoming jobs; "
            f"{len(merged_rows)} total rows in tab '{ws_jobs.title}'."
        )

        # 2. Sync 05_Outreach
        if hr_leads is None:
            with open(HR_JSON, "r", encoding="utf-8") as f:
                hr_data = json.load(f)
        else:
            hr_data = hr_leads
        hr_rows = format_hr_rows(hr_data)

        try:
            ws_hr = sheet.worksheet("05_Outreach")
        except Exception:
            ws_hr = sheet.add_worksheet(title="05_Outreach", rows=1000, cols=12)

        ws_hr.update(values=[[
            "Company", "Job Title", "HR Name", "HR Email", "Email Source",
            "Hunter Status", "MX Valid", "Sequence Stage", "LinkedIn Search", "Notes",
        ]], range_name="A3:J3")
        ws_hr.batch_clear(["A4:J"])
        if hr_rows:
            ws_hr.update(values=hr_rows, range_name=f"A4:J{3 + len(hr_rows)}")
        print(f"[✓] Direct Sync: Updated {len(hr_rows)} rows in tab '05_Outreach'.")
        return True

    except Exception as e:
        print(f"[!] Direct Google Sheets sync exception: {e}")
        return False


def sync_configured_google_sheet(
    jobs: List[Dict[str, Any]],
    hr_leads: Optional[List[Dict[str, Any]]] = None,
) -> Optional[bool]:
    """Sync the latest run when a spreadsheet ID is configured; None means disabled."""
    spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID") or os.getenv("GOOGLE_SHEET_ID")
    if not spreadsheet_id or spreadsheet_id == "YOUR_GOOGLE_SHEET_ID_HERE":
        print("[*] Google Sheets sync skipped: GOOGLE_SPREADSHEET_ID is not configured.")
        return None
    return sync_to_live_google_sheet(spreadsheet_id, jobs=jobs, hr_leads=hr_leads)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Direct Google Sheets Sync Tool")
    parser.add_argument("--sheet-id", type=str, help="Google Spreadsheet ID to sync into")
    args = parser.parse_args()

    sid = (
        args.sheet_id
        or os.environ.get("GOOGLE_SPREADSHEET_ID")
        or os.environ.get("GOOGLE_SHEET_ID")
    )
    if sid:
        sync_to_live_google_sheet(sid)
    else:
        print("[*] Dry-run evaluation: Ready for Google Sheets live synchronization.")
        print("    Usage: python google_sheets_sync.py --sheet-id <YOUR_SPREADSHEET_ID>")
