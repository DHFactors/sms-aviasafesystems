# ============================================================================
# FILE: test_gmail_live.py
# PATH: backend/scripts/test_gmail_live.py
# PURPOSE: Live Gmail REST verification for the registration-acknowledgment
#          dispatcher. Exercises the full HTTPS path — OAuth2 refresh-token
#          exchange -> Gmail API messages.send — and dispatches a real test
#          message via gmail_dispatcher.send_registration_acknowledgment().
#
#          Requires real credentials. Set on the Render dashboard or locally:
#            GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN
#            GMAIL_SENDER_EMAIL (optional), GMAIL_NOTIFICATION_BCC (optional)
#
# Usage:
#   cd backend
#   python scripts/test_gmail_live.py [--to ghanshyamacharya@outlook.com]
#                                     [--contact "Ghanshyam Acharya"]
#                                     [--org "AviaSAFE Systems (Live Test)"]
#
# AUTHOR: AviaSAFE Systems
# ============================================================================

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure `app` is importable regardless of CWD (running from backend/ or from
# the scripts/ directory directly).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import gmail_dispatcher


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the Gmail REST handshake and dispatch a live "
        "registration-acknowledgment test message over HTTPS."
    )
    parser.add_argument("--to", default="ghanshyamacharya@outlook.com",
                        help="Recipient address for the test message")
    parser.add_argument("--contact", default="Ghanshyam Acharya",
                        help="Contact name used in the message body")
    parser.add_argument("--org", default="AviaSAFE Systems (Live Gmail REST Test)",
                        help="Organization name used in the subject/body")
    args = parser.parse_args()

    if not gmail_dispatcher.gmail_configured():
        print(
            "ERROR: Gmail OAuth credentials are not configured.", file=sys.stderr
        )
        print(
            "Set GMAIL_CLIENT_ID and GMAIL_REFRESH_TOKEN (plus "
            "GMAIL_CLIENT_SECRET) before running this script.",
            file=sys.stderr,
        )
        return 1

    sender = gmail_dispatcher.settings.GMAIL_SENDER_EMAIL or "(default sender)"
    print(f"Gmail REST target: gmail.googleapis.com (HTTPS) as {sender}")

    print(
        f"Step 1: dispatch test message to {args.to} via "
        "send_registration_acknowledgment()..."
    )
    result = asyncio.run(
        gmail_dispatcher.send_registration_acknowledgment(
            args.to, args.contact, args.org
        )
    )
    if result.get("sent"):
        print("Step 1 OK: OAuth token exchange + Gmail API send succeeded.")
        print(f"  subject: {result.get('subject')}")
        print(f"  bcc: {result.get('bcc') or 'none'}")
        return 0

    print(
        f"Step 1 FAILED: {result.get('error') or result.get('reason')}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())