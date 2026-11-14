"""Dynamic multi-strategy search and extraction engine for company interview questions and project details.

Operates on-the-spot for any company and role. Uses resilient search via ddgs
with fallback to domain-specific queries, checks robots.txt, and extracts
structured evidence using httpx and BeautifulSoup.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS

ROOT = Path(__file__).resolve().parent
CATALOG_PATH = ROOT / "source_catalog.json"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 18.0
PACING_DELAY = 0.8
MAX_PAGE_CHARS = 1_500_000

logger = logging.getLogger("company_search.dynamic")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def clean_text(text: str, limit: int = 2000) -> str:
    """Normalize whitespace and truncate."""
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def get_catalog() -> dict[str, Any]:
    if CATALOG_PATH.exists():
        try:
            return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"interview_sources": [], "official_project_sources": []}


def get_approved_domains(category: str = "interview") -> list[str]:
    cat = get_catalog()
    key = "interview_sources" if category == "interview" else "official_project_sources"
    domains = [
        item["domain"].lower().strip()
        for item in cat.get(key, [])
        if item.get("approved")
    ]
    if category == "interview" and not domains:
        domains = [
            "geeksforgeeks.org",
            "interviewexperiences.in",
            "ambitionbox.com",
            "boardinfinity.com",
            "prepinsta.com",
        ]
    return domains


def is_host_approved(url: str, category: str = "interview") -> bool:
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    allowed = get_approved_domains(category)
    return any(host == d or host.endswith("." + d) for d in allowed)


@dataclass
class SearchResultHit:
    engine: str
    query: str
    category: str  # "interview" or "project"
    title: str
    url: str
    snippet: str = ""


class PublicFetcher:
    """Polite HTTP client enforcing robots.txt and safe redirects."""

    def __init__(self, user_agent: str = DEFAULT_UA) -> None:
        self.ua = user_agent
        self.client = httpx.Client(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=False,
            headers={
                "User-Agent": self.ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        self.robots_cache: dict[str, tuple[RobotFileParser | None, str]] = {}
        self.last_req_time = 0.0

    def is_robots_allowed(self, url: str) -> tuple[bool, str]:
        p = urlsplit(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin not in self.robots_cache:
            robots_url = f"{origin}/robots.txt"
            try:
                r = self.client.get(robots_url)
                if r.status_code == 404:
                    self.robots_cache[origin] = (None, "robots.txt 404")
                elif r.status_code >= 400:
                    self.robots_cache[origin] = (None, f"robots.txt HTTP {r.status_code}; fail closed")
                else:
                    rfp = RobotFileParser(robots_url)
                    rfp.parse(r.text.splitlines())
                    self.robots_cache[origin] = (rfp, "robots.txt checked")
            except Exception as exc:
                self.robots_cache[origin] = (None, f"robots fetch error: {type(exc).__name__}")

        parser, note = self.robots_cache[origin]
        if parser is None:
            return note == "robots.txt 404", note
        return parser.can_fetch(self.ua, url), note

    def fetch_html(self, url: str, allowed_domains: Optional[list[str]] = None) -> tuple[Optional[int], str, str]:
        curr = url
        try:
            for _ in range(5):
                if allowed_domains:
                    host = (urlsplit(curr).hostname or "").lower().rstrip(".")
                    if not any(host == d or host.endswith("." + d) for d in allowed_domains):
                        return None, "", "Redirect host outside allowed list"

                allowed, rnote = self.is_robots_allowed(curr)
                if not allowed:
                    return None, "", f"Skipped by robots policy ({rnote})"

                delay = PACING_DELAY - (time.monotonic() - self.last_req_time)
                if delay > 0:
                    time.sleep(delay)

                res = self.client.get(curr)
                self.last_req_time = time.monotonic()

                if res.status_code in {301, 302, 303, 307, 308}:
                    loc = res.headers.get("location")
                    if not loc:
                        return res.status_code, "", "Redirect missing Location header"
                    curr = loc
                    if curr.startswith("/"):
                        p = urlsplit(str(res.url))
                        curr = f"{p.scheme}://{p.netloc}{curr}"
                    continue

                if res.status_code >= 400:
                    return res.status_code, "", f"HTTP {res.status_code}"

                content_type = res.headers.get("content-type", "").lower()
                if "html" not in content_type:
                    return res.status_code, "", f"Non-HTML content type ({content_type})"

                return res.status_code, res.text[:MAX_PAGE_CHARS], "Fetched successfully"
            return None, "", "Exceeded maximum redirects"
        except Exception as exc:
            return None, "", f"Fetch error: {type(exc).__name__}"

    def close(self) -> None:
        self.client.close()


def extract_content(html: str, category: str = "interview") -> dict[str, Any]:
    """Parse HTML and extract meaningful text, headings, and excerpts."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("script, style, noscript, svg, header, footer, nav, form, iframe, button"):
        tag.decompose()

    page_title = clean_text(soup.title.get_text(" ", strip=True) if soup.title else "", 300)

    # Collect headings and main text
    headings = [clean_text(h.get_text(" ", strip=True), 300) for h in soup.select("h1, h2, h3, h4, strong") if len(h.get_text(strip=True)) > 4]
    
    nodes = soup.select("article p, article li, main p, main li, .interview-experience p, .interview-experience li, p, li")
    raw_lines = [clean_text(n.get_text(" ", strip=True), 1500) for n in nodes]
    unique_lines = list(dict.fromkeys(line for line in raw_lines if len(line) >= 20))

    if category == "interview":
        cues = re.compile(
            r"\?|questions? asked|round \d|technical round|hr round|managerial round|"
            r"describe|explain|tell (?:me|us)|how would you|what is|coding challenge|"
            r"online assessment|aptitude|difficulty|interview experience|package|selection",
            re.I,
        )
    else:
        cues = re.compile(
            r"case study|client story|project|solution|architecture|challenge|"
            r"result|technologies used|tech stack|cloud|data pipeline|automation|analytics|service",
            re.I,
        )

    matched_excerpts = [line for line in unique_lines if cues.search(line)][:35]
    if not matched_excerpts:
        matched_excerpts = unique_lines[:20]

    # Combine top clean text for the LLM context window
    full_text_sample = "\n".join(headings[:10] + unique_lines[:50])

    return {
        "title": page_title,
        "headings": headings[:15],
        "excerpts": matched_excerpts,
        "full_text_sample": full_text_sample[:8000],
        "visible_text_chars": sum(len(line) for line in unique_lines),
    }


