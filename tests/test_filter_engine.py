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
    print(" [OK] Full pipeline evaluation tests passed")


class TestFilterEngineSuite(unittest.TestCase):
    """Unittest test runner adapter."""

    def test_experience(self):
        test_experience_filtering()

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
    test_full_pipeline_evaluation()
    print("\nALL FILTER TESTS PASSED SUCCESSFULLY!\n")
