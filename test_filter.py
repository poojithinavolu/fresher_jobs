"""
Unit & Integration Tests for Fresher Job Scraper Filters
=========================================================
Verifies that:
1. Experience parsing correctly accepts 0-1 yrs and rejects > 1 yr.
2. Title blacklist correctly rejects Senior, Lead, Manager titles.
3. Company blacklist correctly rejects training institutes & scams.
4. 48-hour date parser correctly identifies recent vs outdated postings.
"""

from datetime import datetime, timedelta
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


def test_six_month_limit_and_requirement_fields():
    from filter_engine import evaluate_job

    base = {
        "title": "Data Analyst Fresher",
        "company": "Acme",
        "location": "Mumbai",
        "date_posted": datetime.now(),
        "experience_range": "0-6 months",
        "description": "Skills: SQL, Power BI. 2025 passout",
    }
    accepted = evaluate_job(dict(base))
    assert accepted["is_valid_fresher_job"] is True
    assert accepted["eligible_passout_years"] == "2025"
    assert "SQL" in accepted["required_skills"]
    assert accepted["prior_experience_required"] == "Unspecified"

    too_experienced = dict(base, experience_range=None, description="Requires 1-2 years experience")
    assert evaluate_job(too_experienced)["is_valid_fresher_job"] is False

    excluded = dict(base, description="Requires project experience and a project completion letter")
    assert evaluate_job(excluded)["is_valid_fresher_job"] is False


def test_nan_salary_metadata_does_not_crash_filtering():
    from filter_engine import evaluate_job

    result = evaluate_job({
        "title": "Data Analyst Fresher",
        "company": "Acme",
        "location": "Mumbai",
        "date_posted": datetime.now(),
        "experience_range": "0-6 months",
        "min_amount": float("nan"),
        "max_amount": float("nan"),
        "description": "Skills: SQL, Excel",
    })
    assert result["min_amount"] > 0
    assert result["max_amount"] > 0
    assert "nan" not in result["salary_display"].lower()


def test_hr_enrichment_tolerates_missing_or_nan_listing_text():
    from hr_enricher import enrich_job_with_hr, process_hr_enrichment

    result = enrich_job_with_hr({
        "company": "Acme",
        "location": "Mumbai",
        "description": float("nan"),
        "title": "Analyst",
        "tech_category": "Analyst",
    })
    assert result["company"] == "Acme"
    assert result["location"] == "Mumbai"
    assert result["hr_email"] == "careers@acme.com"
    assert len(process_hr_enrichment([{"company": float("nan"), "description": float("nan")}])) == 0


def test_all_boards_use_the_same_per_query_result_limit(monkeypatch):
    import pandas as pd
    import scraper

    calls = []

    def fake_scrape_jobs(**kwargs):
        calls.append(kwargs)
        return pd.DataFrame()

    monkeypatch.setattr(scraper, "scrape_jobs", fake_scrape_jobs)
    scraper.run_scraping_query(
        "data analyst fresher", "Mumbai",
        sites=["naukri", "indeed", "linkedin"], results_wanted=25,
    )
    assert [call["results_wanted"] for call in calls] == [25, 25, 25]


def test_board_requests_run_concurrently_without_same_board_overlap(monkeypatch):
    import threading
    import pandas as pd
    import scraper

    barrier = threading.Barrier(3)
    lock = threading.Lock()
    active = 0
    peak_active = 0

    def fake_scrape_jobs(**kwargs):
        nonlocal active, peak_active
        with lock:
            active += 1
            peak_active = max(peak_active, active)
        try:
            barrier.wait(timeout=2)
            return pd.DataFrame()
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(scraper, "scrape_jobs", fake_scrape_jobs)
    scraper.run_scraping_query(
        "data analyst fresher", "Mumbai",
        sites=["naukri", "indeed", "linkedin"], results_wanted=25,
    )

    assert peak_active == 3


def test_one_board_failure_does_not_discard_other_board_results(monkeypatch):
    import pandas as pd
    import scraper

    def fake_scrape_jobs(**kwargs):
        site = kwargs["site_name"][0]
        if site == "indeed":
            raise RuntimeError("temporary Indeed failure")
        return pd.DataFrame([{"site": site, "title": "Data Analyst"}])

    monkeypatch.setattr(scraper, "scrape_jobs", fake_scrape_jobs)
    result = scraper.run_scraping_query(
        "data analyst fresher", "Mumbai",
        sites=["naukri", "indeed", "linkedin"], results_wanted=25,
    )

    assert set(result["site"]) == {"naukri", "linkedin"}
    assert result.attrs["site_errors"] == {"indeed": "temporary Indeed failure"}


