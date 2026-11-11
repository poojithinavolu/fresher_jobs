"""
========================================================================================
 🚀 FRESHER JOB INTELLIGENCE & PLACEMENT ENGINE (ALL-IN-ONE MASTER SCRIPT)
========================================================================================
A 100% free-of-cost ($0 API fees), self-contained automation system that:
  1. SCRAPES live fresher jobs across LinkedIn, Naukri, and Indeed (via JobSpy).
  2. FILTERS strictly:
       - Posted strictly within the last 48 hours (<= 48h lookback).
       - Pure freshers only (0-1 yrs exp max, drops experienced / mid-senior jobs).
       - Level 2+ blocker (rejects Roman numerals 'II', 'III', 'SDE 2', 'Engineer 2').
       - Strictly matches 5 positions: Data Analytics, Business Analytics, Analyst,
         MIS Executive, and Web Dev / Full Stack Development.
       - Drops 40+ known training institutes, coaching centers, and placement scams.
  3. ENRICHES every job:
       - Extracts hidden CTC from descriptions (e.g. '3.5 - 5 LPA').
       - Applies Indian market compensation benchmarks if confidential by employer.
       - NEVER leaves experience or salary fields blank!
  4. EXPORTS clean, deduplicated data:
       - Multi-tab formatted Excel (.xlsx) with clickable direct apply hyperlinks.
       - Sanitized JSON (.json) ready for APIs / n8n without NaN errors.
       - Standard UTF-8 CSV (.csv).
  5. BUILT-IN AUTOMATION & INTEGRATION:
       - CLI mode: python fresher_job_master.py
       - Quick test: python fresher_job_master.py --quick
       - Recurring scheduler: python fresher_job_master.py --interval 120 (runs every 2h)
       - Local API server for n8n: python fresher_job_master.py --serve
       - Telegram alerts: broadcasts top jobs to Telegram if bot token configured
       - Google Sheets sync: updates live Google Sheets if credentials provided
       - Built-in test suite: python fresher_job_master.py --test

Author: Fresher Placement Automation System
========================================================================================
"""

import os
import sys
import re
import time
import json
import math
import logging
import argparse
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional, Tuple

# Ensure UTF-8 console output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("FresherJobMaster")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ======================================================================================
# 1. CENTRAL CONFIGURATION & SEARCH QUERIES
# ======================================================================================

MAX_HOURS_OLD: int = 48
TARGET_SITES: List[str] = ["naukri", "linkedin", "indeed"]
DEFAULT_LOCATIONS: List[str] = ["Mumbai", "Hyderabad"]
INDEED_COUNTRY: str = "india"
RESULTS_PER_QUERY: int = 25
QUERY_DELAY_SECONDS: float = 2.0
MAX_ALLOWED_EXPERIENCE_YEARS: float = 1.0

# The 5 Strict Tech Positions Requested
ROLE_QUERIES: Dict[str, List[str]] = {
    "Data Analytics": [
        "data analyst fresher",
        "junior data analyst",
        "data analytics trainee",
        "power bi fresher",
        "sql data analyst fresher",
    ],
    "Business Analytics": [
        "business analyst fresher",
        "junior business analyst",
        "business analytics trainee",
        "entry level business analyst",
    ],
    "Analyst": [
        "analyst fresher",
        "junior analyst",
        "operations analyst fresher",
        "research analyst fresher",
    ],
    "MIS Executive": [
        "MIS executive fresher",
        "MIS analyst fresher",
        "management information system fresher",
        "advanced excel MIS fresher",
    ],
    "Web Development & Full Stack": [
        "web developer fresher",
        "junior web developer",
        "full stack developer fresher",
        "junior full stack developer",
        "frontend developer fresher",
        "react developer fresher",
        "python developer fresher",
    ],
}

# Role-specific Fresher Compensation Benchmarks in India (Mumbai/Hyderabad)
BENCHMARKS: Dict[str, Tuple[int, int]] = {
    "Data Analytics": (350000, 500000),
    "Business Analytics": (300000, 480000),
    "Analyst": (300000, 450000),
    "MIS Executive": (240000, 360000),
    "Web Development & Full Stack": (350000, 550000),
}


# ======================================================================================
# 2. ANTI-SCAM, SENIORITY & LEVEL 2+ BLACKLISTS
# ======================================================================================

# Forbidden title keywords (indicates senior / experienced roles)
FORBIDDEN_TITLE_KEYWORDS: List[str] = [
    "senior", "sr", "lead", "leader", "principal", "architect",
    "manager", "head", "director", "vp", "vice president", "specialist",
    "chief", "staff engineer", "expert", "consultant 2", "mid-level",
    "mid level", "level 2", "level 3", "2+", "3+", "4+", "5+", "6+", "7+",
    "8+", "9+", "10+", "years experience"
]

FORBIDDEN_JOB_LEVELS: List[str] = [
    "mid_senior", "director", "executive", "associate_director"
]

