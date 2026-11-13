"""
Admin Alerter & Health Monitor (Observe & Control)
=================================================
Design Reference: Layer 04 (OBSERVE & CONTROL)
  - Every run logged, every failure alerted
  - 09_Errors -> Telegram admin alert
  - Uptime Kuma ping integration
  - Kill-switch state monitoring
"""

import os
import sys
import requests
from datetime import datetime
from typing import Optional, Dict, Any

from pathlib import Path

# Add project root and services directory to sys.path
SERVICES_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVICES_DIR.parent
for p in [str(PROJECT_ROOT), str(SERVICES_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Ensure UTF-8 console output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def send_telegram_admin_alert(
    message: str,
    bot_token: Optional[str] = None,
    admin_chat_id: Optional[str] = None
) -> bool:
    """
    Sends an instant critical notification to the system administrator's Telegram account.
    """
    token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = admin_chat_id or os.environ.get("TELEGRAM_ADMIN_CHAT_ID")

    if not token or not chat_id:
        print(f"[*] Telegram Admin Alert (Simulated - set TELEGRAM_BOT_TOKEN & TELEGRAM_ADMIN_CHAT_ID for live push):\n    {message}")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": f"🚨 *SYSTEM ALERT · Fresher Job Intelligence*\n\n{message}",
        "parse_mode": "Markdown"
    }

    try:
        resp = requests.post(url, json=payload, timeout=5)
        return resp.status_code == 200
    except Exception as e:
        print(f"[!] Failed to push Telegram admin alert: {e}")
        return False

def ping_uptime_kuma(push_url: Optional[str] = None, msg: str = "OK") -> bool:
    """
    Pings Uptime Kuma monitoring endpoint upon successful execution cycle.
    """
    url = push_url or os.environ.get("UPTIME_KUMA_PUSH_URL")
    if not url:
        return False
    try:
        resp = requests.get(f"{url}?status=up&msg={msg}", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False

if __name__ == "__main__":
    print("[*] Testing Admin Alerter...")
    send_telegram_admin_alert("Pipeline run #24 completed successfully. 37 fresh jobs synced to Google Sheets.")
