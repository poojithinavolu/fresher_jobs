"""
Unit Tests for Cross-Site Deduplication Engine
==============================================
Verifies normalization rules, canonical URL extraction, cross-site matching,
and intelligent record merging.
"""
import pytest
from dedup_engine import (
    normalize_company,
    normalize_title,
    normalize_city,
    canonical_url,
    compute_cross_site_key,
    are_titles_similar,
    deduplicate_jobs,
)


def test_normalize_company():
    assert normalize_company("MountBlue Technologies Pvt Ltd") == "mountblue"
    assert normalize_company("Deloitte India") == "deloitte"
    assert normalize_company("Tata Communications Private Limited") == "tatacommunications"
    assert normalize_company("Acme Infotech Services Inc.") == "acme"
    assert normalize_company("eLitmus Evaluation Pvt Ltd") == "elitmus"
    assert normalize_company(None) == ""


def test_normalize_title():
    assert normalize_title("Software Engineer Trainee (Fresher 2026 Batch)", "MountBlue") == "software engineer trainee"
    assert normalize_title("Deloitte Careers 2026 – Analyst Role | Freshers", "Deloitte") == "analyst"
    assert normalize_title("Off Campus Drive 2026: Graduate Engineer Trainee", "TCS") == "graduate engineer trainee"
    assert normalize_title("Junior Web Developer - 0 to 1 Year Experience", "") == "junior web developer"
    assert normalize_title(None) == ""


def test_normalize_city():
    assert normalize_city("Bengaluru, Karnataka") == "bangalore"
    assert normalize_city("Bangalore Urban") == "bangalore"
    assert normalize_city("Gurugram, Haryana") == "gurgaon"
    assert normalize_city("Bombay") == "mumbai"
    assert normalize_city("Hyderabad / Secunderabad") == "hyderabad"
    assert normalize_city("Unknown Small Town") == "india"
    assert normalize_city(None) == "india"


def test_canonical_url():
    url1 = "https://example.com/jobs/123?utm_source=linkedin&utm_medium=feed&ref=banner"
    url2 = "https://example.com/jobs/123"
    assert canonical_url(url1) == canonical_url(url2)
    assert canonical_url("https://www.elitmus.com/jobs/33235?jobs_evaluation=2786") == "https://www.elitmus.com/jobs/33235"
    assert canonical_url(None) == ""


def test_are_titles_similar():
    assert are_titles_similar("software engineer trainee", "software engineer trainee") is True
    assert are_titles_similar("junior full stack developer", "full stack developer trainee", threshold=0.4) is True
    assert are_titles_similar("frontend developer", "backend developer") is False


def test_deduplicate_jobs_cross_site_merging():
    input_jobs = [
        {
            "title": "Software Engineer Trainee",
            "company": "MountBlue Technologies Pvt Ltd",
            "location": "Bangalore",
            "site": "elitmus",
            "job_url": "https://www.elitmus.com/jobs/33235",
            "description": "Short brief description",
        },
        {
            "title": "Software Engineer Trainee (2026 Batch)",
            "company": "MountBlue Technologies",
            "location": "Bengaluru",
            "site": "useastra",
            "job_url": "https://useastra.in/jobs/mountblue-software-engineer-trainee-19283",
            "description": "Full comprehensive job description with all details and skills",
            "salary_min": 401000,
            "salary_max": 401000,
        },
        {
            "title": "Web Developer",
            "company": "InnovalQ Technologies",
            "location": "Coimbatore",
            "site": "unstop",
            "job_url": "https://unstop.com/jobs/web-developer-1795660",
            "description": "Unique listing",
        },
    ]

    deduped, stats = deduplicate_jobs(input_jobs)

    assert stats["total_input"] == 3
    assert stats["unique_output"] == 2
    assert stats["cross_site_duplicates"] == 1
    assert "elitmus" in stats["sources_represented"]
    assert "useastra" in stats["sources_represented"]
    assert "unstop" in stats["sources_represented"]

    # Verify merged record properties
    mountblue_job = next(j for j in deduped if "mountblue" in normalize_company(j["company"]))
    assert "elitmus" in mountblue_job["site"]
    assert "useastra" in mountblue_job["site"]
    assert mountblue_job["cross_site_duplicate"] is True
    assert "Full comprehensive job description" in mountblue_job["description"]
    assert mountblue_job["salary_min"] == 401000
