"""
Student Matching & Personalized Digest Dispatcher
=================================================
Matches verified fresher jobs with students based on:
  - Target Role Track (Data Analytics, Business Analytics, Web Development, etc.)
  - Target City (Mumbai, Hyderabad, Remote)
  - 1 message per student per day (Top 6 matched jobs)
  - Enforces strict idempotency: (student_id + date + channel)

Matches Layer 04 (STUDENT DIGEST) of the Architecture Blueprint.
"""

import os
import sys
import json
import sqlite3
from datetime import datetime, date
from typing import List, Dict, Any

from pathlib import Path

# Add project root and services directory to sys.path
SERVICES_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVICES_DIR.parent
for p in [str(PROJECT_ROOT), str(SERVICES_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

OUTPUT_DIR = str(PROJECT_ROOT / "output")
DB_PATH = str(PROJECT_ROOT / "output" / "pipeline_history.db")
JOBS_JSON = str(PROJECT_ROOT / "output" / "fresher_jobs_latest.json")

def init_delivery_store(db_path: str = DB_PATH):
    """Initializes the SQLite deliveries idempotency table."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS student_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            dispatch_date TEXT NOT NULL,
            channel TEXT NOT NULL,
            job_keys TEXT NOT NULL,
            delivered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_id, dispatch_date, channel)
        )
    """)
    conn.commit()
    conn.close()

def load_jobs() -> List[Dict[str, Any]]:
    if not os.path.exists(JOBS_JSON):
        return []
    with open(JOBS_JSON, "r", encoding="utf-8") as f:
        return json.load(f)

def load_students() -> List[Dict[str, Any]]:
    """Loads student roster from cohort JSON or database, falling back to defaults."""
    cohort_file = os.path.join(OUTPUT_DIR, "students_roster_50.json")
    if os.path.exists(cohort_file):
        try:
            with open(cohort_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_STUDENTS

# Default student roster (can also be read from Excel '03_Students')
DEFAULT_STUDENTS = [
    {
        "student_id": "STU-1001",
        "name": "Aarav Sharma",
        "email": "aarav.sharma@example.com",
        "telegram_chat_id": "123456789",
        "target_track": "Data Analytics",
        "target_city": "Mumbai",
        "whatsapp_opt_in": True,
        "channel": "telegram"
    },
    {
        "student_id": "STU-1002",
        "name": "Pooja Reddy",
        "email": "pooja.reddy@example.com",
        "telegram_chat_id": "987654321",
        "target_track": "Business Analytics",
        "target_city": "Hyderabad",
        "whatsapp_opt_in": True,
        "channel": "telegram"
    },
    {
        "student_id": "STU-1003",
        "name": "Rohan Mehta",
        "email": "rohan.mehta@example.com",
        "telegram_chat_id": "554433221",
        "target_track": "Web Development & Full Stack",
        "target_city": "Mumbai",
        "whatsapp_opt_in": False,
        "channel": "telegram"
    }
]

def is_already_delivered(student_id: str, channel: str, dispatch_date: str, db_path: str = DB_PATH) -> bool:
    """Checks if student was already delivered their daily digest today."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM student_deliveries WHERE student_id = ? AND dispatch_date = ? AND channel = ?",
        (student_id, dispatch_date, channel)
    )
    res = cur.fetchone()
    conn.close()
    return res is not None

def record_delivery(student_id: str, channel: str, dispatch_date: str, job_keys: List[str], db_path: str = DB_PATH):
    """Records delivery in the idempotency store."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO student_deliveries (student_id, dispatch_date, channel, job_keys) VALUES (?, ?, ?, ?)",
        (student_id, dispatch_date, channel, ",".join(job_keys))
    )
    conn.commit()
    conn.close()

def match_jobs_for_student(student: Dict[str, Any], jobs: List[Dict[str, Any]], top_k: int = 6) -> List[Dict[str, Any]]:
    """Scores and filters top K jobs for a specific student's track and city."""
    target_track = student.get("target_track", "").lower()
    target_city = student.get("target_city", "").lower()
    
    candidates = []
    for j in jobs:
        score = j.get("quality_score", 70)
        job_category = j.get("tech_category", "").lower()
        job_loc = j.get("location", "").lower()
        
        # Track match bonus
        if target_track in job_category or any(w in job_category for w in target_track.split()):
            score += 25
            
        # City match bonus
        if target_city in job_loc:
            score += 20
        elif "remote" in job_loc or "hybrid" in job_loc:
            score += 10
            
        candidates.append((score, j))
        
    candidates.sort(key=lambda x: x[0], reverse=True)
    return [c[1] for c in candidates[:top_k]]

def format_personalized_digest(student: Dict[str, Any], matched_jobs: List[Dict[str, Any]]) -> str:
    """Formats a personalized Telegram / WhatsApp digest for the student."""
    today_str = datetime.now().strftime("%A, %d %B %Y")
    name = student.get("name", "Student")
    track = student.get("target_track", "Tech")
    city = student.get("target_city", "All India")
    
    lines = [
        f"🎯 *DAILY FRESHER DIGEST FOR {name.upper()}*",
        f"📅 _{today_str}_ | 🏷️ *{track}* | 📍 *{city}*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        ""
    ]
    
    for idx, j in enumerate(matched_jobs, start=1):
        title = j.get("title", "Software Role")
        company = j.get("company", "Reputed Firm")
        loc = j.get("location", "India")
        exp = j.get("experience_range", "Fresher")
        url = j.get("job_url_direct") or j.get("job_url", "")
        min_sal = j.get("min_amount")
        max_sal = j.get("max_amount")
        sal_str = ""
        if min_sal and max_sal and str(min_sal) != "nan" and str(max_sal) != "nan":
            sal_str = f" | 💰 ₹{int(min_sal):,}-₹{int(max_sal):,}"
            
        lines.append(f"*{idx}. {title}* @ *{company}*")
        lines.append(f"   📍 {loc}{sal_str}")
        lines.append(f"   ⏳ Experience: {exp}")
        lines.append(f"   🔗 [Click to Apply Here]({url})")
        lines.append("")
        
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("⚡ _Verified <48h freshness strictly. Zero spam or paid consultancies._")
    return "\n".join(lines)

def run_student_dispatch(dry_run: bool = True):
    """Executes the daily student match and dispatch cycle."""
    init_delivery_store()
    jobs = load_jobs()
    students = load_students()
    if not jobs:
        print("[!] No jobs found in output/fresher_jobs_latest.json to match.")
        return
        
    today = date.today().isoformat()
    print(f"\n[*] Matching {len(jobs)} active jobs against {len(students)} students (Date: {today})...")
    
    for student in students:
        sid = student["student_id"]
        channel = student.get("channel", "telegram")
        
        if is_already_delivered(sid, channel, today):
            print(f"[-] {student['name']} ({sid}) already received today's digest. Skipping (Idempotent).")
            continue
            
        matched = match_jobs_for_student(student, jobs, top_k=6)
        if not matched:
            print(f"[-] No matching jobs found for {student['name']}.")
            continue
            
        digest_text = format_personalized_digest(student, matched)
        job_keys = [j.get("job_key", str(idx)) for idx, j in enumerate(matched)]
        
        print(f"\n========================================================")
        print(f" [+] DISPATCH PREPARED FOR: {student['name']} ({student['target_track']} in {student['target_city']})")
        print(f"========================================================")
        print(digest_text)
        
        if not dry_run:
            # Here n8n or direct Telegram Bot API sends the message
            record_delivery(sid, channel, today, job_keys)
            print(f"[✓] Recorded delivery for {sid} in idempotency database.")
        else:
            print(f"[*] (Dry-run mode active. No message actually pushed to network.)")

if __name__ == "__main__":
    run_student_dispatch(dry_run=True)
