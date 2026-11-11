"""
HR Contact & Domain Enrichment Engine
--------------------------------------
Discovers and extracts HR, talent acquisition, and careers contact details
for hiring companies scraped from job boards.

Outputs:
- hr_leads_latest.json
- Appends to formatted Excel HR Calling Sheet
"""

import re
import urllib.parse
from typing import Dict, Any, List, Optional
import requests

GENERIC_HR_PREFIXES = ["careers", "hr", "talent", "recruitment", "hiring", "jobs"]

def clean_company_name(name: str) -> str:
    """Removes legal suffixes and noise from company names."""
    if not name:
        return ""
    cleaned = re.sub(
        r"(?i)\b(pvt\.?|ltd\.?|private|limited|llc|inc\.?|technologies|solutions|services|infotech|corp\.?|corporation|group)\b",
        "",
        name,
    )
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return " ".join(cleaned.split()).strip()

def guess_company_domain(company_name: str) -> str:
    """Derives a likely domain name from the company name."""
    clean = clean_company_name(company_name).lower()
    slug = re.sub(r"\s+", "", clean)
    if not slug:
        return ""
    return f"{slug}.com"

def generate_google_dork_links(company_name: str, city: str = "India") -> Dict[str, str]:
    """
    Generates exact Google Search Dork queries for telecallers to find HR
    names and phone numbers in 1 click.
    """
    clean = clean_company_name(company_name)
    linkedin_hr_dork = f'site:linkedin.com/in ("HR" OR "Talent Acquisition" OR "Recruiter") "{clean}" "{city}"'
    phone_dork = f'"{clean}" ("HR" OR "Careers" OR "Office") ("contact number" OR "phone" OR "+91")'
    
    return {
        "linkedin_hr_search_url": f"https://www.google.com/search?q={urllib.parse.quote(linkedin_hr_dork)}",
        "phone_search_url": f"https://www.google.com/search?q={urllib.parse.quote(phone_dork)}",
    }

def enrich_job_with_hr(job: Dict[str, Any], hunter_api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Enriches a single job listing with HR email, company domain, and 1-click HR search links.
    """
    company = job.get("company", "").strip()
    location = job.get("location", "India")
    domain = guess_company_domain(company)
    
    hr_email = ""
    hr_phone = ""
    confidence = "Pattern"
    
    # 1. Check if description has an email explicitly mentioned
    desc = job.get("description", "") or ""
    found_emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", desc)
    valid_emails = [
        e for e in found_emails 
        if not e.endswith(".png") and not e.endswith(".jpg") and not "example" in e
    ]
    
    if valid_emails:
        hr_email = valid_emails[0]
        confidence = "Direct from Posting"
    
    # 2. Check if description has an Indian mobile / phone number
    found_phones = re.findall(r"(?:(?:\+?91[\-\s]?)?[6789]\d{9})", desc)
    if found_phones:
        hr_phone = found_phones[0]
        
    # 3. If hunter_api_key is provided and domain exists, query Hunter free domain search
    if not hr_email and hunter_api_key and domain:
        try:
            url = f"https://api.hunter.io/v2/domain-search?domain={domain}&department=human_resources&api_key={hunter_api_key}"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                emails = data.get("emails", [])
                if emails:
                    first = emails[0]
                    hr_email = first.get("value", "")
                    confidence = "Hunter.io Verified"
        except Exception:
            pass
            
    # 4. Fallback pattern if no direct email found
    if not hr_email and domain:
        hr_email = f"careers@{domain}"
        confidence = "Inferred Pattern"

    dorks = generate_google_dork_links(company, location)
    
    return {
        "company": company,
        "job_title": job.get("title", ""),
        "location": location,
        "tech_category": job.get("tech_category", "Tech"),
        "hr_email": hr_email,
        "hr_phone": hr_phone,
        "hr_source": confidence,
        "apply_url": job.get("job_url_direct") or job.get("job_url", ""),
        "source": job.get("site", ""),
        "date_posted": job.get("date_posted", ""),
        "linkedin_hr_search": dorks["linkedin_hr_search_url"],
        "phone_search": dorks["phone_search_url"],
        "call_status": "Pending",
        "telecaller_notes": ""
    }

def process_hr_enrichment(jobs: List[Dict[str, Any]], hunter_api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """Enriches a deduplicated list of hiring companies."""
    seen_companies = set()
    hr_records = []
    
    for job in jobs:
        comp = job.get("company", "").strip().lower()
        if not comp or comp in seen_companies:
            continue
        seen_companies.add(comp)
        
        enriched = enrich_job_with_hr(job, hunter_api_key)
        hr_records.append(enriched)
        
    return hr_records