# Prominent Edtech & Training Institutes posing as employers or fee consultancies
COMPANY_BLACKLIST: List[str] = [
    "internshala", "unacademy", "byjus", "byju's", "whitehat jr", "vedantu",
    "toppr", "upgrad", "upgrade", "simplilearn", "edureka", "intellipaat",
    "great learning", "scaler", "newton school", "alma better", "almabetter",
    "masai school", "coding ninjas", "geekster", "acciojob", "crio.do",
    "qspiders", "jspiders", "pyspiders", "naresh i technologies", "naresh it",
    "durga software", "durga soft", "besant technologies", "apponix",
    "ethnus", "kelly technologies", "sla consultants", "croma campus",
    "sevenmentor", "fita academy", "cetpa", "actalent training",
    "training institute", "coaching institute", "it academy",
    "learning solutions", "skills academy", "training center",
    "training centre", "finishing school", "placement guarantee",
    "job guarantee", "hire and train", "train and hire", "edtech", "edutech"
]

FORBIDDEN_DESCRIPTION_PATTERNS: List[str] = [
    "registration fee", "training fee", "security deposit",
    "pay after placement", "unpaid internship", "unpaid intern",
    "no stipend", "commission only", "earn from home data entry",
    "sms sending job", "part time form filling", "captcha typing"
]


# ======================================================================================
# 3. VERIFICATION & INTELLIGENCE FILTER ENGINE
# ======================================================================================

def parse_date_posted(date_val: Any) -> Optional[datetime]:
    """Standardizes date_posted formats into a datetime object."""
    if date_val is None:
        return None
    if isinstance(date_val, datetime):
        return date_val
    if isinstance(date_val, date):
        return datetime.combine(date_val, datetime.min.time())

    val_str = str(date_val).strip().lower()
    now = datetime.now()

    if "just posted" in val_str or "today" in val_str or "hour" in val_str:
        return now
    elif "yesterday" in val_str:
        return now - timedelta(days=1)

    days_match = re.search(r"(\d+)\s+day", val_str)
    if days_match:
        return now - timedelta(days=int(days_match.group(1)))

    weeks_match = re.search(r"(\d+)\s+week", val_str)
    if weeks_match:
        return now - timedelta(weeks=int(weeks_match.group(1)))

    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(val_str[:10], fmt)
        except (ValueError, IndexError):
            pass
    return None


def is_within_hours(date_val: Any, max_hours: int = MAX_HOURS_OLD) -> Tuple[bool, str]:
    """Verifies if a job was posted strictly within the allowed hours limit (<= 48h)."""
    parsed = parse_date_posted(date_val)
    if parsed is None:
        return True, "Date missing (allowed by upstream 48h filter)"

    age_hours = (datetime.now() - parsed).total_seconds() / 3600.0
    if age_hours <= max_hours:
        return True, f"Posted {age_hours:.1f}h ago (within {max_hours}h limit)"
    return False, f"Too old: posted {age_hours:.1f}h ago (> {max_hours}h limit)"


def parse_experience_range(exp_str: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    """Extracts minimum and maximum years from experience strings."""
    if not exp_str:
        return None, None
    clean = str(exp_str).strip().lower()

    if "fresher" in clean or "entry" in clean or "intern" in clean:
        return 0.0, 0.0

    range_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)", clean)
    if range_match:
        return float(range_match.group(1)), float(range_match.group(2))

    single_match = re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:yr|year)", clean)
    if single_match:
        yr = float(single_match.group(1))
        return yr, yr
    return None, None


