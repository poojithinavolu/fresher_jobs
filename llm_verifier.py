"""
LLM Verifier & Skills Curator Module
====================================
Acts as the final intelligent gatekeeper for fresher jobs:
1. Extracts relevant requirements, qualifications, responsibilities, and experience sections from JDs.
2. Prompts LLM to strictly verify whether the role is genuine fresher (0 prior experience / 0-1 yr).
3. If experienced (>1 yr or prior professional work required), rejects the job.
4. If fresher, curates a concise list of concrete technical and domain skills (without fluff).
"""

import os
import re
import json
import logging
from typing import Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
logger = logging.getLogger("LLMVerifier")

_CACHED_LLM = None


def get_llm():
    """Returns an active LangChain ChatModel (Groq or OpenRouter)."""
    global _CACHED_LLM
    if _CACHED_LLM is not None:
        return _CACHED_LLM

    # Try Groq first (high RPM, 500 tok/s LPU inference, 100% free tier)
    groq_key = os.getenv("GROQ_API_KEY", "").strip().lstrip("#")
    if groq_key and not groq_key.startswith("YOUR_"):
        try:
            from langchain_openai import ChatOpenAI
            model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
            _CACHED_LLM = ChatOpenAI(
                api_key=groq_key,
                base_url="https://api.groq.com/openai/v1",
                model=model,
                temperature=0.1,
                max_tokens=600,
            )
            logger.info("Initialized Groq ChatOpenAI LLM: %s", model)
            return _CACHED_LLM
        except Exception as exc:
            logger.warning("Failed to initialize Groq ChatOpenAI: %s", exc)

    # Try OpenRouter as secondary option
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if openrouter_key and not openrouter_key.startswith("YOUR_") and not openrouter_key.startswith("#"):
        if not openrouter_key.startswith("sk-or-"):
            openrouter_key = f"sk-or-v1-{openrouter_key}"
        try:
            from langchain_openai import ChatOpenAI
            model = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
            _CACHED_LLM = ChatOpenAI(
                api_key=openrouter_key,
                base_url="https://openrouter.ai/api/v1",
                model=model,
                temperature=0.1,
                max_tokens=500,
                default_headers={
                    "HTTP-Referer": "https://github.com/placement-prep/fresher-job-scraper",
                    "X-Title": "Fresher Job Intelligence Scraper",
                },
            )
            logger.info("Initialized OpenRouter LLM: %s", model)
            return _CACHED_LLM
        except Exception as exc:
            logger.warning("Failed to initialize OpenRouter ChatOpenAI: %s", exc)

    return None


def extract_requirements_and_skills_context(description: str, max_chars: int = 3500) -> str:
    """
    Extracts the key requirements, skills, qualifications, responsibilities,
    and experience sections from a raw job description, stripping corporate boilerplate.
    """
    if not description or not str(description).strip():
        return ""

    text = str(description).strip()
    if "<" in text and ">" in text:
        text = BeautifulSoup(text, "html.parser").get_text(separator="\n", strip=True)

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""

    section_keywords = [
        "requirement", "qualification", "responsibilit", "what you", "who you",
        "skill", "experience", "eligibility", "role overview", "role description",
        "duties", "profile", "must have", "good to have", "nice to have", "technical stack"
    ]

    boilerplate_markers = [
        "equal opportunity employer", "eeo is the law", "reasonable accommodation",
        "background check", "color, religion, sex", "sexual orientation, gender identity",
        "physical demands", "work environment", "veteran status", "about amgen",
        "about persistent", "about cognizant", "about wipro", "about infosys", "about accenture"
    ]

    captured_lines = []
    in_relevant_section = False

    for line in lines:
        clean_line = re.sub(r"^[*#-]+|\*\*|:", "", line).strip()
        lower_line = clean_line.lower()

        if any(b in lower_line for b in boilerplate_markers):
            in_relevant_section = False
            continue

        if len(clean_line) < 65 and any(k in lower_line for k in section_keywords):
            in_relevant_section = True
            captured_lines.append(f"\n### {clean_line}")
            continue

        if len(clean_line) < 65 and any(k in lower_line for k in [
            "about us", "about company", "about the company", "benefits", "perks",
            "compensation", "why join", "equal opportunity"
        ]):
            in_relevant_section = False
            continue

        if in_relevant_section:
            captured_lines.append(line)

    extracted_text = "\n".join(captured_lines).strip()

    # Fallback if specific sections were not isolated
    if len(extracted_text) < 250:
        filtered_lines = [
            l for l in lines
            if not any(b in l.lower() for b in boilerplate_markers)
        ]
        extracted_text = "\n".join(filtered_lines)

    return extracted_text[:max_chars].strip()


