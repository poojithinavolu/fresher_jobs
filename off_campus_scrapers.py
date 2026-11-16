"""Off-Campus Drives & Specialty Fresher Job Boards Scraper
=========================================================
Concurrent, fault-isolated scraper adapters for top Indian off-campus drive
and fresher hiring platforms without requiring API keys or user logins:
- Unstop (Public JSON API)
- eLitmus (HTML parsing)
- UseAstra (Off-Campus Drives & JobPosting Schema)
- FreshersDunia (WordPress REST API)
- FreshersHunt (WordPress REST API)
- CampusDrive (Batch off-campus drive parser)
- Jobs4Fresher (Recruitment parser)
- JoinSaarthi (Job cards parser)

All adapters output standardized dictionaries compatible with JobSpy / filter_engine.
"""
from __future__ import annotations

import concurrent.futures
import html
import logging
import re
from typing import Any, Dict, List, Optional
import pandas as pd

logger = logging.getLogger("OffCampusScraper")

OFFCAMPUS_SITES = [
    "unstop",
    "elitmus",
    "useastra",
    "freshersdunia",
    "freshershunt",
    "campusdrive",
    "jobs4fresher",
    "joinsaarthi",
]


def _get_session():
    """Returns a curl_cffi Session with Chrome impersonation or requests.Session fallback."""
    try:
        from curl_cffi import requests as cffi_requests
        return cffi_requests.Session(impersonate="chrome120")
    except Exception:
        import requests
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        return s


def scrape_unstop_jobs(
    search_term: str = "",
    location: str = "",
    results_wanted: int = 15,
) -> List[Dict[str, Any]]:
    """Fetches fresher jobs from Unstop's public search API."""
    jobs: List[Dict[str, Any]] = []
    base_url = "https://unstop.com/api/public/opportunity/search-result"
    params = [
        "opportunity=jobs",
        "experience=0",
        f"per_page={max(5, min(results_wanted, 50))}",
        "oppstatus=open",
    ]
    if search_term and search_term.strip():
        params.append(f"searchTerm={search_term.strip()}")
    url = f"{base_url}?{'&'.join(params)}"

    session = _get_session()
    try:
        r = session.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json().get("data", {}).get("data", [])
            for item in data:
                title = str(item.get("title") or "").strip()
                if not title:
                    continue
                org = item.get("organisation", {})
                company = (org.get("name") if isinstance(org, dict) else str(org)) or "Unstop Employer"
                locs = [
                    l.get("city") for l in (item.get("locations") or [])
                    if isinstance(l, dict) and l.get("city")
                ]
                loc_str = ", ".join(locs) if locs else "India"
                apply_url = item.get("seo_url") or f"https://unstop.com/jobs/{item.get('id')}"
                date_posted = str(item.get("approved_date") or item.get("updated_at") or "")[:10]
                job_detail = item.get("jobDetail") or {}
                desc = item.get("details") or f"Opportunity at {company} for {title}"

                skills_req = [
                    sk.get("name") for sk in (item.get("required_skills") or [])
                    if isinstance(sk, dict) and sk.get("name")
                ]
                skills_str = ", ".join(skills_req) if skills_req else ""

                jobs.append({
                    "title": title,
                    "company": company.strip(),
                    "location": loc_str,
                    "site": "unstop",
                    "date_posted": date_posted,
                    "job_url_direct": apply_url,
                    "job_url": apply_url,
                    "description": desc,
                    "job_type": "fulltime",
                    "skills_requirements": skills_str,
                    "salary_min": job_detail.get("min_salary"),
                    "salary_max": job_detail.get("max_salary"),
                })
        else:
            logger.warning("Unstop API returned status %s", r.status_code)
    except Exception as exc:
        logger.warning("Unstop scraper failed: %s", exc)
    return jobs


