# Fresher Jobs & Placement Support — Project Guide

This guide describes the current source tree: what the application is intended to do, what is implemented, how the scheduled run works, and which placement-support ideas are still plans. It is written for someone who has not worked on the project before.

## 1. Project purpose

The project is intended to help a placement team find recent entry-level jobs in India, remove listings that do not meet the fresher criteria, keep the results organized, and make suitable opportunities easier to share with students.

The long-term workflow is:

1. Collect jobs from supported job boards.
2. Verify role, freshness, and experience; extract useful job details.
3. Save the results locally and update the placement team's Google Sheet.
4. Identify newly found jobs so later student notifications do not repeat old listings.
5. In a later phase, research interview preparation for a company and specific role for selected eligible jobs.
6. In a future phase, distribute matching job alerts and interview preparation to students by email and WhatsApp.

**What is actually working in the main workflow today:** job collection, filtering, local CSV/JSON/Excel exports, a local duplicate-history database, and optional direct Google Sheets sync. Company/role research is an isolated prototype under `company_search/`; it is not called by the main workflow. Student email and WhatsApp delivery are not connected.

## 2. Current search scope and filtering rules

### Search locations and roles

The default locations are Mumbai and Hyderabad. The configured role families are:

- Business Analyst
- Data Analyst
- Analyst
- Marketing Analyst
- HR Analyst
- Full Stack Developer
- Web Developer

Each family has plain, fresher, and/or junior search phrases in **config.py**. The application searches Naukri, Indeed, and LinkedIn through JobSpy. Monster India / JobsAhead is not included because the current JobSpy integration does not support it.

The default run collects up to 25 results per query and location from each supported site. **--quick** is a separate diagnostic mode that uses one phrase per role family and five results per query; it is not the full search.

### Eligibility checks

The current configured experience ceiling is **one year**. The pipeline also checks the posting age (48 hours by default; scheduled workflow runs pass 20 hours), role category, prohibited titles/levels, excluded internship/project/training requirements, and configured scam/training-fee signals.

For fresher eligibility, the filter reads the board's experience field and checks explicit experience ranges in the job description. It recognizes common ranges such as 1–2 years, 2 to 4 years, and open-ended values such as 5+ years. A requirement above the configured ceiling is rejected. Missing or unverifiable experience is intended to fail closed.

The filter is rule-based Python; it does not use an LLM. It can reliably handle common structured values and explicit wording, but it cannot perfectly understand every ambiguous sentence in every job description.

### Extracted fields versus enforced criteria

The project extracts useful fields such as eligible passout years, skills, prior-experience wording, and job requirements for exports. Extracting a passout year or skill does **not** currently mean the job has been strictly screened against a student's graduation year or skill profile.

Undisclosed salary values may be filled with a role-based market estimate by **filter_engine.py**. Such a value is a benchmark, not a salary confirmed by the employer.

## 3. How a normal run works

The supported command-line entry point is **main.py**.

1. **config.py** supplies the role phrases, sites, locations, time limit, result limit, and experience ceiling.
2. **scraper.py** runs the query/location tasks. Each task queries the enabled sites through JobSpy; site calls run concurrently. Two independent query/location tasks may run at once, while the Naukri adapter is serialized to protect its JobSpy integration.
3. Job records are normalized and deduplicated within their source, then sent to **filter_engine.py**.
4. The filter classifies each record as valid or rejected and records reasons for rejection.
5. **HistoryStore** compares valid jobs with the local SQLite database and writes newly seen jobs to **new_fresher_jobs_latest.json**.
6. **main.py** writes timestamped and **latest** CSV, JSON, and Excel files. It also writes rejection and HR-enrichment output.
7. **google_sheets_sync.py** optionally upserts valid jobs into the configured spreadsheet.
8. The CLI prints counts by site, role, and location, plus example matches.

The **new_fresher_jobs_latest.json** file is only an output for a possible notification workflow. The main script does not currently send that list to students.

## 4. Naukri experience verification

The project has a custom **EntryLevelNaukri** adapter in **scraper.py**. It applies Naukri's **experience=0** search filter and inspects the raw detail response for structured experience fields before JobSpy's typed model drops fields it does not expose. The structured detail value replaces the search-card value when available. A failed detail request or missing detail experience is marked unverified so it cannot silently pass as 0–1.

The experience filter also checks explicit numeric experience claims in the description. This catches common cases where the search-card range and description disagree, without invoking an LLM.