def is_fresher_job(
    title: Optional[str],
    experience_range: Optional[str],
    description: Optional[str] = None,
    job_level: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Strictly verifies if a job listing is purely suitable for a fresher.
    Rejects:
      - Senior / Managerial / Lead keywords
      - Roman numerals and Level 2+ identifiers (e.g. SW Engineer II, SDE 2, Analyst II)
      - Experience requirements strictly greater than 1.0 year (or ceiling > 2.0 yrs)
      - Non-fresher descriptions demanding multi-year experience
    """
    title_str = (title or "").strip().lower()
    desc_str = (description or "").strip().lower()
    level_str = (job_level or "").strip().lower()

    # 1. Metadata job level check
    for fl in FORBIDDEN_JOB_LEVELS:
        if fl in level_str:
            return False, f"Forbidden job level: {level_str}"

    # 2. Senior / Lead / Manager keyword check
    title_words = re.sub(r"[^\w\s]", " ", title_str)
    for kw in FORBIDDEN_TITLE_KEYWORDS:
        clean_kw = re.sub(r"[^\w\s]", " ", kw).strip()
        if clean_kw and re.search(r"\b" + re.escape(clean_kw) + r"\b", title_words):
            return False, f"Title contains senior keyword: '{kw}'"

    # 3. Level 2+ / Roman Numeral Blocker (Crucial for SW Engineer II, SDE 2, etc.)
    level_pattern = r"\b(ii|iii|iv|v|l2|l3|l4|level\s*[2-9])\b|\b(?:sde|swe|engineer|developer|analyst|consultant|executive|specialist)\s*[-_ ]*[2-9]\b"
    level_match = re.search(level_pattern, title_str)
    if level_match:
        return False, f"Title indicates Level 2+ / experienced role: '{level_match.group(0)}'"

    # 4. Explicit experience range from metadata
    min_exp, max_exp = parse_experience_range(experience_range)
    if min_exp is not None:
        if min_exp > MAX_ALLOWED_EXPERIENCE_YEARS:
            return False, f"Min experience required ({min_exp} yrs) exceeds fresher limit ({MAX_ALLOWED_EXPERIENCE_YEARS} yr)"
        if max_exp is not None and max_exp > 2.0:
            return False, f"Experience ceiling ({max_exp} yrs) is too high for a targeted fresher position"

    # 5. Check description for senior experience demands
    senior_desc = re.search(r"\b([2-9]|1\d)\+?\s*(?:to\s*\d+\s*)?years?(?:\s*of)?\s*experience", desc_str)
    if senior_desc:
        matched = senior_desc.group(0)
        context = desc_str[max(0, senior_desc.start() - 30) : senior_desc.end()]
        if any(w in context for w in ["candidate", "must have", "minimum", "requires", "experience in"]):
            return False, f"Description mentions experienced requirement: '{matched}'"

    # 6. Verify positive proof of fresher / entry-level qualification
    has_fresher_title = any(w in title_str for w in ["fresher", "junior", "trainee", "intern", "entry level", "entry-level", "associate", "graduate", "l1", "level 1"])
    has_fresher_exp = (min_exp is not None and min_exp <= 1.0)
    has_fresher_desc = any(w in desc_str for w in ["fresher", "0-1 year", "0 to 1 year", "fresh graduate", "entry level", "trainee", "campus hiring", "2024 passout", "2025 passout", "2026 passout", "recent graduate"])

    # Discard generic software roles without any junior/fresher marker
    if not (has_fresher_title or has_fresher_exp or has_fresher_desc):
        if any(g in title_str for g in ["sw engineer", "software engineer", "developer", "engineer"]) and not any(j in title_str for j in ["junior", "fresher", "trainee", "entry", "associate"]):
            return False, f"Generic software role without explicit fresher/junior designation: '{title}'"

    return True, "Verified fresher role"


def is_legitimate_company(company_name: Optional[str], title: Optional[str] = None, description: Optional[str] = None) -> Tuple[bool, str]:
    """Ensures the employer is not a coaching institute, training fee center, or scam."""
    company_str = (company_name or "").strip().lower()
    title_str = (title or "").strip().lower()
    desc_str = (description or "").strip().lower()

    if not company_str:
        return False, "Empty company name"

    for bl in COMPANY_BLACKLIST:
        if bl in company_str:
            return False, f"Company '{company_name}' matched blacklist: '{bl}'"

    if any(m in title_str for m in ["trainer", "faculty", "instructor", "teaching faculty", "tutor"]):
        return False, f"Title indicates training faculty rather than tech hire: '{title}'"

    for pattern in FORBIDDEN_DESCRIPTION_PATTERNS:
        if pattern in desc_str:
            return False, f"Description contains scam pattern: '{pattern}'"

    return True, "Legitimate employer"


def categorize_role(title: Optional[str], description: Optional[str] = None) -> Optional[str]:
    """
    Strictly maps the listing to one of the 5 target tracks requested.
    Returns None if the job does not belong to the 5 requested positions.
    """
    title_clean = (title or "").lower()
    text = f"{title_clean} {description or ''}".lower()

    if any(k in title_clean for k in ["data analytic", "data analyst", "power bi", "tableau", "sql analyst"]) or \
       ("data" in title_clean and "analyst" in title_clean):
        return "Data Analytics"
    elif any(k in title_clean for k in ["business analytic", "business analyst", "bi analyst"]) or \
         ("business" in title_clean and "analyst" in title_clean):
        return "Business Analytics"
    elif any(k in title_clean for k in ["mis executive", "mis analyst", "advanced excel", "reporting executive", "management information"]):
        return "MIS Executive"
    elif any(k in title_clean for k in ["full stack", "fullstack", "mern", "mean stack", "web dev", "frontend", "front-end", "front end", "react", "node", "ui developer", "python web"]):
        return "Web Development & Full Stack"
    elif "analyst" in title_clean and not any(x in title_clean for x in ["financial analyst", "equity analyst", "market research analyst", "credit analyst"]):
        return "Analyst"

    # Secondary check on full description ONLY if title is generic trainee or associate
    if any(w in title_clean for w in ["fresher", "trainee", "associate", "graduate"]):
        if "data analytic" in text or "data analyst" in text:
            return "Data Analytics"
        elif "business analyst" in text:
            return "Business Analytics"
        elif "mis" in text and "executive" in text:
            return "MIS Executive"
        elif any(k in text for k in ["web dev", "full stack", "frontend", "mern"]):
            return "Web Development & Full Stack"
        elif "analyst" in text:
            return "Analyst"

    return None


def enrich_experience_and_salary(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enriches every job so that Experience and Salary are NEVER left blank.
    Extracts from description, and applies market benchmark if undisclosed.
    """
    title = str(job.get("title") or "")
    desc = str(job.get("description") or "")
    cat = job.get("tech_category") or categorize_role(title, desc) or "Analyst"

    # 1. Experience Enrichment
    exp = job.get("experience_range")
    if not exp or str(exp).strip().lower() in ("none", "nan", ""):
        exp_match = re.search(r"\b([0-2])\s*(?:-|to)\s*([1-2])\s*(?:years?|yrs?)\b", desc, re.I)
        if exp_match:
            exp = f"{exp_match.group(1)}-{exp_match.group(2)} Yrs"
        elif any(w in (title + " " + desc).lower() for w in ["fresher", "entry level", "trainee", "intern"]):
            exp = "0-1 Yrs (Fresher)"
        else:
            exp = "0-1 Yrs (Entry Level)"
    job["experience_range"] = str(exp).strip()

    # 2. Salary Enrichment
    min_sal = job.get("min_amount")
    max_sal = job.get("max_amount")

    has_valid_salary = False
    try:
        if min_sal is not None and not (isinstance(min_sal, float) and (math.isnan(min_sal) or min_sal == 0)):
            has_valid_salary = True
    except Exception:
        pass

    if not has_valid_salary:
        lpa_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(?:lpa|lacs?|lakhs?)", desc, re.I)
        if lpa_match:
            min_sal = int(float(lpa_match.group(1)) * 100000)
            max_sal = int(float(lpa_match.group(2)) * 100000)
            job["salary_source_type"] = "Extracted from JD"
        else:
            month_match = re.search(r"(?:₹|rs\.?)\s*(\d{2,3}(?:,\d{3})*)\s*(?:-|to)\s*(?:₹|rs\.?)?\s*(\d{2,3}(?:,\d{3})*)\s*(?:per\s*month|/month|pm)\b", desc, re.I)
            if month_match:
                min_sal = int(month_match.group(1).replace(",", "")) * 12
                max_sal = int(month_match.group(2).replace(",", "")) * 12
                job["salary_source_type"] = "Extracted from Monthly JD"
            else:
                b_min, b_max = BENCHMARKS.get(cat, (300000, 450000))
                min_sal = b_min
                max_sal = b_max
                job["salary_source_type"] = "Market Benchmark (Undisclosed)"

    job["min_amount"] = min_sal
    job["max_amount"] = max_sal
    job["salary_display"] = f"₹{int(min_sal):,} - ₹{int(max_sal):,}" if min_sal and max_sal else "Not Disclosed"
    return job


def evaluate_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """Runs the complete verification filter pipeline on a single job record."""
    title = job.get("title")
    company = job.get("company")
    date_posted = job.get("date_posted")
    experience = job.get("experience_range")
    desc = job.get("description")
    level = job.get("job_level")

    within_48h, date_reason = is_within_hours(date_posted, MAX_HOURS_OLD)
    fresher_ok, exp_reason = is_fresher_job(title, experience, desc, level)
    legit_ok, legit_reason = is_legitimate_company(company, title, desc)

    is_valid = within_48h and fresher_ok and legit_ok
    rejection_reasons = []

    if not within_48h:
        rejection_reasons.append(date_reason)
    if not fresher_ok:
        rejection_reasons.append(exp_reason)
    if not legit_ok:
        rejection_reasons.append(legit_reason)

    category = categorize_role(title, desc)
    if not category:
        is_valid = False
        rejection_reasons.append("Role does not match any of the 5 target categories (Data Analytics, Business Analytics, Analyst, MIS Executive, Web Dev/Full Stack)")
        category = "Unmatched Tech Role"

    job["tech_category"] = category
    job = enrich_experience_and_salary(job)

    # Compute a quality confidence score (0-100)
    score = 60
    if job.get("min_amount") or job.get("max_amount"):
        score += 15
    if job.get("job_url_direct") or (job.get("job_url") and "http" in str(job.get("job_url"))):
        score += 10
    if job.get("emails"):
        score += 15
    score = min(score, 100)

    job["is_valid_fresher_job"] = is_valid
    job["rejection_reason"] = " | ".join(rejection_reasons) if rejection_reasons else "None"
    job["quality_score"] = score if is_valid else 0

    return job


# ======================================================================================
# 4. SCRAPING ENGINE (JOBSPY INTEGRATION)
# ======================================================================================

def sanitize_for_json(obj: Any) -> Any:
    """Recursively replaces NaN/Inf with None and formats dates into ISO strings."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    return obj


def clean_composite_key(val: Any) -> str:
    """Normalizes string for deduplication key."""
    if not val:
        return ""
    return "".join(c.lower() for c in str(val) if c.isalnum() or c.isspace()).strip()


def run_scraping_query(
    search_term: str,
    location: str,
    sites: List[str] = TARGET_SITES,
    hours_old: int = MAX_HOURS_OLD,
    results_wanted: int = RESULTS_PER_QUERY,
    proxies: Optional[List[str]] = None,
):
    """Executes a single scrape_jobs call across target boards with error isolation."""
    from jobspy import scrape_jobs
    import pandas as pd

    logger.info(f"Scraping -> Query: '{search_term}' | Location: '{location}' | Sites: {sites} | Hours: {hours_old}")
    # Isolate boards: JobSpy's multi-board call can fail as a whole when one
    # adapter errors, silently losing results from every requested board.
    frames = []
    for site in sites:
        try:
            df = scrape_jobs(
                site_name=[site],
                search_term=search_term,
                location=location,
                results_wanted=results_wanted,
                hours_old=hours_old,
                country_indeed=INDEED_COUNTRY,
                proxies=proxies,
                fetch_description=True,
                verbose=0,
            )
            logger.info("Fetched %s raw listings from %s for '%s' in '%s'", len(df), site, search_term, location)
            if not df.empty:
                frames.append(df)
        except Exception as e:
            logger.warning("Error scraping %s for query '%s' in '%s': %s", site, search_term, location, e)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def scrape_all_fresher_jobs(
    locations: Optional[List[str]] = None,
    roles_dict: Optional[Dict[str, List[str]]] = None,
    sites: Optional[List[str]] = None,
    hours_old: int = MAX_HOURS_OLD,
    results_per_query: int = RESULTS_PER_QUERY,
    proxies: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Main orchestration loop. Iterates through the 5 categories across cities,
    fetches raw jobs, deduplicates, and filters for verified freshers.
    """
    import pandas as pd
    target_locations = locations or DEFAULT_LOCATIONS
    target_roles = roles_dict or ROLE_QUERIES
    target_sites = sites or TARGET_SITES

    all_raw_jobs: List[Dict[str, Any]] = []
    seen_urls = set()
    seen_composite_keys = set()

    start_time = time.time()
    query_count = 0

    for role_category, queries in target_roles.items():
        logger.info(f"\n==================== Category: {role_category} ====================")
        for search_query in queries:
            for loc in target_locations:
                query_count += 1
                df = run_scraping_query(
                    search_term=search_query,
                    location=loc,
                    sites=target_sites,
                    hours_old=hours_old,
                    results_wanted=results_per_query,
                    proxies=proxies,
                )
                if not df.empty:
                    all_raw_jobs.extend(df.to_dict(orient="records"))
                time.sleep(QUERY_DELAY_SECONDS)

    total_scraped = len(all_raw_jobs)
    logger.info(f"\nTotal raw jobs pulled across all queries: {total_scraped}")

    valid_jobs: List[Dict[str, Any]] = []
    rejected_jobs: List[Dict[str, Any]] = []

    for raw_job in all_raw_jobs:
        # 1. URL Deduplication
        job_url = raw_job.get("job_url_direct") or raw_job.get("job_url") or ""
        if job_url and job_url in seen_urls:
            continue
        if job_url:
            seen_urls.add(job_url)

        # 2. Composite Key Deduplication
        comp_key = f"{clean_composite_key(raw_job.get('title'))}_{clean_composite_key(raw_job.get('company'))}_{clean_composite_key(raw_job.get('location'))}"
        if comp_key in seen_composite_keys:
            continue
        seen_composite_keys.add(comp_key)

        # 3. Evaluate Criteria (48h, fresher only, anti-scam, 5 roles)
        evaluated = evaluate_job(raw_job)
        if evaluated["is_valid_fresher_job"]:
            valid_jobs.append(evaluated)
        else:
            rejected_jobs.append(evaluated)

    elapsed = time.time() - start_time
    stats = {
        "duration_seconds": round(elapsed, 2),
        "total_queries_executed": query_count,
        "total_raw_scraped": total_scraped,
        "total_unique_jobs": len(valid_jobs) + len(rejected_jobs),
        "valid_fresher_jobs": len(valid_jobs),
        "rejected_jobs_count": len(rejected_jobs),
        "by_site": {},
        "by_category": {},
        "by_location": {},
    }

    for j in valid_jobs:
        site = j.get("site", "unknown")
        stats["by_site"][site] = stats["by_site"].get(site, 0) + 1
        cat = j.get("tech_category", "unknown")
        stats["by_category"][cat] = stats["by_category"].get(cat, 0) + 1
        loc = str(j.get("location", "unknown")).split(",")[0].strip()
        stats["by_location"][loc] = stats["by_location"].get(loc, 0) + 1

    return {
        "valid_jobs": valid_jobs,
        "rejected_jobs": rejected_jobs,
        "stats": stats,
    }


# ======================================================================================
# 5. MULTI-FORMAT EXPORTERS (EXCEL, JSON, CSV)
# ======================================================================================

def export_to_excel(
    df_valid,
    rejected_jobs: list,
    stats: dict,
    excel_path: str,
) -> bool:
    """Exports a formatted 3-tab Excel workbook with clickable direct apply URLs."""
    import pandas as pd
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        wb = Workbook()

        # Tab 1: Verified Fresher Jobs
        ws_jobs = wb.active
        ws_jobs.title = "Verified Fresher Jobs"
        ws_jobs.views.sheetView[0].showGridLines = True

        header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        zebra_fill = PatternFill(start_color="F2F5F9", end_color="F2F5F9", fill_type="solid")
        thin_border = Border(
            left=Side(style="thin", color="D9D9D9"), right=Side(style="thin", color="D9D9D9"),
            top=Side(style="thin", color="D9D9D9"), bottom=Side(style="thin", color="D9D9D9")
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
            "min_amount": "Min Salary",
            "max_amount": "Max Salary",
            "salary_display": "Salary Range",
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
            row_values = ["" if pd.isna(row_data[c]) or row_data[c] is None else str(row_data[c]) for c in cols_to_write]
            ws_jobs.append(row_values)
            is_even = (row_idx % 2 == 0)
            for col_idx in range(1, len(cols_to_write) + 1):
                cell = ws_jobs.cell(row=row_idx, column=col_idx)
                cell.border = thin_border
                cell.alignment = Alignment(vertical="center")
                if is_even:
                    cell.fill = zebra_fill
                if "URL" in headers[col_idx - 1] and cell.value and cell.value.startswith("http"):
                    cell.hyperlink = cell.value
                    cell.font = link_font
            ws_jobs.row_dimensions[row_idx].height = 20

        ws_jobs.freeze_panes = "A2"
        for col in ws_jobs.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws_jobs.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 45)

        # Tab 2: Run Summary
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

        # Tab 3: Rejected Jobs Audit
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
                    rj.get("site", ""), rj.get("title", ""), rj.get("company", ""),
                    rj.get("location", ""), str(rj.get("date_posted", "")),
                    rj.get("experience_range", ""), rj.get("rejection_reason", ""),
                    rj.get("job_url_direct") or rj.get("job_url") or "",
                ])
                for col_idx in range(1, len(rej_headers) + 1):
                    cell = ws_rejected.cell(row=row_idx, column=col_idx)
                    cell.border = thin_border
                    cell.alignment = Alignment(vertical="center")

            ws_rejected.freeze_panes = "A2"

        wb.save(excel_path)
        return True
    except PermissionError:
        print(f"[*] Notice: Could not overwrite '{os.path.basename(excel_path)}' because it is currently open in Excel. Close Excel to refresh it.")
        return False
    except Exception as e:
        print(f"[!] Warning: Could not generate formatted Excel sheet: {e}")
        return False


