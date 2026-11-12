# Fresher Job Scraper

A Python JobSpy pipeline for recent entry-level openings in India.

## Active sources

The primary CLI (`main.py`) queries **Naukri, Indeed, and LinkedIn** separately for fault isolation, using the same search phrases, locations, and per-query result limit for each board. Search phrases include plain role names and fresher/junior variants. JobSpy has no public experience argument, so the Naukri adapter extension sends Naukri's separate `experience=0` filter and the project verifies each returned job's experience afterward. Deduplication is scoped to each source so an earlier board cannot suppress a matching listing from another board. JobSpy currently has no Monster India / JobsAhead adapter; it is not included as a supported source. JobSpy's supported sites are documented in its [upstream README](https://github.com/speedyapply/JobSpy/blob/main/README.md).

## Target rules

- Roles: Business Analyst, Data Analyst, Analyst, Marketing Analyst, HR Analyst, Full Stack Developer, Web Developer.
- Experience: up to one year (0–1 years); postings without verifiable experience requirements are excluded.
- Freshness: within 48 hours; missing posting dates are excluded because freshness cannot be verified.
- Google Sheets columns: Job Title, Company, Location, Role, Date Posted, Experience, Min Salary, Max Salary, Apply URL, Source, Last Updated.
- Excludes internship roles and explicit project experience/letter/certificate and training experience/letter/certificate requirements, plus existing scam/training-fee indicators.

## Setup and run

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py --quick
python main.py
```

Copy `.env.example` to `.env`, set `GOOGLE_SPREADSHEET_ID`, and keep the service-account key at the path in `GOOGLE_SERVICE_ACCOUNT_FILE`. Share the spreadsheet with the service account's `client_email` as an Editor. The sync detects the existing jobs tab by its `Job Title`, `Company`, and `Location` headers; otherwise it uses `02_Jobs`. Each run upserts by Apply URL and preserves earlier rows, so the scheduled 20-hour overlap does not discard jobs from the initial 48-hour fill. Keep the JSON key out of source control. Without these credentials, local CSV/JSON/XLSX exports still work and the sheet sync is skipped.

### GitHub Actions schedule

The `.github/workflows/fresher-job-scraper.yml` workflow runs daily at 11:00 and 16:00 India time (GitHub cron is UTC). Scheduled runs use a 20-hour lookback; run it once manually with 48 hours for the initial fill. Add repository Actions secrets named `GOOGLE_SPREADSHEET_ID` and `GOOGLE_SERVICE_ACCOUNT_JSON` (the full service-account JSON contents). The workflow writes the JSON to the ignored `credentials.json` file only during the run and commits a small success timestamp so GitHub does not disable this public repo's schedule for inactivity.

If Naukri rate-limits the current network, set `JOBSPY_PROXIES` in the process environment to a comma-separated list of JobSpy-compatible proxy URLs before running the scraper. Proxy credentials are not stored in project files.

## Project map

- `main.py`: supported command-line workflow and exports.
- `scraper.py`: per-board JobSpy collection, deduplication, pipeline orchestration.
- `filter_engine.py`: freshness, experience, exclusion, role classification, and field extraction.
- `config.py`: locations, roles, limits, and exclusion lists.
- `output/`: latest and timestamped exports plus local run history.
- Other integration modules (API, database, Telegram, Sheets, email) are optional and are not required for scraping.

## Verification

Run `python -m pytest -q` for filter regression checks. Live board coverage depends on the boards' current availability, rate limits, and network access; a scrape records per-board counts/errors and cannot guarantee a fixed number of results.