**Verification limit:** live Naukri detail responses have not been successfully confirmed from the current environment. The adapter searches likely structured field names and fails closed when it cannot find one; a live run is needed to confirm the exact field Naukri returns. In that situation, some or all Naukri results may be rejected as unverified until the response mapping is confirmed. Do not interpret an unverified rejection as proof the job itself is ineligible.

## 5. Local outputs and Google Sheets

Local run output is written under **output/**. Common files include:

- **fresher_jobs_latest.csv**, **.json**, **.xlsx** — the latest valid jobs.
- Timestamped **fresher_jobs_*.csv**, **.json**, **.xlsx** — run snapshots.
- **new_fresher_jobs_latest.json** — jobs newly seen by the local history database.
- **rejected_jobs_latest.json** — rejected jobs and their reasons.
- **hr_leads_latest.json** and **new_hr_contacts_latest.json** — HR contact-enrichment output.
- **pipeline_history.db** — SQLite history for duplicate tracking during local runs.

The jobs tab sync uses 11 columns: Job Title, Company, Location, Role, Date Posted, Experience, Min Salary, Max Salary, Apply URL, Source, and Last Updated. It upserts by Apply URL and preserves existing rows. Extra extracted fields such as skills and passout years are available in local exports, not in those 11 sheet columns.

Google Sheets requires **GOOGLE_SPREADSHEET_ID** and a service-account JSON file configured through **GOOGLE_SERVICE_ACCOUNT_FILE**. The service account needs access to the spreadsheet. Never commit **.env** or **credentials.json**; both are ignored by Git.

The current main workflow also calls HR enrichment and passes the resulting leads to the Sheets sync. This is separate from emailing students. The standalone Brevo mailer targets HR contacts; it is not invoked by **main.py**.

## 6. GitHub Actions automation

The workflow is **.github/workflows/fresher-job-scraper.yml**. It declares scheduled runs at 11:00 and 16:00 in Asia/Kolkata. Scheduled executions use a 20-hour lookback. A manual workflow dispatch offers 20- or 48-hour lookback choices, including a 48-hour initial fill.

The workflow expects repository secrets named **GOOGLE_SPREADSHEET_ID** and **GOOGLE_SERVICE_ACCOUNT_JSON**. It creates **credentials.json** only for the workflow run, executes **main.py**, and records a small successful-run timestamp commit.

The schedule declaration is not proof that GitHub has actually started the scheduled run. Check the Actions run history for operational confirmation.

### Important state limitation on hosted Actions

**HistoryStore** uses a SQLite file under **output/**. A GitHub-hosted Actions job runs on a fresh runner, so that local database does not automatically carry over to the next scheduled run. The workflow does not currently persist **pipeline_history.db** to durable storage. Consequently, GitHub Actions may treat jobs from a previous run as new in **new_fresher_jobs_latest.json**. The Google Sheet can still avoid duplicate rows by Apply URL, but the local **new_jobs** detection is not durable across hosted runs.

Student notifications still need durable per-job state before relying on “new job only” delivery. Company research is currently a separate experiment under **company_search/** and is not called from the scraper or Actions workflow.

## 7. Student messaging and interview research: status

### Student email and WhatsApp

These are **not implemented as an automatic end-to-end student notification workflow**:

- **brevo_mailer.py** is an HR outreach dispatcher and is not called by **main.py**.
- **whatsapp_client.py** is a standalone simulator using an Evolution-style endpoint; it defaults to dry-run and has no integration with the scraper's main run.
- **student_matcher.py** contains matching and digest logic, but its default roster uses sample data and it is not wired into **main.py**.
- **telegram_bot.py** is a separate Telegram bot prototype.

Brevo credentials and template IDs alone will not connect these modules. A student roster with email/phone and consent state, a supported Brevo WhatsApp delivery path, template variables, and a call from the main workflow still need to be implemented. Brevo's WhatsApp API and WhatsApp campaign API should be treated as separate from an existing WhatsApp group chat; the intended delivery mode must be selected before coding.

### Company-and-role research experiment

**company_search/** is an isolated Python prototype, not part of the application. It uses DuckDuckGo HTML/Lite for discovery, then `httpx` and BeautifulSoup for direct page fetch and extraction. Queries and fetched pages are restricted to the approved domains in `company_search/source_catalog.json`; robots rules and redirects are checked, and blocked pages are skipped. It records search hits, HTTP/robots outcomes, and extracted source text. The baseline and limitations for two saved job listings are in `company_search/manual_research.md`.

The prototype uses no API key. Search HTML can change or rate-limit. Reddit has relevant candidate discussions, but the tested path is disallowed by robots.txt; Glassdoor and Indeed returned 403, and those restrictions are not bypassed. The Hitachi Digital Deal Desk listing has no exact-role interview report in the sources found; adjacent-role evidence is clearly labeled as such. The prototype does not generate interview questions, invent company-project assignments, or run from `main.py` or GitHub Actions.

### Planned interview-preparation product (not implemented)

The intended later workflow is: select a filtered eligible job → search the company and role against approved candidate-report/question sources and official company project pages → fetch and extract permitted public text → retain source URLs, dates, role match, and evidence snippets → assemble a bounded evidence pack → use a chosen LLM provider (Groq or OpenRouter are options, not configured) to curate and answer a short, role-relevant Q&A set grounded only in that pack → render the reviewed material into a consistent PDF layout. The LLM must mark unsupported details as unknown and distinguish first-hand reports from editorial guides and adjacent roles. Provider limits, prompt size, output schema, and cost need to be handled before integration.

This is a roadmap only. There is currently no LLM integration, Q&A generation stage, PDF generation pipeline, or reusable PDF template in the repository. These should first be built and checked inside `company_search/`, then integrated into the main job workflow only after the standalone output is reliable. The current allowlist findings are empirical snapshots, not a promise that every domain or result will remain available.

## 8. Project file map

### Main workflow

- **main.py** — CLI, orchestration, exports, HR enrichment call, and Google Sheets sync.
- **config.py** — sites, locations, role queries, limits, exclusions, pacing, and query concurrency.
- **scraper.py** — JobSpy requests, per-board error isolation, Naukri adapter, detail cache, and deduplication.
- **filter_engine.py** — freshness, experience, role, exclusion, field extraction, and salary handling. It retains up to 16,000 characters of each job description in `job_requirement`, so eligibility details near the end are available to research and exports.
- **history_store.py** — local SQLite job-history deduplication.
- **google_sheets_sync.py** — direct spreadsheet authentication, row mapping, and upsert behavior.
- **company_search/** — isolated no-key search/scraping experiment; not imported by the app.
- **.github/workflows/fresher-job-scraper.yml** — scheduled and manual GitHub Actions entry points.

### Related integrations and prototypes

- **hr_enricher.py**, **hr_email_templates.py**, **brevo_mailer.py** — HR lead enrichment and standalone HR outreach components.
- **student_matcher.py**, **whatsapp_client.py**, **telegram_bot.py** — student matching and messaging prototypes; not connected to the scraper's main CLI.
- **api.py**, **redirect_service.py** — optional local HTTP API and tracked-redirect prototype.
- **db_sync.py**, **schema.sql**, **retention_manager.py**, **docker-compose.yml** — optional database schema, sync, retention, and local service configuration.
- **master_orchestrator.py**, **admin_alerter.py**, **n8n_workflow_http_google_sheets.json** — broader orchestration, alerting, and n8n prototypes; **main.py** remains the primary supported scraper entry point.
- **test_filter.py** — existing filter-focused test file. Consult the current test run before relying on a test status; this guide does not claim a fresh test-suite result.
- **output/** — local exports and SQLite state; ignored by Git apart from its **.gitkeep**.
- **legacy/** — older project material.

## 9. Running locally

From the project folder in PowerShell:

~~~powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
~~~

Useful options:

~~~powershell
python main.py --hours 48
python main.py --quick
python main.py --locations Mumbai Hyderabad
python main.py --sites naukri indeed linkedin
python main.py --roles "Data Analyst" "Business Analyst"
python main.py --limit 25
~~~

Run the isolated two-job company research experiment:

~~~powershell
python company_search/scrape_research.py --engine both
~~~

**--quick** is for a small diagnostic run. Use the full command for the complete configured phrase set.

## 10. Current caveats and next steps

1. Confirm the live Naukri detail JSON field and verify a mismatch example end to end. Until then, detail-field absence fails closed.
2. Persist history across GitHub Actions runs; otherwise the “new job” boundary resets on hosted runners.
3. Decide the student roster and consent source, then implement Brevo email and WhatsApp as distinct delivery channels.
4. Evaluate the no-key search prototype against more companies and roles before deciding whether it belongs in the application.
5. If a new Google jobs worksheet is expected to be created automatically, inspect that path in **google_sheets_sync.py**; the existing project should first be verified against the already configured sheet.

These caveats matter because the application has several prototypes around the main scraper. A module existing in the repository does not by itself mean it runs in the scheduled workflow.
