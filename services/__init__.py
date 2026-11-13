"""Placement Services & Distribution Subsystem.

Contains microservice modules and prototypes for:
- Student-Job Matching (student_matcher)
- Outreach & Communication (brevo_mailer, whatsapp_client, telegram_bot, admin_alerter)
- Relational Database & Sync (db_sync, retention_manager, schema.sql)
- HTTP Endpoints & Redirect Tracking (api, redirect_service)
- Layered Orchestrator (master_orchestrator)
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root and services directory are on sys.path
SERVICES_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVICES_DIR.parent
for p in [str(PROJECT_ROOT), str(SERVICES_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)
