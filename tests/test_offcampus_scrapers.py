"""
Unit Tests for Off-Campus Drives and Specialty Fresher Scrapers
===============================================================
Mocks network responses to verify parsing, error isolation, schema conformity,
and dispatch in run_scraping_query.
"""
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest

from off_campus_scrapers import (
    scrape_unstop_jobs,
    scrape_elitmus_jobs,
    scrape_useastra_jobs,
    scrape_freshersdunia_jobs,
    scrape_freshershunt_jobs,
    scrape_campusdrive_jobs,
    scrape_jobs4fresher_jobs,
    scrape_joinsaarthi_jobs,
)
from scraper import run_scraping_query


def test_scrape_unstop_jobs():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "data": [
                {
                    "id": 101,
                    "title": "Flutter Developer",
                    "organisation": {"name": "SchoTech"},
                    "locations": [{"city": "Gurgaon"}],
                    "seo_url": "https://unstop.com/jobs/flutter-dev-101",
                    "approved_date": "2026-11-16T10:00:00Z",
                    "details": "Great opportunity for freshers",
                    "required_skills": [{"name": "Flutter"}, {"name": "Dart"}],
                    "jobDetail": {"min_salary": 20000, "max_salary": 30000},
                }
            ]
        }
    }
    mock_session.get.return_value = mock_resp

    with patch("off_campus_scrapers._get_session", return_value=mock_session):
        jobs = scrape_unstop_jobs("developer", "India", results_wanted=5)

    assert len(jobs) == 1
    j = jobs[0]
    assert j["title"] == "Flutter Developer"
    assert j["company"] == "SchoTech"
    assert j["location"] == "Gurgaon"
    assert j["site"] == "unstop"
    assert "Flutter" in j["skills_requirements"]
    assert j["salary_min"] == 20000


def test_scrape_elitmus_jobs():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = """
    <html><body>
      <div class="row">
        <a href="/jobs/33235-mountblue-software-engineer">Software Engineer Trainee</a>
        <div>MountBlue Technologies | Full Time | Bangalore | Fresher (2026) | ₹ 4,01,000</div>
      </div>
    </body></html>
    """
    mock_session.get.return_value = mock_resp

    with patch("off_campus_scrapers._get_session", return_value=mock_session):
        jobs = scrape_elitmus_jobs(results_wanted=5)

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Software Engineer Trainee"
    assert jobs[0]["company"] == "MountBlue Technologies"
    assert "Bangalore" in jobs[0]["location"]
    assert jobs[0]["site"] == "elitmus"


def test_scrape_useastra_jobs():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = """
    <html><body>
      <a href="/jobs/cognizant-genc-developer-19710">Cognizant fresher hiring for Programmer Analyst Trainee at Cognizant</a>
    </body></html>
    """
    mock_session.get.return_value = mock_resp

    with patch("off_campus_scrapers._get_session", return_value=mock_session):
        jobs = scrape_useastra_jobs(results_wanted=5)

    assert len(jobs) == 1
    assert "Programmer Analyst Trainee" in jobs[0]["title"]
    assert jobs[0]["company"] == "Cognizant"
    assert jobs[0]["site"] == "useastra"


def test_scrape_freshersdunia_jobs():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            "id": 999,
            "title": {"rendered": "Deloitte Careers 2026 – Analyst Role | Freshers"},
            "date": "2026-11-16T12:00:00",
            "link": "https://freshersdunia.in/deloitte-analyst-2026",
            "content": {"rendered": "<p>Deloitte is hiring freshers for analyst position in Mumbai.</p>"},
        }
    ]
    mock_session.get.return_value = mock_resp

    with patch("off_campus_scrapers._get_session", return_value=mock_session):
        jobs = scrape_freshersdunia_jobs(results_wanted=5)

    assert len(jobs) == 1
    assert jobs[0]["company"] == "Deloitte"
    assert jobs[0]["title"] == "Analyst"
    assert jobs[0]["site"] == "freshersdunia"


def test_scrape_freshershunt_jobs():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            "id": 888,
            "title": {"rendered": "Wipro Off Campus Drive 2026 | Project Engineer | Bangalore — Apply Now"},
            "date": "2026-11-16T14:00:00",
            "link": "https://freshershunt.in/wipro-drive-2026",
            "content": {"rendered": "<p>Wipro hiring freshers.</p>"},
        }
    ]
    mock_session.get.return_value = mock_resp

    with patch("off_campus_scrapers._get_session", return_value=mock_session):
        jobs = scrape_freshershunt_jobs(results_wanted=5)

    assert len(jobs) == 1
    assert jobs[0]["company"] == "Wipro"
    assert jobs[0]["title"] == "Project Engineer"
    assert jobs[0]["site"] == "freshershunt"


def test_site_dispatch_in_scraper():
    """Verifies that run_scraping_query routes off-campus sites correctly to our adapter."""
    with patch("off_campus_scrapers.scrape_unstop_jobs") as mock_unstop:
        mock_unstop.return_value = [
            {
                "title": "React Developer",
                "company": "Tech Corp",
                "location": "Mumbai",
                "site": "unstop",
                "date_posted": "2026-11-16",
                "job_url": "https://unstop.com/jobs/1",
                "job_url_direct": "https://unstop.com/jobs/1",
                "description": "Fresher role",
            }
        ]

        df = run_scraping_query("react developer", "Mumbai", sites=["unstop"])
        assert len(df) == 1
        assert df.iloc[0]["site"] == "unstop"
        assert df.iloc[0]["title"] == "React Developer"
        mock_unstop.assert_called_once()
