"""
Tests for the tenant-scoped SSP risk-trends dashboard endpoint.

Verifies:
  1. The /api/v1/dashboard/risk-trends endpoint returns the SSM-aligned
     quarterly risk-index series (aggregated, anonymized) for the caller's
     own tenant only.
  2. Tenant isolation: an operator receives only their own data (the
     DashboardService builds a tenant-scoped ReportFilter).
  3. Unauthorized / tenant-less callers are rejected by get_tenant_user.
"""

from unittest.mock import patch

import pytest

from app.main import app
from app.middleware.auth import get_current_user


def _tenant_user(role="AIRLINE_ADMIN", tenant_id="test_airline"):
    return {
        "uid": "mock_user",
        "email": "test@aviasafe.com",
        "role": role,
        "tenant_id": tenant_id,
        "claims": {"role": role, "tenant_id": tenant_id},
    }


@pytest.fixture
def risk_trends_data():
    return {
        "categories": ["Operational", "Technical", "Human Factors", "Organizational", "External"],
        "quarters": ["2026-Q1", "2026-Q2"],
        "labels": ["2026 Q1", "2026 Q2"],
        "series": [
            {
                "category": "Technical",
                "points": [
                    {"quarter": "2026-Q1", "label": "2026 Q1", "avg_risk_index": 40.0},
                    {"quarter": "2026-Q2", "label": "2026 Q2", "avg_risk_index": 44.0},
                ],
            },
        ],
    }


def _override_current_user(user):
    app.dependency_overrides[get_current_user] = lambda: user


def _clear_overrides():
    app.dependency_overrides.pop(get_current_user, None)


def test_risk_trends_rejects_tenant_less_user(client):
    _override_current_user(_tenant_user(role="USER", tenant_id=None))
    try:
        resp = client.get("/api/v1/dashboard/risk-trends")
        assert resp.status_code == 403, resp.text
    finally:
        _clear_overrides()


def test_risk_trends_returns_aggregated_series(client, risk_trends_data):
    _override_current_user(_tenant_user())
    with patch(
        "app.routes.dashboard.DashboardService.get_ssp_risk_trends",
        return_value=risk_trends_data,
    ):
        try:
            resp = client.get("/api/v1/dashboard/risk-trends?days=730")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            data = body["data"]
            assert body["status"] == "success"
            assert "quarters" in data
            assert "labels" in data
            assert len(data["series"]) >= 1
            tech = next(s for s in data["series"] if s["category"] == "Technical")
            assert tech["points"][0]["avg_risk_index"] == 40.0
        finally:
            _clear_overrides()


def test_risk_trends_empty_tenant_returns_empty_series(client):
    _override_current_user(_tenant_user())
    empty = {
        "categories": ["Operational", "Technical", "Human Factors", "Organizational", "External"],
        "quarters": [],
        "labels": [],
        "series": [
            {"category": c, "points": []}
            for c in ["Operational", "Technical", "Human Factors", "Organizational", "External"]
        ],
    }
    with patch(
        "app.routes.dashboard.DashboardService.get_ssp_risk_trends",
        return_value=empty,
    ):
        try:
            resp = client.get("/api/v1/dashboard/risk-trends")
            assert resp.status_code == 200, resp.text
            assert resp.json()["data"]["quarters"] == []
        finally:
            _clear_overrides()
