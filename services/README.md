# Placement Services & Distribution Subsystem (Prototypes)

This directory contains standalone microservice modules and prototypes designed to support student matching, multi-channel distribution, and relational database auditing.

---

## Modules Overview

* **`master_orchestrator.py`**: Layered coordinator prototype that demonstrates end-to-end execution across scraping, filtering, database synchronization, student matching, and HR outreach.
* **`brevo_mailer.py`**: Transactional email dispatcher integrating with Brevo (Sendinblue) API for automated HR outreach.
* **`whatsapp_client.py`**: WhatsApp delivery client simulator complying with India DPDPA 2023 opt-in/opt-out consent rules.
* **`telegram_bot.py`**: 24/7 interactive Telegram placement bot using standard long-polling.
* **`student_matcher.py`**: Top-6 personalized job recommendation engine matching freshers by role track, location, and skills.
* **`admin_alerter.py`**: Instant critical notification dispatcher for system administrators via Telegram.
* **`hr_email_templates.py`**: Multi-touch HR outreach email sequences.
* **`api.py`**: FastAPI server exposing scraper endpoints for webhook/n8n triggers.
* **`redirect_service.py`**: URL token generator and telemetry tracking for link clicks.
* **`db_sync.py`**: Relational synchronization between SQLite and PostgreSQL 16.
* **`retention_manager.py`**: Database backup generator and 12-month data retention policy enforcer.
* **`schema.sql`**: Complete PostgreSQL relational DDL schema.
* **`docker-compose.yml`**: Docker stack definition for PostgreSQL, Redis, and n8n services.
* **`n8n_workflow_http_google_sheets.json`**: Reference workflow template for n8n automation.
