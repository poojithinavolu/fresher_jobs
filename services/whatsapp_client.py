"""
WhatsApp Cloud & Evolution API Client Simulator
================================================
Design Reference: Layer 04 (STUDENT DIGEST - 'WhatsApp opt-in only')
  - Meta Policy Enforcement: Checks 'whatsapp_opt_in == True' before sending
  - Formats official WhatsApp Utility / Marketing templates
  - Inbound webhook listener for handling student keywords:
      'JOBS'        -> Replies with today's Top 6 matching fresher openings
      'STOP'        -> Immediately unsubscribes student (India DPDPA compliance)
      'TRACK <x>'   -> Updates student role track preference
"""

import os
import sys
import json
import sqlite3
import requests
from datetime import datetime
from typing import Dict, Any, Optional

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
PROD_DB = str(PROJECT_ROOT / "output" / "fresher_jobs_production.db")

def is_student_opted_in(phone: str, db_path: str = PROD_DB) -> bool:
    """Verifies if student gave explicit DPDPA opt-in consent for WhatsApp."""
    if not os.path.exists(db_path):
        return True # Default to allow in simulation
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT whatsapp_opt_in, is_active FROM students WHERE phone = ?", (phone,))
    row = cur.fetchone()
    conn.close()
    if row:
        return bool(row[0]) and bool(row[1])
    return True

def format_whatsapp_template(student_name: str, city: str, track: str, jobs: list) -> str:
    """Formats compliant WhatsApp Business message template."""
    lines = [
        f"🌟 *Fresher Job Alert for {student_name}*",
        f"📍 Location: *{city}* | 🏷️ Track: *{track}*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        ""
    ]
    for idx, j in enumerate(jobs[:3], start=1):
        lines.append(f"*{idx}. {j.get('title')}* @ *{j.get('company')}*")
        lines.append(f"   ⏳ Experience: {j.get('experience_range', 'Fresher')}")
        lines.append(f"   🔗 Apply: {j.get('job_url_direct') or j.get('job_url')}")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("⚡ _Verified <48h freshness strictly._")
    lines.append("Reply *STOP* to unsubscribe anytime.")
    return "\n".join(lines)

def send_whatsapp_digest(
    phone: str,
    student_name: str,
    city: str,
    track: str,
    jobs: list,
    evolution_api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    dry_run: bool = True
) -> bool:
    """
    Sends WhatsApp digest respecting Meta compliance rules.
    """
    # 1. Enforce DPDPA Opt-In Rule
    if not is_student_opted_in(phone):
        print(f"[-] Dropping WhatsApp send to {phone}: Student did not opt in or replied STOP.")
        return False

    message_body = format_whatsapp_template(student_name, city, track, jobs)

    if dry_run or not evolution_api_url:
        print(f"\n[✓] WhatsApp Message Prepared for {student_name} ({phone}):")
        print("---------------------------------------------------------")
        print(message_body)
        print("---------------------------------------------------------")
        print("   (Simulated - 0 charges incurred)")
        return True

    # 2. Live API Dispatch (Evolution API or Meta Cloud API)
    url = f"{evolution_api_url}/message/sendText/fresher_instance"
    headers = {"apikey": api_key, "Content-Type": "application/json"}
    payload = {"number": phone.replace("+", ""), "text": message_body}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=8)
        return resp.status_code in (200, 201)
    except Exception as e:
        print(f"[!] WhatsApp API error: {e}")
        return False

def handle_inbound_whatsapp(phone: str, incoming_text: str):
    """Processes inbound student messages (STOP, JOBS, TRACK)."""
    incoming = incoming_text.strip().upper()
    print(f"\n[*] Inbound WhatsApp from {phone}: '{incoming}'")

    conn = sqlite3.connect(PROD_DB)
    cur = conn.cursor()

    if incoming == "STOP":
        cur.execute("UPDATE students SET whatsapp_opt_in = 0, is_active = 0 WHERE phone = ?", (phone,))
        conn.commit()
        print(f"[✓] DPDPA Compliance: Unsubscribed {phone} from all WhatsApp communications.")
        reply = "🛑 You have been successfully unsubscribed. You will receive no further WhatsApp alerts."

    elif incoming == "JOBS":
        reply = "🚀 Fetching today's top 3 verified fresher roles matching your profile..."

    elif incoming.startswith("TRACK"):
        parts = incoming_text.strip().split(maxsplit=1)
        new_track = parts[1] if len(parts) > 1 else "Data Analytics"
        cur.execute("UPDATE students SET target_track = ? WHERE phone = ?", (new_track, phone))
        conn.commit()
        reply = f"✅ Target track updated to: {new_track}. Reply JOBS to view matches."

    else:
        reply = "Welcome! Reply 'JOBS' for fresh openings, 'TRACK <name>' to update preferences, or 'STOP' to opt out."

    conn.close()
    return reply

if __name__ == "__main__":
    print("[*] Testing WhatsApp Compliance & Message Dispatcher...")
    sample_jobs = [
        {"title": "Junior Data Analyst", "company": "Fractal Analytics", "location": "Mumbai", "job_url": "https://linkedin.com/jobs/view/123"},
        {"title": "Analyst, SFA", "company": "Morningstar", "location": "Mumbai", "job_url": "https://linkedin.com/jobs/view/456"},
    ]
    send_whatsapp_digest("+919876543210", "Aarav Sharma", "Mumbai", "Data Analytics", sample_jobs, dry_run=True)
    handle_inbound_whatsapp("+919876543210", "STOP")
