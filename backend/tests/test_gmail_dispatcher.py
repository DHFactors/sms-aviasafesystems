"""Unit tests for the Gmail REST registration-acknowledgment dispatcher.

Covers email composition (subject / sender / HTML body), recipient addressing
(To + optional Bcc), the real HTTPS flow via a fake httpx.AsyncClient — OAuth2
refresh-token exchange followed by Gmail API messages.send — and the graceful
fallbacks: empty credentials, token failures and HTTP send failures must never
raise — a mail problem can never crash or roll back a valid tenant record.
"""

import asyncio
import base64
import email
from email.header import decode_header, make_header
from email.mime.multipart import MIMEMultipart

import httpx
import pytest

from app.core.config import settings
from app.services import gmail_dispatcher


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=None, response=self
            )

    def json(self):
        return self._json


class _FakeClient:
    """Drop-in httpx.AsyncClient recording every request the dispatcher makes."""

    instances = []
    default_token_status = 200
    default_send_status = 200

    def __init__(self, timeout=None):
        self.timeout = timeout
        self.posts = []
        _FakeClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        if url == gmail_dispatcher.OAUTH_TOKEN_URL:
            if _FakeClient.default_token_status >= 400:
                return _FakeResponse(
                    _FakeClient.default_token_status,
                    text="{\"error\": \"invalid_grant\"}",
                )
            return _FakeResponse(200, {"access_token": "ya29.fake-access-token"})
        if _FakeClient.default_send_status >= 400:
            return _FakeResponse(
                _FakeClient.default_send_status,
                text="{\"error\": \"quota exceeded\"}",
            )
        return _FakeResponse(200, {"id": "msg-1", "threadId": "t-1"})


@pytest.fixture(autouse=True)
def _fake_httpx(monkeypatch):
    _FakeClient.instances = []
    _FakeClient.default_token_status = 200
    _FakeClient.default_send_status = 200
    monkeypatch.setattr(gmail_dispatcher.httpx, "AsyncClient", _FakeClient)
    yield _FakeClient
    _FakeClient.instances = []


