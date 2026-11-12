"""
Core Multi-Board Scraper using JobSpy
=====================================
Fetches live jobs across Naukri, LinkedIn, and Indeed concurrently
with zero external paid API subscriptions ($0 cost).
Includes error-isolation, pacing, deduplication, and quality evaluation.
"""

import time
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import RLock
from typing import List, Dict, Any, Optional
import pandas as pd
import jobspy
from jobspy import scrape_jobs
from jobspy.model import Site as JobSpySite
from jobspy.naukri import Naukri

from config import (
    MAX_HOURS_OLD,
    TARGET_SITES,
    DEFAULT_LOCATIONS,
    INDEED_COUNTRY,
    RESULTS_PER_QUERY,
    QUERY_DELAY_SECONDS,
    JOBSPY_PROXIES,
    ROLE_QUERIES,
)
from filter_engine import evaluate_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("FresherJobScraper")
_NAUKRI_MAPPING_LOCK = RLock()


class EntryLevelNaukri(Naukri):
    """JobSpy Naukri adapter with Naukri's native experience search filter."""

    def _search_params(self):
        params = super()._search_params()
        # Naukri's search endpoint uses experience=0 for its 0–1 year band.
        # JobSpy currently has no ScraperInput experience field for Naukri.
        params["experience"] = "0"
        return params


def clean_str(val: Any) -> str:
    """Helper to sanitize string for composite deduplication key."""
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
) -> pd.DataFrame:
    """
    Scrapes boards concurrently, with at most one active request per board.
    """
    logger.info(f"Scraping -> Query: '{search_term}' | Location: '{location}' | Sites: {sites} | Hours: {hours_old}")

    def scrape_one_site(site: str) -> tuple[str, pd.DataFrame, Optional[str]]:
        try:
            call = lambda: scrape_jobs(
                site_name=[site], search_term=search_term, location=location,
                results_wanted=results_wanted, hours_old=hours_old,
                country_indeed=INDEED_COUNTRY, proxies=proxies,
                fetch_description=True, verbose=0,
            )
            if site == "naukri":
                # JobSpy has no public experience argument. Swap only the Naukri
                # adapter under a lock for this call, restoring it immediately.
                with _NAUKRI_MAPPING_LOCK:
                    previous = jobspy.SCRAPER_MAPPING[JobSpySite.NAUKRI]
                    jobspy.SCRAPER_MAPPING[JobSpySite.NAUKRI] = EntryLevelNaukri
                    try:
                        df = call()
                    finally:
                        jobspy.SCRAPER_MAPPING[JobSpySite.NAUKRI] = previous
            else:
                df = call()
            errors = (getattr(df, "attrs", {}) or {}).get("errors", {})
            if site in errors:
                site_errors[site] = str(errors[site])
                logger.warning("JobSpy reported %s failure for %s: %s", site, search_term, errors[site])
            warnings = (getattr(df, "attrs", {}) or {}).get("warnings", {})
            if site in warnings:
                logger.warning("JobSpy warning for %s: %s", site, warnings[site])
            return site, df, str(errors[site]) if site in errors else None
        except Exception as exc:
            logger.warning("Scraper failed for %s (%s, %s): %s", site, search_term, location, exc)

            # Keep failures isolated to this board so another board's results
            # still reach filtering and the sheet sync.
            return site, pd.DataFrame(), str(exc)

    if len(sites) > 1:
        # The caller waits for this batch before starting the next query, so
        # each board has at most one in-flight request and keeps its normal
        # per-query pacing. Network waits across independent boards overlap.
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
    and subjects every listing to the strict 48-hour fresher filter.
    """
    target_locations = locations or DEFAULT_LOCATIONS
    target_roles = roles_dict or ROLE_QUERIES
    target_sites = sites or TARGET_SITES
    proxies = proxies if proxies is not None else (JOBSPY_PROXIES or None)

    all_raw_jobs: List[Dict[str, Any]] = []
    seen_urls = set()
    seen_composite_keys = set()

    start_time = time.time()
    query_count = 0
    site_errors: Dict[str, List[str]] = {}
    site_queries_attempted = {site: 0 for site in target_sites}

    for role_category, queries in target_roles.items():
        logger.info(f"\n==================== Category: {role_category} ====================")
        for search_query in queries:
            for loc in target_locations:
                query_count += 1
                for site in target_sites:
                    site_queries_attempted[site] = site_queries_attempted.get(site, 0) + 1
                df = run_scraping_query(
                    search_term=search_query,
                    location=loc,
                    sites=target_sites,
                    hours_old=hours_old,
                    results_wanted=results_per_query,
                    proxies=proxies,
                )

                if not df.empty:
                    # Convert to list of dictionaries
                    records = df.to_dict(orient="records")
                    all_raw_jobs.extend(records)
                for site, error in df.attrs.get("site_errors", {}).items():
                    site_errors.setdefault(site, []).append(error)

                # Pacing delay between queries
                time.sleep(QUERY_DELAY_SECONDS)

    total_scraped = len(all_raw_jobs)
    logger.info(f"\nTotal raw jobs pulled across all queries: {total_scraped}")

    # Process and filter each job
    valid_jobs: List[Dict[str, Any]] = []
    rejected_jobs: List[Dict[str, Any]] = []

    for raw_job in all_raw_jobs:
        # Deduplicate within each board. Keep cross-board copies so the first
        # site in TARGET_SITES cannot silently take ownership of the listing.
        source = clean_str(raw_job.get("site")) or "unknown"

        # 1. URL Deduplication (site-aware)
        job_url = raw_job.get("job_url_direct") or raw_job.get("job_url") or ""
        url_key = (source, str(job_url).strip().casefold()) if job_url else None
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

        # 3. Evaluate criteria (48h, fresher experience, anti-scam blacklist)
        evaluated = evaluate_job(raw_job)

        if evaluated["is_valid_fresher_job"]:
            valid_jobs.append(evaluated)
        else:
            rejected_jobs.append(evaluated)

    elapsed = time.time() - start_time

    # Compile stats
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