def test_cross_board_duplicates_are_kept_with_their_own_sources(monkeypatch):
    import pandas as pd
    import scraper

    now = datetime.now()
    same_listing = {
        "title": "Data Analyst Fresher",
        "company": "Acme",
        "location": "Mumbai",
        "date_posted": now - timedelta(hours=2),
        "experience_range": "0-1 Yrs",
        "description": "Entry-level role",
    }
    rows = [
        dict(same_listing, site=site, job_url=f"https://{site}.example/jobs/1")
        for site in ["naukri", "indeed", "linkedin"]
    ]
    monkeypatch.setattr(scraper, "run_scraping_query", lambda **kwargs: pd.DataFrame(rows))
    monkeypatch.setattr(scraper.time, "sleep", lambda *_: None)

    result = scraper.scrape_fresher_jobs(
        locations=["Mumbai"],
        roles_dict={"Data Analyst": ["data analyst fresher"]},
        sites=["naukri", "indeed", "linkedin"],
    )

    assert {job["site"] for job in result["valid_jobs"]} == {"naukri", "indeed", "linkedin"}
    assert result["stats"]["site_queries_attempted"] == {
        "naukri": 1, "indeed": 1, "linkedin": 1,
    }


def test_naukri_experience_is_a_separate_search_parameter():
    from jobspy.model import ScraperInput
    from scraper import EntryLevelNaukri

    adapter = EntryLevelNaukri()
    adapter.scraper_input = ScraperInput(search_term="data analyst", location="Mumbai")
    params = adapter._search_params()
    assert params["keyword"] == "data analyst"
    assert params["experience"] == "0"


def test_job_queries_include_plain_and_fresher_titles():
    from config import ROLE_QUERIES

    assert "data analyst" in ROLE_QUERIES["Data Analyst"]
    assert "data analyst fresher" in ROLE_QUERIES["Data Analyst"]


def test_google_sheets_job_rows_include_requested_fields():
    from google_sheets_sync import format_jobs_rows, merge_job_rows

    rows = format_jobs_rows([{
        "tech_category": "Data Analyst",
        "title": "Data Analyst Fresher",
        "company": "Acme",
        "experience_range": "0-1 Yrs",
        "eligible_passout_years": "2025, 2026",
        "required_skills": "SQL, Excel",
        "prior_experience_required": "No",
        "job_requirement": "Analyze business data",
    }])
    # Only the user's retained A:K fields are written; no Score or detail columns.
    assert len(rows[0]) == 11
    assert rows[0][:10] == [
        "Data Analyst Fresher", "Acme", "", "Data Analyst", "", "0-1 Yrs",
        "", "", "", "",
    ]
    assert rows[0][10]  # Last Updated timestamp
    assert "Analyze business data" not in rows[0]
    assert "No" not in rows[0]

    old = ["Old Analyst", "Old Co", "Mumbai", "Analyst", "2026-11-01", "0-1 Yrs", "", "", "https://example.com/old", "NAUKRI", "old timestamp"]
    updated = ["Updated Analyst", "Old Co", "Mumbai", "Analyst", "2026-11-02", "0-1 Yrs", "", "", "https://example.com/old", "NAUKRI", "new timestamp"]
    added = ["New Analyst", "New Co", "Hyderabad", "Analyst", "2026-11-02", "0-6 months", "", "", "https://example.com/new", "INDEED", "new timestamp"]
    merged = merge_job_rows([old], [updated, added])
    assert len(merged) == 2
    assert merged[0][0] == "Updated Analyst"
    assert merged[1][0] == "New Analyst"

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


if __name__ == "__main__":
    print("\nRunning Fresher Job Scraper Test Suite...")
    test_experience_filtering()
    test_title_blacklist()
    test_company_blacklist()
    test_date_freshness()
    test_categorization()
    test_full_pipeline_evaluation()
    print("\nALL TESTS PASSED SUCCESSFULLY!\n")
