# ============================================================================
# Wiring tests for Batch 1 (identity layer): middleware/auth, users, and
# regulator_service now read/write Postgres through app/db/pg.py. The pg
# layer (and Firebase auth) is monkeypatched so no database is required.
# ============================================================================

import pytest

import app.middleware.auth as auth_mod
import app.services.regulator_service as reg_mod
import app.services.users as users_mod


# ---- middleware/auth.py ---------------------------------------------------


def test_tenant_status_suspended(monkeypatch):
    monkeypatch.setattr(
        auth_mod.pg, "fetch_by",
        lambda model, col, value: {"status": "SUSPENDED", "slug": value},
    )
    assert auth_mod._tenant_is_suspended("active-air") is True


def test_tenant_status_not_suspended(monkeypatch):
    monkeypatch.setattr(
        auth_mod.pg, "fetch_by",
        lambda model, col, value: {"status": "ACTIVE", "slug": value},
    )
    assert auth_mod._tenant_is_suspended("active-air") is False


def test_tenant_status_fail_open_on_missing(monkeypatch):
    monkeypatch.setattr(auth_mod.pg, "fetch_by", lambda model, col, value: None)
    assert auth_mod._tenant_is_suspended("ghost-air") is False


def test_tenant_status_fail_open_on_error(monkeypatch):
    def _boom(model, col, value):
        raise RuntimeError("db down")

    monkeypatch.setattr(auth_mod.pg, "fetch_by", _boom)
    assert auth_mod._tenant_is_suspended("active-air") is False


def test_email_claim_fallback_sources_from_pg(monkeypatch):
    captured = {}

    def _fake_fetch_all(model, *, where=None, order_by=None, limit=None):
        captured["limit"] = limit
        captured["where"] = where
        return [{
            "id": "fixedwing",
            "slug": "fixedwing",
            "safety_manager": {"email": "sm@fixedwing.test"},
        }]

    monkeypatch.setattr(auth_mod.pg, "fetch_all", _fake_fetch_all)
    resolved = auth_mod._lookup_tenant_by_email("sm@fixedwing.test")
    assert resolved == {"tenant_id": "fixedwing", "role": "AIRLINE_ADMIN"}
    assert captured["limit"] == 50
    assert captured["where"]  # a real JSONB filter expression was built


# ---- users.py -------------------------------------------------------------


def test_list_tenant_users_maps_doc_shape(monkeypatch):
    monkeypatch.setattr(users_mod.pg, "fetch_all", lambda model, **kw: [
        {
            "uid": "u1",
            "email": "a@b.c",
            "display_name": "A B",
            "role": "STAFF",
            "department": "Flight Operations",
            "created_at": "2026-01-01T00:00:00+00:00",
            "last_login": "2026-02-01T00:00:00+00:00",
        },
        {"uid": "u2", "email": "z@y.c", "created_at": None, "last_login": None},
    ])
    rows = users_mod.list_tenant_users("fixedwing")
    assert rows[1] == {
        "uid": "u1",
        "email": "a@b.c",
        "displayName": "A B",
        "role": "STAFF",
        "department": "Flight Operations",
        "createdAt": "2026-01-01T00:00:00+00:00",
        "lastLogin": "2026-02-01T00:00:00+00:00",
    }
    assert rows[0]["uid"] == "u2"  # None createdAt sorts first ("" < ISO text)
    assert rows[0]["createdAt"] is None


def test_get_user_department_by_uid_then_email(monkeypatch):
    calls = []

    def _fake_fetch_by(model, col, value):
        calls.append(col)
        if col == "uid" and value == "u1":
            return {"uid": "u1", "department": "CAMO"}
        if col == "email" and value == "ops@x.test":
            return {"email": "ops@x.test", "department": "Flight Operations"}
        return None

    monkeypatch.setattr(users_mod.pg, "fetch_by", _fake_fetch_by)
    assert users_mod.get_user_department(uid="u1") == "CAMO"
    assert users_mod.get_user_department(email="ops@x.test") == "Flight Operations"
    assert users_mod.get_user_department(uid="ghost") == ""
    assert users_mod.get_user_department() == ""


def test_upsert_user_doc_writes_through_pg(monkeypatch):
    captured = {}

    def _fake_upsert(model, col, value, data):
        captured["col"] = col
        captured["value"] = value
        captured["data"] = data

    monkeypatch.setattr(users_mod.pg, "upsert", _fake_upsert)
    users_mod.upsert_user_doc("u9", {"uid": "u9", "role": "STAFF"})
    assert captured == {"col": "uid", "value": "u9", "data": {"uid": "u9", "role": "STAFF"}}


# ---- regulator_service.py -------------------------------------------------


def test_list_regulators_enriches_status_and_count(monkeypatch):
    monkeypatch.setattr(reg_mod.pg, "fetch_all", lambda model, **kw: [
        {"id": "caan", "slug": "caan", "name": "CAAN",
         "operator_tenant_ids": ["fixedwing", "rotarywing"], "status": "active"},
    ])
    regs = reg_mod.list_regulators()
    assert regs[0]["id"] == "caan"
    assert regs[0]["operator_count"] == 2
    assert regs[0]["status"] == "active"


def test_get_regulator_builds_operator_list(monkeypatch):
    def _fake_fetch_by(model, col, value):
        if model.__tablename__ == "tenants":
            return {"slug": "fixedwing", "name": "FW", "country": "Nepal",
                    "regulator_id": "caan", "active": True}
        return {"slug": "caan", "operator_tenant_ids": ["fixedwing"], "status": "active"}

    monkeypatch.setattr(reg_mod.pg, "fetch_by", _fake_fetch_by)
    monkeypatch.setattr(reg_mod.pg, "fetch_all", lambda model, **kw: [])
    reg = reg_mod.get_regulator("caan")
    assert reg["operators"][0]["tenant_id"] == "fixedwing"
    assert reg["operators"][0]["country"] == "Nepal"


def test_get_regulator_missing_returns_none(monkeypatch):
    monkeypatch.setattr(reg_mod.pg, "fetch_by", lambda model, col, value: None)
    assert reg_mod.get_regulator("ghost") is None


def test_update_regulator_status_persists_and_returns_merged(monkeypatch):
    monkeypatch.setattr(
        reg_mod.pg, "fetch_by",
        lambda model, col, value: {"id": "caan", "slug": "caan", "status": "active"},
    )
    captured = {}

    def _fake_update(model, col, value, doc):
        captured["value"] = value
        captured["doc"] = doc

    monkeypatch.setattr(reg_mod.pg, "update", _fake_update)
    merged = reg_mod.update_regulator_status(
        "caan", {"uid": "admin"}, status="suspended", from_date="2026-01-01"
    )
    assert merged["status"] == "suspended"
    assert captured["value"] == "caan"
    assert captured["doc"]["active"] is False
    assert captured["doc"]["contract"]["start_date"] == "2026-01-01"
    assert captured["doc"]["status_updated_by"] == "admin"


def test_update_regulator_status_unknown_raises(monkeypatch):
    monkeypatch.setattr(reg_mod.pg, "fetch_by", lambda model, col, value: None)
    with pytest.raises(ValueError):
        reg_mod.update_regulator_status("ghost", {"uid": "admin"}, status="active")