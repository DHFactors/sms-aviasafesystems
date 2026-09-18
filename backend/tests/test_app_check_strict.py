"""H3 — App Check strict enforcement (SECURITY_REVIEW H3 remediation).

The shared verify_app_check / verify_app_check_lenient dependencies only
reject present-but-invalid tokens; an absent header passes through. The new
verify_app_check_strict rejects missing headers outright and is wired onto
the sensitive public endpoints:

  POST /api/v1/auth/login
  POST /api/v1/auth/register
  GET  /api/v1/auth/tenant-lookup

Guest copilot chat (POST /api/v1/copilot/guest/chat) intentionally stays on
verify_app_check_lenient: browser Tracking Prevention in InPrivate browsing
can suppress or staleness the reCAPTCHA token, and the endpoint is primarily
guarded by a strict per-IP sliding-window rate limit (10/min) with page-scoped
guidance only (see app/middleware/app_check.py:verify_app_check_strict doc and
app/routes/copilot.py copilot_guest_chat docstring).
"""

import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.middleware.app_check import (
    APP_CHECK_HEADER,
    verify_app_check,
    verify_app_check_lenient,
    verify_app_check_strict,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeRequest:
    def __init__(self, headers):
        self.headers = {k: v for k, v in (headers or {}).items()}


class _FakeVerification:
    app_id = "projects/test/apps/fake"
    token_type = "DISCOVERY"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# verify_app_check_strict unit behaviour
# ---------------------------------------------------------------------------

def test_strict_rejects_missing_header():
    req = _FakeRequest({})
    with pytest.raises(HTTPException) as exc:
        _run(verify_app_check_strict(req))
    assert exc.value.status_code == 403
    assert "App Check token required" in exc.value.detail


def test_strict_rejects_invalid_token(monkeypatch):
    monkeypatch.setattr("app.middleware.app_check._verify_sync", lambda token: None)
    req = _FakeRequest({APP_CHECK_HEADER: "stale-token"})
    with pytest.raises(HTTPException) as exc:
        _run(verify_app_check_strict(req))
    assert exc.value.status_code == 401


def test_strict_passes_when_token_verified(monkeypatch):
    monkeypatch.setattr("app.middleware.app_check._verify_sync", lambda token: _FakeVerification())
    req = _FakeRequest({APP_CHECK_HEADER: "valid-token"})
    assert _run(verify_app_check_strict(req)) is None


# ---------------------------------------------------------------------------
# verify_app_check / verify_app_check_lenient remain unchanged (allow absent)
# ---------------------------------------------------------------------------

def test_lenient_verify_app_check_still_allows_missing_header():
    assert _run(verify_app_check(_FakeRequest({}))) is None
    assert _run(verify_app_check_lenient(_FakeRequest({}))) is None


def test_non_strict_verify_app_check_still_rejects_invalid_token(monkeypatch):
    monkeypatch.setattr("app.middleware.app_check._verify_sync", lambda token: None)
    with pytest.raises(HTTPException) as exc:
        _run(verify_app_check(_FakeRequest({APP_CHECK_HEADER: "bad"})))
    assert exc.value.status_code == 401


def test_lenient_verify_app_check_ignores_invalid_token(monkeypatch):
    monkeypatch.setattr("app.middleware.app_check._verify_sync", lambda token: None)
    assert _run(verify_app_check_lenient(_FakeRequest({APP_CHECK_HEADER: "bad"}))) is None


# ---------------------------------------------------------------------------
# Sensitive endpoints — absent App Check header is rejected
# ---------------------------------------------------------------------------

def test_login_rejected_without_app_check_token():
    resp = TestClient(app).post(
        "/api/v1/auth/login",
        json={"email": "safety@summitair.com", "password": "Good-Pass-2026"},
    )
    assert resp.status_code == 403
    assert "App Check token required" in resp.json()["detail"]


def test_register_rejected_without_app_check_token():
    resp = TestClient(app).post(
        "/api/v1/auth/register",
        json={
            "email": "safety@summitair.com",
            "password": "Good-Pass-2026",
            "full_name": "Test User",
            "organization": "Summit Air",
            "role": "AIRLINE_ADMIN",
        },
    )
    assert resp.status_code == 403


def test_tenant_lookup_rejected_without_app_check_token():
    resp = TestClient(app).get("/api/v1/auth/tenant-lookup?code=ABC123")
    assert resp.status_code == 403


def test_login_rejected_with_invalid_app_check_token():
    resp = TestClient(app).post(
        "/api/v1/auth/login",
        json={"email": "safety@summitair.com", "password": "Good-Pass-2026"},
        headers={APP_CHECK_HEADER: "forged-token"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Sensitive endpoints — a verified token lets the handler run
# ---------------------------------------------------------------------------

def test_login_with_verified_app_check_token_reaches_handler(monkeypatch):
    monkeypatch.setattr("app.middleware.app_check._verify_sync", lambda token: _FakeVerification())

    async def _bad_credentials(email, password):
        return None

    monkeypatch.setattr("app.services.login_service.verify_credentials", _bad_credentials)
    monkeypatch.setattr("app.services.audit_service.log_audit", lambda *a, **k: None)

    resp = TestClient(app).post(
        "/api/v1/auth/login",
        json={"email": "safety@summitair.com", "password": "wrong-pass"},
        headers={APP_CHECK_HEADER: "good-token"},
    )
    assert resp.status_code == 401  # App Check passed; credentials were then rejected
    assert "Invalid email or password" in resp.json()["detail"]


def test_login_with_verified_app_check_token_succeeds(monkeypatch):
    monkeypatch.setattr("app.middleware.app_check._verify_sync", lambda token: _FakeVerification())

    async def _good_credentials(email, password):
        return {"uid": "u-1", "email": email, "display_name": "Test User"}

    class _TokenAuth:
        token = "custom-token-123"

        def create_custom_token(self, uid):
            return self.token.encode("utf-8")

    monkeypatch.setattr("app.services.login_service.verify_credentials", _good_credentials)
    monkeypatch.setattr("app.services.login_service.get_auth", lambda: _TokenAuth())
    monkeypatch.setattr("app.services.audit_service.log_audit", lambda *a, **k: None)

    resp = TestClient(app).post(
        "/api/v1/auth/login",
        json={"email": "safety@summitair.com", "password": "Good-Pass-2026"},
        headers={APP_CHECK_HEADER: "good-token"},
    )
    assert resp.status_code == 200
    assert resp.json()["custom_token"] == "custom-token-123"