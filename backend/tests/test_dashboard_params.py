# ============================================================================
# P3-13 — Dashboard standard params (period / granularity / group_by).
# ============================================================================

import pytest
from fastapi import HTTPException

from app.routes.dashboard_params import dashboard_params


def _call(**kw):
    base = dict(period=None, granularity=None, group_by=None,
                period_start=None, period_end=None, days=None)
    base.update(kw)
    return dashboard_params(**base)


def test_period_tokens_resolve_days():
    assert _call(period="30d")["days"] == 30
    assert _call(period="90d")["days"] == 90
    assert _call(period="1y")["days"] == 365


def test_legacy_days_back_compat():
    assert _call(days=45)["days"] == 45


def test_custom_period_requires_both_boundaries():
    with pytest.raises(HTTPException) as exc:
        _call(period="custom", period_start="2026-01-01")
    assert exc.value.status_code == 422
    out = _call(period="custom",
                period_start="2026-01-01", period_end="2026-01-31")
    assert out["days"] == 30
    assert out["period_start"] is not None


def test_custom_period_end_before_start_rejected():
    with pytest.raises(HTTPException):
        _call(period="custom", period_start="2026-02-01", period_end="2026-01-01")


def test_invalid_period_and_granularity():
    with pytest.raises(HTTPException) as e1:
        _call(period="7d")
    assert e1.value.status_code == 422
    with pytest.raises(HTTPException) as e2:
        _call(granularity="hour")
    assert e2.value.status_code == 422
    assert _call(granularity="week")["granularity"] == "week"


def test_group_by_passthrough():
    assert _call(group_by="department")["group_by"] == "department"
