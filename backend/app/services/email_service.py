# ============================================================================
# FILE: email_service.py
# PATH: backend/app/services/email_service.py
# PURPOSE: Send the AviaSAFE tenant welcome email. Provider-agnostic:
#          - none      (default) render + log + return an HTML preview, never
#                      touches the network (safe for demo / tests)
#          - smtp      stdlib smtplib with STARTTLS (SMTP_HOST/PORT/USER/PASS)
#          - sendgrid  SendGrid v3 REST API (SENDGRID_API_KEY)
#          Every send is non-blocking from the caller's perspective: failures
#          are caught, logged, and returned in the result dict so the audit log
#          always records the outcome.
# AUTHOR: AviaSAFE Systems
# ============================================================================

import hashlib
import logging
import random
import smtplib
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.config import settings

logger = logging.getLogger("email")

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "welcome_email.html"

_TEMPLATE_CACHE: Optional[str] = None


def _template_html() -> str:
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE is None:
        try:
            _TEMPLATE_CACHE = _TEMPLATE_PATH.read_text(encoding="utf-8")
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to load welcome email template: {e}")
            _TEMPLATE_CACHE = "<p>Welcome to AviaSAFE SMS. Login: {login_url} Email: {admin_email}</p>"
    return _TEMPLATE_CACHE


def render_welcome_email(context: Dict[str, Any]) -> Dict[str, str]:
    """Render (subject, html, text) for the welcome email from a context dict.

    Context keys: contact_name, tenant_name, login_url, admin_email, password,
    support_email, year.
    """
    now = datetime.utcnow()
    ctx = {
        "contact_name": context.get("contact_name") or "there",
        "tenant_name": context.get("tenant_name") or "your organization",
        "login_url": context.get("login_url") or settings.APP_LOGIN_URL,
        "admin_email": context.get("admin_email") or "",
        "password": context.get("password") or "",
        "support_email": context.get("support_email") or settings.APP_SUPPORT_EMAIL,
        "year": context.get("year") or str(now.year),
    }
    html = _template_html().format(**ctx)
    text = (
        "Welcome to AviaSAFE SMS\n\n"
        f"Dear {ctx['contact_name']},\n\n"
        f"Your organization {ctx['tenant_name']} has been onboarded to AviaSAFE SMS.\n\n"
        f"Login URL: {ctx['login_url']}\n"
        f"Admin Email: {ctx['admin_email']}\n"
        f"Temporary Password: {ctx['password']}\n\n"
        "For security, please change your password after your first login.\n\n"
        f"For assistance, contact: {ctx['support_email']}\n\n"
        "Regards,\nAviaSAFE SMS Team"
    )
    subject = f"Welcome to AviaSAFE SMS - Your {ctx['tenant_name']} Tenant Credentials"
    return {"subject": subject, "html": html, "text": text}


def _from_address() -> tuple:
    sender = settings.EMAIL_FROM or "no-reply@aviasafesystems.com"
    return (settings.EMAIL_FROM_NAME, sender)


def _send_smtp(to: str, rendered: Dict[str, str]) -> Dict[str, Any]:
    msg = EmailMessage()
    msg["Subject"] = rendered["subject"]
    msg["From"] = formataddr(_from_address())
    msg["To"] = to
    msg.set_content(rendered["text"])
    msg.add_alternative(rendered["html"], subtype="html")

    host = settings.SMTP_HOST
    if not host:
        raise ValueError("SMTP_HOST is not configured")
    port = int(settings.SMTP_PORT or 587)
    with smtplib.SMTP(host, port, timeout=30) as server:
        if port == 587 or port == 25:
            server.starttls(context=ssl.create_default_context())
        if settings.SMTP_USER and settings.SMTP_PASS:
            server.login(settings.SMTP_USER, settings.SMTP_PASS)
        server.send_message(msg)
    return {"sent": True, "provider": "smtp", "to": to, "host": host}


