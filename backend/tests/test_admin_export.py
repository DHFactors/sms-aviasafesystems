# ============================================================================
# Tests for SUPER_ADMIN data exports — GET /api/v1/admin/export/*
# (dummy-data, purge-data, all-tables, table/{table_name})
# ============================================================================

import asyncio
import datetime as _dt
import re
import uuid as _uuid
from types import SimpleNamespace

import pytest

from app.db import db_models as dm
from app.db.ids import tenant_uuid
from app.services.admin_data_service import (
    DEMO_EXPORT_KINDS,
    DEMO_EXPORT_TABLES,
    _blocks_to_csv,
    _csv_repr,
    _dicts_to_csv,
    export_all_tables_csv,
    export_demo_data_csv,
    export_purge_summary_csv,
    export_single_table_csv,
)

PURGE_TABLE_ORDER = [
    "hazard_rca_factors",
    "hazard_assessments",
    "hazard_capas",
    "hazard_rca_entries",
    "verifications",
    "closures",
    "corrective_actions",
    "flight_diversions",
    "safety_deficiencies",
    "psoe_findings",
    "psoe_assessments",
    "survey_responses",
    "surveys",
    "caps",
    "cans",
    "reports",
    "hazards",
    "bow_tie_controls",
    "bow_tie_consequences",
    "bow_tie_threats",
    "bow_tie_analyses",
    "risk_register",
    "barrier_register",
    "state_risk_register",
    "regulatory_reports",
]

TS_RE = r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}"


class _FakeResult:
    def mappings(self):
        return SimpleNamespace(all=lambda: [])

    def scalar_one(self):
        return 7


class _FakeSession:
    def __init__(self):
        self.executed = []

    async def execute(self, stmt, *args, **kwargs):
        self.executed.append(stmt)
        return _FakeResult()


class _FakeScope:
    def __init__(self):
        self.session = _FakeSession()

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        return False


@pytest.fixture
def export_scope(monkeypatch):
    scopes = []
    factory = lambda: _FakeScope()
    monkeypatch.setattr("app.services.admin_data_service.session_scope", lambda: scopes.append(factory()) or scopes[-1])
    return scopes


def _run(coro):
    return asyncio.run(coro)


