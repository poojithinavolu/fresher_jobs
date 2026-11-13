"""Excel Exporter for Fresher Job Listings & Execution Reports.

Generates a formatted, multi-tab Excel workbook:
- Sheet 1: 'Verified Fresher Jobs' (formatted table, frozen header, auto-fit columns)
- Sheet 2: 'HR Telecalling Leads' (for backend calling team with 1-click search links)
- Sheet 3: 'Run Summary' (metrics & category breakdown)
- Sheet 4: 'Rejected Jobs Audit' (inspection log of rejected postings)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
import pandas as pd

logger = logging.getLogger("ExcelExporter")


def export_to_excel(
    df_valid: pd.DataFrame,
    rejected_jobs: List[Dict[str, Any]],
    stats: Dict[str, Any],
    excel_path: str,
    hr_leads: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Exports a multi-tab Excel workbook with formatted headers, auto-adjusted widths, and hyperlinks."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter

        wb = Workbook()

        # -------------------------------------------------------------
        # Sheet 1: Verified Fresher Jobs
        # -------------------------------------------------------------
        ws_jobs = wb.active
        ws_jobs.title = "Verified Fresher Jobs"
        ws_jobs.views.sheetView[0].showGridLines = True

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

        cols_to_write = [c for c in display_mapping.keys() if c in df_valid.columns]
        headers = [display_mapping[c] for c in cols_to_write]

        ws_jobs.append(headers)
        for col_idx in range(1, len(headers) + 1):
            cell = ws_jobs.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        ws_jobs.row_dimensions[1].height = 28

        for row_idx, (_, row_data) in enumerate(df_valid[cols_to_write].iterrows(), start=2):
            row_values = []
            for c in cols_to_write:
                val = row_data[c]
                if pd.isna(val) or val is None:
                    row_values.append("")
                else:
                    row_values.append(str(val))
            ws_jobs.append(row_values)

            is_even = (row_idx % 2 == 0)
            for col_idx in range(1, len(cols_to_write) + 1):
                cell = ws_jobs.cell(row=row_idx, column=col_idx)
                cell.border = thin_border
                cell.alignment = Alignment(vertical="center")
                if is_even:
                    cell.fill = zebra_fill

                header_name = headers[col_idx - 1]
                if "URL" in header_name and cell.value and str(cell.value).startswith("http"):
                    cell.hyperlink = str(cell.value)
                    cell.font = link_font

            ws_jobs.row_dimensions[row_idx].height = 20

        ws_jobs.freeze_panes = "A2"

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
        # Sheet 4: Rejected Jobs Audit (if any)
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