SYSTEM_GATEKEEPER_PROMPT = """You are an expert technical recruitment gatekeeper for FRESHER job roles (strictly 0 to 1 year experience, zero prior work experience required).

Rules:
1. "is_fresher_eligible":
   - Set to TRUE if the role accepts freshers (0 prior experience), fresh graduates, trainees, interns, or 0-1 years experience, OR if NO prior professional work experience requirement is stated in the description.
   - Set to FALSE if the description requires prior professional experience beyond freshers (e.g., "1+ year", "minimum 1-2 years", "2+ years", "3-5 years", "prior work experience in production environment required").
2. "curated_skills":
   - Extract a clean, concise, comma-separated list of ONLY concrete technical skills, tools, programming languages, and functional domain competencies (e.g., "Python, SQL, Tableau, Advanced Excel, Data Modeling").
   - Strictly omit buzzwords like "good communication", "team player", "proactive", "motivated", "detail-oriented".

Respond ONLY with a valid JSON object matching:
{
  "is_fresher_eligible": true or false,
  "experience_detected": "string summary",
  "rejection_reason": "string or null",
  "curated_skills": "Skill 1, Skill 2, Skill 3"
}
"""


def extract_fallback_skills(text: str, title: str = "", role: str = "") -> str:
    """Extracts concrete technical skills and tools from text or role fallback."""
    found = []
    combined = f"{title} {role} {text}".lower()

    tech_keywords = [
        ("Python", r"\bpython\b"),
        ("SQL", r"\bsql\b"),
        ("Advanced Excel", r"\b(?:advanced\s+)?excel\b"),
        ("Power BI", r"\bpower\s*bi\b"),
        ("Tableau", r"\btableau\b"),
        ("JavaScript", r"\bjavascript\b|\bjs\b"),
        ("React", r"\breact(?:\.js)?\b"),
        ("Node.js", r"\bnode(?:\.js)?\b"),
        ("Java", r"\bjava\b"),
        ("C++", r"\bc\+\+\b"),
        ("HTML/CSS", r"\bhtml\b|\bcss\b"),
        ("Git", r"\bgit\b"),
        ("REST APIs", r"\brest(?:ful)?\s*api[s]?\b"),
        ("Pandas", r"\bpandas\b"),
        ("NumPy", r"\bnumpy\b"),
        ("AWS", r"\baws\b|\bamazon\s+web\s+services\b"),
        ("Azure", r"\bazure\b"),
        ("Docker", r"\bdocker\b"),
        ("Linux", r"\blinux\b"),
        ("JIRA", r"\bjira\b"),
        ("Agile", r"\bagile\b|\bscrum\b"),
        ("VLOOKUP/HLOOKUP", r"\bvlookup\b|\bhlookup\b"),
        ("Data Analysis", r"\bdata\s+analy(?:sis|tics)\b"),
        ("Data Modeling", r"\bdata\s+model(?:ing)?\b"),
        ("ETL", r"\betl\b"),
        ("KYC/AML", r"\bkyc\b|\baml\b"),
        ("Requirements Gathering", r"\brequirement[s]?\s+gathering\b"),
        ("BRD/FRD", r"\bbrd\b|\bfrd\b"),
        ("Quality Assurance", r"\bqa\b|\bquality\s+assurance\b|\btesting\b"),
    ]

    for label, pattern in tech_keywords:
        if re.search(pattern, combined, re.IGNORECASE):
            found.append(label)

    if found:
        return ", ".join(found[:8])

    t_lower = f"{title} {role}".lower()
    if "data" in t_lower:
        return "Python, SQL, Advanced Excel, Data Analysis, Power BI, Tableau"
    elif "web" in t_lower or "developer" in t_lower or "frontend" in t_lower or "backend" in t_lower:
        return "HTML, CSS, JavaScript, React, Node.js, Git, REST APIs"
    elif "business" in t_lower:
        return "Requirements Gathering, BRD/FRD, Advanced Excel, Process Modeling, Agile, JIRA"
    elif "tax" in t_lower or "accounting" in t_lower or "finance" in t_lower:
        return "Financial Reporting, Tax Compliance, Advanced Excel, General Ledger, Auditing"
    elif "qa" in t_lower or "quality" in t_lower or "test" in t_lower:
        return "Manual Testing, Test Cases, Quality Assurance, JIRA, Bug Tracking, Regression Testing"
    else:
        return "Analytical Problem Solving, Microsoft Excel, Data Validation, Reporting, Process Documentation"


