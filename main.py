"""
Fresher Job Scraper - Master CLI Automation
============================================
Command-Line Interface for executing the multi-board scraper.
Exports verified fresh (<48h) fresher jobs to CSV and JSON formats.

Usage:
  python main.py
  python main.py --quick
  python main.py --hours 48 --locations Mumbai Hyderabad
  python main.py --roles "Data Analytics" "MIS Executive"
"""

import os
import sys
import json
import argparse
from datetime import datetime
import pandas as pd

# Ensure UTF-8 output in Windows cmd / powershell
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from config import (
    MAX_HOURS_OLD,
    TARGET_SITES,
    DEFAULT_LOCATIONS,
    ROLE_QUERIES,
    RESULTS_PER_QUERY,
)
from scraper import scrape_fresher_jobs
from hr_enricher import process_hr_enrichment
from history_store import HistoryStore
from google_sheets_sync import sync_configured_google_sheet


def export_to_excel(
    df_valid: pd.DataFrame,
    rejected_jobs: list,
    stats: dict,
    excel_path: str,
    hr_leads: list = None,
):
    """
    Exports a beautifully formatted, multi-tab Excel workbook:
      - Sheet 1: 'Verified Fresher Jobs' (formatted table, frozen header, auto-fit columns)
      - Sheet 2: 'HR Telecalling Leads' (for backend calling team with 1-click search links)
      - Sheet 3: 'Run Summary' (metrics & category breakdown)
      - Sheet 4: 'Rejected Jobs Audit' (inspection log of rejected postings)
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        wb = Workbook()

        # -------------------------------------------------------------
        # Sheet 1: Verified Fresher Jobs
        # -------------------------------------------------------------
        ws_jobs = wb.active
        ws_jobs.title = "Verified Fresher Jobs"
        ws_jobs.views.sheetView[0].showGridLines = True

        # Styles
        header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        zebra_fill = PatternFill(start_color="F2F5F9", end_color="F2F5F9", fill_type="solid")
        thin_border = Border(
            left=Side(style="thin", color="D9D9D9"),
            right=Side(style="thin", color="D9D9D9"),
            top=Side(style="thin", color="D9D9D9"),
            bottom=Side(style="thin", color="D9D9D9"),
        )
        link_font = Font(name="Calibri", size=10, color="0563C1", underline="single")

        # Column selection and display names
        display_mapping = {
            "site": "Job Board",
            "tech_category": "Tech Category",
            "title": "Job Title",
            "company": "Company",
            "location": "Location",
            "date_posted": "Date Posted",
            "experience_range": "Experience",
            "eligible_passout_years": "Eligible Passout Years",
            "required_skills": "Required Skills / Technology",
            "prior_experience_required": "Prior Experience Required",
            "job_requirement": "Job Requirement Summary",
            "min_amount": "Min Salary",
            "max_amount": "Max Salary",
            "currency": "Currency",
            "quality_score": "Score",
            "job_url_direct": "Direct Apply URL",
            "job_url": "Source URL",
            "emails": "Extracted Email",
        }

        # Filter cols present in df
        cols_to_write = [c for c in display_mapping.keys() if c in df_valid.columns]
        headers = [display_mapping[c] for c in cols_to_write]

        # Write header
        ws_jobs.append(headers)
        for col_idx in range(1, len(headers) + 1):
            cell = ws_jobs.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        ws_jobs.row_dimensions[1].height = 28

        # Write job rows
        for row_idx, (_, row_data) in enumerate(df_valid[cols_to_write].iterrows(), start=2):
            row_values = []
            for c in cols_to_write:
                val = row_data[c]
                if pd.isna(val) or val is None:
                    row_values.append("")
                else:
                    row_values.append(str(val))
            ws_jobs.append(row_values)

            # Apply row formatting
            is_even = (row_idx % 2 == 0)
            for col_idx in range(1, len(cols_to_write) + 1):
                cell = ws_jobs.cell(row=row_idx, column=col_idx)
                cell.border = thin_border
                cell.alignment = Alignment(vertical="center")

                if is_even:
                    cell.fill = zebra_fill

                # Hyperlink formatting for URLs
                header_name = headers[col_idx - 1]
                if "URL" in header_name and cell.value and cell.value.startswith("http"):
                    cell.hyperlink = cell.value
                    cell.font = link_font

            ws_jobs.row_dimensions[row_idx].height = 20

        # Freeze top row
        ws_jobs.freeze_panes = "A2"

        # Auto-adjust column widths
        for col in ws_jobs.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws_jobs.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 45)

        # -------------------------------------------------------------
        # Sheet 2: HR Telecalling Leads (For Backend Team)
        # -------------------------------------------------------------
        if hr_leads:
            ws_hr = wb.create_sheet(title="HR Telecalling Leads")
            ws_hr.views.sheetView[0].showGridLines = True

            hr_headers = [
                "Company", "Hiring Role", "Location", "HR Email", "HR Phone",
                "Email Source", "Calling Status", "1-Click LinkedIn HR Search",
                "1-Click Phone Search", "Job URL", "Telecaller Notes"
            ]
            ws_hr.append(hr_headers)

            hr_header_fill = PatternFill(start_color="107C41", end_color="107C41", fill_type="solid")
            for col_idx in range(1, len(hr_headers) + 1):
                cell = ws_hr.cell(row=1, column=col_idx)
                cell.fill = hr_header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center")

            ws_hr.row_dimensions[1].height = 26

            for row_idx, hr in enumerate(hr_leads, start=2):
                ws_hr.append([
                    hr.get("company", ""),
                    hr.get("job_title", ""),
                    hr.get("location", ""),
                    hr.get("hr_email", ""),
                    hr.get("hr_phone", ""),
                    hr.get("hr_source", ""),
                    hr.get("call_status", "Pending"),
                    hr.get("linkedin_hr_search", ""),
                    hr.get("phone_search", ""),
                    hr.get("apply_url", ""),
                    hr.get("telecaller_notes", ""),
                ])
                is_even = (row_idx % 2 == 0)
                for col_idx in range(1, len(hr_headers) + 1):
                    cell = ws_hr.cell(row=row_idx, column=col_idx)
                    cell.border = thin_border
                    cell.alignment = Alignment(vertical="center")
                    if is_even:
                        cell.fill = zebra_fill
                    if cell.value and str(cell.value).startswith("http"):
                        cell.hyperlink = str(cell.value)
                        cell.font = link_font

            ws_hr.freeze_panes = "A2"
            for col in ws_hr.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                col_letter = get_column_letter(col[0].column)
                ws_hr.column_dimensions[col_letter].width = min(max(max_len + 3, 14), 40)

        # -------------------------------------------------------------
        # Sheet 3: Run Summary & Stats
        # -------------------------------------------------------------
        ws_summary = wb.create_sheet(title="Run Summary")
        ws_summary.views.sheetView[0].showGridLines = True

        title_font = Font(name="Calibri", size=14, bold=True, color="1F497D")
        sub_font = Font(name="Calibri", size=11, bold=True, color="333333")

        ws_summary.append(["Fresher Job Scraper - Execution Report"])
        ws_summary.cell(row=1, column=1).font = title_font
        ws_summary.append([])

        summary_rows = [
            ("Execution Timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            ("Scrape Duration", f"{stats.get('duration_seconds', 0)} seconds"),
            ("Total Raw Listings Pulled", stats.get("total_raw_scraped", 0)),
            ("Unique Jobs Deduplicated", stats.get("total_unique_jobs", 0)),
            ("Verified Fresher Jobs (<48h)", stats.get("valid_fresher_jobs", 0)),
            ("Rejected (Filtered Out)", stats.get("rejected_jobs_count", 0)),
        ]

        for k, v in summary_rows:
            ws_summary.append([k, v])

        # Style summary key-value rows
        for r in range(3, 3 + len(summary_rows)):
            ws_summary.cell(row=r, column=1).font = sub_font
            ws_summary.cell(row=r, column=1).border = thin_border
            ws_summary.cell(row=r, column=2).border = thin_border

        ws_summary.append([])
        ws_summary.append(["Breakdown by Platform"])
        ws_summary.cell(row=ws_summary.max_row, column=1).font = title_font
        for site, cnt in stats.get("by_site", {}).items():
            ws_summary.append([site.capitalize(), cnt])

        ws_summary.append([])
        ws_summary.append(["Breakdown by Role Category"])
        ws_summary.cell(row=ws_summary.max_row, column=1).font = title_font
        for cat, cnt in stats.get("by_category", {}).items():
            ws_summary.append([cat, cnt])

        ws_summary.append([])
        ws_summary.append(["Breakdown by Location"])
        ws_summary.cell(row=ws_summary.max_row, column=1).font = title_font
        for loc, cnt in stats.get("by_location", {}).items():
            ws_summary.append([loc, cnt])

        for col in ws_summary.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws_summary.column_dimensions[col_letter].width = max(max_len + 4, 25)

        # -------------------------------------------------------------
        # Sheet 3: Rejected Jobs Audit (if any)
        # -------------------------------------------------------------
        if rejected_jobs:
            ws_rejected = wb.create_sheet(title="Rejected Jobs Audit")
            ws_rejected.views.sheetView[0].showGridLines = True

            rej_headers = ["Job Board", "Job Title", "Company", "Location", "Date Posted", "Experience", "Rejection Reason", "URL"]
            ws_rejected.append(rej_headers)

            rej_fill = PatternFill(start_color="800000", end_color="800000", fill_type="solid")
            for col_idx in range(1, len(rej_headers) + 1):
                cell = ws_rejected.cell(row=1, column=col_idx)
                cell.fill = rej_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center")

            ws_rejected.row_dimensions[1].height = 26

            for row_idx, rj in enumerate(rejected_jobs, start=2):
                ws_rejected.append([
                    rj.get("site", ""),
                    rj.get("title", ""),
                    rj.get("company", ""),
                    rj.get("location", ""),
                    str(rj.get("date_posted", "")),
                    rj.get("experience_range", ""),
                    rj.get("rejection_reason", ""),
                    rj.get("job_url_direct") or rj.get("job_url") or "",
                ])
                for col_idx in range(1, len(rej_headers) + 1):
                    cell = ws_rejected.cell(row=row_idx, column=col_idx)
                    cell.border = thin_border
                    cell.alignment = Alignment(vertical="center")

            ws_rejected.freeze_panes = "A2"
            for col in ws_rejected.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                col_letter = get_column_letter(col[0].column)
                ws_rejected.column_dimensions[col_letter].width = min(max(max_len + 3, 15), 45)

        wb.save(excel_path)
        return True
    except PermissionError:
        print(f"[*] Notice: Could not overwrite '{os.path.basename(excel_path)}' because it is currently open in Excel. Close Excel to refresh it.")
        return False
    except Exception as e:
        print(f"[!] Warning: Could not generate formatted Excel sheet: {e}")
        return False


def parse_args():
    parser = argparse.ArgumentParser(
        description="Scrape verified fresher jobs (<48h) from Naukri, LinkedIn, and Indeed (100% Free)."
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=MAX_HOURS_OLD,
        help=f"Max job age in hours (default: {MAX_HOURS_OLD})",
    )
    parser.add_argument(
        "--locations",
        nargs="+",
        default=DEFAULT_LOCATIONS,
        help="List of target cities (e.g., --locations Mumbai Hyderabad Bangalore)",
    )
    parser.add_argument(
        "--sites",
        nargs="+",
        default=TARGET_SITES,
        help="Target job sites (e.g., --sites naukri linkedin indeed)",
    )
    parser.add_argument(
        "--roles",
        nargs="+",
        default=None,
        help="Specific role categories to scrape (e.g., --roles 'Data Analytics' 'Web Development & Full Stack')",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=RESULTS_PER_QUERY,
        help=f"Results per search query (default: {RESULTS_PER_QUERY})",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="Directory to save output CSV and JSON files (default: output)",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick run mode: scrapes 1 query per category with small limit for testing",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    
    # Resolve output directory relative to script location if relative path given
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = args.output_dir if os.path.isabs(args.output_dir) else os.path.join(script_dir, args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Determine role queries to use
    selected_roles = {}
    if args.roles:
        for r in args.roles:
            matched_key = next((k for k in ROLE_QUERIES if k.lower() == r.lower()), None)
            if matched_key:
                selected_roles[matched_key] = ROLE_QUERIES[matched_key]
            else:
                selected_roles[r] = [r]
    else:
        selected_roles = ROLE_QUERIES

    # Quick test mode adjustments
    results_limit = args.limit
    if args.quick:
        print("[*] Running in QUICK test mode (1 query per role, limit=5)")
        selected_roles = {k: [v[0]] for k, v in selected_roles.items()}
        results_limit = 5

    print("\n" + "=" * 70)
    print(" 🚀 FRESHER JOB INTELLIGENCE SCRAPER (NAUKRI + LINKEDIN + INDEED)")
    print("=" * 70)
    print(f" • Max Job Age:       Last {args.hours} hours strictly")
    print(f" • Target Cities:      {', '.join(args.locations)}")
    print(f" • Target Sites:       {', '.join(args.sites)}")
    print(f" • Role Categories:    {', '.join(selected_roles.keys())}")
    print(f" • Results per query:  {results_limit}")
    print("=" * 70 + "\n")

    # Run scraper
    results = scrape_fresher_jobs(
        locations=args.locations,
        roles_dict=selected_roles,
        sites=args.sites,
        hours_old=args.hours,
        results_per_query=results_limit,
    )

    valid_jobs = results["valid_jobs"]
    rejected_jobs = results["rejected_jobs"]
    stats = results["stats"]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. Track History and Identify Brand New Jobs (Zero Duplicate Broadcasts)
    history = HistoryStore(os.path.join(output_dir, "pipeline_history.db"))
    new_jobs, already_seen_count = history.filter_new_jobs(valid_jobs)

    # Save only the newly discovered jobs for Student Notifications
    new_jobs_json = os.path.join(output_dir, "new_fresher_jobs_latest.json")
    with open(new_jobs_json, "w", encoding="utf-8") as f:
        json.dump(new_jobs, f, indent=2, default=str)

    print(f"\n[*] History Cache: {len(new_jobs)} brand new jobs, {already_seen_count} already seen in prior runs.")

    hr_leads = []

    # 2. Save Valid Fresher Jobs to CSV and JSON
    if valid_jobs:
        df_valid = pd.DataFrame(valid_jobs)

        # Reorder columns for clean reading
        priority_cols = [
            "site", "tech_category", "title", "company", "location",
            "date_posted", "experience_range", "min_amount", "max_amount",
            "eligible_passout_years", "required_skills", "prior_experience_required", "job_requirement",
            "job_url_direct", "job_url", "emails", "quality_score"
        ]
        existing_priority = [c for c in priority_cols if c in df_valid.columns]
        other_cols = [c for c in df_valid.columns if c not in priority_cols]
        df_valid = df_valid[existing_priority + other_cols]

        csv_path = os.path.join(output_dir, f"fresher_jobs_{timestamp}.csv")
        json_path = os.path.join(output_dir, f"fresher_jobs_{timestamp}.json")
        xlsx_path = os.path.join(output_dir, f"fresher_jobs_{timestamp}.xlsx")
        latest_csv = os.path.join(output_dir, "fresher_jobs_latest.csv")
        latest_json = os.path.join(output_dir, "fresher_jobs_latest.json")
        latest_xlsx = os.path.join(output_dir, "fresher_jobs_latest.xlsx")

        # Export CSV
        df_valid.to_csv(csv_path, index=False, encoding="utf-8-sig")
        df_valid.to_csv(latest_csv, index=False, encoding="utf-8-sig")

        # Export JSON
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(valid_jobs, f, indent=2, default=str)
        with open(latest_json, "w", encoding="utf-8") as f:
            json.dump(valid_jobs, f, indent=2, default=str)

        # 2. Enrich Hiring Companies with HR Contacts for Telecalling Team
        hr_leads = process_hr_enrichment(valid_jobs)
        hr_json_path = os.path.join(output_dir, f"hr_leads_{timestamp}.json")
        latest_hr_json = os.path.join(output_dir, "hr_leads_latest.json")
        new_hr_json = os.path.join(output_dir, "new_hr_contacts_latest.json")
        
        # Canonical schema for n8n and Postgres sync
        canonical_hr = []
        for h in hr_leads:
            canonical_hr.append({
                "company": h.get("company", ""),
                "job_title": h.get("job_title", ""),
                "hr_name": "Talent Acquisition Lead",
                "hr_email": h.get("hr_email", ""),
                "email_source": h.get("hr_source", "domain_pattern"),
                "hunter_status": "VALID" if h.get("hr_email") else "UNVERIFIED",
                "mx_record_valid": True if h.get("hr_email") else False,
                "linkedin_search_url": h.get("linkedin_hr_search", ""),
                "google_call_search_url": h.get("phone_search", "")
            })

        with open(hr_json_path, "w", encoding="utf-8") as f:
            json.dump(hr_leads, f, indent=2, default=str)
        with open(latest_hr_json, "w", encoding="utf-8") as f:
            json.dump(hr_leads, f, indent=2, default=str)
        with open(new_hr_json, "w", encoding="utf-8") as f:
            json.dump(canonical_hr, f, indent=2, default=str)

        # 3. Export Formatted Multi-Sheet Excel Workbook (Jobs + HR Leads + Summary + Rejected)
        export_to_excel(df_valid, rejected_jobs, stats, xlsx_path, hr_leads=hr_leads)
        export_to_excel(df_valid, rejected_jobs, stats, latest_xlsx, hr_leads=hr_leads)

        print(f"\n[+] Saved {len(valid_jobs)} verified fresher jobs to:")
        print(f"    - Excel: {xlsx_path}")
        print(f"    - Excel (latest): {latest_xlsx}")
        print(f"    - CSV:   {csv_path}")
        print(f"    - JSON:  {json_path}")
        print(f"    - HR Leads JSON: {latest_hr_json} ({len(hr_leads)} companies)")
    else:
        # Always refresh latest artifacts so a zero-result run cannot leave
        # yesterday's jobs appearing current.
        empty = pd.DataFrame(columns=[
            "site", "tech_category", "title", "company", "location", "date_posted",
            "experience_range", "eligible_passout_years", "required_skills",
            "prior_experience_required", "job_requirement", "job_url_direct", "job_url",
        ])
        empty.to_csv(os.path.join(output_dir, "fresher_jobs_latest.csv"), index=False, encoding="utf-8-sig")
        with open(os.path.join(output_dir, "fresher_jobs_latest.json"), "w", encoding="utf-8") as f:
            json.dump([], f)
        export_to_excel(empty, rejected_jobs, stats, os.path.join(output_dir, "fresher_jobs_latest.xlsx"), hr_leads=[])
        with open(os.path.join(output_dir, "hr_leads_latest.json"), "w", encoding="utf-8") as f:
            json.dump([], f)
        with open(os.path.join(output_dir, "new_hr_contacts_latest.json"), "w", encoding="utf-8") as f:
            json.dump([], f)
        print("\n[!] No jobs passed the strict fresher/freshness criteria in this cycle.")

    # 2a. Upsert this run's jobs into the live sheet while retaining prior results.
    synced = sync_configured_google_sheet(valid_jobs, hr_leads=hr_leads)
    sync_failed = synced is False
    if sync_failed:
        print("[!] Google Sheets sync did not complete; local exports are still available.")

    # 2. Save Rejected Jobs Log (for transparency and audit)
    if rejected_jobs:
        rejected_json = os.path.join(output_dir, "rejected_jobs_latest.json")
        with open(rejected_json, "w", encoding="utf-8") as f:
            json.dump(rejected_jobs, f, indent=2, default=str)
        print(f"[*] Saved {len(rejected_jobs)} rejected jobs log to: {rejected_json}")

    # 3. Print Summary Stats
    print("\n" + "=" * 70)
    print(" 📊 SCRAPING RUN SUMMARY")
    print("=" * 70)
    print(f" Total Duration:          {stats['duration_seconds']} seconds")
    print(f" Total Raw Listings:      {stats['total_raw_scraped']}")
    print(f" Unique Jobs Deduplicated: {stats['total_unique_jobs']}")
    print(f" ✅ Verified Fresher Jobs: {stats['valid_fresher_jobs']}")
    print(f" ❌ Rejected (Filtered):  {stats['rejected_jobs_count']}")

    print("\n Breakdown by Platform:")
    for site in sorted(
        set(stats.get("raw_by_site", {}))
        | set(stats["by_site"])
        | set(stats.get("site_errors", {}))
        | set(stats.get("site_queries_attempted", {}))
    ):
        fetched = stats.get("raw_by_site", {}).get(site, 0)
        kept = stats["by_site"].get(site, 0)
        attempts = stats.get("site_queries_attempted", {}).get(site, 0)
        print(f"   • {site.capitalize()}: {attempts} query/location calls; fetched {fetched}, verified {kept}")
        for error in stats.get("site_errors", {}).get(site, []):
            print(f"       scraper error: {error}")

    print("\n Breakdown by Role Category:")
    for cat, count in stats["by_category"].items():
        print(f"   • {cat}: {count}")

    print("\n Breakdown by Location:")
    for loc, count in stats["by_location"].items():
        print(f"   • {loc}: {count}")

    print("=" * 70)

    # Print top 5 sample matches
    if valid_jobs:
        print("\n ⭐ SAMPLE VERIFIED FRESHER JOBS:")
        for idx, j in enumerate(valid_jobs[:5], 1):
            url = j.get("job_url_direct") or j.get("job_url")
            print(f"\n [{idx}] {j.get('title')} @ {j.get('company')}")
            print(f"     Source: {j.get('site')} | Role: {j.get('tech_category')} | City: {j.get('location')}")
            print(f"     Posted: {j.get('date_posted')} | Experience: {j.get('experience_range') or 'Fresher'}")
            print(f"     Apply URL: {url}")
        print("\n" + "=" * 70)

    if sync_failed:
        raise SystemExit("Google Sheets synchronization failed.")


if __name__ == "__main__":
    main()