def _send_sendgrid(to: str, rendered: Dict[str, str]) -> Dict[str, Any]:
    api_key = settings.SENDGRID_API_KEY
    if not api_key:
        raise ValueError("SENDGRID_API_KEY is not configured")
    sender_name, sender = _from_address()
    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": sender, "name": sender_name},
        "subject": rendered["subject"],
        "content": [
            {"type": "text/plain", "value": rendered["text"]},
            {"type": "text/html", "value": rendered["html"]},
        ],
    }
    req = urllib.request.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=bytes(__import__("json").dumps(payload), "utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        status = resp.status
    if status != 202:
        raise RuntimeError(f"SendGrid returned HTTP {status}")
    return {"sent": True, "provider": "sendgrid", "to": to}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_string(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_MAX_EMAIL_RETRIES = 3
_BASE_DELAY = 1.0


def _retry_with_backoff(func, *args, max_retries: int = _MAX_EMAIL_RETRIES, **kwargs) -> Dict[str, Any]:
    """Execute func with exponential backoff + jitter. On exhaustion, quarantine to DLQ."""
    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            last_error = exc
            delay = _BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            logger.warning(
                f"Email dispatch attempt {attempt}/{max_retries} failed: {exc}. "
                f"Retrying in {delay:.1f}s"
            )
            time.sleep(delay)

    logger.error(f"All {max_retries} email dispatch attempts exhausted: {last_error}")
    try:
        from app.services.dlq_service import DlqService
        dlq = DlqService()
        dlq.quarantine(
            original_operation="email_dispatch",
            payload={"args": [str(a) for a in args], "kwargs": {k: str(v) for k, v in kwargs.items()}},
            error_message=str(last_error),
            max_attempts=max_retries,
        )
    except Exception as dlq_err:
        logger.error(f"Failed to quarantine failed email to DLQ: {dlq_err}")

    return {"sent": False, "error": str(last_error), "retries_exhausted": True}


def send_welcome_email(to: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Send the welcome email to `to`. Never raises; returns a result dict.
    Includes SHA-256 digest of the rendered payload and exponential backoff retry."""
    try:
        rendered = render_welcome_email(context)
        payload_hash = sha256_string(rendered.get("html", ""))
        provider = (settings.EMAIL_PROVIDER or "none").strip().lower()

        if provider == "smtp":
            result = _retry_with_backoff(_send_smtp, to, rendered)
        elif provider == "sendgrid":
            result = _retry_with_backoff(_send_sendgrid, to, rendered)
        else:
            result = {
                "sent": False,
                "provider": "none",
                "to": to,
                "reason": "EMAIL_PROVIDER is 'none' — welcome email logged, not delivered",
                "preview": rendered["html"],
            }
        result["payload_sha256"] = payload_hash
        logger.info(f"Welcome email to {to}: provider={result.get('provider')} sent={result.get('sent', False)} hash={payload_hash}")
        return result
    except Exception as e:
        logger.error(f"Welcome email to {to} failed: {e}")
        return {"sent": False, "provider": (settings.EMAIL_PROVIDER or "none").lower(), "to": to, "error": str(e)}


def send_regulatory_report(
    to: str,
    subject: str,
    html_body: str,
    text_body: str,
    attachment_bytes: Optional[bytes] = None,
    attachment_filename: Optional[str] = None,
) -> Dict[str, Any]:
    """Dispatch a regulatory report email with optional PDF attachment.
    Uses exponential backoff + jitter; quarantines to DLQ on exhaustion."""
    rendered = {"subject": subject, "html": html_body, "text": text_body}
    payload_hash = sha256_bytes(attachment_bytes) if attachment_bytes else sha256_string(html_body)
    provider = (settings.EMAIL_PROVIDER or "none").strip().lower()

    def _send_fn(to_addr: str, rendered_data: Dict[str, str]) -> Dict[str, Any]:
        msg = EmailMessage()
        msg["Subject"] = rendered_data["subject"]
        msg["From"] = formataddr(_from_address())
        msg["To"] = to_addr
        msg.set_content(rendered_data["text"])
        msg.add_alternative(rendered_data["html"], subtype="html")
        if attachment_bytes and attachment_filename:
            msg.add_attachment(
                attachment_bytes,
                maintype="application",
                subtype="pdf",
                filename=attachment_filename,
            )
        host = settings.SMTP_HOST
        if not host:
            raise ValueError("SMTP_HOST is not configured")
        port = int(settings.SMTP_PORT or 587)
        with smtplib.SMTP(host, port, timeout=30) as server:
            if port in (587, 25):
                server.starttls(context=ssl.create_default_context())
            if settings.SMTP_USER and settings.SMTP_PASS:
                server.login(settings.SMTP_USER, settings.SMTP_PASS)
            server.send_message(msg)
        return {"sent": True, "provider": "smtp", "to": to_addr, "host": host}

    if provider == "smtp":
        result = _retry_with_backoff(_send_fn, to, rendered)
    else:
        result = {
            "sent": False,
            "provider": provider,
            "to": to,
            "reason": f"EMAIL_PROVIDER '{provider}' not configured for regulatory dispatch",
        }
    result["payload_sha256"] = payload_hash
    return result
