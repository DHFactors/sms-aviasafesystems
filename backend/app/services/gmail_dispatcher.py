# ============================================================================
# FILE: gmail_dispatcher.py
# PATH: backend/app/services/gmail_dispatcher.py
# PURPOSE: Dedicated Gmail SMTP channel for self-service registration intake
#          acknowledgments (betasms.aviasafesystems.com).
#
#          send_registration_acknowledgment() composes and dispatches the
#          plain-text acknowledgment via smtplib + email.mime. It NEVER raises:
#          SMTP failures are caught, logged and returned in the result dict so
#          a transient email problem can never crash or roll back a valid,
#          already-provisioned tenant record.
#
#          Configuration (environment / Render dashboard):
#            GMAIL_SMTP_HOST          smtp.gmail.com
#            GMAIL_SMTP_PORT          587
#            GMAIL_SMTP_USER          sender gmail address
#            GMAIL_SMTP_PASSWORD      app password / SMTP credential
#            GMAIL_NOTIFICATION_BCC   optional bcc observer address
#
#          When GMAIL_SMTP_USER / GMAIL_SMTP_PASSWORD are empty the dispatch is
#          skipped gracefully (logged only) — the endpoint still returns 200.
#
# AUTHOR: AviaSAFE Systems
# ============================================================================

import asyncio
import logging
import smtplib
import ssl
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Any, Dict, Optional

from app.core.config import settings

logger = logging.getLogger("email")

SENDER_NAME = "Ghanshyam Acharya"
GMAIL_DEFAULT_HOST = "smtp.gmail.com"
GMAIL_DEFAULT_PORT = 587
EM_DASH = "\u2014"  # em-dash: "AviaSAFE Beta Registration Request — [Org]"


def _host() -> str:
    return str(settings.GMAIL_SMTP_HOST or GMAIL_DEFAULT_HOST).strip()


def _port() -> int:
    return int(settings.GMAIL_SMTP_PORT or GMAIL_DEFAULT_PORT)


def _user() -> Optional[str]:
    value = (settings.GMAIL_SMTP_USER or "").strip()
    return value or None


def _password() -> Optional[str]:
    value = settings.GMAIL_SMTP_PASSWORD
    return value if value else None


def _bcc() -> Optional[str]:
    value = (settings.GMAIL_NOTIFICATION_BCC or "").strip()
    return value or None


def gmail_configured() -> bool:
    """True only when a real Gmail user + password are available for delivery."""
    return bool(_user() and _password())


def render_registration_acknowledgment(
    contact_name: str,
    organization_name: str,
) -> Dict[str, str]:
    """Compose the registration acknowledgment message parts.

    Returns (subject, from_header, text) for the plain-text email. The sender
    is "Ghanshyam Acharya <GMAIL_SMTP_USER>"; when the Gmail user is unset the
    header falls back to the platform no-reply address (the dispatch is skipped
    before reaching this point unless credentials exist).
    """
    sender = _user() or "no-reply@aviasafesystems.com"
    subject = f"AviaSAFE Beta Registration Request {EM_DASH} {organization_name}"
    text = (
        f"Dear {contact_name},\n\n"
        "Thank you very much for your interest in AviaSAFE Systems.\n\n"
        f"Your request to register {organization_name} has been received and is "
        "currently being assessed by our team to provision your dedicated sandbox "
        "environment.\n\n"
        "We will get back to you at the earliest with your setup credentials and "
        "tenant onboarding guide.\n\n"
        "Best regards,\n"
        "Ghanshyam Acharya\n"
        "Founder / Developer, AviaSAFE Systems\n"
        "https://betasms.aviasafesystems.com"
    )
    return {
        "subject": subject,
        "from": formataddr((SENDER_NAME, sender)),
        "text": text,
    }


def _build_message(
    to_email: str,
    contact_name: str,
    organization_name: str,
) -> MIMEText:
    """Assemble the MIME message with To + optional Bcc addressing."""
    rendered = render_registration_acknowledgment(contact_name, organization_name)
    msg = MIMEText(rendered["text"], "plain", "utf-8")
    msg["Subject"] = rendered["subject"]
    msg["From"] = rendered["from"]
    msg["To"] = to_email
    bcc = _bcc()
    if bcc:
        msg["Bcc"] = bcc
    return msg


def _dispatch(msg: MIMEText) -> None:
    """Blocking SMTP send. Raises on any transport failure (caller catches)."""
    host = _host()
    port = _port()
    user = _user()
    password = _password()

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.ehlo()
        if port in (587, 25):
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        if user and password:
            server.login(user, password)
        server.send_message(msg)


def send_registration_acknowledgment(
    to_email: str,
    contact_name: str,
    organization_name: str,
) -> Dict[str, Any]:
    """Send the registration acknowledgment. NEVER raises.

    Returns a result dict (sent True/False). When Gmail credentials are empty
    the dispatch is skipped with a logged reason — a missing mailbox must never
    cause a valid tenant registration to be rolled back.
    """
    if not gmail_configured():
        logger.info(
            "Registration acknowledgment to %s skipped: "
            "GMAIL_SMTP_USER/GMAIL_SMTP_PASSWORD not configured",
            to_email,
        )
        return {
            "sent": False,
            "provider": "gmail",
            "to": to_email,
            "reason": "GMAIL_SMTP_USER/GMAIL_SMTP_PASSWORD not configured",
        }

    try:
        msg = _build_message(to_email, contact_name, organization_name)
        _dispatch(msg)
        logger.info(
            "Registration acknowledgment sent to %s (subject=%r, bcc=%r)",
            to_email,
            msg["Subject"],
            _bcc(),
        )
        return {
            "sent": True,
            "provider": "gmail",
            "to": to_email,
            "bcc": _bcc(),
            "subject": msg["Subject"],
        }
    except Exception as e:
        logger.error("Registration acknowledgment to %s failed: %s", to_email, e)
        return {"sent": False, "provider": "gmail", "to": to_email, "error": str(e)}


async def send_registration_acknowledgment_async(
    to_email: str,
    contact_name: str,
    organization_name: str,
) -> Dict[str, Any]:
    """Non-blocking wrapper for BackgroundTasks: the blocking SMTP I/O runs in
    a worker thread so the response is never held up by mail delivery."""
    return await asyncio.to_thread(
        send_registration_acknowledgment,
        to_email,
        contact_name,
        organization_name,
    )