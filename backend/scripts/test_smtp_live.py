# ============================================================================
# FILE: test_smtp_live.py
# PATH: backend/scripts/test_smtp_live.py
# PURPOSE: Live SMTP verification for the Gmail registration-acknowledgment
#          dispatcher. Connects to Gmail SMTP through the same
#          gmail_dispatcher._get_smtp_connection() path (IPv4-forced, SMTP_SSL
#          on 465 / STARTTLS on 587), performs the EHLO -> (SSL|STARTTLS) ->
#          LOGIN handshake, then dispatches a real test message via
#          gmail_dispatcher.send_registration_acknowledgment().
#
#          Requires real credentials. Set on the Render dashboard or locally:
#            GMAIL_SMTP_USER / GMAIL_SMTP_PASSWORD
#            (fallbacks: SMTP_USER, SMTP_PASSWORD / SMTP_PASS)
#
# Usage:
#   cd backend
#   python scripts/test_smtp_live.py [--to ghanshyamacharya@outlook.com]
#                                    [--contact "Ghanshyam Acharya"]
#                                    [--org "AviaSAFE Systems (Live SMTP Test)"]
#
# AUTHOR: AviaSAFE Systems
# ============================================================================

import argparse
import smtplib
import sys
from pathlib import Path

# Ensure `app` is importable regardless of CWD (running from backend/ or from
# the scripts/ directory directly).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.services import gmail_dispatcher
from app.services.gmail_dispatcher import send_registration_acknowledgment


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the Gmail SMTP handshake and dispatch a live "
        "registration-acknowledgment test message."
    )
    parser.add_argument("--to", default="ghanshyamacharya@outlook.com",
                        help="Recipient address for the test message")
    parser.add_argument("--contact", default="Ghanshyam Acharya",
                        help="Contact name used in the message body")
    parser.add_argument("--org", default="AviaSAFE Systems (Live SMTP Test)",
                        help="Organization name used in the subject/body")
    args = parser.parse_args()

    if not gmail_dispatcher.gmail_configured():
        print(
            "ERROR: Gmail SMTP credentials are not configured.", file=sys.stderr
        )
        print(
            "Set GMAIL_SMTP_USER / GMAIL_SMTP_PASSWORD (or SMTP_USER and "
            "SMTP_PASSWORD / SMTP_PASS) before running this script.",
            file=sys.stderr,
        )
        return 1

    host = gmail_dispatcher._host()
    port = gmail_dispatcher._port()
    user = gmail_dispatcher._user()
    print(f"Gmail SMTP target: {host}:{port} as {user}")
    print("Step 1: SMTP handshake (EHLO -> SSL/STARTTLS -> LOGIN)...")

    try:
        server = gmail_dispatcher._get_smtp_connection(
            host, port, user, gmail_dispatcher._password()
        )
        server.close()
        print("Step 1 OK: connection, TLS and login accepted.")
    except smtplib.SMTPException as err:
        print(f"Step 1 FAILED (SMTP error): {err}", file=sys.stderr)
        return 1
    except Exception as err:  # noqa: BLE001 - CLI diagnostics
        print(f"Step 1 FAILED: {err}", file=sys.stderr)
        return 1

    print(
        "Step 2: dispatch test message to "
        f"{args.to} via send_registration_acknowledgment()..."
    )
    result = send_registration_acknowledgment(
        args.to, args.contact, args.org
    )
    if result.get("sent"):
        print("Step 2 OK: test message dispatched successfully.")
        print(f"  subject: {result.get('subject')}")
        print(f"  bcc: {result.get('bcc') or 'none'}")
        return 0

    print(f"Step 2 FAILED: {result.get('error') or result.get('reason')}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
