"""
Configuration for the Fresher Job Scraper
=========================================
Centralized settings for locations, target roles, search queries, 
freshness lookback, and anti-scam/training blacklists.
"""

import os
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass
from typing import List, Dict

# Maximum age of jobs to keep in hours (20 = last 20 hours)
MAX_HOURS_OLD: int = 20

# Target job boards (all 100% free via JobSpy)
# JobSpy 1.4.x supports these boards. Monster India / JobsAhead is not a
# JobSpy adapter and is reported as unsupported instead of silently claimed.
TARGET_SITES: List[str] = ["naukri", "indeed", "linkedin"]
UNSUPPORTED_SITES: List[str] = ["monsterindia (JobsAhead)"]

# Target locations (India)
DEFAULT_LOCATIONS: List[str] = ["Mumbai", "Hyderabad"]

# Country code for Indeed
INDEED_COUNTRY: str = "india"

# Maximum raw results to fetch per (query, location, site) combination
# 25 ensures single-page sub-second retrieval without multi-page delay loops or rate limits.
RESULTS_PER_QUERY: int = 25

# Pacing delay between queries in seconds (helps avoid rate limits)
QUERY_DELAY_SECONDS: float = 1.0
# Run three independent query/location jobs at a time.
QUERY_CONCURRENCY: int = 3
# Optional rotating proxy list for boards that rate-limit this network.
JOBSPY_PROXIES: List[str] = [
    proxy.strip() for proxy in os.getenv("JOBSPY_PROXIES", "").split(",") if proxy.strip()
]

# Requested fresher job families with high-yield search terms
ROLE_QUERIES: Dict[str, List[str]] = {
    "Business Analyst": [
        "business analyst", "junior business analyst", "business analyst fresher",
    ],
    "Data Analyst": [
        "data analyst", "junior data analyst", "data analyst fresher",
    ],
    "Marketing Analyst": [
        "marketing analyst", "junior marketing analyst", "marketing analyst fresher",
    ],
    "HR Analyst": [
        "HR analyst", "junior HR analyst", "HR analyst fresher",
    ],
    "Analyst": [
        "analyst", "junior analyst", "trainee analyst", "analyst fresher",
    ],
    "Full Stack Developer": [
        "full stack developer", "junior full stack developer", "full stack developer fresher",
        "associate software engineer", "software engineer trainee",
    ],
    "Web Developer": [
        "web developer", "junior web developer", "web developer fresher",
        "frontend developer fresher", "react developer fresher",
    ],
}

# Maximum years of experience allowed.
# Jobs requiring strictly more than this will be filtered out.
MAX_ALLOWED_EXPERIENCE_YEARS: float = 1.0

# Forbidden title keywords (indicates senior / experienced / non-fresher roles)
FORBIDDEN_TITLE_KEYWORDS: List[str] = [
    "senior", "sr", "lead", "leader", "principal", "architect",
    "manager", "head", "director", "vp", "vice president", "specialist",
    "chief", "staff engineer", "expert", "consultant 2", "mid-level",
    "mid level", "level 2", "level 3", "2+", "3+", "4+", "5+", "6+", "7+",
    "8+", "9+", "10+", "years experience"
]

# Forbidden job levels in platform metadata
FORBIDDEN_JOB_LEVELS: List[str] = [
    "mid_senior", "director", "executive", "associate_director"
]


# Common training institutes, coaching centers, fee-charging consultancies,
# unpaid scam centers, and deceptive recruiters in India that spam job boards.
COMPANY_BLACKLIST: List[str] = [
    # Prominent Edtech & Training Institutes posing as employers
    "internshala", "unacademy", "byjus", "byju's", "whitehat jr", "vedantu",
    "toppr", "upgrad", "upgrade", "simplilearn", "edureka", "intellipaat",
    "great learning", "scaler", "newton school", "alma better", "almabetter",
    "masai school", "coding ninjas", "geekster", "acciojob", "crio.do",
    
    # Well-known training/placement fee institutes in Mumbai & Hyderabad
    "qspiders", "jspiders", "pyspiders", "naresh i technologies", "naresh it",
    "durga software", "durga soft", "besant technologies", "apponix",
    "ethnus", "kelly technologies", "sla consultants", "croma campus",
    "sevenmentor", "fita academy", "cetpa", "actalent training",
    
    # Generic spam & deceptive training markers
    "training institute", "coaching institute", "it academy",
    "learning solutions", "skills academy", "training center",
    "training centre", "finishing school", "placement guarantee",
    "job guarantee", "hire and train", "train and hire",
    "edtech", "edutech"
]

# Words in title or description that signal deceptive, unpaid, or training-fee postings
FORBIDDEN_DESCRIPTION_PATTERNS: List[str] = [
    "registration fee",
    "training fee",
    "security deposit",
    "pay after placement",
    "unpaid internship",
    "unpaid intern",
    "no stipend",
    "commission only",
    "earn from home data entry",
    "sms sending job",
    "part time form filling",
    "captcha typing"
]
