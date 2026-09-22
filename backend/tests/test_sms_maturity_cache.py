# ============================================================================
# Module A `sms_maturity` cache — P1-1 / P1-2 / P1-3 verification.
#
#  - write -> read round-trip against the LIVE assessment schema (P1-1)
#  - RLS enabled + `p_sms_maturity_tenant_isolation` policy present (P1-2)
#  - cross-tenant read denied when acting as the `authenticated` JWT role
#  - dashboard -> Module A boundary: the dashboard layer no longer touches the
#    `sms_maturity` table; only Module A's service/endpoints own it (P1-3)
# ============================================================================

import asyncio
import inspect
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.ids import register_tenant, tenant_uuid
from app.db.session import session_scope
from app.services import dashboard_service, sms_maturity_service

POLICY = "p_sms_maturity_tenant_isolation"


# ---------------------------------------------------------------------------
# Live-DB helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.run(coro)


def _create_tenant(slug: str) -> str:
    """Insert a throwaway tenant row so the sms_maturity FK is satisfiable."""
    tid = register_tenant(slug)

    async def _go():
        async with session_scope() as session:
            await session.execute(text(
                "INSERT INTO public.tenants "
                "(id, slug, name, is_demo, is_beta_sandbox, created_at, updated_at) "
                "VALUES (:id, :slug, :name, false, false, now(), now()) "
                "ON CONFLICT DO NOTHING"
            ), {"id": tid, "slug": slug, "name": slug})

    _run(_go())
    return tid


def _delete_tenant(slug: str) -> None:
    tid = register_tenant(slug)

    async def _go():
        async with session_scope() as session:
            await session.execute(
                text("DELETE FROM public.sms_maturity WHERE tenant_id = :id"),
                {"id": tid},
            )
            await session.execute(
                text("DELETE FROM public.tenants WHERE id = :id"), {"id": tid}
            )

    _run(_go())


