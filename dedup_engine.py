"""Cross-Site Deduplication and Job Merging Engine
=================================================
Provides canonical normalization for companies, job titles, locations,
and apply URLs to detect and merge duplicate job postings across different
job portals (e.g. Indeed, LinkedIn, Foundit, Unstop, eLitmus, UseAstra, etc.).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

logger = logging.getLogger("dedup_engine")


def safe_str(val: Any) -> str:
    """Safely convert any value to string, handling None, NaN, and whitespace."""
    if val is None:
        return ""
    if isinstance(val, float):
        import math
        if math.isnan(val):
            return ""
    s = str(val).strip()
    return "" if s.lower() in {"nan", "none", "nat", "null"} else s


def normalize_company(company: Any) -> str:
    """
    Normalizes company names to a canonical alphanumeric form for cross-site matching.
    Removes legal suffixes (Pvt Ltd, Inc, Corp), common filler words, and punctuation.
    """
    raw = safe_str(company).lower()
    if not raw:
        return ""

    # Replace punctuation and separator characters with spaces
    cleaned = re.sub(r"[,\.\(\)\-\_\/\|\&\@\+]", " ", raw)

    # Strip company legal entities and recruitment boilerplate
    suffixes = [
        r"\bprivate limited\b", r"\bpvt ltd\b", r"\bpvt\b", r"\blimited\b", r"\bltd\b",
        r"\btechnologies\b", r"\btechnology\b", r"\bsolutions\b", r"\bservices\b",
        r"\bsoftware\b", r"\bconsulting\b", r"\bgroup\b", r"\bindia\b", r"\bcareers\b",
        r"\brecruitment\b", r"\bhiring\b", r"\binc\b", r"\bcorp\b", r"\bcorporation\b",
        r"\bllc\b", r"\bevaluation\b", r"\bventures\b", r"\binfotech\b", r"\bsystems\b",
    ]
    for pattern in suffixes:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)

    # Collapse whitespace and keep alphanumeric tokens
    tokens = [tok for tok in cleaned.split() if tok.isalnum()]
    return "".join(tokens)


def normalize_title(title: Any, company: Any = "") -> str:
    """
    Normalizes job titles for fuzzy cross-site matching by stripping recruitment noise,
    batch years, salary claims, and employer names.
    """
    raw = safe_str(title).lower()
    if not raw:
        return ""

    # Strip employer name tokens from title if company is known
    comp_norm = normalize_company(company)
    if comp_norm:
        # Match tokens >= 3 characters to avoid stripping short prepositions
        raw_comp = safe_str(company).lower()
        for tok in raw_comp.split():
            tok_clean = "".join(c for c in tok if c.isalnum())
            if len(tok_clean) >= 3:
                raw = re.sub(rf"\b{re.escape(tok_clean)}\b", " ", raw, flags=re.IGNORECASE)

    # Noise phrases commonly added by aggregators
    noise_patterns = [
        r"\boff\s+campus\s+drive\b", r"\boff\s+campus\b", r"\bcampus\s+drive\b",
        r"\brecruitment\s+202[0-9]\b", r"\bhiring\s+202[0-9]\b", r"\bcareers\s+202[0-9]\b",
        r"\brecruitment\b", r"\bhiring\b", r"\bcareers\b",
        r"\bbatch\s*202[0-9]\b", r"\b202[0-9]\s*batch\b", r"\b202[0-9]\s*passouts?\b",
        r"\b202[0-9]\b",
        r"\bapply\s+online\b", r"\bapply\s+now\b", r"\bfreshers?\s+apply\b",
        r"\bfreshers?\b",
        r"\bwalk\s*in\s*drive\b", r"\bwalk\s*in\b", r"\bimmediate\s+joiners?\b",
        r"\bmultiple\s+openings?\b", r"\bany\s+graduate\b",
        r"\brole\b", r"\bopening\b", r"\bvacancy\b", r"\bjob\b",
        r"\b0\s*[-to]+\s*[1-3]\s*years?\b", r"\b0\s*[-to]+\s*[1-3]\s*yrs?\b",
        r"\b[0-3]\s*years?\b", r"\b[0-3]\s*yrs?\b", r"\bexperience\b",
        r"\bsalary\s+up\s+to\s+[^\|–\-]+",
    ]
    for pat in noise_patterns:
        raw = re.sub(pat, " ", raw, flags=re.IGNORECASE)

    raw = re.sub(r"[\–\—\|\:\,\(\)\-\_\/]", " ", raw)
    tokens = [tok for tok in raw.split() if tok.isalnum()]
    return " ".join(tokens)


def normalize_city(loc: Any) -> str:
    """Normalizes location strings to canonical Indian tech metro names."""
    raw = safe_str(loc).lower()
    if not raw:
        return "india"

    replacements = {
        "bengaluru": "bangalore",
        "gurugram": "gurgaon",
        "bombay": "mumbai",
        "madras": "chennai",
        "calcutta": "kolkata",
        "hyderabad/secunderabad": "hyderabad",
        "new delhi": "delhi",
    }
    for old, new in replacements.items():
        raw = raw.replace(old, new)

    top_metros = [
        "bangalore", "hyderabad", "pune", "mumbai", "chennai",
        "gurgaon", "noida", "delhi", "kolkata", "ahmedabad",
        "coimbatore", "chandigarh", "jaipur", "kochi", "trivandrum",
    ]
    for city in top_metros:
        if city in raw:
            return city
    return "india"


def canonical_url(raw_url: Any) -> str:
    """
    Cleans tracking, UTM parameters, and session tokens from apply URLs
    to allow cross-board link matching.
    """
    url = safe_str(raw_url)
    if not url or not url.startswith("http"):
        return ""
    try:
        parsed = urlparse(url)
        ignored_params = {
            "ref", "source", "trk", "fbclid", "gclid", "jobs_evaluation",
            "e_id", "sub_source", "campaign", "sid",
        }
        filtered = [
            (k, v) for k, v in parse_qsl(parsed.query)
            if not k.startswith("utm_") and k.lower() not in ignored_params
        ]
        clean_query = urlencode(filtered)
        clean_path = parsed.path.rstrip("/")
        return urlunparse((parsed.scheme, parsed.netloc.lower(), clean_path, "", clean_query, "")).strip()
    except Exception:
        return url.strip()


def compute_cross_site_key(job: Dict[str, Any]) -> Tuple[str, str, str]:
    """Generates the primary composite deduplication key: (company, title, city)."""
    comp = normalize_company(job.get("company"))
    title = normalize_title(job.get("title"), job.get("company"))
    city = normalize_city(job.get("location"))
    return comp, title, city


def are_titles_similar(title1: str, title2: str, threshold: float = 0.70) -> bool:
    """Jaccard word-set similarity check for normalized titles."""
    tokens1 = set(title1.split())
    tokens2 = set(title2.split())
    if not tokens1 or not tokens2:
        return False
    if tokens1 == tokens2:
        return True
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    return (len(intersection) / len(union)) >= threshold


def deduplicate_jobs(
    jobs: List[Dict[str, Any]],
    prefer_rich_description: bool = True,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    High-performance cross-site deduplication and record merging engine.

    Returns:
        (deduplicated_job_list, audit_stats_dict)
    """
    seen_urls: Dict[str, Dict[str, Any]] = {}
    seen_composite: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    unique_jobs: List[Dict[str, Any]] = []

    stats: Dict[str, Any] = {
        "total_input": len(jobs),
        "unique_output": 0,
        "url_duplicates": 0,
        "cross_site_duplicates": 0,
        "sources_represented": set(),
    }

    for job in jobs:
        source = safe_str(job.get("site") or "unknown").lower()
        if source:
            stats["sources_represented"].add(source)

        direct_url = job.get("job_url_direct") or ""
        page_url = job.get("job_url") or job.get("apply_url") or ""
        can_direct = canonical_url(direct_url)
        can_page = canonical_url(page_url)

        comp, title, city = compute_cross_site_key(job)
        comp_key = (comp, title, city) if (comp and title) else None

        match: Optional[Dict[str, Any]] = None
        match_reason: str = ""

        # 1. Exact canonical URL match
        if can_direct and can_direct in seen_urls:
            match = seen_urls[can_direct]
            match_reason = "canonical_url"
            stats["url_duplicates"] += 1
        elif can_page and can_page in seen_urls:
            match = seen_urls[can_page]
            match_reason = "canonical_url"
            stats["url_duplicates"] += 1
        # 2. Exact composite key match (company + title + city)
        elif comp_key and comp_key in seen_composite:
            match = seen_composite[comp_key]
            match_reason = "composite_exact"
            stats["cross_site_duplicates"] += 1
        # 3. Fuzzy title match for same company and city
        elif comp and comp_key:
            for (c_other, t_other, loc_other), existing_job in seen_composite.items():
                if c_other == comp and (loc_other == city or city == "india" or loc_other == "india"):
                    if are_titles_similar(t_other, title, threshold=0.75):
                        match = existing_job
                        match_reason = "composite_fuzzy"
                        stats["cross_site_duplicates"] += 1
                        break

        # Duplicate detected -> Merge metadata
        if match is not None:
            existing_sites = [s.strip() for s in str(match.get("site", "")).split(",") if s.strip()]
            if source not in existing_sites:
                existing_sites.append(source)
                match["site"] = ", ".join(existing_sites)

            match["cross_site_duplicate"] = True
            dup_sources = match.setdefault("duplicate_sources", [])
            if source not in dup_sources:
                dup_sources.append(source)

            # Keep the longer, richer description
            if prefer_rich_description:
                curr_desc = safe_str(match.get("description"))
                new_desc = safe_str(job.get("description"))
                if len(new_desc) > len(curr_desc):
                    match["description"] = new_desc

            # Enrich salary info if missing
            if not match.get("salary_min") and job.get("salary_min"):
                match["salary_min"] = job.get("salary_min")
                match["salary_max"] = job.get("salary_max")

            # Enrich skills if missing
            if not match.get("skills_requirements") and job.get("skills_requirements"):
                match["skills_requirements"] = job.get("skills_requirements")

            continue

        # New unique listing
        job_copy = dict(job)
        job_copy["sources"] = [source]
        job_copy["cross_site_duplicate"] = False
        unique_jobs.append(job_copy)

        if can_direct:
            seen_urls[can_direct] = job_copy
        if can_page:
            seen_urls[can_page] = job_copy
        if comp_key:
            seen_composite[comp_key] = job_copy

    stats["unique_output"] = len(unique_jobs)
    stats["sources_represented"] = sorted(list(stats["sources_represented"]))
    return unique_jobs, stats
