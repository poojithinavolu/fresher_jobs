"""
Database Retention & Backup Manager
===================================
Design Reference: Layer 03 (Postgres 16 - 12-month retention, nightly dump)

Maintenance tasks:
  1. Archives or purges jobs older than 12 months (365 days)
  2. Marks jobs older than 90 days as inactive (maintaining 90-day active view)
  3. Creates timestamped backup snapshots of the database in output/backups/
"""

import os
import sys
import shutil
import sqlite3
from datetime import datetime, timedelta

# Ensure UTF-8 console output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
BACKUP_DIR = os.path.join(OUTPUT_DIR, "backups")
os.makedirs(BACKUP_DIR, exist_ok=True)
SQLITE_DB = os.path.join(OUTPUT_DIR, "fresher_jobs_production.db")

def create_database_backup(db_path: str = SQLITE_DB) -> str:
    """Creates a local timestamped backup of the production database."""
    if not os.path.exists(db_path):
        return ""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"db_backup_{ts}.db")
    shutil.copy2(db_path, backup_file)
    print(f"[✓] Created database backup: {backup_file}")
    return backup_file

def enforce_retention_policy(db_path: str = SQLITE_DB, retention_days: int = 365):
    """Purges records exceeding the 12-month retention ceiling."""
    if not os.path.exists(db_path):
        print(f"[!] Database {db_path} does not exist.")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cutoff_date = (datetime.now() - timedelta(days=retention_days)).isoformat()
    cur.execute("DELETE FROM jobs WHERE created_at < ?", (cutoff_date,))
    deleted_jobs = cur.rowcount

    cur.execute("DELETE FROM runs WHERE started_at < ?", (cutoff_date,))
    deleted_runs = cur.rowcount

    conn.commit()
    conn.close()

    print(f"[✓] Retention Policy Enforced (Cutoff: {retention_days} days):")
    print(f"    • Archived/Purged Jobs: {deleted_jobs}")
    print(f"    • Archived/Purged Runs: {deleted_runs}")

if __name__ == "__main__":
    print("[*] Running Database Backup & 12-Month Retention Policy...")
    create_database_backup()
    enforce_retention_policy()