def execute_ddgs_search(query: str, max_results: int = 6) -> list[dict[str, str]]:
    """Execute search query using ddgs with error handling."""
    results = []
    try:
        ddgs = DDGS()
        raw = list(ddgs.text(query, max_results=max_results))
        for r in raw:
            title = clean_text(r.get("title", ""), 300)
            href = str(r.get("href", "")).strip()
            snippet = clean_text(r.get("body", "") or r.get("snippet", ""), 600)
            if href and title:
                results.append({"title": title, "url": href, "snippet": snippet})
    except Exception as exc:
        logger.warning(f"DDGS search query '{query}' warning: {exc}")
    return results


def search_interview_sources(company: str, role: str, max_sources: int = 5) -> list[SearchResultHit]:
    """Search for candidate interview experiences and questions dynamically."""
    hits: list[SearchResultHit] = []
    seen_urls: set[str] = set()

    approved_domains = get_approved_domains("interview")

    # Multi-tier targeted search queries
    queries = [
        f'site:interviewexperiences.in "{company}" interview',
        f'site:geeksforgeeks.org "{company}" interview experience',
        f'site:geeksforgeeks.org "{company}" "{role}" interview',
        f'site:ambitionbox.com "{company}" interview questions',
        f'"{company}" "{role}" interview questions asked experience',
        f'"{company}" interview questions answers fresher experience',
    ]

    for q in queries:
        if len(hits) >= max_sources:
            break
        raw_items = execute_ddgs_search(q, max_results=4)
        for item in raw_items:
            url = item["url"]
            if url in seen_urls:
                continue

            host = (urlsplit(url).hostname or "").lower().rstrip(".")
            is_approved = any(host == d or host.endswith("." + d) for d in approved_domains)

            # Filter out non-interview social media
            if any(b in host for b in ["youtube.com", "facebook.com", "twitter.com", "instagram.com"]):
                continue

            # Keep the fixed source policy strict: a URL that merely contains
            # "interview" is not sufficient approval for a fetch.
            if is_approved:
                seen_urls.add(url)
                hits.append(
                    SearchResultHit(
                        engine="ddgs",
                        query=q,
                        category="interview",
                        title=item["title"],
                        url=url,
                        snippet=item["snippet"],
                    )
                )
                if len(hits) >= max_sources:
                    break
        time.sleep(0.3)

    return hits