def _sql_literal(whereclause) -> str:
    from sqlalchemy.dialects import postgresql

    try:
        return str(whereclause.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Endpoint registration
# ---------------------------------------------------------------------------

def test_export_endpoints_registered_on_admin_router():
    from app.routes.admin import router

    paths = {getattr(r, "path", None) for r in router.routes}
    for expected in [
        "/export/dummy-data",
        "/export/purge-data",
        "/export/all-tables",
        "/export/table/{table_name}",
    ]:
        assert expected in paths


# ---------------------------------------------------------------------------
# Pure CSV helpers
# ---------------------------------------------------------------------------

def test_csv_repr_normalizes_values():
    assert _csv_repr(None) == ""
    assert _csv_repr(True) == "true"
    assert _csv_repr(False) == "false"
    assert _csv_repr({"a": 1}) == '{"a": 1}'
    assert _csv_repr(["x", "y"]) == '["x", "y"]'
    assert _csv_repr(_dt.datetime(2026, 9, 5, 10, 30)) == "2026-09-05T10:30:00"
    assert _csv_repr(_dt.date(2026, 9, 5)) == "2026-09-05"
    assert _csv_repr(_uuid.UUID("9df22c82-1f8b-5bdf-a0b4-6f1c0f0c0000")) == "9df22c82-1f8b-5bdf-a0b4-6f1c0f0c0000"
    assert _csv_repr(123) == 123
    assert _csv_repr("text") == "text"


def test_dicts_to_csv_uses_first_seen_column_order():
    rows = [{"b": 2, "a": 1}, {"c": 3, "b": 4}]
    text = _dicts_to_csv(rows)
    lines = text.splitlines()
    assert lines[0] == "b,a,c"
    assert lines[1] == "2,1,"
    assert lines[2] == "4,,3"


def test_dicts_to_csv_empty_returns_empty_string():
    assert _dicts_to_csv([]) == ""


def test_blocks_to_csv_emits_delimiters_and_counts():
    text = _blocks_to_csv([("hazards", "id,title\n1,Headwind\n2,Xwind"), ("cans", "id\n5")])
    assert "# TABLE:hazards  rows=2" in text
    assert "# TABLE:cans  rows=1" in text
    assert "id,title\n1,Headwind\n2,Xwind" in text
    empty = _blocks_to_csv([("beta", "")])
    assert empty.splitlines() == ["# TABLE:beta  rows=0"]


# ---------------------------------------------------------------------------
# Dummy-data export
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", sorted(DEMO_EXPORT_KINDS))
def test_dummy_export_filename_timestamped(kind, export_scope):
    csv_text, filename, rows = _run(export_demo_data_csv(kind))
    assert re.match(rf"^dummy_data_{kind}_{TS_RE}\.csv$", filename), filename
    assert isinstance(rows, int)
    assert csv_text == "" or csv_text.startswith("# TABLE:") or csv_text.startswith("id") or csv_text


def test_dummy_export_rejects_unknown_kind(export_scope):
    with pytest.raises(ValueError):
        _run(export_demo_data_csv("bogus"))


def test_dummy_vsr_filters_report_type_voluntary(export_scope):
    _run(export_demo_data_csv("vsr"))
    stmt = export_scope[-1].session.executed[0]
    sql = _sql_literal(stmt.whereclause)
    assert "report_type" in sql and "'voluntary'" in sql


def test_dummy_mor_filters_report_type_mandatory(export_scope):
    _run(export_demo_data_csv("mor"))
    stmt = export_scope[-1].session.executed[0]
    sql = _sql_literal(stmt.whereclause)
    assert "report_type" in sql and "'mandatory'" in sql


def test_dummy_can_filters_is_demo_on_cans(export_scope):
    _run(export_demo_data_csv("can"))
    stmt = export_scope[-1].session.executed[0]
    assert "cans.is_demo" in _sql_literal(stmt.whereclause)


def test_dummy_survey_exports_surveys_and_responses(export_scope):
    csv_text, filename, rows = _run(export_demo_data_csv("survey"))
    executed = [s for scope in export_scope for s in scope.session.executed]
    assert len(executed) == 2
    assert "surveys.is_demo" in _sql_literal(executed[0].whereclause)
    assert "survey_responses.is_demo" in _sql_literal(executed[1].whereclause)
    assert csv_text == "# TABLE:surveys  rows=0\n# TABLE:survey_responses  rows=0"


def test_dummy_all_covers_every_demo_table(export_scope):
    csv_text, filename, rows = _run(export_demo_data_csv("all"))
    executed = [s for scope in export_scope for s in scope.session.executed]
    assert len(executed) == len(DEMO_EXPORT_TABLES)
    for name in DEMO_EXPORT_TABLES:
        assert f"# TABLE:{name}  rows=0" in csv_text


def test_dummy_tenant_filter_uses_deterministic_slug_uuid(export_scope):
    _run(export_demo_data_csv("can", tenant_id="fixedwing"))
    stmt = export_scope[-1].session.executed[0]
    sql = _sql_literal(stmt.whereclause)
    assert tenant_uuid("fixedwing") in sql
    assert "is_demo" in sql


def test_dummy_tenant_filter_accepts_raw_uuid(export_scope):
    raw = str(_uuid.uuid4())
    _run(export_demo_data_csv("can", tenant_id=raw))
    stmt = export_scope[-1].session.executed[0]
    assert raw in _sql_literal(stmt.whereclause)


# ---------------------------------------------------------------------------
# Purge summary export
# ---------------------------------------------------------------------------

def test_purge_summary_covers_every_purge_table(export_scope):
    csv_text, filename, rows = _run(export_purge_summary_csv())
    assert re.match(rf"^purge_summary_{TS_RE}\.csv$", filename)
    executed = export_scope[-1].session.executed
    assert len(executed) == len(PURGE_TABLE_ORDER)
    assert csv_text.splitlines()[0] == "table,demo_rows"
    for table in PURGE_TABLE_ORDER:
        assert f"{table},7" in csv_text
    assert rows == len(PURGE_TABLE_ORDER) * 7


def test_purge_export_endpoint_registered_on_admin_router():
    from app.routes.admin import router

    paths = {getattr(r, "path", None) for r in router.routes}
    assert "/export/purge-data" in paths


# ---------------------------------------------------------------------------
# All-tables / single-table export
# ---------------------------------------------------------------------------

def test_all_tables_dump_covers_every_orm_table(export_scope):
    csv_text, filename, rows = _run(export_all_tables_csv())
    assert re.match(rf"^all_tables_{TS_RE}\.csv$", filename)
    tables_with_is_demo = {
        mapper.class_.__tablename__ for mapper in dm.Base.registry.mappers
    }
    executed = [s for scope in export_scope for s in scope.session.executed]
    assert len(executed) == len(tables_with_is_demo)
    for name in tables_with_is_demo:
        assert f"# TABLE:{name}" in csv_text


def test_single_table_export_filename_and_rows(export_scope):
    csv_text, filename, rows = _run(export_single_table_csv("hazards"))
    assert re.match(rf"^hazards_{TS_RE}\.csv$", filename)


def test_single_table_export_unknown_raises_keyerror(export_scope):
    with pytest.raises(KeyError):
        _run(export_single_table_csv("not_a_table"))


def test_single_table_export_accepts_any_registered_table(export_scope):
    for table in DEMO_EXPORT_TABLES:
        _, filename, _ = _run(export_single_table_csv(table))
        assert filename.startswith(table + "_")