def scrape_elitmus_jobs(
    search_term: str = "",
    location: str = "",
    results_wanted: int = 20,
) -> List[Dict[str, Any]]:
    """Parses live fresher opportunities from eLitmus jobs board."""
    jobs: List[Dict[str, Any]] = []
    url = "https://www.elitmus.com/jobs"
    session = _get_session()
    try:
        from bs4 import BeautifulSoup
        r = session.get(url, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            seen_hrefs = set()
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if (
                    href.startswith("/jobs/")
                    and not href.startswith("/jobs/refer")
                    and "pay_meter" not in href
                    and len(href) > 12
                ):
                    title = a.get_text(strip=True)
                    if not title or title.lower() in {"show details", "refer via", "our clients"}:
                        continue
                    clean_href = href.split("?")[0]
                    if clean_href in seen_hrefs:
                        continue
                    seen_hrefs.add(clean_href)

                    full_url = f"https://www.elitmus.com{href}"
                    parent = a.find_parent("div", class_=lambda c: c and ("row" in c or "container" in c)) or a.find_parent("div")
                    text_parts = [p.strip() for p in parent.get_text("|", strip=True).split("|") if p.strip()] if parent else []

                    company = text_parts[1] if len(text_parts) >= 2 else "eLitmus Partner"
                    loc_val = text_parts[3] if len(text_parts) >= 4 else "India"

                    jobs.append({
                        "title": title,
                        "company": company,
                        "location": loc_val,
                        "site": "elitmus",
                        "date_posted": "",
                        "job_url_direct": full_url,
                        "job_url": full_url,
                        "description": " | ".join(text_parts),
                        "job_type": "fulltime",
                    })
                    if len(jobs) >= results_wanted:
                        break
        else:
            logger.warning("eLitmus returned status %s", r.status_code)
    except Exception as exc:
        logger.warning("eLitmus scraper failed: %s", exc)
    return jobs


def scrape_useastra_jobs(
    search_term: str = "",
    location: str = "",
    results_wanted: int = 15,
) -> List[Dict[str, Any]]:
    """Scrapes off-campus drives and fresher openings from UseAstra."""
    jobs: List[Dict[str, Any]] = []
    url = "https://useastra.in/jobs/off-campus-drives"
    session = _get_session()
    try:
        from bs4 import BeautifulSoup
        r = session.get(url, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            cards = soup.find_all("a", href=lambda h: h and h.startswith("/jobs/") and not h.endswith("/off-campus-drives"))
            seen = set()
            for c in cards:
                href = c["href"]
                if href in seen:
                    continue
                seen.add(href)

                raw_text = c.get_text(" ", strip=True)
                parts = raw_text.split(" at ")
                title = parts[0].strip() if len(parts) >= 1 else raw_text
                company = parts[1].strip() if len(parts) >= 2 else "Off Campus Drive"
                apply_url = f"https://useastra.in{href}"

                jobs.append({
                    "title": title[:100],
                    "company": company[:80],
                    "location": "India",
                    "site": "useastra",
                    "date_posted": "",
                    "job_url_direct": apply_url,
                    "job_url": apply_url,
                    "description": f"Off campus fresher opportunity at {company}: {title}",
                    "job_type": "fulltime",
                })
                if len(jobs) >= results_wanted:
                    break
        else:
            logger.warning("UseAstra returned status %s", r.status_code)
    except Exception as exc:
        logger.warning("UseAstra scraper failed: %s", exc)
    return jobs


def scrape_freshersdunia_jobs(
    search_term: str = "",
    location: str = "",
    results_wanted: int = 15,
) -> List[Dict[str, Any]]:
    """Queries FreshersDunia's public WordPress REST API for fresh recruitment posts."""
    jobs: List[Dict[str, Any]] = []
    url = f"https://freshersdunia.in/wp-json/wp/v2/posts?per_page={max(5, min(results_wanted, 50))}"
    session = _get_session()
    try:
        from bs4 import BeautifulSoup
        r = session.get(url, timeout=10)
        if r.status_code == 200:
            posts = r.json()
            for p in posts:
                raw_title = html.unescape(BeautifulSoup(p.get("title", {}).get("rendered", ""), "html.parser").get_text(strip=True))
                comp_match = re.match(r"^([A-Za-z0-9\s\.\&]+?)\s+(?:Recruitment|Careers|Off\s+Campus|Hiring)", raw_title, re.IGNORECASE)
                company = comp_match.group(1).strip() if comp_match else raw_title.split("–")[0].split("-")[0].strip()

                title_match = re.search(r"–\s*([^\|–]+?)(?:Role|Drive|Job|Opening|\s*\||$)", raw_title, re.IGNORECASE)
                title = title_match.group(1).strip() if title_match else raw_title

                content_html = p.get("content", {}).get("rendered", "")
                content_text = BeautifulSoup(content_html, "html.parser").get_text("\n", strip=True) if content_html else ""
                apply_link = str(p.get("link") or "")

                jobs.append({
                    "title": title[:100],
                    "company": company[:80],
                    "location": "India",
                    "site": "freshersdunia",
                    "date_posted": str(p.get("date") or "")[:10],
                    "job_url_direct": apply_link,
                    "job_url": apply_link,
                    "description": content_text[:1500],
                    "job_type": "fulltime",
                })
        else:
            logger.warning("FreshersDunia API returned status %s", r.status_code)
    except Exception as exc:
        logger.warning("FreshersDunia scraper failed: %s", exc)
    return jobs


def scrape_freshershunt_jobs(
    search_term: str = "",
    location: str = "",
    results_wanted: int = 15,
) -> List[Dict[str, Any]]:
    """Queries FreshersHunt's public WordPress REST API for off-campus drive posts."""
    jobs: List[Dict[str, Any]] = []
    url = f"https://freshershunt.in/wp-json/wp/v2/posts?per_page={max(5, min(results_wanted, 50))}"
    session = _get_session()
    try:
        from bs4 import BeautifulSoup
        r = session.get(url, timeout=10)
        if r.status_code == 200:
            posts = r.json()
            for p in posts:
                raw_title = html.unescape(BeautifulSoup(p.get("title", {}).get("rendered", ""), "html.parser").get_text(strip=True))
                parts = [part.strip() for part in raw_title.split("|")]
                company_part = parts[0] if len(parts) >= 1 else raw_title
                comp_match = re.match(r"^([A-Za-z0-9\s\.\&]+?)\s+(?:Recruitment|Careers|Off\s+Campus|Hiring|Internship)", company_part, re.IGNORECASE)
                company = comp_match.group(1).strip() if comp_match else company_part

                title = parts[1] if len(parts) >= 2 else raw_title
                loc_val = parts[2].replace("— Apply Now", "").strip() if len(parts) >= 3 else "India"

                content_html = p.get("content", {}).get("rendered", "")
                content_text = BeautifulSoup(content_html, "html.parser").get_text("\n", strip=True) if content_html else ""

                jobs.append({
                    "title": title[:100],
                    "company": company[:80],
                    "location": loc_val[:80],
                    "site": "freshershunt",
                    "date_posted": str(p.get("date") or "")[:10],
                    "job_url_direct": str(p.get("link") or ""),
                    "job_url": str(p.get("link") or ""),
                    "description": content_text[:1500],
                    "job_type": "fulltime",
                })
        else:
            logger.warning("FreshersHunt API returned status %s", r.status_code)
    except Exception as exc:
        logger.warning("FreshersHunt scraper failed: %s", exc)
    return jobs


def scrape_campusdrive_jobs(
    search_term: str = "",
    location: str = "",
    results_wanted: int = 15,
) -> List[Dict[str, Any]]:
    """Scrapes batch-wise off-campus drives from CampusDrive.in."""
    jobs: List[Dict[str, Any]] = []
    urls = [
        "https://campusdrive.in/jobs/2026-batch",
        "https://campusdrive.in/jobs/2025-batch",
    ]
    session = _get_session()
    try:
        from bs4 import BeautifulSoup
        seen = set()
        for page_url in urls:
            r = session.get(page_url, timeout=8)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                txt = a.get_text(" ", strip=True)
                href = a["href"]
                if (
                    len(txt) > 20
                    and any(k in txt for k in ["Off Campus", "Hiring", "Recruitment", "Internship", "Trainee"])
                    and href.startswith("/")
                    and not href.startswith("/jobs/")
                    and href not in seen
                ):
                    seen.add(href)
                    parts = txt.split(":")
                    comp_raw = parts[0].replace("Off Campus Drive", "").replace("Recruitment", "").replace("Hiring", "").replace("2026", "").replace("2025", "").strip()
                    role_raw = parts[1].split("|")[0].strip() if len(parts) > 1 else txt
                    full_url = f"https://campusdrive.in{href}"

                    jobs.append({
                        "title": role_raw[:100],
                        "company": comp_raw[:80],
                        "location": "India",
                        "site": "campusdrive",
                        "date_posted": "",
                        "job_url_direct": full_url,
                        "job_url": full_url,
                        "description": f"Off campus drive at {comp_raw} for {role_raw}",
                        "job_type": "fulltime",
                    })
                    if len(jobs) >= results_wanted:
                        break
            if len(jobs) >= results_wanted:
                break
    except Exception as exc:
        logger.warning("CampusDrive scraper failed: %s", exc)
    return jobs


def scrape_jobs4fresher_jobs(
    search_term: str = "",
    location: str = "",
    results_wanted: int = 15,
) -> List[Dict[str, Any]]:
    """Scrapes fresh corporate recruitment drives from Jobs4Fresher."""
    jobs: List[Dict[str, Any]] = []
    url = "https://jobs4fresher.com"
    session = _get_session()
    try:
        from bs4 import BeautifulSoup
        r = session.get(url, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            seen = set()
            for a in soup.find_all("a", href=True):
                href = a["href"]
                m = re.match(r"https://jobs4fresher\.com/([a-z0-9\-]+)-(?:recruitment|hiring|off-campus-drive)-2026-([a-z0-9\-]+)/", href)
                if m and href not in seen:
                    seen.add(href)
                    comp_slug = m.group(1).replace("-", " ").title()
                    loc_slug = m.group(2).replace("-", " ").title()
                    txt = a.get_text(" ", strip=True) or f"{comp_slug} Fresher Recruitment"
                    jobs.append({
                        "title": txt[:100] if len(txt) > 5 else f"Graduate Engineer Trainee - {comp_slug}",
                        "company": comp_slug,
                        "location": loc_slug,
                        "site": "jobs4fresher",
                        "date_posted": "",
                        "job_url_direct": href,
                        "job_url": href,
                        "description": f"Recruitment drive at {comp_slug} in {loc_slug}",
                        "job_type": "fulltime",
                    })
                    if len(jobs) >= results_wanted:
                        break
    except Exception as exc:
        logger.warning("Jobs4Fresher scraper failed: %s", exc)
    return jobs


def scrape_joinsaarthi_jobs(
    search_term: str = "",
    location: str = "",
    results_wanted: int = 15,
) -> List[Dict[str, Any]]:
    """Scrapes verified fresher job cards from JoinSaarthi."""
    jobs: List[Dict[str, Any]] = []
    url = "https://joinsaarthi.com/jobs"
    session = _get_session()
    try:
        from bs4 import BeautifulSoup
        r = session.get(url, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            cards = soup.find_all("a", href=lambda h: h and h.startswith("/jobs/") and len(h.split("/")) >= 4)
            seen = set()
            for c in cards:
                href = c["href"]
                if href in seen:
                    continue
                seen.add(href)

                full_url = f"https://joinsaarthi.com{href}"
                text_parts = [t.strip() for t in c.get_text("|", strip=True).split("|") if t.strip()]
                company = text_parts[0] if len(text_parts) >= 1 else "Saarthi Employer"
                title = text_parts[1] if len(text_parts) >= 2 else "Fresher"
                loc = "India"
                for p in text_parts[2:]:
                    if any(city in p.lower() for city in ["bangalore", "bengaluru", "hyderabad", "pune", "mumbai", "noida", "gurgaon", "delhi", "chennai", "india"]):
                        loc = p
                        break

                jobs.append({
                    "title": title[:100],
                    "company": company[:80],
                    "location": loc[:80],
                    "site": "joinsaarthi",
                    "date_posted": "",
                    "job_url_direct": full_url,
                    "job_url": full_url,
                    "description": " | ".join(text_parts),
                    "job_type": "fulltime",
                })
                if len(jobs) >= results_wanted:
                    break
    except Exception as exc:
        logger.warning("JoinSaarthi scraper failed: %s", exc)
    return jobs


_SCRAPER_MAP = {
    "unstop": scrape_unstop_jobs,
    "elitmus": scrape_elitmus_jobs,
    "useastra": scrape_useastra_jobs,
    "freshersdunia": scrape_freshersdunia_jobs,
    "freshershunt": scrape_freshershunt_jobs,
    "campusdrive": scrape_campusdrive_jobs,
    "jobs4fresher": scrape_jobs4fresher_jobs,
    "joinsaarthi": scrape_joinsaarthi_jobs,
}


def scrape_all_offcampus_boards(
    sites: Optional[List[str]] = None,
    search_term: str = "",
    location: str = "",
    results_per_site: int = 15,
    max_workers: int = 6,
) -> pd.DataFrame:
    """
    Executes scrapers across all requested off-campus and fresher portals concurrently.
    Returns a unified Pandas DataFrame matching standard JobSpy schema.
    """
    target_sites = [s.lower() for s in (sites or OFFCAMPUS_SITES) if s.lower() in _SCRAPER_MAP]
    if not target_sites:
        return pd.DataFrame()

    all_jobs: List[Dict[str, Any]] = []

    def _worker(site_name: str) -> List[Dict[str, Any]]:
        fn = _SCRAPER_MAP.get(site_name)
        if not fn:
            return []
        try:
            return fn(search_term=search_term, location=location, results_wanted=results_per_site)
        except Exception as exc:
            logger.warning("Error scraping site %s: %s", site_name, exc)
            return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, len(target_sites))) as executor:
        futures = {executor.submit(_worker, s): s for s in target_sites}
        for fut in concurrent.futures.as_completed(futures):
            site_name = futures[fut]
            try:
                res = fut.result()
                logger.info("OffCampus: Fetched %d listings from %s", len(res), site_name)
                all_jobs.extend(res)
            except Exception as exc:
                logger.warning("Site %s failed completely: %s", site_name, exc)

    if not all_jobs:
        return pd.DataFrame()
    return pd.DataFrame(all_jobs)
