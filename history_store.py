"""
Persistent Job Deduplication Store
----------------------------------
Maintains a local SQLite database of previously broadcast jobs and HR leads.
Prevents duplicate notifications from being sent to students or duplicate calls
being assigned to telecallers across recurring runs.
"""

import sqlite3
import os
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Tuple


class HistoryStore:
    def __init__(self, db_path: str = None):
        if db_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(script_dir, "output", "pipeline_history.db")
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS seen_jobs (
                    job_hash TEXT PRIMARY KEY,
                    title TEXT,
                    company TEXT,
                    location TEXT,
                    apply_url TEXT,
                    first_seen TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS seen_hrs (
                    company_clean TEXT PRIMARY KEY,
                    hr_email TEXT,
                    first_seen TIMESTAMP
                )
            """)
            conn.commit()

    @staticmethod
    def compute_job_hash(job: Dict[str, Any]) -> str:
        url = job.get("job_url_direct") or job.get("job_url") or ""
        title = (job.get("title") or "").strip().lower()
        company = (job.get("company") or "").strip().lower()
        raw = f"{url}|{title}|{company}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def filter_new_jobs(self, jobs: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
        """
        Splits incoming valid jobs into:
        - new_jobs (never seen before in historical runs)
        - already_seen_count
        Marks new jobs into the database.
        """
        new_jobs = []
        seen_count = 0

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for job in jobs:
                job_hash = self.compute_job_hash(job)
                cursor.execute("SELECT 1 FROM seen_jobs WHERE job_hash = ?", (job_hash,))
                if cursor.fetchone():
                    seen_count += 1
                else:
                    new_jobs.append(job)
                    cursor.execute("""
                        INSERT INTO seen_jobs (job_hash, title, company, location, apply_url, first_seen)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        job_hash,
                        job.get("title", ""),
                        job.get("company", ""),
                        job.get("location", ""),
                        job.get("job_url_direct") or job.get("job_url") or "",
                        datetime.now()
                    ))
            conn.commit()

        return new_jobs, seen_count
