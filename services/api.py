"""
Local Scraper API Server
========================
Provides a lightweight HTTP REST endpoint so n8n (running in Docker)
can trigger the Python scraper and receive fresh jobs via a standard HTTP Request node.

Run with:
  python api.py
"""

import os
import sys
import json
import math
import logging
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, Query
from fastapi.responses import JSONResponse, RedirectResponse
import uvicorn
import pandas as pd

# Add project root and services directory to sys.path
SERVICES_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVICES_DIR.parent
for p in [str(PROJECT_ROOT), str(SERVICES_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from scraper import scrape_fresher_jobs
from excel_exporter import export_to_excel
from google_sheets_sync import sync_configured_google_sheet
from services.redirect_service import resolve_and_record_click, get_click_stats

app = FastAPI(title="Fresher Job Scraper API", version="1.0.0")
logger = logging.getLogger("ScraperAPI")

OUTPUT_DIR = str(PROJECT_ROOT / "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def sanitize_for_json(obj):
    """Recursively replaces NaN, Inf with None so JSON serialization never throws 500."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    return obj


@app.get("/")
def home():
    return {
        "status": "online",
        "endpoints": {
            "/jobs": "Get the latest verified fresher jobs instantly (cached)",
            "/scrape": "Trigger a fresh scraping run across Naukri, LinkedIn, Indeed",
            "/r/{token}": "Tracked student redirect endpoint (records CTR and forwards HTTP 302)",
            "/stats": "View real-time student engagement, click-through rates, and link analytics"
        }
    }


@app.get("/r/{token}")
def handle_redirect(token: str):
    """
    Resolves the tracked token, logs the student click event into SQLite,
    and returns an HTTP 302 redirect to the live job application URL.
    """
    dest = resolve_and_record_click(token)
    if dest:
        return RedirectResponse(url=dest, status_code=302)
    return JSONResponse(status_code=404, content={"status": "error", "message": "Tracked link expired or invalid"})


@app.get("/stats")
def show_stats():
    """Returns click-through analytics and student engagement metrics."""
    return JSONResponse(content={"status": "success", "analytics": get_click_stats()})


@app.get("/jobs")
def get_latest_jobs():
    """
    Returns the latest verified fresher jobs from output/fresher_jobs_latest.json
    without waiting for a new scraping cycle.
    """
    latest_json = os.path.join(OUTPUT_DIR, "fresher_jobs_latest.json")
    if os.path.exists(latest_json):
        with open(latest_json, "r", encoding="utf-8") as f:
            data = json.load(f)
            clean_data = sanitize_for_json(data)
            return JSONResponse(content={"status": "success", "count": len(clean_data), "jobs": clean_data})
    return JSONResponse(content={"status": "empty", "count": 0, "jobs": []})


@app.get("/scrape")
def trigger_scrape(
    hours: int = 48,
    quick: bool = False,
    limit: int = 15
):
    """
    Triggers a live scrape across Naukri, LinkedIn, and Indeed,
    saves the Excel and JSON files, and returns the verified jobs directly to n8n.
    """
    logger.info(f"Triggering scrape: hours={hours}, quick={quick}, limit={limit}")
    
    results = scrape_fresher_jobs(
        hours_old=hours,
        results_per_query=5 if quick else limit
    )
    
    valid_jobs = results["valid_jobs"]
    rejected_jobs = results["rejected_jobs"]
    stats = results["stats"]
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if valid_jobs:
        df_valid = pd.DataFrame(valid_jobs)
        
        # Save timestamped and latest files
        csv_path = os.path.join(OUTPUT_DIR, f"fresher_jobs_{timestamp}.csv")
        json_path = os.path.join(OUTPUT_DIR, f"fresher_jobs_{timestamp}.json")
        xlsx_path = os.path.join(OUTPUT_DIR, f"fresher_jobs_{timestamp}.xlsx")
        latest_csv = os.path.join(OUTPUT_DIR, "fresher_jobs_latest.csv")
        latest_json = os.path.join(OUTPUT_DIR, "fresher_jobs_latest.json")
        latest_xlsx = os.path.join(OUTPUT_DIR, "fresher_jobs_latest.xlsx")
        
        df_valid.to_csv(csv_path, index=False, encoding="utf-8-sig")
        df_valid.to_csv(latest_csv, index=False, encoding="utf-8-sig")
        
        clean_valid = sanitize_for_json(valid_jobs)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(clean_valid, f, indent=2, default=str)
        with open(latest_json, "w", encoding="utf-8") as f:
            json.dump(clean_valid, f, indent=2, default=str)
            
        export_to_excel(df_valid, rejected_jobs, stats, xlsx_path)
        export_to_excel(df_valid, rejected_jobs, stats, latest_xlsx)

    sheet_sync = sync_configured_google_sheet(valid_jobs)
    if sheet_sync is False:
        logger.error("Google Sheets sync failed for this API-triggered run")
    
    clean_jobs = sanitize_for_json(valid_jobs)
    return JSONResponse(content={
        "status": "success",
        "verified_fresher_count": len(clean_jobs),
        "rejected_count": len(rejected_jobs),
        "stats": sanitize_for_json(stats),
        "jobs": clean_jobs
    })


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print(" 🚀 Scraper API Server running on http://127.0.0.1:8000")
    print(" In n8n, use: http://localhost:8000/jobs or http://127.0.0.1:8000/jobs")
    print("=" * 60 + "\n")
    uvicorn.run(app, host="127.0.0.1", port=8000)