def _unique_slug(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


# ---------------------------------------------------------------------------
# P1-1 — round-trip against the live schema
# ---------------------------------------------------------------------------

def test_cache_write_read_round_trip():
    slug = _unique_slug("smcache")
    _create_tenant(slug)
    try:
        payload = {
            "overall_sms_maturity": 3.0,
            "pillars": {
                "safety_policy": 2.0,
                "safety_risk_management": 3.0,
                "safety_assurance": 4.0,
                "safety_promotion": 3.0,
            },
            "question_averages": {"q1": 2.0, "q2": 3.0},
            "low_pillars": [{"pillar": "safety_policy", "pct": 25.0}],
            "recommendations": [{"pillar": "safety_policy", "actions": ["Do X"]}],
        }
        sms_maturity_service.write_sms_maturity(slug, payload)

        cached = sms_maturity_service.read_sms_maturity(slug)
        assert cached is not None
        assert cached["overall_sms_maturity"] == 3.0
        assert cached["level"] == 3
        assert cached["pillars"] == payload["pillars"]
        assert cached["element_scores"] == payload["question_averages"]
        assert cached["gap_analysis"] == payload["low_pillars"]
        assert cached["recommendations"] == payload["recommendations"]
        assert cached["generated_at"] is not None
    finally:
        _delete_tenant(slug)


def test_cache_read_missing_tenant_returns_none():
    slug = _unique_slug("smmissing")
    assert sms_maturity_service.read_sms_maturity(slug) is None


def test_cache_accepts_live_column_names():
    """A payload already using the live column names is written unchanged."""
    slug = _unique_slug("smlive")
    _create_tenant(slug)
    try:
        sms_maturity_service.write_sms_maturity(slug, {
            "overall_sms_maturity": 5.0,
            "pillars": {"safety_policy": 5.0},
            "element_scores": {"e1": 90.0},
            "gap_analysis": {"e1": "low"},
            "recommendations": [],
        })
        cached = sms_maturity_service.read_sms_maturity(slug)
        assert cached["element_scores"] == {"e1": 90.0}
        assert cached["gap_analysis"] == {"e1": "low"}
        assert cached["level"] == 5
    finally:
        _delete_tenant(slug)


# ---------------------------------------------------------------------------
# P1-2 — RLS enabled + policy present + cross-tenant read denied
# ---------------------------------------------------------------------------

def test_rls_enabled_and_policy_present():
    async def _go():
        async with session_scope() as session:
            rowsecurity = (await session.execute(text(
                "SELECT rowsecurity FROM pg_tables "
                "WHERE schemaname='public' AND tablename='sms_maturity'"
            ))).scalar_one_or_none()
            policies = (await session.execute(text(
                "SELECT policyname FROM pg_policies "
                "WHERE schemaname='public' AND tablename='sms_maturity'"
            ))).scalars().all()
            return rowsecurity, list(policies)

    rowsecurity, policies = _run(_go())
    assert rowsecurity is True, "sms_maturity RLS must be enabled"
    assert POLICY in policies, policies


def test_rls_denies_cross_tenant_read():
    slug_a = _unique_slug("smrls-a")
    slug_b = _unique_slug("smrls-b")
    _create_tenant(slug_a)
    _create_tenant(slug_b)
    try:
        sms_maturity_service.write_sms_maturity(
            slug_a, {"overall_sms_maturity": 4.0, "recommendations": []})
        sms_maturity_service.write_sms_maturity(
            slug_b, {"overall_sms_maturity": 2.0, "recommendations": []})
        id_a, id_b = tenant_uuid(slug_a), tenant_uuid(slug_b)

        async def _go():
            async with session_scope() as session:
                # Act as the authenticated JWT role and claim tenant A.
                await session.execute(text("SET LOCAL ROLE authenticated"))
                await session.execute(
                    text("SELECT set_config('request.jwt.claims', :c, true)"),
                    {"c": '{"app_metadata":{"tenant_id":"%s"}}' % id_a},
                )
                own = (await session.execute(
                    text("SELECT count(*) FROM public.sms_maturity WHERE tenant_id = :t"),
                    {"t": id_a},
                )).scalar_one()
                other = (await session.execute(
                    text("SELECT count(*) FROM public.sms_maturity WHERE tenant_id = :t"),
                    {"t": id_b},
                )).scalar_one()
                return own, other

        own, other = _run(_go())
        assert own == 1, "tenant must see its own maturity row"
        assert other == 0, "RLS must hide another tenant's maturity row"
    finally:
        _delete_tenant(slug_a)
        _delete_tenant(slug_b)


# ---------------------------------------------------------------------------
# P1-3 — dashboard -> Module A boundary
# ---------------------------------------------------------------------------

def test_dashboard_no_longer_accesses_sms_maturity_table():
    """The dashboard layer must go through Module A, never the table itself."""
    src = inspect.getsource(dashboard_service)
    assert "SmsMaturity" not in src
    assert "sms_maturity_service" in src


def test_cache_endpoint_round_trip():
    """POST /api/v1/sms-maturity/{tenant_id}/cache writes; GET reads back."""
    from app.main import app
    from app.middleware.auth import get_current_user

    slug = _unique_slug("smapi")
    _create_tenant(slug)
    app.dependency_overrides[get_current_user] = lambda: {
        "uid": "u", "role": "AIRLINE_ADMIN", "tenant_id": slug,
        "email": "officer@example.com",
    }
    try:
        c = TestClient(app)
        r = c.post(f"/api/v1/sms-maturity/{slug}/cache", json={
            "overall_sms_maturity": 4.0,
            "pillars": {"safety_policy": 4.0},
            "recommendations": [{"action": "A"}],
        })
        assert r.status_code == 201, r.text

        g = c.get(f"/api/v1/sms-maturity/{slug}/cache")
        assert g.status_code == 200, g.text
        body = g.json()
        assert body["status"] == "success"
        assert body["data"]["overall_sms_maturity"] == 4.0
        assert body["data"]["recommendations"] == [{"action": "A"}]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        _delete_tenant(slug)


def test_cache_endpoint_rejects_cross_tenant_scope():
    from app.main import app
    from app.middleware.auth import get_current_user

    slug_a = _unique_slug("smapi-a")
    slug_b = _unique_slug("smapi-b")
    _create_tenant(slug_a)
    _create_tenant(slug_b)
    app.dependency_overrides[get_current_user] = lambda: {
        "uid": "u", "role": "AIRLINE_ADMIN", "tenant_id": slug_a,
        "email": "officer@example.com",
    }
    try:
        c = TestClient(app)
        r = c.post(f"/api/v1/sms-maturity/{slug_b}/cache",
                   json={"overall_sms_maturity": 4.0})
        assert r.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        _delete_tenant(slug_a)
        _delete_tenant(slug_b)


def test_cache_endpoint_requires_auth():
    from app.main import app

    slug = _unique_slug("smanon")
    c = TestClient(app)
    r = c.post(f"/api/v1/sms-maturity/{slug}/cache",
               json={"overall_sms_maturity": 4.0})
    assert r.status_code in (401, 403)
