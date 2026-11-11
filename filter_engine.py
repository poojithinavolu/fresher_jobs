"""
Filter Engine for Fresher Job Listings
======================================
Strict verification pipeline that ensures:
1. Freshness: Posted strictly within the last 48 hours.
2. Experience: Strictly for freshers (0 to 1 year max, rejecting all senior/experienced roles).
3. Legitimacy: Excludes training institutes, scam consultancies, and unpaid schemes.
4. Categorization: Maps each job to one of the 5 requested tracks.
"""

import math
import re
from datetime import datetime, date, timedelta
from typing import Tuple, Optional, Dict, Any

from config import (
    MAX_HOURS_OLD,
    MAX_ALLOWED_EXPERIENCE_YEARS,
    FORBIDDEN_TITLE_KEYWORDS,
    FORBIDDEN_JOB_LEVELS,
    COMPANY_BLACKLIST,
    FORBIDDEN_DESCRIPTION_PATTERNS,
)


def _text(value: Any) -> str:
    """Normalize JobSpy's nullable/NaN fields to safe strings."""
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "nat"} else text


def parse_date_posted(date_val: Any) -> Optional[datetime]:
    """
    Parses various date_posted formats from LinkedIn, Indeed, and Naukri
    into a standardized Python datetime object.
    """
    if date_val is None:
        return None

    if isinstance(date_val, datetime):
        return date_val

    if isinstance(date_val, date):
        return datetime.combine(date_val, datetime.min.time())

    val_str = str(date_val).strip().lower()
    now = datetime.now()

    # Relative date patterns
    if "just posted" in val_str or "today" in val_str or "hour" in val_str:
        return now
    elif "yesterday" in val_str:
        return now - timedelta(days=1)

    # e.g. "1 day ago", "2 days ago"
    days_match = re.search(r"(\d+)\s+day", val_str)
    if days_match:
        days = int(days_match.group(1))
        return now - timedelta(days=days)

    # e.g. "1 week ago"
    weeks_match = re.search(r"(\d+)\s+week", val_str)
    if weeks_match:
        weeks = int(weeks_match.group(1))
        return now - timedelta(weeks=weeks)

    # Standard ISO formats: YYYY-MM-DD
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(val_str[:10], fmt)
        except (ValueError, IndexError):
            pass

    return None


def is_within_hours(date_val: Any, max_hours: int = MAX_HOURS_OLD) -> Tuple[bool, str]:
    """
    Verifies if a job was posted within the allowed hours limit (default: 48h).
    """
    parsed_date = parse_date_posted(date_val)
    if parsed_date is None:
        return False, "Posting date unavailable; cannot verify freshness"

    age_hours = (datetime.now() - parsed_date).total_seconds() / 3600.0

    if age_hours <= max_hours:
        return True, f"Posted {age_hours:.1f}h ago (within {max_hours}h limit)"
    else:
        return False, f"Too old: posted {age_hours:.1f}h ago (> {max_hours}h limit)"