def search_project_sources(company: str, role: str, max_sources: int = 4) -> list[SearchResultHit]:
    """Search for company projects, engineering case studies, and tech stack details."""
    hits: list[SearchResultHit] = []
    seen_urls: set[str] = set()

    queries = [
        f'"{company}" case studies client stories projects solutions',
        f'"{company}" technology stack engineering architecture products',
        f'"{company}" client success stories official',
    ]

    for q in queries:
        if len(hits) >= max_sources:
            break
        raw_items = execute_ddgs_search(q, max_results=4)
        for item in raw_items:
            url = item["url"]
            if url in seen_urls:
                continue

            host = (urlsplit(url).hostname or "").lower().rstrip(".")
            if any(b in host for b in ["youtube.com", "facebook.com", "twitter.com", "instagram.com", "wikipedia.org"]):
                continue

            seen_urls.add(url)
            hits.append(
                SearchResultHit(
                    engine="ddgs",
                    query=q,
                    category="project",
                    title=item["title"],
                    url=url,
                    snippet=item["snippet"],
                )
            )
            if len(hits) >= max_sources:
                break
        time.sleep(0.3)

    return hits


def run_dynamic_company_research(
    company: str,
    role: str,
    max_interview_sources: int = 4,
    max_project_sources: int = 3,
) -> dict[str, Any]:
    """
    Main entry point for on-the-spot company research.
    Searches and extracts interview reports and company project profiles dynamically.
    """
    company_clean = clean_text(company, 120)
    role_clean = clean_text(role, 120)
    logger.info(f"Starting dynamic research for Company: '{company_clean}', Role: '{role_clean}'...")

    fetcher = PublicFetcher()
    interview_hits = search_interview_sources(company_clean, role_clean, max_sources=max_interview_sources)
    project_hits = search_project_sources(company_clean, role_clean, max_sources=max_project_sources)

    interview_pages = []
    for hit in interview_hits:
        logger.info(f"Fetching interview source: {hit.url}")
        status, html, note = fetcher.fetch_html(
            hit.url,
            allowed_domains=get_approved_domains("interview"),
        )
        content = extract_content(html, "interview") if html else {"title": hit.title, "headings": [], "excerpts": [], "full_text_sample": "", "visible_text_chars": 0}
        interview_pages.append({
            **asdict(hit),
            "http_status": status,
            "fetch_note": note,
            **content,
        })

    project_pages = []
    for hit in project_hits:
        logger.info(f"Fetching project source: {hit.url}")
        status, html, note = fetcher.fetch_html(hit.url)
        content = extract_content(html, "project") if html else {"title": hit.title, "headings": [], "excerpts": [], "full_text_sample": "", "visible_text_chars": 0}
        project_pages.append({
            **asdict(hit),
            "http_status": status,
            "fetch_note": note,
            **content,
        })

    fetcher.close()

    total_extracted = sum(len(p["excerpts"]) for p in interview_pages) + sum(len(p["excerpts"]) for p in project_pages)
    logger.info(f"Dynamic research finished: {len(interview_pages)} interview sources, {len(project_pages)} project sources, {total_extracted} total text excerpts.")

    return {
        "company": company_clean,
        "role": role_clean,
        "interview_sources": interview_pages,
        "project_sources": project_pages,
        "total_sources_gathered": len(interview_pages) + len(project_pages),
        "total_excerpts": total_extracted,
    }