@pytest.fixture
def _gmail_env(monkeypatch):
    monkeypatch.setattr(settings, "GMAIL_CLIENT_ID", "client-123.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "GMAIL_CLIENT_SECRET", "secret-456")
    monkeypatch.setattr(settings, "GMAIL_REFRESH_TOKEN", "refresh-789")
    monkeypatch.setattr(settings, "GMAIL_SENDER_EMAIL", "ghanshyam.acharya@gmail.com")
    monkeypatch.setattr(settings, "GMAIL_NOTIFICATION_BCC", "ops@aviasafesystems.com")


def _decoded_message(raw_b64):
    return email.message_from_string(
        base64.urlsafe_b64decode(raw_b64).decode("utf-8")
    )


def _decoded_header(value):
    """Decode an RFC 2047 encoded header (em-dashes trigger encoding)."""
    return str(make_header(decode_header(value)))


def _last_send_payload(fake):
    posts = fake.instances[0].posts
    assert len(posts) == 2
    return posts[1][1]["json"]["raw"]


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

def test_build_message_subject_sender_body(_gmail_env):
    msg = gmail_dispatcher._build_message(
        "safety@summitair.com", "Anil Shrestha", "Summit Air"
    )
    assert isinstance(msg, MIMEMultipart)
    assert msg["Subject"] == "Welcome to AviaSAFE SMS Beta \u2014 Summit Air"
    assert msg["From"] == "AviaSAFE Systems <ghanshyam.acharya@gmail.com>"
    assert msg["To"] == "safety@summitair.com"
    assert msg["Bcc"] == "ops@aviasafesystems.com"

    payload = msg.get_payload()[0]
    html = payload.get_payload(decode=True).decode("utf-8")
    assert payload.get_content_type() == "text/html"
    assert "Dear Anil Shrestha," in html
    assert "<strong>Summit Air</strong> has been registered" in html
    assert "AviaSAFE Aviation SMS Beta Platform" in html
    assert "Ghanshyam Acharya" in html


def test_build_message_default_sender_when_unset(_gmail_env, monkeypatch):
    monkeypatch.setattr(settings, "GMAIL_SENDER_EMAIL", "")
    msg = gmail_dispatcher._build_message("a@b.com", "A", "Org")
    assert msg["From"] == "AviaSAFE Systems <me>"


def test_gmail_configured_reflects_credentials(_gmail_env):
    assert gmail_dispatcher.gmail_configured() is True


def test_gmail_configured_false_without_refresh_token(_gmail_env, monkeypatch):
    monkeypatch.setattr(settings, "GMAIL_REFRESH_TOKEN", None)
    assert gmail_dispatcher.gmail_configured() is False


# ---------------------------------------------------------------------------
# Dispatch path (fake HTTPS client)
# ---------------------------------------------------------------------------

def test_send_dispatches_with_to_and_bcc(_gmail_env, _fake_httpx):
    result = asyncio.run(
        gmail_dispatcher.send_registration_acknowledgment(
            "safety@summitair.com", "Anil Shrestha", "Summit Air"
        )
    )

    assert result["sent"] is True
    assert result["provider"] == "gmail_rest"
    assert result["to"] == "safety@summitair.com"
    assert result["bcc"] == "ops@aviasafesystems.com"
    assert result["subject"] == "Welcome to AviaSAFE SMS Beta \u2014 Summit Air"

    posts = _fake_httpx.instances[0].posts
    assert len(posts) == 2

    token_url, token_kwargs = posts[0]
    assert token_url == gmail_dispatcher.OAUTH_TOKEN_URL
    assert token_kwargs["data"] == {
        "client_id": "client-123.apps.googleusercontent.com",
        "client_secret": "secret-456",
        "refresh_token": "refresh-789",
        "grant_type": "refresh_token",
    }

    send_url, send_kwargs = posts[1]
    assert send_url == gmail_dispatcher.GMAIL_SEND_URL
    assert send_kwargs["headers"]["Authorization"] == "Bearer ya29.fake-access-token"
    assert send_kwargs["headers"]["Content-Type"] == "application/json"

    msg = _decoded_message(send_kwargs["json"]["raw"])
    assert msg["To"] == "safety@summitair.com"
    assert msg["Bcc"] == "ops@aviasafesystems.com"
    assert msg["From"] == "AviaSAFE Systems <ghanshyam.acharya@gmail.com>"
    assert _decoded_header(msg["Subject"]) == "Welcome to AviaSAFE SMS Beta \u2014 Summit Air"


def test_send_omits_bcc_when_unconfigured(_gmail_env, _fake_httpx, monkeypatch):
    monkeypatch.setattr(settings, "GMAIL_NOTIFICATION_BCC", "")
    result = asyncio.run(
        gmail_dispatcher.send_registration_acknowledgment(
            "safety@summitair.com", "Anil Shrestha", "Summit Air"
        )
    )
    assert result["sent"] is True
    assert result["bcc"] is None
    msg = _decoded_message(_last_send_payload(_fake_httpx))
    assert "Bcc" not in msg


def test_async_alias_runs_dispatch(_gmail_env, _fake_httpx):
    result = asyncio.run(
        gmail_dispatcher.send_registration_acknowledgment_async(
            "safety@summitair.com", "Anil Shrestha", "Summit Air"
        )
    )
    assert result["sent"] is True
    assert len(_fake_httpx.instances[0].posts) == 2


# ---------------------------------------------------------------------------
# Graceful fallbacks (never raise, never roll back)
# ---------------------------------------------------------------------------

def test_send_skips_when_credentials_empty(monkeypatch, _fake_httpx):
    monkeypatch.setattr(settings, "GMAIL_CLIENT_ID", None)
    monkeypatch.setattr(settings, "GMAIL_REFRESH_TOKEN", None)

    result = asyncio.run(
        gmail_dispatcher.send_registration_acknowledgment(
            "safety@summitair.com", "Anil Shrestha", "Summit Air"
        )
    )

    assert result["sent"] is False
    assert result["provider"] == "gmail_rest"
    assert "not configured" in result["reason"]
    assert _fake_httpx.instances == []


def test_send_catches_token_failure_gracefully(_gmail_env, _fake_httpx):
    _fake_httpx.default_token_status = 401

    result = asyncio.run(
        gmail_dispatcher.send_registration_acknowledgment(
            "safety@summitair.com", "Anil Shrestha", "Summit Air"
        )
    )

    assert result["sent"] is False
    assert "401" in result["error"]


def test_send_catches_send_failure_gracefully(_gmail_env, _fake_httpx):
    _fake_httpx.default_send_status = 500

    result = asyncio.run(
        gmail_dispatcher.send_registration_acknowledgment(
            "safety@summitair.com", "Anil Shrestha", "Summit Air"
        )
    )

    assert result["sent"] is False
    assert result["provider"] == "gmail_rest"
    assert "HTTP 500" in result["error"]
    assert "quota exceeded" in result["error"]