def parse_experience_range(exp_str: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    """
    Extracts min and max years from experience strings.
    Examples:
      - '0-1 Yrs' -> (0.0, 1.0)
      - '0-2 Yrs' -> (0.0, 2.0)
      - '3-4 Yrs' -> (3.0, 4.0)
      - '7-12 Yrs' -> (7.0, 12.0)
      - 'Fresher' -> (0.0, 0.0)
    """
    if not exp_str:
        return None, None

    exp_clean = str(exp_str).strip().lower()

    if "fresher" in exp_clean:
        return 0.0, 0.0
    # Match 'X - Y yrs' or 'X to Y years'
    range_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)", exp_clean)
    if range_match:
        min_yr = float(range_match.group(1))
        max_yr = float(range_match.group(2))
        if re.search(r"months?|mos?\b", exp_clean[range_match.end():]):
            min_yr /= 12
            max_yr /= 12
        return min_yr, max_yr

    months = re.search(r"(\d+(?:\.\d+)?)\s*(?:months?|mos?)\b", exp_clean)
    if months:
        years = float(months.group(1)) / 12
        return years, years

    # Match 'X+ yrs' or 'X yrs'
    single_match = re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:yr|year)", exp_clean)
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
    Strictly verifies if a job listing is suitable for a fresher.
    Rejects experienced, mid-level, lead, senior, and managerial roles.
    """
    title_str = _text(title).lower()
    desc_str = _text(description).lower()
    level_str = _text(job_level).lower()

    # 1. Check metadata job level
    if re.search(r"\bintern(?:ship)?\b", title_str):
        return False, "Internship role excluded"
    for forbidden_level in FORBIDDEN_JOB_LEVELS:
        if forbidden_level in level_str:
            return False, f"Forbidden job level: {level_str}"

    # 2. Check title for senior/lead/manager keywords
    title_words = re.sub(r"[^\w\s]", " ", title_str)
    for keyword in FORBIDDEN_TITLE_KEYWORDS:
        clean_kw = re.sub(r"[^\w\s]", " ", keyword).strip()
        if not clean_kw:
            continue
        pattern = r"\b" + re.escape(clean_kw) + r"\b"
        if re.search(pattern, title_words):
            return False, f"Title contains senior/non-fresher keyword: '{keyword}'"

    # 3. Check for Roman numerals or level numbers indicating experienced roles
    # e.g. "SW Engineer II", "SDE 2", "Developer III", "Analyst L2", "Level 2"
    level_pattern = r"\b(ii|iii|iv|v|l2|l3|l4|level\s*[2-9])\b|\b(?:sde|swe|engineer|developer|analyst|consultant|executive|specialist)\s*[-_ ]*[2-9]\b"
    level_match = re.search(level_pattern, title_str)
    if level_match:
        return False, f"Title indicates Level 2+ / experienced role: '{level_match.group(0)}'"

    # 4. Check board metadata and the JD before allowing the listing through.
    # Experience is frequently missing in board cards, so validate descriptions too.
    exp_text = str(experience_range or "")
    if not exp_text.strip() or exp_text.lower() in {"nan", "none"}:
        found = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(years?|yrs?|months?|mos?)\b", desc_str)
        if found:
            exp_text = f"{found.group(1)}-{found.group(2)} {found.group(3)}"
        else:
            found = re.search(r"\b(\d+(?:\.\d+)?)\s*(years?|yrs?|months?|mos?)\s+(?:of\s+)?experience\b", desc_str)
            if found:
                exp_text = f"{found.group(1)} {found.group(2)}"
    min_exp, max_exp = parse_experience_range(exp_text)
    if min_exp is not None:
        if min_exp > MAX_ALLOWED_EXPERIENCE_YEARS:
            return False, f"Minimum experience required ({min_exp} yrs) exceeds fresher limit ({MAX_ALLOWED_EXPERIENCE_YEARS} yr)"
        # If upper bound of experience is too high (e.g. 0-5 Yrs, 0-7 Yrs), it's not a pure fresher role
        if max_exp is not None and max_exp > MAX_ALLOWED_EXPERIENCE_YEARS:
            return False, f"Maximum experience ({max_exp} yrs) exceeds {MAX_ALLOWED_EXPERIENCE_YEARS} yr limit"
    else:
        return False, "Experience requirement missing; cannot verify six-month maximum"

    # 5. Check description for senior experience demands
    senior_desc_match = re.search(r"\b([2-9]|1\d)\+?\s*(?:to\s*\d+\s*)?years?(?:\s*of)?\s*experience", desc_str)
    if senior_desc_match:
        matched_text = senior_desc_match.group(0)
        if any(w in desc_str[max(0, senior_desc_match.start() - 30) : senior_desc_match.end()] for w in ["candidate", "must have", "minimum", "requires", "experience in"]):
            return False, f"Description mentions experienced candidate requirement: '{matched_text}'"

    if re.search(r"\b(?:internship|project)\s+(?:experience|letter|certificate)\b|\bproject\s+experience\b|\btraining\s+(?:experience|certificate|letter)\b|\b(?:training|project)\s+completion\s+(?:letter|certificate)\b", desc_str):
        return False, "Internship/project/training experience or documentation requirement"

    # 6. VERIFY POSITIVE PROOF OF FRESHER / ENTRY-LEVEL QUALIFICATION
    # Never guess! If the listing has no experience metadata, it MUST have a fresher/junior marker in title or JD
    has_fresher_title = any(w in title_str for w in ["fresher", "junior", "trainee", "intern", "entry level", "entry-level", "associate", "graduate", "l1", "level 1"])
    has_fresher_exp = min_exp is not None and min_exp <= 1.0
    has_fresher_desc = any(w in desc_str for w in ["fresher", "0-1 year", "0 to 1 year", "fresh graduate", "entry level", "trainee", "campus hiring", "2024 passout", "2025 passout", "2026 passout", "recent graduate"])

    # If title is a pure entry-level track (like "Web Developer", "Data Analyst") without senior markers,
    # but has no description and no experience tag, check if it's explicitly fresher or ambiguous
    if not (has_fresher_title or has_fresher_exp or has_fresher_desc):
        # If it's a generic title like "SW Engineer" or "Software Engineer" without "Junior/Fresher", reject it!
        if any(g in title_str for g in ["sw engineer", "software engineer", "developer", "engineer"]) and not any(j in title_str for j in ["junior", "fresher", "trainee", "entry", "associate"]):
            return False, f"Generic software role without explicit fresher/junior designation: '{title}'"

    return True, "Verified fresher role"


def is_legitimate_company(
    company_name: Optional[str],
    title: Optional[str] = None,
    description: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Ensures the employer is not a blacklisted training institute,
    deceptive coaching center, or unpaid scam scheme.
    """
    company_str = _text(company_name).lower()
    title_str = _text(title).lower()
    desc_str = _text(description).lower()

    if not company_str:
        return False, "Empty company name"

    # 1. Check company name against blacklist
    for blacklisted in COMPANY_BLACKLIST:
        if blacklisted in company_str:
            return False, f"Company '{company_name}' matched blacklist: '{blacklisted}'"

    # 2. Check for training/coaching markers in title
    if any(m in title_str for m in ["trainer", "faculty", "instructor", "teaching faculty", "tutor"]):
        return False, f"Title indicates training staff rather than tech role: '{title}'"

    # 3. Check description for scam patterns (fees, unpaid, deposit)
    for pattern in FORBIDDEN_DESCRIPTION_PATTERNS:
        if pattern in desc_str:
            return False, f"Description contains scam pattern: '{pattern}'"

    return True, "Legitimate employer"


