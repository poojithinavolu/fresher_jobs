"""
HR Cold Outreach 3-Step Email Sequence
--------------------------------------
Based on the architecture specification:
- Step 1 (Day 0): Initial Fresher Candidate Presentation
- Step 2 (Day 4): Quick Bump + Proof of Work / Project GitHub Portfolios
- Step 3 (Day 10): Respectful Breakup / Closing Loop

Capped at 100 emails/day via Brevo Free Tier (300 free emails/day limit).
"""

from typing import Dict, Any


def get_day_0_pitch(company: str, job_title: str, location: str) -> Dict[str, str]:
    """Day 0: Initial Outreach sent when job is <24 hours old."""
    subject = f"Candidate profiles for {job_title} at {company} (Zero upfront fees)"
    body = f"""Hi Team {company},

I noticed your team recently posted an opening for a {job_title} based in {location}.

We manage an exclusive cohort of pre-screened fresh graduates specialized in Python, SQL, PowerBI, and Modern Web Development who are available for immediate joining in {location}.

Every candidate has completed 3+ production-grade capstone projects and has undergone rigorous technical assessments.

We would be happy to share 3–5 tailored, verified resumes with your recruiting team for review at zero upfront recruitment fee.

Could we send these profiles over for your review today?

Best regards,

Placement & Candidate Operations Team
Fresher Job Intelligence Hub
"""
    return {"subject": subject, "body": body}


def get_day_4_followup(company: str, job_title: str) -> Dict[str, str]:
    """Day 4: Polite bump highlighting candidate technical portfolios."""
    subject = f"Re: Candidate profiles for {job_title} at {company}"
    body = f"""Hi Team {company},

Following up on my note from earlier this week regarding your {job_title} role.

I understand your team is likely reviewing numerous applications. To save your technical screeners time, our shortlisted candidates have public GitHub portfolios and live deployed projects that your engineering leads can evaluate in under 2 minutes.

Would you be open to reviewing 2 shortlisted candidate profiles this week?

Warm regards,

Placement & Candidate Operations Team
"""
    return {"subject": subject, "body": body}


def get_day_10_breakup(company: str, job_title: str) -> Dict[str, str]:
    """Day 10: Respectful breakup email to keep domain reputation pristine."""
    subject = f"Closing the loop: {job_title} candidate shortlist"
    body = f"""Hi Team {company},

I assume your team has likely filled the {job_title} opening or is proceeding with other candidate pipelines, so I won't follow up again on this position.

If you ever need pre-vetted fresh talent across Data Analytics, Backend, or Full Stack development in the future, feel free to keep my contact handy.

Wishing you and {company} continued success with your hiring!

Best regards,

Placement & Candidate Operations Team
"""
    return {"subject": subject, "body": body}
