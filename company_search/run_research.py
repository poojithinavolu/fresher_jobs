"""Unified CLI runner for Dynamic Company Interview Research & Agentic Report Generation.

Usage:
  # Run for any arbitrary company and role on the spot:
  python company_search/run_research.py --company "Hitachi" --role "Data Analyst"
  python company_search/run_research.py --company "TCS" --role "Full Stack Developer"
  python company_search/run_research.py --company "indē wild" --role "Junior Data Analyst"

  # Or run automatically for the latest scraped fresher jobs:
  python company_search/run_research.py --from-scraper --max-jobs 2
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from company_search.agentic_pipeline import run_agentic_research

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("run_research")


def load_scraper_jobs(max_jobs: int = 3) -> list[dict[str, str]]:
    """Loads verified jobs from output/fresher_jobs_latest.json with robust fallbacks."""
    latest_file = PROJECT_ROOT / "output" / "fresher_jobs_latest.json"

    if not latest_file.exists():
        logger.info(f"No scraper output found at {latest_file}. Using standard target candidates.")
        return [
            {"company": "Google", "role": "SDE1"},
            {"company": "Hitachi", "role": "Data Analyst"},
        ][:max_jobs]

    try:
        data = json.loads(latest_file.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else data.get("jobs", [])
        jobs = []
        for r in rows:
            company = str(r.get("company") or r.get("Company") or "").strip()
            title = str(r.get("title") or r.get("Job Title") or r.get("role") or "").strip()
            if company and title:
                jobs.append({"company": company, "role": title})
        return jobs[:max_jobs] or [
            {"company": "Google", "role": "SDE1"},
            {"company": "Hitachi", "role": "Data Analyst"},
        ][:max_jobs]
    except Exception as exc:
        logger.error(f"Error loading jobs from {latest_file}: {exc}")
        return [
            {"company": "Google", "role": "SDE1"},
            {"company": "Hitachi", "role": "Data Analyst"},
        ][:max_jobs]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--company", type=str, help="Company name to research (e.g. 'Hitachi', 'TCS', 'EY')")
    parser.add_argument("--role", type=str, default="Data Analyst", help="Target job role (default: 'Data Analyst')")
    parser.add_argument("--from-scraper", action="store_true", help="Read target companies directly from output/fresher_jobs_latest.json")
    parser.add_argument("--max-jobs", type=int, default=2, help="Max jobs to process when using --from-scraper")

    args = parser.parse_args()

    print("\n" + "═" * 70)
    print(" 🚀 AGENTIC COMPANY INTERVIEW & PROJECT RESEARCH PIPELINE")
    print("═" * 70)

    jobs_to_run = []
    if args.company:
        jobs_to_run.append({"company": args.company, "role": args.role})
    elif args.from_scraper:
        jobs_to_run = load_scraper_jobs(max_jobs=args.max_jobs)
        if not jobs_to_run:
            print("[!] No jobs found in scraper output; running default sample (EY - Data Analyst).")
            jobs_to_run.append({"company": "EY", "role": "Data Analyst"})
    else:
        # Default sample if no arguments provided
        jobs_to_run.append({"company": "Hitachi", "role": "Data Analyst"})

    for idx, j in enumerate(jobs_to_run, start=1):
        comp = j["company"]
        role = j["role"]
        print(f"\n[Target {idx}/{len(jobs_to_run)}] Researching '{comp}' for role '{role}'...")
        try:
            res = run_agentic_research(company=comp, role=role)
        except RuntimeError as exc:
            print("\n" + "!" * 70)
            print(f" ❌ ERROR EXECUTING RESEARCH FOR '{comp}':\n {exc}")
            print("!" * 70 + "\n")
            return 1

        print("\n" + "─" * 70)
        print(f" ✅ RESEARCH COMPLETED: {comp} ({role})")
        print("─" * 70)
        print(f" • Total Verified Q&As:  {res['total_questions']}")
        print(f" • Total Sources Used:    {res['total_sources']}")
        print(f" • Structured JSON Pack:  {res['json_path']}")
        print(f" • Downloadable PDF:      {res['pdf_path']}")
        print("─" * 70)

    print("\n[✓] All requested company research workflows finished successfully.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