def categorize_role(title: Optional[str], description: Optional[str] = None) -> Optional[str]:
    """
    Strictly maps the job title/description to one of the 5 target tracks requested.
    Returns None if the job is not in the 5 requested positions.
    """
    title_clean = _text(title).lower()
    text = f"{title_clean} {_text(description)}".lower()

    if "marketing" in title_clean and "analyst" in title_clean:
        return "Marketing Analyst"
    elif any(k in title_clean for k in ["human resources analyst", "hr analyst", "people analyst"]):
        return "HR Analyst"
    elif any(k in title_clean for k in ["data analytic", "data analyst", "power bi", "tableau", "sql analyst"]) or \
       ("data" in title_clean and "analyst" in title_clean):
        return "Data Analyst"
    elif any(k in title_clean for k in ["business analytic", "business analyst", "bi analyst"]) or \
         ("business" in title_clean and "analyst" in title_clean):
        return "Business Analyst"
    elif any(k in title_clean for k in ["full stack", "fullstack", "mern", "mean stack", "web dev", "frontend", "front-end", "front end", "react", "node", "ui developer", "python web"]):
        return "Full Stack Developer" if any(k in title_clean for k in ["full stack", "fullstack", "mern", "mean stack"]) else "Web Developer"
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
    Guarantees that EVERY job has a concrete experience and salary value.
    Extracts from description text if missing from card metadata,
    and applies standard fresher market benchmarks when undisclosed.
    """
    title = _text(job.get("title"))
    desc = _text(job.get("description"))
    cat = job.get("tech_category") or categorize_role(title, desc)
    
    # -------------------------------------------------------------
    # 1. Experience Enrichment (Never Leave Blank)
    # -------------------------------------------------------------
    exp = job.get("experience_range")
    if not _text(exp):
        # Try extracting from description text
        # e.g. "0-1 years", "1 to 2 yrs", "0 - 2 yrs"
        exp_match = re.search(r"\b([0-2])\s*(?:-|to)\s*([1-2])\s*(?:years?|yrs?)\b", desc, re.I)
        if exp_match:
            exp = f"{exp_match.group(1)}-{exp_match.group(2)} Yrs"
        elif any(w in (title + " " + desc).lower() for w in ["fresher", "entry level", "trainee", "intern"]):
            exp = "Unspecified (entry-level marker only)"
        else:
            exp = "Not specified"
            
    job["experience_range"] = str(exp).strip()
    full_text = f"{title}\n{desc}"
    passouts = re.findall(r"\b(202[456]|2[456])\s*(?:passouts?|batch|graduates?)\b", full_text, re.I)
    job["eligible_passout_years"] = ", ".join(sorted({f"20{p[-2:]}" for p in passouts}))
    skill_block = re.search(r"(?:skills|required skills|technical skills|technology stack|tech stack|requirements)\s*[:\-]?\s*(.{0,600})", desc, re.I | re.S)
    job["required_skills"] = re.sub(r"\s+", " ", skill_block.group(1)).strip()[:500] if skill_block else ""
    req_exp = re.search(r"\b(?:minimum|required|at least)\s+(?:\d+\s*)?(?:months?|years?)\s+(?:of\s+)?experience\b", desc, re.I)
    no_exp = re.search(r"\b(?:no|zero)\s+(?:prior\s+)?experience\s+(?:required|needed)\b|\bfresher\b", desc, re.I)
    job["prior_experience_required"] = "Yes" if req_exp else ("No" if no_exp else "Unspecified")
    job["job_requirement"] = desc[:1200]

    # -------------------------------------------------------------
    # 2. Salary Enrichment (Never Leave Blank)
    # -------------------------------------------------------------
    min_sal = job.get("min_amount")
    max_sal = job.get("max_amount")
    
    # Both bounds must be finite positive numbers; pandas commonly supplies NaN.
    try:
        min_value = float(min_sal)
        max_value = float(max_sal)
        has_valid_salary = (
            math.isfinite(min_value)
            and math.isfinite(max_value)
            and min_value > 0
            and max_value > 0
        )
    except Exception:
        has_valid_salary = False

    if not has_valid_salary:
        # Try extracting LPA from description: "3.5 - 5 LPA", "4 to 6 Lacs", etc.
        lpa_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(?:lpa|lacs?|lakhs?)", desc, re.I)
        if lpa_match:
            min_sal = int(float(lpa_match.group(1)) * 100000)
            max_sal = int(float(lpa_match.group(2)) * 100000)
            job["salary_source_type"] = "Extracted from JD"
        else:
            # Monthly stipend / salary: "₹25,000 - ₹35,000 / month"
            month_match = re.search(r"(?:₹|rs\.?)\s*(\d{2,3}(?:,\d{3})*)\s*(?:-|to)\s*(?:₹|rs\.?)?\s*(\d{2,3}(?:,\d{3})*)\s*(?:per\s*month|/month|pm)\b", desc, re.I)
            if month_match:
                m1 = int(month_match.group(1).replace(",", "")) * 12
                m2 = int(month_match.group(2).replace(",", "")) * 12
                min_sal = m1
                max_sal = m2
                job["salary_source_type"] = "Extracted from Monthly JD"
            else:
                # Role-specific Fresher Industry Benchmarks in India (Mumbai/Hyderabad)
                BENCHMARKS = {
                    "Data Analytics": (350000, 500000),
                    "Business Analytics": (300000, 480000),
                    "Analyst": (300000, 450000),
                    "MIS Executive": (240000, 360000),
                    "Web Development & Full Stack": (350000, 550000),
                    "General Tech Fresher": (300000, 450000)
                }
                b_min, b_max = BENCHMARKS.get(cat, (300000, 450000))
                min_sal = b_min
                max_sal = b_max
                job["salary_source_type"] = "Market Benchmark (Undisclosed)"

    job["min_amount"] = min_sal
    job["max_amount"] = max_sal
    job["salary_display"] = (
        f"₹{int(float(min_sal)):,} - ₹{int(float(max_sal)):,}"
        if has_valid_salary or (min_sal and max_sal)
        else "Not Disclosed"
    )

    return job


def evaluate_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Runs the complete evaluation suite on a single job record.
    Returns the enriched job record with validation flags.
    """
    title = job.get("title")
    company = job.get("company")
    date_posted = job.get("date_posted")
    experience = job.get("experience_range")
    desc = job.get("description")
    level = job.get("job_level")

    # Run tests
    job = enrich_experience_and_salary(job)
    experience = job.get("experience_range")
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
        rejection_reasons.append("Role does not match a requested category (Business/Data/Marketing/HR Analyst, Analyst, Full Stack Developer, Web Developer)")
        category = "Unmatched Tech Role"

    job["tech_category"] = category

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
