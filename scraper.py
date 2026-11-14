"""
Core Multi-Board Scraper using JobSpy
=====================================
Fetches live jobs across Naukri, LinkedIn, and Indeed concurrently
with zero external paid API subscriptions ($0 cost).
Includes error-isolation, pacing, deduplication, and quality evaluation.
"""

import time
import math
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import RLock
from typing import List, Dict, Any, Optional
import pandas as pd
import jobspy
from jobspy import scrape_jobs
from jobspy.linkedin import LinkedIn
from jobspy.model import Site as JobSpySite
from jobspy.naukri import Naukri

from config import (
    MAX_HOURS_OLD,
    TARGET_SITES,
    DEFAULT_LOCATIONS,
    INDEED_COUNTRY,
    RESULTS_PER_QUERY,
    QUERY_DELAY_SECONDS,
    QUERY_CONCURRENCY,
    JOBSPY_PROXIES,
    ROLE_QUERIES,
)
from filter_engine import (
    evaluate_job,
    is_within_hours,
    is_legitimate_company,
    is_valid_location,
    categorize_role,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("FresherJobScraper")
_LINKEDIN_LOCK = RLock()


class EntryLevelNaukri(Naukri):
    """Naukri adapter that targets freshers (0-1 yrs) using Naukri's native experience filter."""

    def _search_params(self):
        params = super()._search_params()
        # Naukri search API: experience=0 targets the 0-1 year fresher band
        params["experience"] = "0"
        return params


class FresherLinkedIn(LinkedIn):
    """LinkedIn adapter configured for entry-level fresher roles with newest-first ordering."""

    def _search_params(self):
        params = super()._search_params()
        # f_E=2 targets Entry level listings; sortBy=DD ensures newest postings first
        params["f_E"] = "2"
        params["sortBy"] = "DD"
        return params

    def _process_job(self, job_card, job_id: str):
        post = super()._process_job(job_card, job_id)
        if post is not None:
            # Explicitly mark job_level as entry_level from verified f_E=2 query
            post = post.model_copy(update={"job_level": "entry_level"})
        return post


# Register custom adapters once globally for the scraper process
jobspy.SCRAPER_MAPPING[JobSpySite.NAUKRI] = EntryLevelNaukri
jobspy.SCRAPER_MAPPING[JobSpySite.LINKEDIN] = FresherLinkedIn


def safe_str(val: Any) -> str:
    """Safely extracts string values handling pandas/numpy NaN without false truthiness."""
    if val is None:
        return ""
    if isinstance(val, float) and math.isnan(val):
        return ""
    s = str(val).strip()
    return "" if s.lower() in {"nan", "none", "nat"} else s


def get_job_url(raw_job: Dict[str, Any]) -> str:
    """Extracts valid job URL or fallback identifier, avoiding NaN truthiness traps."""
    direct = safe_str(raw_job.get("job_url_direct"))
    if direct:
        return direct
    url = safe_str(raw_job.get("job_url"))
    if url:
        return url
    return safe_str(raw_job.get("id"))


def clean_str(val: Any) -> str:
    """Helper to sanitize string for composite deduplication key."""
    text = safe_str(val)
    if not text:
        return ""
    return "".join(c.lower() for c in text if c.isalnum() or c.isspace()).strip()


def hydrate_linkedin_description(raw_job: Dict[str, Any], session: Optional[Any] = None) -> None:
    """
    Hydrates full job description for candidate LinkedIn jobs via LinkedIn guest endpoint.
    Guarantees that explicit experience requirements in JD (e.g. 1-3 yrs, 5+ yrs) are captured.
    """
    import re
    import requests
    from bs4 import BeautifulSoup

    effective_url = safe_str(raw_job.get("job_url_direct") or raw_job.get("job_url") or raw_job.get("id"))
    jid_match = re.search(r"(\d{8,12})", effective_url)
    if not jid_match:
        return

    jid = jid_match.group(1)
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        requester = session if session is not None else requests
        resp = requester.get(url, headers=headers, timeout=6)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            desc_div = soup.find("div", class_="show-more-less-html__markup")
            desc_text = desc_div.get_text("\n").strip() if desc_div else soup.get_text("\n").strip()
            raw_job["description"] = desc_text
        elif resp.status_code == 429:
            logger.warning("LinkedIn guest endpoint rate-limited (HTTP 429) for job %s", jid)
    except Exception as exc:
        logger.debug("LinkedIn description fetch failed for %s: %s", jid, exc)


def run_scraping_query(
    search_term: str,
    location: str,
    sites: List[str] = TARGET_SITES,
    hours_old: int = MAX_HOURS_OLD,
    results_wanted: int = RESULTS_PER_QUERY,
    proxies: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Scrapes boards concurrently with error isolation and lightweight search-card extraction.
    """
    logger.info(f"Scraping -> Query: '{search_term}' | Location: '{location}' | Sites: {sites} | Hours: {hours_old}")

    def scrape_one_site(site: str) -> tuple[str, pd.DataFrame, Optional[str]]:
        try:
            # fetch_description=False delivers sub-second search responses across all boards.
            # Naukri includes title, company, location, experienceText, date, and apply URL.
            # Indeed includes title, company, location, full HTML description, date, and apply URL.
            # LinkedIn includes title, company, location, entry-level classification, and apply URL.
            call = lambda: scrape_jobs(
                site_name=[site],
                search_term=search_term,
                location=location,
                results_wanted=results_wanted,
                hours_old=hours_old,
                country_indeed=INDEED_COUNTRY,
                proxies=proxies,
                fetch_description=False,
                verbose=0,
            )
            if site == "linkedin":
                # Polite board serialization to eliminate 429 rate limit errors
                with _LINKEDIN_LOCK:
                    time.sleep(1.5)
                    df = call()
            else:
                df = call()
            errors = (getattr(df, "attrs", {}) or {}).get("errors", {})
            if site in errors:
                logger.warning("JobSpy reported %s failure for %s: %s", site, search_term, errors[site])
            warnings = (getattr(df, "attrs", {}) or {}).get("warnings", {})
            if site in warnings:
                logger.warning("JobSpy warning for %s: %s", site, warnings[site])
            return site, df, str(errors[site]) if site in errors else None
        except Exception as exc:
            logger.warning("Scraper failed for %s (%s, %s): %s", site, search_term, location, exc)
            return site, pd.DataFrame(), str(exc)

    if len(sites) > 1:
        with ThreadPoolExecutor(max_workers=len(sites)) as executor:
            site_results = list(executor.map(scrape_one_site, sites))
    else:
        site_results = [scrape_one_site(site) for site in sites]

    frames = []
    site_errors = {}
    for site, df, error in site_results:
        if error:
            site_errors[site] = error
        logger.info("Fetched %s listings from %s", len(df), site)
        if not df.empty:
            frames.append(df)

    nonempty = [frame.dropna(axis="columns", how="all") for frame in frames if not frame.empty]
    result = pd.concat(nonempty, ignore_index=True) if nonempty else pd.DataFrame()
    result.attrs["site_errors"] = site_errors
    return result


def scrape_fresher_jobs(
    locations: Optional[List[str]] = None,
    roles_dict: Optional[Dict[str, List[str]]] = None,
    sites: Optional[List[str]] = None,
    hours_old: int = MAX_HOURS_OLD,
    results_per_query: int = RESULTS_PER_QUERY,
    proxies: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Main orchestration loop.
    Iterates through each category, executes the queries across sites,
    and subjects every listing to the strict fresher verification pipeline.
    """
    target_locations = locations or DEFAULT_LOCATIONS
    target_roles = roles_dict or ROLE_QUERIES
    target_sites = sites or TARGET_SITES
    proxies = proxies if proxies is not None else (JOBSPY_PROXIES or None)

    all_raw_jobs: List[Dict[str, Any]] = []
    seen_urls = set()
    seen_composite_keys = set()

    start_time = time.time()
    site_errors: Dict[str, List[str]] = {}
    site_queries_attempted = {site: 0 for site in target_sites}

    query_tasks = [
        (role_category, search_query, loc)
        for role_category, queries in target_roles.items()
        for search_query in queries
        for loc in target_locations
    ]
    query_count = len(query_tasks)
    for site in target_sites:
        site_queries_attempted[site] = query_count

    def run_task(task):
        role_category, search_query, loc = task
        logger.info(
            "Scraping query -> Category: %s | Query: '%s' | Location: %s",
            role_category, search_query, loc,
        )
        df = run_scraping_query(
            search_term=search_query,
            location=loc,
            sites=target_sites,
            hours_old=hours_old,
            results_wanted=results_per_query,
            proxies=proxies,
        )
        time.sleep(QUERY_DELAY_SECONDS)
        return df

    worker_count = max(1, min(QUERY_CONCURRENCY, len(query_tasks)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        for df in executor.map(run_task, query_tasks):
            if not df.empty:
                all_raw_jobs.extend(df.to_dict(orient="records"))
            for site, error in df.attrs.get("site_errors", {}).items():
                site_errors.setdefault(site, []).append(error)

    total_scraped = len(all_raw_jobs)
    logger.info(f"\nTotal raw jobs pulled across all queries: {total_scraped}")

    # Process and filter each job
    valid_jobs: List[Dict[str, Any]] = []
    rejected_jobs: List[Dict[str, Any]] = []

    li_session = None
    try:
        import requests
        li_session = requests.Session()
    except Exception:
        pass

    for raw_job in all_raw_jobs:
        source = clean_str(raw_job.get("site")) or "unknown"

        # Normalize URL fields to eliminate pandas NaN truthiness traps downstream
        direct_url = safe_str(raw_job.get("job_url_direct"))
        page_url = safe_str(raw_job.get("job_url"))
        effective_url = direct_url or page_url or safe_str(raw_job.get("id"))
        raw_job["job_url_direct"] = direct_url if direct_url else None
        raw_job["job_url"] = page_url if page_url else (effective_url if effective_url.startswith("http") else None)
        raw_job["apply_url"] = effective_url

        # 1. URL Deduplication (site-aware)
        url_key = (source, effective_url.casefold()) if effective_url else None
        if url_key and url_key in seen_urls:
            continue
        if url_key:
            seen_urls.add(url_key)

        # 2. Composite Key Deduplication (site + Title + Company + City)
        comp_key = (
            source,
            clean_str(raw_job.get("title")),
            clean_str(raw_job.get("company")),
            clean_str(raw_job.get("location")),
        )
        if comp_key in seen_composite_keys:
            continue
        seen_composite_keys.add(comp_key)

        # 3. Hydrate description for candidate LinkedIn jobs that pass preliminary triage
        if source == "linkedin" and not safe_str(raw_job.get("description")):
            title_clean = safe_str(raw_job.get("title"))
            company_clean = safe_str(raw_job.get("company"))
            loc_clean = safe_str(raw_job.get("location"))
            within_h, _ = is_within_hours(raw_job.get("date_posted"), hours_old)
            legit, _ = is_legitimate_company(company_clean, title_clean)
            loc_ok, _ = is_valid_location(loc_clean)
            cat = categorize_role(title_clean)
            if within_h and legit and loc_ok and cat:
                hydrate_linkedin_description(raw_job, session=li_session)
                time.sleep(0.5)

        # 4. Evaluate criteria (freshness, fresher experience, anti-scam blacklist)
        evaluated = evaluate_job(raw_job)

        if evaluated["is_valid_fresher_job"]:
            valid_jobs.append(evaluated)
        else:
            rejected_jobs.append(evaluated)

    elapsed = time.time() - start_time

    # Compile comprehensive stats
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
        "site_errors": {site: sorted(set(errors)) for site, errors in site_errors.items()},
        "raw_by_site": {},
        "site_queries_attempted": site_queries_attempted,
    }

    for raw in all_raw_jobs:
        site = raw.get("site", "unknown")
        stats["raw_by_site"][site] = stats["raw_by_site"].get(site, 0) + 1

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
