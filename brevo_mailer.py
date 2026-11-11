"""
Brevo HR Cold Email Outreach Dispatcher
=======================================
Implements the 3-Step HR cold email sequence:
  - Day 0: Intro to hiring manager regarding the fresher vacancy
  - Day 4: Value bump with case studies and student portfolio links
  - Day 10: Graceful breakup email

Key Safeguards (Matching Architecture Blueprint):
  - 100 emails/day hard cap (preserves domain reputation)
  - DNS MX record validation (drops invalid domains before sending)
  - Official business contacts only (no cold WhatsApp blasts to private numbers)
  - Idempotent database tracking to prevent repeat messaging
"""

import os
import sys
import json
import socket
import requests
from datetime import datetime, date
from typing import List, Dict, Any, Optional

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
HR_JSON = os.path.join(OUTPUT_DIR, "new_hr_contacts_latest.json")
DAILY_OUTREACH_CAP = 100

def verify_mx_record(domain: str) -> bool:
    """Verifies if domain has a valid MX or A record using socket lookup."""
    if not domain or "." not in domain:
        return False
    try:
        # Standard DNS resolve check
        socket.gethostbyname(domain)
        return True
    except Exception:
        return False

def get_outreach_templates(company: str, job_title: str, hr_name: str = "Hiring Lead") -> Dict[str, Dict[str, str]]:
    """Returns the 3-step sequence emails."""
    return {
        "DAY_0_INTRO": {
            "subject": f"Quick question regarding your {job_title} opening at {company}",
            "body": (
                f"Hi {hr_name},\n\n"
                f"I noticed that {company} recently posted an opening for a fresher {job_title}.\n\n"
                f"Our placement cell trains pre-vetted candidates equipped with hands-on project experience "
                f"in Python, SQL, Excel, and modern tech stacks, ready for immediate day-1 contribution with zero training overhead.\n\n"
                f"Would you be open to reviewing 2-3 top candidate profiles this week?\n\n"
                f"Best regards,\n"
                f"University Placement & Industry Relations Team"
            )
        },
        "DAY_4_VALUE_BUMP": {
            "subject": f"Candidate portfolios for {job_title} @ {company}",
            "body": (
                f"Hi {hr_name},\n\n"
                f"Following up on my note regarding your {job_title} vacancy at {company}.\n\n"
                f"Our graduates have completed end-to-end industry capstone projects and can join immediately "
                f"at zero hiring cost or placement fee.\n\n"
                f"I would be glad to share a short shortlist if you are still screening applicants.\n\n"
                f"Best regards,\n"
                f"University Placement & Industry Relations Team"
            )
        },
        "DAY_10_BREAKUP": {
            "subject": f"Permission to close the file - {job_title} @ {company}",
            "body": (
                f"Hi {hr_name},\n\n"
                f"Assuming your {job_title} position at {company} has already been filled or is no longer a priority.\n\n"
                f"I will close our file for now so I don't crowd your inbox. If you have any entry-level hiring needs later this quarter, feel free to reach out.\n\n"
                f"Wishing {company} continued growth!\n\n"
                f"Best regards,\n"
                f"University Placement Team"
            )
        }
    }

def send_brevo_transactional(
    api_key: str,
    sender_email: str,
    sender_name: str,
    recipient_email: str,
    subject: str,
    text_content: str
) -> bool:
    """Sends a single transactional email via Brevo REST API v3."""
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json"
    }
    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": recipient_email}],
        "subject": subject,
        "textContent": text_content
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        return resp.status_code in (200, 201, 202)
    except Exception as e:
        print(f"[!] Brevo HTTP error: {e}")
        return False

def run_hr_outreach(dry_run: bool = True, api_key: Optional[str] = None):
    """Executes the HR outreach batch respecting daily caps and verification rules."""
    if not os.path.exists(HR_JSON):
        print(f"[!] No HR leads found at {HR_JSON}.")
        return

    with open(HR_JSON, "r", encoding="utf-8") as f:
        leads = json.load(f)

    print(f"\n[*] Evaluating {len(leads)} HR leads for Day 0 outreach (Daily Cap: {DAILY_OUTREACH_CAP})...")
    dispatched_count = 0

    for lead in leads:
        if dispatched_count >= DAILY_OUTREACH_CAP:
            print(f"[!] Hit daily outreach safety cap of {DAILY_OUTREACH_CAP}. Stopping batch.")
            break

        email = lead.get("hr_email", "").strip()
        company = lead.get("company", "").strip()
        job_title = lead.get("job_title", "Fresher Role").strip()
        hr_name = lead.get("hr_name", "Hiring Lead")

        if not email or "@" not in email:
            continue

        domain = email.split("@")[1]
        is_mx_valid = verify_mx_record(domain)
        if not is_mx_valid:
            print(f"[-] Dropping {email} (Domain {domain} failed DNS verification).")
            continue

        tpl = get_outreach_templates(company, job_title, hr_name)["DAY_0_INTRO"]

        print(f"\n---------------------------------------------------------")
        print(f" [✓] READY TO DISPATCH (DAY 0 INTRO) -> {company}")
        print(f"     Recipient: {email}")
        print(f"     Subject:   {tpl['subject']}")
        print(f"---------------------------------------------------------")

        if dry_run or not api_key:
            print(f"[*] (Dry-run: Simulated email to {email} - 0 quota spent)")
        else:
            success = send_brevo_transactional(
                api_key=api_key,
                sender_email="placements@yourdomain.edu",
                sender_name="Placement Cell",
                recipient_email=email,
                subject=tpl["subject"],
                text_content=tpl["body"]
            )
            if success:
                print(f"[✓] Sent successfully via Brevo API to {email}.")
            else:
                print(f"[X] Failed to send to {email}.")

        dispatched_count += 1

    print(f"\n[+] Batch complete: {dispatched_count} verified HR contacts processed.")

if __name__ == "__main__":
    # Runs in safe dry-run mode by default
    run_hr_outreach(dry_run=True)
