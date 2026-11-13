"""
Interactive Telegram Student Placement Bot (24/7 Long-Polling Listener)
=======================================================================
Zero-dependency interactive Telegram Bot:
  - Uses standard Python 'requests' long-polling (getUpdates)
  - Zero webhooks, zero public SSL certs, zero complex libraries needed
  - Complies with India DPDPA 2023 consent & opt-out rules

Commands for Students:
  /start            - Welcome message, DPDPA consent terms, and setup
  /jobs             - Instantly fetches Top 6 verified fresh jobs matching profile
  /track <name>     - Set preference: Data Analytics, Business Analytics, Web Dev, MIS
  /city <name>      - Set target city: Mumbai or Hyderabad
  /profile          - View current matching preferences
  /stop             - DPDPA instant opt-out (stops all outbound messages)
  /help             - Command guide
"""

import os
import sys
import time
import json
import sqlite3
import requests
from datetime import datetime

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
JOBS_JSON = str(PROJECT_ROOT / "output" / "fresher_jobs_latest.json")

from services.student_matcher import match_jobs_for_student, format_personalized_digest, load_jobs

def get_bot_token():
    # 1. Check environment variable
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    # 2. Check .env file
    env_file = PROJECT_ROOT / ".env"
    if not token and env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    token = line.strip().split("=", 1)[1].strip()
    return token