def verify_fresher_and_curate_skills(
    description: str,
    title: str = "",
    company: str = "",
    llm: Any = None,
) -> Dict[str, Any]:
    """
    Evaluates a job description with LLM to strictly ensure fresher eligibility
    and curate a clean list of required skills.
    """
    context = extract_requirements_and_skills_context(description)
    if not context or len(context) < 80:
        # Insufficient text to run deep LLM analysis; rely on rule-based defaults
        return {
            "is_fresher_eligible": True,
            "experience_detected": "Unspecified in text",
            "rejection_reason": None,
            "curated_skills": extract_fallback_skills(description, title=title),
        }

    active_llm = llm or get_llm()
    if active_llm is None:
        logger.warning("No LLM available for fresher verification; skipping LLM gate.")
        return {
            "is_fresher_eligible": True,
            "experience_detected": "LLM not configured",
            "rejection_reason": None,
            "curated_skills": extract_fallback_skills(context, title=title),
        }

    from langchain_core.messages import SystemMessage, HumanMessage

    user_content = f"Job Title: {title}\nCompany: {company}\n\nJob Description Excerpt:\n{context}"
    try:
        response = active_llm.invoke([
            SystemMessage(content=SYSTEM_GATEKEEPER_PROMPT),
            HumanMessage(content=user_content),
        ])
        raw_text = response.content.strip()

        # Extract JSON from response
        json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            is_eligible = bool(data.get("is_fresher_eligible", True))
            
            skills_val = data.get("curated_skills", "")
            if isinstance(skills_val, list):
                skills = ", ".join(str(s).strip() for s in skills_val if str(s).strip())
            elif isinstance(skills_val, dict):
                skills = ", ".join(f"{k}: {v}" for k, v in skills_val.items())
            else:
                skills = str(skills_val or "").strip()
            
            skills = re.sub(r"^[*\-•\s]+", "", skills)
            skills = re.sub(r"\n+[*\-•\s]*", ", ", skills)
            skills = re.sub(r",\s*,+", ", ", skills).strip(" ,")

            if not skills:
                skills = extract_fallback_skills(context, title=title)

            exp_det = str(data.get("experience_detected", "") or "").strip()
            reason = data.get("rejection_reason")

            return {
                "is_fresher_eligible": is_eligible,
                "experience_detected": exp_det,
                "rejection_reason": reason if not is_eligible else None,
                "curated_skills": skills,
            }
    except Exception as exc:
        logger.error("LLM verification call failed: %s", exc)

    return {
        "is_fresher_eligible": True,
        "experience_detected": "Evaluation exception",
        "rejection_reason": None,
        "curated_skills": extract_fallback_skills(context, title=title),
    }


def hydrate_job_description(job: Dict[str, Any]) -> str:
    """
    Hydrates the job description for a job dictionary from Naukri, LinkedIn, or Indeed
    if not already present.
    """
    existing_desc = str(job.get("description") or "").strip()
    if len(existing_desc) > 150:
        return existing_desc

    site = str(job.get("site") or "").lower()
    apply_url = str(job.get("apply_url") or job.get("job_url_direct") or job.get("job_url") or "")
    job_id = str(job.get("id") or "")

    # 1. Naukri Hydration
    if site == "naukri" or "naukri.com" in apply_url:
        numeric_id = ""
        # Extract numeric id from URL (e.g. ...-0-to-1-years-131126011049)
        url_match = re.search(r"(\d{10,14})$", apply_url.rstrip("/"))
        if url_match:
            numeric_id = url_match.group(1)
        elif job_id.replace("nk-", "").isdigit():
            numeric_id = job_id.replace("nk-", "")

        if numeric_id:
            try:
                from curl_cffi import requests as cffi_requests
                from jobspy.naukri.constant import job_page_headers
                from jobspy.naukri import generate_nkparam
                session = cffi_requests.Session(impersonate="chrome")
                url = f"https://www.naukri.com/jobapi/v4/job/{numeric_id}"
                headers = job_page_headers | {"nkparam": generate_nkparam(str(numeric_id))}
                res = session.get(url, headers=headers, timeout=8)
                if res.status_code == 200:
                    data = res.json().get("jobDetails", {})
                    desc_html = data.get("description", "")
                    clean_desc = BeautifulSoup(desc_html, "html.parser").get_text(separator="\n", strip=True)
                    if clean_desc:
                        job["description"] = clean_desc
                        return clean_desc
            except Exception as e:
                logger.debug("Naukri hydration failed for %s: %s", numeric_id, e)

    # 2. LinkedIn Hydration
    if site == "linkedin" or "linkedin.com" in apply_url:
        li_id = ""
        m = re.search(r"/view/(\d+)", apply_url)
        if m:
            li_id = m.group(1)
        elif job_id.replace("li-", "").isdigit():
            li_id = job_id.replace("li-", "")

        if li_id:
            try:
                import requests
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{li_id}"
                res = requests.get(url, headers=headers, timeout=8)
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, "html.parser")
                    desc_div = soup.find("div", class_="show-more-less-html__markup")
                    if desc_div:
                        clean_desc = desc_div.get_text(separator="\n", strip=True)
                        job["description"] = clean_desc
                        return clean_desc
            except Exception as e:
                logger.debug("LinkedIn hydration failed for %s: %s", li_id, e)

    return existing_desc
