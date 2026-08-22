"""Pytest mirror of the Firestore rule-lint (Chunk 17 / Headway audit).

Parses firestore.rules and asserts the structural invariants that the
JS lint also enforces, so the Python CI stage catches rule regressions.
"""

import re
from pathlib import Path

RULES = (Path(__file__).resolve().parents[2] / "firestore" /
         "firestore.rules").read_text(encoding="utf-8")


def test_no_unconditional_allow():
    assert not re.search(r"allow\s+(read|write)[^;]*:\s*if\s+true\s*;", RULES)


def test_partitioned_collections_reference_path_tenant():
    for coll in ("metadata", "responses", "surveys", "reports", "mor",
                 "hazards", "can_cap", "verification", "flight_diversions"):
        block = re.search(
            rf"match /tenants/\{{tenantId\}}/{coll}[\s\S]*?\n    \}}", RULES)
        assert block, coll
        assert "tenantId" in block.group(0), coll


def test_top_level_mirrors_denied():
    for coll in ("hazards", "cans", "caps", "sras", "surveys"):
        m = re.search(
            rf"match /{coll}/\{{id\}}\s*\{{[\s\S]*?allow read, write: if false",
            RULES)
        assert m, f"top-level /{coll} must be explicitly denied"


def test_demo_sessions_owner_uid_enforced():
    assert "request.auth.uid == resource.data.owner_uid" in RULES
    assert "request.auth.uid == request.resource.data.owner_uid" in RULES


def test_caan_oversight_readonly_block():
    m = re.search(
        r"match /caan_oversight/\{docId\}\s*\{([\s\S]{0,600}?)\}", RULES)
    assert m
    body = m.group(1)
    assert "isCaanInspector()" in body
    assert "allow write: if false" in body


def test_psoe_dual_tenant_condition():
    m = re.search(r"match /psoe_assessments/\{docId\}\s*\{([\s\S]*?)\n    \}",
                  RULES)
    assert m
    body = m.group(1)
    assert "request.auth.token.tenant_id == resource.data.tenant_id" in body
    assert "matchesOwnTenantData()" in body or \
           "request.resource.data.tenant_id" in body


def test_copilot_quarantine_tags_match_rules_spec():
    from app.services import groq_copilot as gc
    assert gc.QUARANTINE_OPEN == "<untrusted_operational_report>"
    assert gc.QUARANTINE_CLOSE == "</untrusted_operational_report>"