def save_pipeline_outputs(valid_jobs: list, rejected_jobs: list, stats: dict) -> Tuple[str, str, str]:
    """Saves all outputs: Excel, CSV, and sanitized JSON."""
    import pandas as pd
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    df_valid = pd.DataFrame(valid_jobs) if valid_jobs else pd.DataFrame()

    csv_path = os.path.join(OUTPUT_DIR, f"fresher_jobs_{timestamp}.csv")
    json_path = os.path.join(OUTPUT_DIR, f"fresher_jobs_{timestamp}.json")
    xlsx_path = os.path.join(OUTPUT_DIR, f"fresher_jobs_{timestamp}.xlsx")

    latest_csv = os.path.join(OUTPUT_DIR, "fresher_jobs_latest.csv")
    latest_json = os.path.join(OUTPUT_DIR, "fresher_jobs_latest.json")
    latest_xlsx = os.path.join(OUTPUT_DIR, "fresher_jobs_latest.xlsx")

    if not df_valid.empty:
        df_valid.to_csv(csv_path, index=False, encoding="utf-8-sig")
        df_valid.to_csv(latest_csv, index=False, encoding="utf-8-sig")

        clean_valid = sanitize_for_json(valid_jobs)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(clean_valid, f, indent=2, default=str)
        with open(latest_json, "w", encoding="utf-8") as f:
            json.dump(clean_valid, f, indent=2, default=str)

        export_to_excel(df_valid, rejected_jobs, stats, xlsx_path)
        export_to_excel(df_valid, rejected_jobs, stats, latest_xlsx)

    if rejected_jobs:
        rejected_json = os.path.join(OUTPUT_DIR, "rejected_jobs_latest.json")
        with open(rejected_json, "w", encoding="utf-8") as f:
            json.dump(sanitize_for_json(rejected_jobs), f, indent=2, default=str)

    return latest_xlsx, latest_csv, latest_json


