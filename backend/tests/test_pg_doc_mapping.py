# ============================================================================
# Tests for app/db/pg.py document mapping (typed columns + JSONB bag). These
# are pure functions — no database connection required.
# ============================================================================

import pytest

from app.db import pg
from app.db.db_models import Regulator, Tenant, UserProfile


def test_row_to_doc_overlays_typed_columns_onto_data():
    row = Tenant(
        slug="fixedwing",
        name="Fixed-Wing Operator",
        status="ACTIVE",
        is_demo=True,
        data={"regulator_id": "caan", "safety_manager": {"email": "sm@fw.test"}},
    )
    doc = pg.row_to_doc(row)
    assert doc["id"] == "fixedwing"
    assert doc["slug"] == "fixedwing"
    assert doc["status"] == "ACTIVE"
    assert doc["is_demo"] is True
    assert doc["regulator_id"] == "caan"
    assert doc["safety_manager"] == {"email": "sm@fw.test"}


def test_row_to_doc_data_bag_wins_over_typed_projection():
    row = Tenant(slug="fixedwing", status="SUSPENDED", data={"status": "ACTIVE"})
    assert pg.row_to_doc(row)["status"] == "ACTIVE"


def test_row_to_doc_preserves_auth_bookkeeping_from_data():
    row = Tenant(
        slug="z",
        data={"created_at": "2026-01-01T00:00:00+00:00", "last_login": "2026-02-01T00:00:00+00:00"},
    )
    doc = pg.row_to_doc(row)
    assert doc["created_at"] == "2026-01-01T00:00:00+00:00"
    assert doc["last_login"] == "2026-02-01T00:00:00+00:00"


def test_row_to_doc_regulator_id_is_slug():
    row = Regulator(slug="caan", name="Civil Aviation Authority", regulator_type="state_regulator",
                    operator_tenant_ids=["fixedwing"])
    doc = pg.row_to_doc(row)
    assert doc["id"] == "caan"
    assert doc["operator_tenant_ids"] == ["fixedwing"]


def test_row_to_doc_user_id_is_uid():
    row = UserProfile(uid="u1", email="a@b.c", role="STAFF", data={"is_developer": True})
    doc = pg.row_to_doc(row)
    assert doc["id"] == "u1"
    assert doc["is_developer"] is True


def test_row_to_doc_none_row_is_empty():
    assert pg.row_to_doc(None) == {}


def test_split_doc_routes_typed_vs_data():
    kwargs = pg._split_doc(
        Tenant,
        {"slug": "fixedwing", "status": "DEMO", "is_demo": True,
         "contract": {"start_date": "2026-01-01"}, "regulator_id": "caan"},
    )
    assert kwargs["slug"] == "fixedwing"
    assert kwargs["status"] == "DEMO"
    assert kwargs["is_demo"] is True
    assert kwargs["regulator_id"] == "caan"
    assert kwargs["data"] == {"contract": {"start_date": "2026-01-01"}}


def test_split_doc_skips_none_values():
    kwargs = pg._split_doc(Tenant, {"slug": "x", "status": None, "name": ""})
    assert "status" not in kwargs
    assert kwargs["name"] == ""


def test_split_doc_user_extras_land_in_data():
    kwargs = pg._split_doc(
        UserProfile,
        {"uid": "u1", "email": "a@b.c", "is_developer": True, "last_login": "2026-02-01T00:00:00+00:00"},
    )
    assert kwargs["uid"] == "u1"
    assert kwargs["email"] == "a@b.c"
    assert kwargs["data"]["is_developer"] is True
    assert kwargs["data"]["last_login"] == "2026-02-01T00:00:00+00:00"