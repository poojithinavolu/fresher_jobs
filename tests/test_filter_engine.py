"""
Consolidated Unit & Integration Tests for Fresher Job Scraper Filters
====================================================================
Verifies that:
1. Experience parsing correctly accepts 0-1 yrs and rejects > 1 yr.
2. Title blacklist correctly rejects Senior, Lead, Manager titles.
3. Company blacklist correctly rejects training institutes & scams.
4. 48-hour date parser correctly identifies recent vs outdated postings.
5. Role categorization and pipeline evaluation match specifications.
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from filter_engine import (
    is_within_hours,
    is_fresher_job,
    is_legitimate_company,
    is_valid_location,
    resolve_apply_url,
    categorize_role,
    evaluate_job,
)


def test_experience_filtering():
    # Freshers (Must Pass)
    assert is_fresher_job("Data Analyst", "0-6 months")[0] is True
    assert is_fresher_job("Data Analyst", "0-1 Yrs")[0] is True
    assert is_fresher_job("Data Analyst", "0-2 Yrs")[0] is False
    assert is_fresher_job("Data Analyst", "0-12 months")[0] is True
    assert is_fresher_job("Data Analyst", "0-18 months")[0] is False
    assert is_fresher_job("Junior Data Analyst", "Unspecified (entry-level marker only)")[0] is False
    assert is_fresher_job("Junior Developer", "0-0 Yrs")[0] is True
    assert is_fresher_job("Business Analyst", "Fresher")[0] is True
    assert is_fresher_job("MIS Executive", None)[0] is False  # Missing exp is not proof of fresher fit

    # Experienced / Non-Fresher (Must Fail)
    assert is_fresher_job("Data Analyst", "3-4 Yrs")[0] is False
    assert is_fresher_job("Developer", "7-12 Yrs")[0] is False
    assert is_fresher_job("Data Scientist", "12-17 Yrs")[0] is False
    assert is_fresher_job("Business Analyst", "2-5 Yrs")[0] is False
    # Validated strict 0-1 fresher ceiling (0 to 2 years rejected even with Junior title)
    assert is_fresher_job("Junior Support Analyst", "0 to 2 years")[0] is False
    assert is_fresher_job("Junior Support Analyst", "0 to 1 year")[0] is True
    assert is_fresher_job("Data Analyst", None, "We welcome freshers to apply for this entry-level role.")[0] is True
    # Generic title without experience proof must fail even with platform entry_level tag
    assert is_fresher_job("Data Analyst", None, job_level="entry_level")[0] is False
    assert is_fresher_job("Full Stack Developer", None, job_level="entry_level")[0] is False
    assert is_fresher_job("Data Analyst", "0-1 Yrs", job_level="entry_level")[0] is True

    # User reported regression cases:
    # 1. Goldman Sachs 1-3 years
    assert is_fresher_job("Analyst", None, "Requires 1-3 years of relevant experience")[0] is False
    # 2. Turium Ai 5+ years
    assert is_fresher_job("Full Stack Developer", None, "Requires 5+ years of experience in React/Node")[0] is False
    # 3. AIQ Space 1+ year
    assert is_fresher_job("Web Application Developer", None, "Minimum 1 year of experience required")[0] is False
    # 4. HCLTech 3-7 years
    assert is_fresher_job("Frontend Developer", None, "3-7 years experience required")[0] is False
    # 5. Synechron 7-10 years
    assert is_fresher_job("Full Stack Developer", None, "7-10 years of experience in Python/Django")[0] is False
    print(" [OK] Experience filtering tests passed")


def test_title_blacklist():
    # Senior / Lead / Level 2 roles (Must Fail)
    assert is_fresher_job("Senior Data Analyst", "0-1 Yrs")[0] is False
    assert is_fresher_job("Data Analytics Team Lead", "0-1 Yrs")[0] is False
    assert is_fresher_job("Sr. Full Stack Developer", "Fresher")[0] is False
    assert is_fresher_job("Lead MIS Executive", "0-1 Yrs")[0] is False
    assert is_fresher_job("Software Architect", "0-1 Yrs")[0] is False
    assert is_fresher_job("SW Engineer II", None)[0] is False
    assert is_fresher_job("SDE 2", None)[0] is False
    assert is_fresher_job("Data Analyst II", None)[0] is False

    # Legitimate Fresher titles (Must Pass)
    assert is_fresher_job("Data Analyst Fresher", "0-6 months")[0] is True
    assert is_fresher_job("Junior Web Developer", "0-6 months")[0] is True
    assert is_fresher_job("Trainee Business Analyst", "0-6 months")[0] is True
    print(" [OK] Title blacklist tests passed")


def test_company_blacklist():
    # Scam / Training institutes (Must Fail)
    assert is_legitimate_company("Qspiders Technologies")[0] is False
    assert is_legitimate_company("Jspiders Training Institute")[0] is False
    assert is_legitimate_company("Naresh I Technologies")[0] is False
    assert is_legitimate_company("Algorek Edutech")[0] is False
    assert is_legitimate_company("Simplilearn")[0] is False
    assert is_legitimate_company("Besant Technologies")[0] is False

    # Legitimate Employers (Must Pass)
    assert is_legitimate_company("Tata Consultancy Services")[0] is True
    assert is_legitimate_company("Wipro Limited")[0] is True
    assert is_legitimate_company("Infosys")[0] is True
    assert is_legitimate_company("Accenture India")[0] is True
    assert is_legitimate_company("Bristol Myers Squibb", "Analyst – Statutory Reporting")[0] is True
    print(" [OK] Company blacklist tests passed")


def test_date_freshness():
    now = datetime.now()
    yesterday = now - timedelta(hours=24)
    two_days_ago = now - timedelta(hours=47)
    four_days_ago = now - timedelta(hours=96)

    # Within 48 hours (Must Pass)
    assert is_within_hours(now, 48)[0] is True
    assert is_within_hours(yesterday, 48)[0] is True
    assert is_within_hours(two_days_ago, 48)[0] is True

    # More than 48 hours (Must Fail)
    assert is_within_hours(four_days_ago, 48)[0] is False
    print(" [OK] Date freshness (48h) tests passed")


def test_categorization():
    assert categorize_role("Data Analyst Fresher") == "Data Analyst"
    assert categorize_role("Junior Business Analyst") == "Business Analyst"
    assert categorize_role("Marketing Analyst") == "Marketing Analyst"
    assert categorize_role("HR Analyst") == "HR Analyst"
    assert categorize_role("Full Stack Developer (MERN)") == "Full Stack Developer"
    assert categorize_role("Junior Operations Analyst") == "Analyst"
    print(" [OK] Role categorization tests passed")


def test_location_validation():
    # Valid targets (Mumbai & Hyderabad metros, remote)
    assert is_valid_location("Mumbai, India")[0] is True
    assert is_valid_location("Navi Mumbai, India")[0] is True
    assert is_valid_location("Hyderabad, Telangana, India")[0] is True
    assert is_valid_location("TS, India")[0] is True
    assert is_valid_location("Greater Hyderabad Area")[0] is True
    assert is_valid_location("Remote, India")[0] is True
    assert is_valid_location("Work from home")[0] is True

    # Invalid targets (Noida, Pune, Bangalore, etc. without Mumbai/Hyd)
    assert is_valid_location("Noida, India")[0] is False
    assert is_valid_location("Pune, India")[0] is False
    assert is_valid_location("Bengaluru, India")[0] is False
    assert is_valid_location("Delhi, India")[0] is False
    print(" [OK] Location validation tests passed")


def test_apply_url_validation():
    # HTTP URLs
    assert resolve_apply_url({"apply_url": "https://careers.google.com/jobs/123"}) == "https://careers.google.com/jobs/123"
    assert resolve_apply_url({"job_url": "https://naukri.com/jobs/456"}) == "https://naukri.com/jobs/456"

    # LinkedIn numeric ID reconstruction
    assert resolve_apply_url({"site": "linkedin", "id": "4490513867"}) == "https://www.linkedin.com/jobs/view/4490513867"

    # Missing / empty
    assert resolve_apply_url({}) == ""
    assert resolve_apply_url({"id": None}) == ""
    print(" [OK] Apply URL resolution tests passed")


def test_full_pipeline_evaluation():
    # Valid job
    job1 = {
        "title": "Data Analyst Fresher",
        "company": "Tata Consultancy Services",
        "location": "Mumbai",
        "date_posted": datetime.now() - timedelta(hours=10),
        "experience_range": "0-6 months",
        "job_url": "https://linkedin.com/jobs/view/123",
    }
    eval1 = evaluate_job(job1)
    assert eval1["is_valid_fresher_job"] is True
    assert eval1["tech_category"] == "Data Analyst"

    # Invalid job - 7 Yrs experience
    job2 = {
        "title": "Data Analyst",
        "company": "Some Company",
        "location": "Hyderabad",
        "date_posted": datetime.now() - timedelta(hours=5),
        "experience_range": "7-10 Yrs",
        "job_url": "https://naukri.com/jobs/view/456",
    }
    eval2 = evaluate_job(job2)
    assert eval2["is_valid_fresher_job"] is False
    assert "exceeds fresher limit" in eval2["rejection_reason"]

    # Invalid job - Training company
    job3 = {
        "title": "Web Developer Fresher",
        "company": "Naresh I Technologies",
        "location": "Hyderabad",
        "date_posted": datetime.now() - timedelta(hours=2),
        "experience_range": "0-1 Yrs",
        "job_url": "https://indeed.com/view/789",
    }
    eval3 = evaluate_job(job3)
    assert eval3["is_valid_fresher_job"] is False
    assert "blacklist" in eval3["rejection_reason"]

    # Invalid job - Noida location (outside target region)
    job4 = {
        "title": "Data Analyst Fresher",
        "company": "Tata Consultancy Services",
        "location": "Noida, India",
        "date_posted": datetime.now() - timedelta(hours=2),
        "experience_range": "0-1 Yrs",
        "job_url": "https://naukri.com/view/789",
    }
    eval4 = evaluate_job(job4)
    assert eval4["is_valid_fresher_job"] is False
    assert "outside" in eval4["rejection_reason"]

    # Invalid job - Missing apply URL
    job5 = {
        "title": "Data Analyst Fresher",
        "company": "Tata Consultancy Services",
        "location": "Mumbai",
        "date_posted": datetime.now() - timedelta(hours=2),
        "experience_range": "0-1 Yrs",
        "job_url": None,
    }
    eval5 = evaluate_job(job5)
    assert eval5["is_valid_fresher_job"] is False
    assert "apply URL" in eval5["rejection_reason"]
    print(" [OK] Full pipeline evaluation tests passed")


def test_user_reported_regression_cases():
    """Verify that all user-reported experienced jobs are strictly rejected."""
    # 1. Goldman Sachs (4472165449)
    gs = evaluate_job({
        "title": "Human Capital Management-Analyst",
        "company": "Goldman Sachs",
        "location": "Hyderabad",
        "date_posted": datetime.now() - timedelta(hours=10),
        "experience_range": None,
        "site": "linkedin",
        "job_level": "entry_level",
        "description": "The Human Capital Management division is seeking an Analyst with 1-3 years of relevant experience."
    })
    assert gs["is_valid_fresher_job"] is False

    # 2. Turium Ai (4489525555)
    turium = evaluate_job({
        "title": "Full Stack Developer",
        "company": "Turium Ai",
        "location": "Hyderabad",
        "date_posted": datetime.now() - timedelta(hours=10),
        "experience_range": None,
        "site": "linkedin",
        "job_level": "entry_level",
        "description": "Looking for a Full Stack Developer with 5+ years of experience in FastAPI and React."
    })
    assert turium["is_valid_fresher_job"] is False

    # 3. AIQ Space (4488509156)
    aiq = evaluate_job({
        "title": "Web Application Developer (React, TypeScript & Web Hosting)",
        "company": "AIQ Space Ventures",
        "location": "Mumbai",
        "date_posted": datetime.now() - timedelta(hours=10),
        "experience_range": None,
        "site": "linkedin",
        "job_level": "entry_level",
        "description": "Requirements: Minimum 1 year of experience building React web applications."
    })
    assert aiq["is_valid_fresher_job"] is False

    # 4. Without description, unverified generic roles must never pass
    for title, company in [
        ("Human Capital Management-Analyst", "Goldman Sachs"),
        ("Full Stack Developer", "Turium Ai"),
        ("MERN Stack Developer – Next.js", "Qloron Pvt Ltd"),
        ("Web Application Developer", "AIQ Space Ventures"),
        ("Frontend Developer", "HCLTech"),
        ("Full Stack Developer – Python, FastAPI", "Synechron"),
    ]:
        job_no_desc = {
            "title": title,
            "company": company,
            "location": "Hyderabad",
            "date_posted": datetime.now() - timedelta(hours=10),
            "experience_range": None,
            "site": "linkedin",
            "job_level": "entry_level",
            "description": None,
        }
        res = evaluate_job(job_no_desc)
        assert res["is_valid_fresher_job"] is False
    print(" [OK] User reported regression cases passed")


class TestFilterEngineSuite(unittest.TestCase):
    """Unittest test runner adapter."""

    def test_experience(self):
        test_experience_filtering()

    def test_regression(self):
        test_user_reported_regression_cases()

    def test_locations(self):
        test_location_validation()

    def test_apply_urls(self):
        test_apply_url_validation()

    def test_titles(self):
        test_title_blacklist()

    def test_companies(self):
        test_company_blacklist()

    def test_freshness(self):
        test_date_freshness()

    def test_roles(self):
        test_categorization()

    def test_evaluation(self):
        test_full_pipeline_evaluation()


if __name__ == "__main__":
    print("\nRunning Fresher Job Scraper Test Suite (tests/)...")
    test_experience_filtering()
    test_title_blacklist()
    test_company_blacklist()
    test_date_freshness()
    test_categorization()
    test_location_validation()
    test_apply_url_validation()
    test_full_pipeline_evaluation()
    test_user_reported_regression_cases()
    print("\nALL FILTER TESTS PASSED SUCCESSFULLY!\n")