# ======================================================================================
# 6. BUILT-IN GOOGLE SHEETS & TELEGRAM NOTIFIER
# ======================================================================================

def sync_to_google_sheets(valid_jobs: list, spreadsheet_id: Optional[str] = None) -> bool:
    """Directly appends/updates verified jobs to Google Sheets if credentials.json is present."""
    creds_file = os.path.join(BASE_DIR, "credentials.json")
    if not os.path.exists(creds_file):
        return False
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_file(creds_file, scopes=scopes)
        client = gspread.authorize(creds)
        
        sheet_id = spreadsheet_id or os.environ.get("GOOGLE_SPREADSHEET_ID")
        if not sheet_id:
            return False
            
        sh = client.open_by_key(sheet_id)
        try:
            ws = sh.worksheet("Verified Fresher Jobs")
        except Exception:
            ws = sh.sheet1

        existing_urls = set(ws.col_values(9)) if ws.row_count > 1 else set()
        new_rows = []
        for j in valid_jobs:
            url = j.get("job_url_direct") or j.get("job_url") or ""
            if url and url not in existing_urls:
                new_rows.append([
                    j.get("title", ""), j.get("company", ""), j.get("location", ""),
                    j.get("tech_category", ""), j.get("date_posted", ""), j.get("experience_range", ""),
                    j.get("min_amount", ""), j.get("max_amount", ""), url,
                    j.get("site", ""), j.get("quality_score", 85), datetime.now().isoformat()
                ])
                existing_urls.add(url)
        if new_rows:
            ws.append_rows(new_rows)
            print(f"[+] Google Sheets: Synced {len(new_rows)} new unique rows!")
        return True
    except Exception as e:
        print(f"[!] Google Sheets Sync note: {e}")
        return False


