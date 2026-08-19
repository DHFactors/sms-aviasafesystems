"""Unit tests for the Gmail SMTP registration-acknowledgment dispatcher.

Covers email composition (subject / sender / body), recipient addressing
(To + optional Bcc), the real smtplib call path via a fake SMTP server, and the
graceful fallbacks: empty credentials and SMTP transport failures must never
raise — a mail problem can never crash or roll back a valid tenant record.
"""

import asyncio
import smtplib

import pytest

from app.core.config import settings
from app.services import gmail_dispatcher


class _FakeSMTP:
    """Drop-in smtplib.SMTP recording everything the dispatcher does."""

    instances = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sent = []
        self.ehlo_calls = 0
        self.tls_started = False
        self.login_credentials = None
        _FakeSMTP.instances.append(self)

    def ehlo(self):
        self.ehlo_calls += 1

    def starttls(self, context=None):
        self.tls_started = True

    def login(self, user, password):
        self.login_credentials = (user, password)

    def send_message(self, msg):
        self.sent.append(msg)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture(autouse=True)
def _fake_smtp(monkeypatch):
    _FakeSMTP.instances = []
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    yield _FakeSMTP
    _FakeSMTP.instances = []


@pytest.fixture
def _gmail_env(monkeypatch):
    monkeypatch.setattr(settings, "GMAIL_SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setattr(settings, "GMAIL_SMTP_PORT", 587)
    monkeypatch.setattr(settings, "GMAIL_SMTP_USER", "ghanshyam.acharya@gmail.com")
    monkeypatch.setattr(settings, "GMAIL_SMTP_PASSWORD", "app-password-123")
    monkeypatch.setattr(settings, "GMAIL_NOTIFICATION_BCC", "ops@aviasafesystems.com")


# ---------------------------------------------------------------------------
# Email composition
# ---------------------------------------------------------------------------

def test_render_subject_sender_and_body(_gmail_env):
    rendered = gmail_dispatcher.render_registration_acknowledgment(
        "Anil Shrestha", "Summit Air"
    )

    assert rendered["subject"] == "AviaSAFE Beta Registration Request \u2014 Summit Air"
    assert rendered["from"] == "Ghanshyam Acharya <ghanshyam.acharya@gmail.com>"

    body = rendered["text"]
    assert "Dear Anil Shrestha," in body
    assert "Thank you very much for your interest in AviaSAFE Systems." in body
    assert "Your request to register Summit Air has been received" in body
    assert "sandbox environment" in body
    assert "setup credentials and tenant onboarding guide" in body
    assert "Best regards," in body
    assert "Ghanshyam Acharya" in body
    assert "Founder / Developer, AviaSAFE Systems" in body
    assert "https://betasms.aviasafesystems.com" in body


def test_gmail_configured_reflects_credentials(_gmail_env):
    assert gmail_dispatcher.gmail_configured() is True


# ---------------------------------------------------------------------------
# Dispatch path (fake SMTP)
# ---------------------------------------------------------------------------

def test_send_dispatches_with_to_and_bcc(_gmail_env, _fake_smtp):
    result = gmail_dispatcher.send_registration_acknowledgment(
        "safety@summitair.com", "Anil Shrestha", "Summit Air"
    )

    assert result["sent"] is True
    assert result["provider"] == "gmail"
    assert result["to"] == "safety@summitair.com"
    assert result["bcc"] == "ops@aviasafesystems.com"

    assert len(_fake_smtp.instances) == 1
    server = _fake_smtp.instances[0]
    assert server.host == "smtp.gmail.com"
    assert server.port == 587
    assert server.tls_started is True
    assert server.login_credentials == ("ghanshyam.acharya@gmail.com", "app-password-123")

    assert len(server.sent) == 1
    msg = server.sent[0]
    assert msg["To"] == "safety@summitair.com"
    assert msg["Bcc"] == "ops@aviasafesystems.com"
    assert msg["From"] == "Ghanshyam Acharya <ghanshyam.acharya@gmail.com>"
    assert msg["Subject"] == "AviaSAFE Beta Registration Request \u2014 Summit Air"


def test_send_omits_bcc_when_unconfigured(_gmail_env, _fake_smtp, monkeypatch):
    monkeypatch.setattr(settings, "GMAIL_NOTIFICATION_BCC", "")
    result = gmail_dispatcher.send_registration_acknowledgment(
        "safety@summitair.com", "Anil Shrestha", "Summit Air"
    )
    assert result["sent"] is True
    msg = _fake_smtp.instances[0].sent[0]
    assert "Bcc" not in msg


def test_async_wrapper_runs_dispatch(_gmail_env, _fake_smtp):
    result = asyncio.run(
        gmail_dispatcher.send_registration_acknowledgment_async(
            "safety@summitair.com", "Anil Shrestha", "Summit Air"
        )
    )
    assert result["sent"] is True
    assert len(_fake_smtp.instances) == 1
    assert len(_fake_smtp.instances[0].sent) == 1


def test_password_whitespace_stripped(_gmail_env, _fake_smtp, monkeypatch):
    """App passwords pasted from the Render dashboard may carry stray spaces;
    they must be stripped before login."""
    monkeypatch.setattr(settings, "GMAIL_SMTP_PASSWORD", "  ab cd  ef gh  ")
    result = gmail_dispatcher.send_registration_acknowledgment(
        "safety@summitair.com", "Anil Shrestha", "Summit Air"
    )
    assert result["sent"] is True
    assert _fake_smtp.instances[0].login_credentials == (
        "ghanshyam.acharya@gmail.com", "abcdefgh",
    )


def test_credentials_fall_back_to_smtp_user_pass(monkeypatch, _fake_smtp):
    """GMAIL_SMTP_* must fall back cleanly to SMTP_USER / SMTP_PASS."""
    monkeypatch.setattr(settings, "GMAIL_SMTP_USER", None)
    monkeypatch.setattr(settings, "GMAIL_SMTP_PASSWORD", None)
    monkeypatch.setattr(settings, "SMTP_USER", "fallback@gmail.com")
    monkeypatch.setattr(settings, "SMTP_PASS", "fallback-secret")

    assert gmail_dispatcher.gmail_configured() is True
    assert gmail_dispatcher._user() == "fallback@gmail.com"
    assert gmail_dispatcher._password() == "fallback-secret"

    result = gmail_dispatcher.send_registration_acknowledgment(
        "safety@summitair.com", "Anil Shrestha", "Summit Air"
    )
    assert result["sent"] is True
    assert _fake_smtp.instances[0].login_credentials == (
        "fallback@gmail.com", "fallback-secret",
    )


# ---------------------------------------------------------------------------
# Graceful fallbacks (never raise, never roll back)
# ---------------------------------------------------------------------------

def test_send_skips_when_credentials_empty(monkeypatch, _fake_smtp):
    monkeypatch.setattr(settings, "GMAIL_SMTP_USER", None)
    monkeypatch.setattr(settings, "GMAIL_SMTP_PASSWORD", None)

    result = gmail_dispatcher.send_registration_acknowledgment(
        "safety@summitair.com", "Anil Shrestha", "Summit Air"
    )

    assert result["sent"] is False
    assert "not configured" in result["reason"]
    assert _fake_smtp.instances == []


def test_send_catches_smtp_failure_gracefully(_gmail_env, _fake_smtp):
    def _boom(self, msg):
        raise smtplib.SMTPException("Connection reset by peer")

    _fake_smtp.send_message = _boom

    result = gmail_dispatcher.send_registration_acknowledgment(
        "safety@summitair.com", "Anil Shrestha", "Summit Air"
    )

    assert result["sent"] is False
    assert result["provider"] == "gmail"
    assert "Connection reset by peer" in result["error"]