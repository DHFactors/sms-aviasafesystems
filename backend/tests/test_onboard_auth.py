"""C1/C2 remediation — auth + access-key enforcement on enterprise onboarding.

Covers POST /api/v1/tenants/onboard:
  * unauthenticated callers are rejected,
  * a caller-supplied key must match BETA_ACCESS_KEY,
  * a non-SUPER_ADMIN caller is rejected even with the correct key,
  * a SUPER_ADMIN with the correct key is delegated to the service.

Also covers the production startup guard that refuses to boot without
BETA_ACCESS_KEY (C2).
"""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app, _validate_production_config
from app.middleware.auth import get_current_user

ENDPOINT = "/api/v1/tenants/onboard"
BETA_KEY = "TEST-BETA-KEY-2026"


def _admin_user(role: str = "SUPER_ADMIN"):
    return {
        "uid": "admin-1",
        "email": "admin@aviasafesystems.com",
        "role": role,
        "tenant_id": None,
        "department": None,
        "claims": {"role": role, "tenant_id": None},
    }


def _body(**overrides):
    body = {
        "organization_name": "Test Air",
        "admin_full_name": "Test Admin",
        "admin_title": "Safety Manager",
        "email": "safety@testair.com",
        "password": "Test-Password-2026",
        "classification": "airline_fixed_wing",
        "beta_access_key": BETA_KEY,
    }
    body.update(overrides)
    return body


def test_onboard_without_auth_returns_401_or_403():
    # No override -> the real get_current_user/get_admin_user runs with no
    # bearer token, so the request is rejected before the handler.
    resp = TestClient(app).post(ENDPOINT, json=_body())
    assert resp.status_code in (401, 403)


def test_onboard_with_wrong_beta_key_returns_403(monkeypatch):
    monkeypatch.setattr(settings, "BETA_ACCESS_KEY", BETA_KEY)
    # Override the underlying user so the real SUPER_ADMIN check passes and the
    # real onboard_tenant service performs the key comparison.
    app.dependency_overrides[get_current_user] = lambda: _admin_user()
    try:
        resp = TestClient(app).post(ENDPOINT, json=_body(beta_access_key="WRONG-KEY"))
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert resp.status_code == 403


def test_onboard_with_correct_beta_key_but_no_admin_role_returns_403(monkeypatch):
    monkeypatch.setattr(settings, "BETA_ACCESS_KEY", BETA_KEY)
    app.dependency_overrides[get_current_user] = lambda: _admin_user(role="AIRLINE_ADMIN")
    try:
        resp = TestClient(app).post(ENDPOINT, json=_body())
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert resp.status_code == 403


def test_onboard_with_admin_role_and_correct_key_succeeds(monkeypatch):
    monkeypatch.setattr(settings, "BETA_ACCESS_KEY", BETA_KEY)
    # DB-backed provisioning is mocked; this test asserts auth + key wiring.
    mock_onboard = AsyncMock(
        return_value={
            "tenant_id": "test-air",
            "tenant_name": "Test Air",
            "seeded_hazards": 0,
            "email_sent": False,
        }
    )
    monkeypatch.setattr("app.api.v1.endpoints.tenants.onboard_tenant", mock_onboard)
    app.dependency_overrides[get_current_user] = lambda: _admin_user()
    try:
        resp = TestClient(app).post(ENDPOINT, json=_body())
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 201
    assert resp.json()["success"] is True
    assert resp.json()["tenant_id"] == "test-air"
    assert mock_onboard.await_count == 1
    assert mock_onboard.call_args.kwargs["beta_access_key"] == BETA_KEY


def test_production_requires_beta_access_key(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "BETA_ACCESS_KEY", None)
    with pytest.raises(RuntimeError):
        _validate_production_config()


def test_production_with_beta_access_key_does_not_raise(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "BETA_ACCESS_KEY", BETA_KEY)
    _validate_production_config()