def send_telegram_alert(valid_jobs: list, bot_token: Optional[str] = None, chat_id: Optional[str] = None) -> bool:
    """Broadcasts a formatted job alert to Telegram channel or admin chat."""
    import requests
    token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
    cid = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not cid or not valid_jobs:
        return False

    text = f"🚀 *FRESHER JOB ALERT ({len(valid_jobs)} New Jobs)*\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for i, j in enumerate(valid_jobs[:6], 1):
        url = j.get("job_url_direct") or j.get("job_url")
        text += f"{i}. *{j.get('title')}* @ {j.get('company')}\n"
        text += f"   📍 {j.get('location')} | 💰 {j.get('salary_display', '3-5 LPA')}\n"
        text += f"   🔗 [Apply Here]({url})\n\n"
    text += f"⏰ *Posted:* Last 48h | 🎯 *Role:* Mumbai & Hyderabad\n"

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": cid, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True},
            timeout=10
        )
        return resp.status_code == 200
    except Exception:
        return False


# ======================================================================================
# 7. EXECUTION MODES: CLI, SCHEDULER, FASTAPI SERVER, TEST SUITE
# ======================================================================================

def run_pipeline(quick: bool = False, hours: int = MAX_HOURS_OLD, limit: int = RESULTS_PER_QUERY):
    """Executes one complete scraping and export pipeline cycle."""
    selected_roles = ROLE_QUERIES
    res_limit = limit
    if quick:
        print("\n[*] Running in QUICK test mode (1 query per role, limit=5)")
        selected_roles = {k: [v[0]] for k, v in selected_roles.items()}
        res_limit = 5

    print("\n" + "=" * 70)
    print(" 🚀 FRESHER JOB INTELLIGENCE ENGINE (ALL-IN-ONE PIPELINE)")
    print("=" * 70)
    print(f" • Freshness Window:   Last {hours} hours strictly")
    print(f" • Target Cities:      {', '.join(DEFAULT_LOCATIONS)}")
    print(f" • Target Sites:       {', '.join(TARGET_SITES)}")
    print(f" • Tech Tracks:        {', '.join(selected_roles.keys())}")
    print(f" • Level 2+ Blocker:   Active (Rejects 'II', 'III', 'SDE 2', 'Engineer 2')")
    print("=" * 70 + "\n")

    results = scrape_all_fresher_jobs(
        hours_old=hours,
        results_per_query=res_limit,
        roles_dict=selected_roles
    )

    valid_jobs = results["valid_jobs"]
    rejected_jobs = results["rejected_jobs"]
    stats = results["stats"]

    latest_xlsx, latest_csv, latest_json = save_pipeline_outputs(valid_jobs, rejected_jobs, stats)

    # Print Summary
    print("\n" + "=" * 70)
    print(" 📊 SCRAPING RUN SUMMARY")
    print("=" * 70)
    print(f" Total Duration:           {stats['duration_seconds']} seconds")
    print(f" Total Raw Listings:       {stats['total_raw_scraped']}")
    print(f" Unique Jobs Deduplicated:  {stats['total_unique_jobs']}")
    print(f" ✅ Verified Fresher Jobs:  {stats['valid_fresher_jobs']}")
    print(f" ❌ Rejected (Filtered):   {stats['rejected_jobs_count']}")

    print("\n Breakdown by Platform:")
    for site, count in stats["by_site"].items():
        print(f"   • {site.capitalize()}: {count}")

    print("\n Breakdown by Role Category:")
    for cat, count in stats["by_category"].items():
        print(f"   • {cat}: {count}")

    print("=" * 70)

    if valid_jobs:
        print(f"\n[+] Saved {len(valid_jobs)} verified fresher jobs to:")
        print(f"    - Excel: {latest_xlsx}")
        print(f"    - CSV:   {latest_csv}")
        print(f"    - JSON:  {latest_json}")
        sync_to_google_sheets(valid_jobs)
        send_telegram_alert(valid_jobs)
    else:
        print("\n[!] No jobs passed the strict criteria in this cycle.")

    return valid_jobs