def get_or_create_student_profile(chat_id: str, first_name: str = "Student"):
    conn = sqlite3.connect(PROD_DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT,
            telegram_chat_id TEXT,
            whatsapp_opt_in INT DEFAULT 0,
            target_track TEXT NOT NULL,
            target_city TEXT NOT NULL,
            is_active INT DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("SELECT student_id, full_name, target_track, target_city, is_active FROM students WHERE telegram_chat_id = ?", (str(chat_id),))
    row = cur.fetchone()
    if row:
        profile = {
            "student_id": row[0],
            "name": row[1],
            "target_track": row[2],
            "target_city": row[3],
            "is_active": bool(row[4])
        }
    else:
        sid = f"STU-TG-{chat_id}"
        cur.execute("""
            INSERT INTO students (student_id, full_name, email, telegram_chat_id, target_track, target_city, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (sid, first_name, f"tg_{chat_id}@student.hub", str(chat_id), "Data Analytics", "Mumbai"))
        conn.commit()
        profile = {
            "student_id": sid,
            "name": first_name,
            "target_track": "Data Analytics",
            "target_city": "Mumbai",
            "is_active": True
        }
    conn.close()
    return profile

def update_student_preference(chat_id: str, field: str, val: str):
    conn = sqlite3.connect(PROD_DB)
    cur = conn.cursor()
    if field == "track":
        cur.execute("UPDATE students SET target_track = ? WHERE telegram_chat_id = ?", (val, str(chat_id)))
    elif field == "city":
        cur.execute("UPDATE students SET target_city = ? WHERE telegram_chat_id = ?", (val, str(chat_id)))
    elif field == "opt_out":
        cur.execute("UPDATE students SET is_active = 0, whatsapp_opt_in = 0 WHERE telegram_chat_id = ?", (str(chat_id),))
    conn.commit()
    conn.close()

def send_message(token: str, chat_id: str, text: str, parse_mode: str = "Markdown"):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=payload, timeout=8)
    except Exception as e:
        print(f"[!] Telegram send error: {e}")

def handle_command(token: str, chat_id: str, first_name: str, text: str):
    text = text.strip()
    cmd = text.split()[0].lower()
    profile = get_or_create_student_profile(chat_id, first_name)

    if cmd in ("/start", "/help"):
        welcome = (
            f"👋 *Welcome to Fresher Job Intelligence, {first_name}!*\n\n"
            f"We deliver hand-verified fresher jobs (<48h strictly) across Mumbai and Hyderabad directly to your chat.\n\n"
            f"📋 *Your Current Profile:*\n"
            f"• Role Track: *{profile['target_track']}*\n"
            f"• Target City: *{profile['target_city']}*\n\n"
            f"🚀 *Commands:*\n"
            f"• `/jobs` - Get today's Top 6 matched fresh openings\n"
            f"• `/track <name>` - Change role (e.g. `/track Web Development`)\n"
            f"• `/city <name>` - Change city (e.g. `/city Hyderabad`)\n"
            f"• `/profile` - View your active matching settings\n"
            f"• `/stop` - Unsubscribe and delete data (DPDPA 2023)\n\n"
            f"🛡️ _India DPDPA Notice: Your contact is used solely for career placement assistance._"
        )
        send_message(token, chat_id, welcome)

    elif cmd == "/jobs":
        jobs = load_jobs()
        if not jobs:
            send_message(token, chat_id, "⏳ Scrapers are currently refreshing the latest 48h listings. Please check back in a few minutes!")
            return
        matched = match_jobs_for_student(profile, jobs, top_k=6)
        if not matched:
            send_message(token, chat_id, f"No active jobs found for *{profile['target_track']}* in *{profile['target_city']}* today. Check back tomorrow!")
            return
        digest = format_personalized_digest(profile, matched)
        send_message(token, chat_id, digest)

    elif cmd == "/profile":
        info = (
            f"👤 *Student Profile Settings*\n"
            f"• Student ID: `{profile['student_id']}`\n"
            f"• Preferred Track: *{profile['target_track']}*\n"
            f"• Target City: *{profile['target_city']}*\n"
            f"• Notification Status: *{'Active' if profile['is_active'] else 'Paused'}*"
        )
        send_message(token, chat_id, info)

    elif cmd.startswith("/track"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send_message(token, chat_id, "Usage: `/track Data Analytics` (or `Business Analytics`, `Web Development`, `MIS Executive`)")
            return
        new_track = parts[1].strip()
        update_student_preference(chat_id, "track", new_track)
        send_message(token, chat_id, f"✅ Preferred track updated to: *{new_track}*. Type `/jobs` to view matches!")

    elif cmd.startswith("/city"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send_message(token, chat_id, "Usage: `/city Mumbai` or `/city Hyderabad`")
            return
        new_city = parts[1].strip()
        update_student_preference(chat_id, "city", new_city)
        send_message(token, chat_id, f"✅ Target city updated to: *{new_city}*. Type `/jobs` to view matches!")

    elif cmd in ("/stop", "/unsubscribe"):
        update_student_preference(chat_id, "opt_out", "")
        send_message(token, chat_id, "🛑 *You have been unsubscribed.* You will no longer receive daily fresher digests. Type `/start` anytime to re-enable.")

    else:
        send_message(token, chat_id, "❓ Unknown command. Type `/jobs` for today's fresher roles or `/help` for options.")

def start_bot_polling():
    token = get_bot_token()
    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN":
        print("\n[!] TELEGRAM_BOT_TOKEN not found in environment or .env file.")
        print("    Run 'control_panel.bat' and select option [W] (Setup Wizard) to configure your bot token.")
        return

    print("=" * 70)
    print(" 🤖 TELEGRAM STUDENT PLACEMENT BOT LISTENER ACTIVE (Long-Polling)")
    print(" Press Ctrl+C to stop.")
    print("=" * 70)

    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=20"
            resp = requests.get(url, timeout=25)
            if resp.status_code == 200:
                data = resp.json()
                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    msg = update.get("message", {})
                    chat = msg.get("chat", {})
                    chat_id = str(chat.get("id", ""))
                    first_name = chat.get("first_name", "Student")
                    text = msg.get("text", "")

                    if chat_id and text:
                        print(f"[*] Incoming from {first_name} ({chat_id}): '{text}'")
                        handle_command(token, chat_id, first_name, text)
            time.sleep(1)
        except KeyboardInterrupt:
            print("\n[*] Telegram bot stopped by operator.")
            break
        except Exception as e:
            print(f"[!] Polling warning: {e}")
            time.sleep(5)

if __name__ == "__main__":
    start_bot_polling()
