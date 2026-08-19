# ============================================================================
# FILE: gmail_dispatcher.py
# PATH: backend/app/services/gmail_dispatcher.py
# PURPOSE: Dedicated Gmail channel for self-service registration intake
#          acknowledgments (betasms.aviasafesystems.com).
#
#          send_registration_acknowledgment() composes and dispatches the
#          acknowledgment via the Gmail REST API over HTTPS (port 443) using
#          httpx and an OAuth2 refresh-token flow:
#            1. Exchange GMAIL_REFRESH_TOKEN for an ephemeral access token at
#               POST https://oauth2.googleapis.com/token
#            2. Send the RFC 2822 MIME message (URL-safe base64) at
#               POST https://gmail.googleapis.com/gmail/v1/users/me/messages/send
#
#          It NEVER raises: HTTP/network failures are caught, logged and
#          returned in the result dict so a transient email problem can never
#          crash or roll back a valid, already-provisioned tenant record.
#
#          Configuration (environment / Render dashboard):
#            GMAIL_CLIENT_ID       OAuth2 client id
#            GMAIL_CLIENT_SECRET   OAuth2 client secret
#            GMAIL_REFRESH_TOKEN   OAuth2 refresh token (long-lived)
#            GMAIL_SENDER_EMAIL    sending Gmail address (defaults to "me")
#            GMAIL_NOTIFICATION_BCC   optional bcc observer address
#
#          When no GMAIL_CLIENT_ID / GMAIL_REFRESH_TOKEN are configured the
#          dispatch is skipped gracefully (logged only) — the endpoint still
#          returns 200.
#
# AUTHOR: AviaSAFE Systems
# ============================================================================

import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

import httpx
from loguru import logger

from app.core.config import settings

SENDER_NAME = "AviaSAFE Systems"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
EM_DASH = "\u2014"  # em-dash: "Welcome to AviaSAFE SMS Beta — [Org]"


def gmail_configured() -> bool:
    """True only when real Gmail OAuth credentials are available for delivery."""
    return bool(
        (settings.GMAIL_CLIENT_ID or "").strip()
        and (settings.GMAIL_REFRESH_TOKEN or "").strip()
    )


def _bcc() -> Optional[str]:
    value = (settings.GMAIL_NOTIFICATION_BCC or "").strip()
    return value or None


async def _get_access_token(client: httpx.AsyncClient) -> str:
    """Exchange the refresh token for an ephemeral access token via HTTPS."""
    res = await client.post(
        OAUTH_TOKEN_URL,
        data={
            "client_id": settings.GMAIL_CLIENT_ID,
            "client_secret": settings.GMAIL_CLIENT_SECRET,
            "refresh_token": settings.GMAIL_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        },
        timeout=10.0,
    )
    res.raise_for_status()
    return res.json()["access_token"]


def _build_message(
    to_email: str,
    contact_name: str,
    organization_name: str,
) -> MIMEMultipart:
    """Assemble the RFC 2822 MIME message (HTML body, To + optional Bcc)."""
    sender = (settings.GMAIL_SENDER_EMAIL or "").strip() or "me"
    subject = f"Welcome to AviaSAFE SMS Beta {EM_DASH} {organization_name}"

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{SENDER_NAME} <{sender}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Auto-Submitted"] = "auto-generated"
    msg["X-Auto-Response-Suppress"] = "All"
    bcc = _bcc()
    if bcc:
        msg["Bcc"] = bcc

    plain_text = (
        f"Dear {contact_name},\n\n"
        f"Your organization {organization_name} has been registered on the "
        "AviaSAFE Aviation SMS Beta Platform.\n\n"
        "You can now sign in to your dashboard to manage hazard reports, risk "
        "assessments, and compliance audits.\n\n"
        "Safe skies,\n"
        "Ghanshyam Acharya\n"
        "AviaSAFE Systems"
    )

    html_body = f"""
    <div style="font-family: Arial, sans-serif; color: #1e293b; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #0f4c81;">AviaSAFE Systems</h2>
        <p>Dear {contact_name},</p>
        <p>Your organization <strong>{organization_name}</strong> has been registered on the <strong>AviaSAFE Aviation SMS Beta Platform</strong>.</p>
        <p>You can now sign in to your dashboard to manage hazard reports, risk assessments, and compliance audits.</p>
        <p style="margin-top: 24px;">Safe skies,<br><strong>Ghanshyam Acharya</strong><br>AviaSAFE Systems</p>
    </div>
    """
    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


async def send_registration_acknowledgment(
    to_email: str,
    contact_name: str,
    organization_name: str,
) -> Dict[str, Any]:
    """Send the registration acknowledgment via Gmail REST API. NEVER raises.

    Returns a result dict (sent True/False). When Gmail OAuth credentials are
    empty the dispatch is skipped with a logged reason — a missing mailbox must
    never cause a valid tenant registration to be rolled back.
    """
    if not gmail_configured():
        logger.info(
            "Registration acknowledgment to {} skipped: "
            "GMAIL_CLIENT_ID/GMAIL_REFRESH_TOKEN not configured",
            to_email,
        )
        return {
            "sent": False,
            "provider": "gmail_rest",
            "to": to_email,
            "reason": "GMAIL_CLIENT_ID/GMAIL_REFRESH_TOKEN not configured",
        }

    logger.info(
        "Attempting to dispatch registration acknowledgment to {} via Gmail REST API (HTTPS)...",
        to_email,
    )
    try:
        msg = _build_message(to_email, contact_name, organization_name)
        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

        async with httpx.AsyncClient(timeout=15.0) as client:
            access_token = await _get_access_token(client)
            response = await client.post(
                GMAIL_SEND_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={"raw": raw_message},
            )

        if response.status_code == 200:
            logger.info(
                "Successfully sent registration acknowledgment email to {} via Gmail REST API",
                to_email,
            )
            return {
                "sent": True,
                "provider": "gmail_rest",
                "to": to_email,
                "bcc": _bcc(),
                "subject": msg["Subject"],
            }

        logger.error(
            "Gmail REST API send failed [{status}]: {text}",
            status=response.status_code,
            text=response.text,
        )
        return {
            "sent": False,
            "provider": "gmail_rest",
            "to": to_email,
            "error": f"HTTP {response.status_code}: {response.text}",
        }
    except Exception as exc:
        logger.error(
            "Failed to dispatch registration acknowledgment via HTTPS: {}", exc
        )
        return {
            "sent": False,
            "provider": "gmail_rest",
            "to": to_email,
            "error": str(exc),
        }


async def send_registration_acknowledgment_async(
    to_email: str,
    contact_name: str,
    organization_name: str,
) -> Dict[str, Any]:
    """Alias kept for callers that referenced the async wrapper directly."""
    return await send_registration_acknowledgment(
        to_email,
        contact_name,
        organization_name,
    )