def start_api_server():
    """Starts the built-in FastAPI server for n8n or external webhook integration."""
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    import uvicorn

    app = FastAPI(title="Fresher Job Scraper API", version="1.0.0")

    @app.get("/")
    def home():
        return {
            "status": "online",
            "endpoints": {
                "/jobs": "Get the latest verified fresher jobs instantly",
                "/scrape": "Trigger a live scraping run across Naukri, LinkedIn, Indeed"
            }
        }

    @app.get("/jobs")
    def get_jobs():
        latest_json = os.path.join(OUTPUT_DIR, "fresher_jobs_latest.json")
        if os.path.exists(latest_json):
            with open(latest_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                return JSONResponse(content={"status": "success", "count": len(data), "jobs": sanitize_for_json(data)})
        return JSONResponse(content={"status": "empty", "count": 0, "jobs": []})

    @app.get("/scrape")
    def trigger_scrape(quick: bool = False, hours: int = 48, limit: int = 15):
        valid = run_pipeline(quick=quick, hours=hours, limit=limit)
        clean = sanitize_for_json(valid)
        return JSONResponse(content={"status": "success", "count": len(clean), "jobs": clean})

    print("\n" + "=" * 60)
    print(" 🚀 Scraper API Server running on http://127.0.0.1:8000")
    print(" For n8n (Docker), use URL: http://host.docker.internal:8000/jobs")
    print("=" * 60 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)


def run_recurring_scheduler(interval_minutes: int, quick: bool = False):
    """Runs the pipeline on an automated recurring timer loop."""
    print(f"\n[+] Recurring Scheduler Active: Running every {interval_minutes} minutes ({interval_minutes/60:.1f} hours).")
    print("[+] Press Ctrl + C to exit at any time.\n")
    try:
        while True:
            print(f"\n--- [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Triggering Pipeline ---")
            run_pipeline(quick=quick)
            print(f"\n--- Sleeping for {interval_minutes} minutes until next cycle ---")
            time.sleep(interval_minutes * 60)
    except KeyboardInterrupt:
        print("\n[*] Scheduler stopped by user.")


def run_unit_tests():
    """Self-contained test suite ensuring 100% of rules pass."""
    print("\nRunning Master Pipeline Verification Tests...")
    
    # 1. Experience & Level 2+ Tests
    assert is_fresher_job("Data Analyst", "0-1 Yrs")[0] is True
    assert is_fresher_job("SW Engineer II", None)[0] is False
    assert is_fresher_job("SDE 2", None)[0] is False
    assert is_fresher_job("Data Analyst II", None)[0] is False
    assert is_fresher_job("Senior Data Analyst", "0-1 Yrs")[0] is False
    assert is_fresher_job("Data Analyst", "3-4 Yrs")[0] is False
    print(" [OK] Experience & Level 2+ rejection tests passed")

    # 2. Company Blacklist Tests
    assert is_legitimate_company("Qspiders Technologies")[0] is False
    assert is_legitimate_company("Naresh I Technologies")[0] is False
    assert is_legitimate_company("Tata Consultancy Services")[0] is True
    print(" [OK] Training institute blacklist tests passed")

    # 3. 48-Hour Freshness Tests
    now = datetime.now()
    assert is_within_hours(now, 48)[0] is True
    assert is_within_hours(now - timedelta(hours=24), 48)[0] is True
    assert is_within_hours(now - timedelta(hours=96), 48)[0] is False
    print(" [OK] 48-hour date freshness tests passed")

    # 4. Role Categorization Tests
    assert categorize_role("Data Analyst Fresher") == "Data Analytics"
    assert categorize_role("Junior Business Analyst") == "Business Analytics"
    assert categorize_role("MIS Executive - Advanced Excel") == "MIS Executive"
    assert categorize_role("Full Stack Developer (MERN)") == "Web Development & Full Stack"
    assert categorize_role("SW Engineer II") is None
    print(" [OK] Role categorization & non-target rejection tests passed")

    print("\nALL VERIFICATION TESTS PASSED SUCCESSFULLY!\n")


# ======================================================================================
# 8. MASTER CLI ENTRYPOINT
# ======================================================================================

def send_to_n8n_webhook(valid_jobs: list, webhook_url: str) -> bool:
    """Sends clean, verified fresher jobs directly to an n8n Cloud Webhook node."""
    import requests
    if not webhook_url or not valid_jobs:
        return False
    try:
        clean_jobs = sanitize_for_json(valid_jobs)
        payload = json.dumps(
            {"jobs": clean_jobs, "count": len(clean_jobs), "timestamp": datetime.now().isoformat()},
            default=str
        )
        resp = requests.post(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        if resp.status_code in (200, 201):
            print(f"[+] n8n Cloud: Successfully posted {len(clean_jobs)} jobs to webhook!")
            return True
        else:
            print(f"[!] n8n Cloud Webhook returned status code: {resp.status_code} ({resp.text[:200]})")
            return False
    except Exception as e:
        print(f"[!] n8n Cloud Webhook error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Fresher Job Intelligence & Placement Engine (All-In-One Master Script)"
    )
    parser.add_argument("--quick", action="store_true", help="Run in fast smoke-test mode (1 query per role, limit=5)")
    parser.add_argument("--hours", type=int, default=MAX_HOURS_OLD, help=f"Max job age in hours (default: {MAX_HOURS_OLD})")
    parser.add_argument("--limit", type=int, default=RESULTS_PER_QUERY, help=f"Results per search query (default: {RESULTS_PER_QUERY})")
    parser.add_argument("--interval", type=int, default=None, help="Recurring interval in minutes (e.g. --interval 120 for every 2 hours)")
    parser.add_argument("--serve", action="store_true", help="Start FastAPI local REST server on port 8000 for n8n")
    parser.add_argument("--test", action="store_true", help="Run self-contained verification test suite")
    parser.add_argument("--webhook", type=str, default=None, help="n8n Cloud Webhook URL to push clean jobs directly into n8n Cloud")

    args = parser.parse_args()

    if args.test:
        run_unit_tests()
    elif args.serve:
        start_api_server()
    elif args.interval:
        run_recurring_scheduler(args.interval, quick=args.quick)
    else:
        valid_jobs = run_pipeline(quick=args.quick, hours=args.hours, limit=args.limit)
        if args.webhook:
            send_to_n8n_webhook(valid_jobs, args.webhook)


if __name__ == "__main__":
    main()

