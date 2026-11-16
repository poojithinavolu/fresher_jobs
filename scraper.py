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
    normalize_location_for_search,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("FresherJobScraper")
_LINKEDIN_LOCK = RLock()
# Cache guest-endpoint descriptions for the current process so a rate-limited
# or repeated card does not cost another HTTP request during the same run.
_LINKEDIN_DESCRIPTION_CACHE: Dict[str, str] = {}


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
    cached = _LINKEDIN_DESCRIPTION_CACHE.get(jid)
    if cached:
        raw_job["description"] = cached
        return

    url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        try:
            from curl_cffi import requests as cffi_requests
            s = cffi_requests.Session(impersonate="chrome")
            resp = s.get(url, headers=headers, timeout=8)
        except Exception:
            requester = session if session is not None else requests
            resp = requester.get(url, headers=headers, timeout=6)

        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            desc_div = soup.find("div", class_="show-more-less-html__markup")
            desc_text = desc_div.get_text("\n").strip() if desc_div else soup.get_text("\n").strip()
            if desc_text:
                _LINKEDIN_DESCRIPTION_CACHE[jid] = desc_text
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
            if site in {"monsterindia", "foundit", "monster"}:
                from foundit_scraper import scrape_foundit_jobs
                df = scrape_foundit_jobs(
                    search_term=search_term,
                    location=location,
                    results_wanted=results_wanted,
                    hours_old=hours_old,
                    proxies=proxies,
                )
                return site, df, None

            if site in {
                "unstop", "elitmus", "useastra", "freshersdunia",
                "freshershunt", "campusdrive", "jobs4fresher", "joinsaarthi",
            }:
                import off_campus_scrapers
                fn = getattr(off_campus_scrapers, f"scrape_{site}_jobs", None)
                if fn:
                    items = fn(
                        search_term=search_term,
                        location=location,
                        results_wanted=results_wanted,
                    )
                    df = pd.DataFrame(items) if items else pd.DataFrame()
                    return site, df, None

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

    # The freshness gate lives in filter_engine and defaults to config.
    # Align it with the window this run actually requested so `--hours` means
    # the same thing during scraping and during filtering.
    import filter_engine as _filter_engine
    _filter_engine.MAX_HOURS_OLD = hours_old

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
        if not df.empty:
            # Preserve the query context: it is needed when a board returns a
            # state ("MH, India") instead of a city, and for audit/debugging.
            df["search_city"] = loc
            df["search_query"] = search_query
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

    # Cross-site deduplication and record merging
    from dedup_engine import deduplicate_jobs
    all_raw_jobs, dedup_stats = deduplicate_jobs(all_raw_jobs)
    if dedup_stats["cross_site_duplicates"] > 0 or dedup_stats["url_duplicates"] > 0:
        logger.info(
            "Cross-site deduplication: %d raw jobs merged into %d unique opportunities (%d duplicates resolved)",
            dedup_stats["total_input"],
            dedup_stats["unique_output"],
            dedup_stats["cross_site_duplicates"] + dedup_stats["url_duplicates"],
        )

    # Process and filter each job
    valid_jobs: List[Dict[str, Any]] = []
    rejected_jobs: List[Dict[str, Any]] = []
    review_jobs: List[Dict[str, Any]] = []

    li_session = None
    try:
        import requests
        li_session = requests.Session()
    except Exception:
        pass

    for raw_job in all_raw_jobs:
        source = clean_str(raw_job.get("site")) or "unknown"

        # Normalize state-only board locations (Indeed: "MH, India" / "TS, India")
        # using the city that produced this result. Keep the raw value for audit.
        location_raw = safe_str(raw_job.get("location"))
        normalized_location = normalize_location_for_search(
            location_raw, raw_job.get("search_city")
        )
        if normalized_location and normalized_location != location_raw:
            raw_job["location_raw"] = location_raw
            raw_job["location"] = normalized_location

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

        # 3. Hydrate description for candidate LinkedIn jobs that pass preliminary triage.
        # A short/empty description is exactly where LinkedIn hides the experience
        # requirement, so do not require a role-category match before hydrating.
        if "linkedin" in source and len(safe_str(raw_job.get("description"))) < 150:
            title_clean = safe_str(raw_job.get("title"))
            company_clean = safe_str(raw_job.get("company"))
            loc_clean = safe_str(raw_job.get("location"))
            within_h, _ = is_within_hours(raw_job.get("date_posted"), hours_old)
            legit, _ = is_legitimate_company(company_clean, title_clean)
            loc_ok, _ = is_valid_location(loc_clean, search_city=raw_job.get("search_city"))
            if within_h and legit and loc_ok:
                hydrate_linkedin_description(raw_job, session=li_session)
                time.sleep(0.5)

        # 4. Evaluate criteria (freshness, fresher experience, anti-scam blacklist)
        evaluated = evaluate_job(raw_job)

        # 4a. Second chance for a missing search-card experience field.
        # A missing field is not proof that the job requires experience. If the
        # only blocker is experience, fetch the full JD (LinkedIn) and re-evaluate
        # so the description / platform entry-level signal can decide.
        def _only_missing_experience(job: Dict[str, Any]) -> bool:
            missing_reasons = {
                "Experience requirement missing; cannot verify fresher limit",
                "Experience could not be verified as strict 0-1 years",
                "Experience is unspecified/unverified; cannot guarantee fresher limit",
            }
            reasons = [
                part.strip()
                for part in str(job.get("rejection_reason", "")).split("|")
                if part.strip()
            ]
            return bool(reasons) and all(reason in missing_reasons for reason in reasons)

        if (
            not evaluated["is_valid_fresher_job"]
            and source in {"linkedin", "indeed"}
            and _only_missing_experience(evaluated)
        ):
            if source == "linkedin" and len(safe_str(evaluated.get("description"))) < 150:
                hydrate_linkedin_description(evaluated, session=li_session)
                time.sleep(0.5)
                evaluated = evaluate_job(evaluated)

            if not evaluated["is_valid_fresher_job"] and _only_missing_experience(evaluated):
                # Do not label an evidence gap as an experienced candidate.
                # Keep it visible for manual review instead of auto-rejecting it.
                evaluated["needs_review"] = True
                evaluated["review_reason"] = (
                    "No experience evidence in the search card or job description; "
                    "kept for manual review instead of automatic rejection"
                )

        if evaluated["is_valid_fresher_job"]:
            # 5. Final LLM Gatekeeper & Skills Curator.
            # HARD GATE: only a job the LLM explicitly approves may reach
            # valid_jobs and the live Google Sheet. Anything we cannot verify
            # goes to manual review instead of being trusted by default.
            try:
                from llm_verifier import hydrate_job_description, verify_fresher_and_curate_skills, extract_fallback_skills
                desc = hydrate_job_description(evaluated)
                if not desc:
                    evaluated["needs_review"] = True
                    evaluated["review_reason"] = (
                        "Description unavailable; cannot run the LLM fresher gate"
                    )
                    review_jobs.append(evaluated)
                    continue

                llm_eval = verify_fresher_and_curate_skills(
                    description=desc,
                    title=str(evaluated.get("title", "")),
                    company=str(evaluated.get("company", ""))
                )
                llm_verified = bool(llm_eval.get("llm_verified", False))
                evaluated["llm_verified"] = llm_verified
                evaluated["llm_eligible"] = bool(llm_eval.get("is_fresher_eligible", False))
                evaluated["llm_experience_detected"] = str(
                    llm_eval.get("experience_detected") or ""
                )

                if not llm_eval.get("is_fresher_eligible", False):
                    if llm_verified:
                        evaluated["is_valid_fresher_job"] = False
                        evaluated["rejection_reason"] = (
                            "LLM Gatekeeper: "
                            f"{llm_eval.get('rejection_reason') or 'Requires prior experience'}"
                        )
                        rejected_jobs.append(evaluated)
                    else:
                        evaluated["needs_review"] = True
                        evaluated["review_reason"] = (
                            "LLM gate unavailable: "
                            f"{llm_eval.get('rejection_reason') or 'verification did not complete'}"
                        )
                        review_jobs.append(evaluated)
                    continue

                skills = str(llm_eval.get("curated_skills") or "").strip()
                if not skills:
                    skills = extract_fallback_skills(desc, title=str(evaluated.get("title", "")), role=str(evaluated.get("tech_category", "")))
                evaluated["skills_requirements"] = skills
            except Exception as e:
                logger.warning("LLM verification step encountered error: %s", e)
                evaluated["needs_review"] = True
                evaluated["review_reason"] = f"LLM gate unavailable: {e}"
                review_jobs.append(evaluated)
                continue

            # Final safety check: NEVER allow a job into valid_jobs without skills_requirements
            if not str(evaluated.get("skills_requirements") or "").strip():
                evaluated["is_valid_fresher_job"] = False
                evaluated["rejection_reason"] = "Missing required skills/responsibilities"
                rejected_jobs.append(evaluated)
                continue

            valid_jobs.append(evaluated)
        elif evaluated.get("needs_review"):
            review_jobs.append(evaluated)
        else:
            rejected_jobs.append(evaluated)

    elapsed = time.time() - start_time

    # Compile comprehensive stats
    stats = {
        "duration_seconds": round(elapsed, 2),
        "total_queries_executed": query_count,
        "total_raw_scraped": total_scraped,
        "total_unique_jobs": len(valid_jobs) + len(rejected_jobs) + len(review_jobs),
        "valid_fresher_jobs": len(valid_jobs),
        "rejected_jobs_count": len(rejected_jobs),
        "review_jobs_count": len(review_jobs),
        "inferred_experience_count": sum(
            1 for job in valid_jobs
            if job.get("experience_source") in {"title_inference", "platform_entry_level"}
        ),
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
        "review_jobs": review_jobs,
        "stats": stats,
    }
