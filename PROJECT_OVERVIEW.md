# Fresher Job Scraper — Project Overview

## What the application does

This Python application uses JobSpy to find recent entry-level jobs in Mumbai and Hyderabad. It searches for Business Analyst, Data Analyst, Analyst, Marketing Analyst, HR Analyst, Full Stack Developer, and Web Developer roles on Naukri, Indeed, and LinkedIn. Monster India / JobsAhead is not supported by the current JobSpy adapter.

The scraper checks posting age and experience, keeps roles with verifiable requirements of up to one year, and filters out specified internship, project-document, training, and scam indicators. It writes local CSV, JSON, and Excel reports and can sync jobs directly to Google Sheets.

The jobs tab uses 11 columns: Job Title, Company, Location, Role, Date Posted, Experience, Min Salary, Max Salary, Apply URL, Source, and Last Updated. Syncs update existing rows by Apply URL and preserve older rows.

## GitHub Actions

The workflow at `.github/workflows/fresher-job-scraper.yml` is intended to run at **11:00 AM and 4:00 PM IST**. Scheduled runs search the previous 20 hours; manual runs can use 20 or 48 hours. It reads the spreadsheet ID and service-account JSON from repository secrets, runs the scraper, and records a small commit after success. GitHub currently reports no scheduled runs for this workflow; manual runs have succeeded. Scheduled timing is best-effort.

## Changes made

- Equalized the per-query result limit across Naukri, Indeed, and LinkedIn (25 each); previously Naukri was allowed 60 while the other sites were allowed 25.
- Made deduplication source-aware so a matching listing from the first site cannot suppress another site's listing.
- Added per-site query-attempt and scraper-error reporting.
- Added bounded threading: the three site calls for each search run concurrently, with no overlapping requests to the same board and errors isolated by site.

## Verification and current status

All **16 local tests pass**. A local 14-case Naukri/Indeed benchmark measured 2m 14s sequential and 2m 02s parallel (9% faster, with the same fetched counts). LinkedIn returned HTTP 429 locally, so that benchmark could not cover all three sites. A recent full sequential Actions run took 23m 54s; its per-site timings suggest roughly 17% savings with threading, but that figure is an estimate. The threading change is pushed to `main` as `e0d9862`; a full scheduled run using that change had not yet been checked when this note was written.
