# Fresher Job Scraper & Agentic Placement Intelligence Platform

A production-grade, modular Python automation platform for fresher job collection, strict eligibility verification, Google Sheets synchronization, and dynamic company interview research.

---

## 1. System Architecture & Directory Map

```
fresher_job_scraper/
│
├── .env                              # Environment configuration (Keys, Sheets ID, Brevo)
├── .env.example                      # Reference template for environment variables
├── .gitignore                        # Git ignore patterns
├── credentials.json                  # Google Service Account JSON (git-ignored)
├── requirements.txt                  # Consolidated production dependencies
├── PROJECT_OVERVIEW.md               # Complete architecture & design manual
├── README.md                         # Project overview and quickstart guide
├── NEXT_AGENT_HANDOFF.md             # Detailed engineering handoff
│
├── main.py                           # Master CLI Entry Point for Fresher Job Scraper & Google Sheets Sync
├── config.py                         # Centralized configuration (roles, locations, sites, filters)
├── scraper.py                        # Multi-board scraping engine (JobSpy, EntryLevelNaukri)
├── filter_engine.py                  # Strict fresher verification & categorization engine
├── excel_exporter.py                 # Multi-tab styled Excel workbook generator
├── google_sheets_sync.py             # Google Sheets direct updater (Service account)
├── hr_enricher.py                    # HR contact & lead enrichment
├── history_store.py                  # SQLite duplicate-prevention store
├── test_filter.py                    # Root test runner for filter engine
│
├── company_search/                   # Subsystem: Dynamic Agentic Company Research & PDF Prep
│   ├── run_research.py               # Unified CLI: python company_search/run_research.py --company "..." --role "..."
│   ├── agentic_pipeline.py           # LangGraph 5-node agentic pipeline (fail-fast, Pydantic validation)
│   ├── dynamic_search.py             # Multi-engine resilient search & polite web fetcher
│   ├── pdf_generator.py              # ReportLab publication-grade PDF generator
│   ├── source_catalog.json           # Approved domains catalog & query patterns
│   ├── test_dynamic_agentic.py       # Full test suite (5/5 passing)
│   ├── README.md                     # Subsystem documentation
│   └── results/                      # Output JSON packs and PDF dossiers
│
├── services/                         # Subsystem: Communication & Backend Services (Prototypes)
│   ├── __init__.py
│   ├── master_orchestrator.py        # 4-layer master coordinator
│   ├── brevo_mailer.py               # Brevo transactional email dispatcher
│   ├── whatsapp_client.py            # WhatsApp client simulator (DPDPA 2023 compliant)
│   ├── telegram_bot.py               # Telegram placement bot
│   ├── student_matcher.py            # Student-job matching engine
│   ├── admin_alerter.py              # Pipeline failure & status alerts
│   ├── hr_email_templates.py         # Outbound HR email templates
│   ├── api.py                        # FastAPI placement & job API
│   ├── redirect_service.py           # Link redirect & click tracker
│   ├── db_sync.py                    # SQLite/PostgreSQL sync
│   ├── retention_manager.py          # Data retention & purge manager
│   ├── schema.sql                    # PostgreSQL relational database schema
│   ├── docker-compose.yml            # Docker stack definition
│   └── n8n_workflow_http_google_sheets.json
│
├── tests/                            # Consolidated Test Suite
│   ├── __init__.py
│   ├── test_filter.py                # Filter engine verification tests
│   └── test_company_research.py      # Company research & PDF verification tests
│
└── output/                           # Production Output Directory (CSV, JSON, XLSX, SQLite DB)
    ├── fresher_jobs_latest.json
    ├── fresher_jobs_latest.csv
    ├── fresher_jobs_latest.xlsx
    └── pipeline_history.db
```

---

## 2. Quickstart & CLI Commands

### A. Fresher Job Scraping & Google Sheets Sync
```powershell
# Quick testing run (1 query per category, small limit):
python main.py --quick

# Standard production run (48-hour window, all configured roles and locations):
python main.py

# Custom lookback and locations:
python main.py --hours 24 --locations Mumbai Hyderabad
```

### B. Dynamic Company Interview Research & PDF Dossiers
```powershell
# Research any arbitrary company and role on the spot:
python company_search/run_research.py --company "Google" --role "SDE1"
python company_search/run_research.py --company "Hitachi" --role "Data Analyst"
python company_search/run_research.py --company "TCS" --role "Web Developer"

# Automatically research top jobs from the latest scraper output:
python company_search/run_research.py --from-scraper --max-jobs 2
```

### C. Run Verification Tests
```powershell
# Test fresher filter engine (5/5 tests passing):
python test_filter.py
# or via tests/:
python tests/test_filter.py

# Test company interview research & publication-grade PDF generation (5/5 tests passing):
python company_search/test_dynamic_agentic.py
# or via tests/:
python tests/test_company_research.py
```

---

## 3. GitHub Actions CI/CD Automation

The workflow `.github/workflows/fresher-job-scraper.yml` automatically triggers scheduled scrapes daily at **11:00** and **16:00 IST** using a 20-hour lookback window, upserting verified fresher listings into the connected Google Sheet without creating duplicate rows.
