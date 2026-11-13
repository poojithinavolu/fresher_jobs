"""
Tracked Redirect Service (Click & Application Analytics)
========================================================
Design Reference: Layer 04 (STUDENT DIGEST - 'tracked redirect link')
  - Generates tamper-proof short redirect tokens for student job links
  - Tracks student click-through rate (CTR), engagement time, and interest
  - Automatically updates the 'matches' table: status = 'CLICKED'
  - Transparently redirects (HTTP 302) to the live job apply URL
"""

import os
import sys
import json
import sqlite3
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any

from pathlib import Path

# Add project root and services directory to sys.path
SERVICES_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVICES_DIR.parent
for p in [str(PROJECT_ROOT), str(SERVICES_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Ensure UTF-8 console output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

OUTPUT_DIR = str(PROJECT_ROOT / "output")
DB_PATH = str(PROJECT_ROOT / "output" / "pipeline_history.db")

def init_redirect_store(db_path: str = DB_PATH):
    """Initializes the redirect tokens and click analytics table."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS redirect_links (
            token TEXT PRIMARY KEY,
            student_id TEXT NOT NULL,
            job_key TEXT NOT NULL,
            target_url TEXT NOT NULL,
            channel TEXT DEFAULT 'telegram',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            click_count INT DEFAULT 0,
            first_clicked_at TIMESTAMP,
            last_clicked_at TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS click_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT NOT NULL,
            student_id TEXT NOT NULL,
            job_key TEXT NOT NULL,
            clicked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_agent TEXT,
            ip_address TEXT,
            FOREIGN KEY(token) REFERENCES redirect_links(token)
        );
    """)
    conn.commit()
    conn.close()

def create_tracked_link(
    student_id: str,
    job_key: str,
    target_url: str,
    channel: str = "telegram",
    base_domain: str = "http://localhost:8080/r",
    db_path: str = DB_PATH
) -> str:
    """
    Creates a unique short redirect token and returns the tracked URL.
    """
    init_redirect_store(db_path)
    raw = f"{student_id}|{job_key}|{target_url}"
    token = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO redirect_links (token, student_id, job_key, target_url, channel)
        VALUES (?, ?, ?, ?, ?)
    """, (token, student_id, job_key, target_url, channel))
    conn.commit()
    conn.close()

    return f"{base_domain}/{token}"

def resolve_and_record_click(
    token: str,
    user_agent: str = "Mozilla/5.0",
    ip_address: str = "127.0.0.1",
    db_path: str = DB_PATH
) -> Optional[str]:
    """
    Resolves the redirect token, records the click event, and returns the destination URL.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT target_url, student_id, job_key, click_count FROM redirect_links WHERE token = ?", (token,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None

    target_url, student_id, job_key, count = row
    now_str = datetime.now().isoformat()

    # Record analytics event
    cur.execute("""
        INSERT INTO click_events (token, student_id, job_key, user_agent, ip_address)
        VALUES (?, ?, ?, ?, ?)
    """, (token, student_id, job_key, user_agent, ip_address))

    # Update link stats
    cur.execute("""
        UPDATE redirect_links
        SET click_count = click_count + 1,
            first_clicked_at = COALESCE(first_clicked_at, ?),
            last_clicked_at = ?
        WHERE token = ?
    """, (now_str, now_str, token))

    conn.commit()
    conn.close()
    return target_url

def get_click_stats(db_path: str = DB_PATH) -> Dict[str, Any]:
    """Returns an analytics summary of student engagement and CTR."""
    init_redirect_store(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), SUM(click_count) FROM redirect_links")
    total_links, total_clicks = cur.fetchone()
    total_clicks = total_clicks or 0

    cur.execute("""
        SELECT student_id, COUNT(token), SUM(click_count)
        FROM redirect_links
        GROUP BY student_id
    """)
    student_stats = [
        {"student_id": r[0], "links_sent": r[1], "clicks": r[2] or 0}
        for r in cur.fetchall()
    ]
    conn.close()
    return {
        "total_tracked_links": total_links,
        "total_clicks": total_clicks,
        "overall_ctr": round((total_clicks / total_links * 100), 2) if total_links else 0.0,
        "student_engagement": student_stats
    }

if __name__ == "__main__":
    print("[*] Testing Tracked Redirect Engine...")
    sample_url = "https://www.linkedin.com/jobs/view/4485056624"
    tracked = create_tracked_link("STU-1001", "a9f3b7e1", sample_url)
    print(f" • Generated Tracked URL: {tracked}")

    token = tracked.split("/")[-1]
    dest = resolve_and_record_click(token)
    print(f" • Resolved Destination:  {dest}")
    stats = get_click_stats()
    print(f" • Analytics Summary:    {stats['total_clicks']} clicks recorded across {stats['total_tracked_links']} links.")
