# ============================================================================
# RBAC Phase 1 (P1-29/P1-30/P1-31) — role conflicts + new literals.
#
#  - P1-29: ACCOUNTABLE_EXECUTIVE / SAG_MEMBER canonical literals + aliases
#  - P1-30: EIP added to CAPStatus
#  - P1-31: role-assignment validator (RBAC_MODEL.md §7)
# ============================================================================

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.rbac import normalize_legacy_role
from app.models.can_cap import CAPStatus
from app.services import role_validation
from app.services.role_validation import validate_role_assignment


def _patch_ae_count(monkeypatch, value):
    monkeypatch.setattr(role_validation, "ae_count", lambda *a, **k: value)


# ---------------------------------------------------------------------------
# P1-31 — conflict constraints
# ---------------------------------------------------------------------------

def test_two_aes_same_tenant_rejected(monkeypatch):
    _patch_ae_count(monkeypatch, 1)
    with pytest.raises(HTTPException) as exc:
        validate_role_assignment("ACCOUNTABLE_EXECUTIVE", "tenant-a")
    assert exc.value.status_code == 400
    assert "ACCOUNTABLE_EXECUTIVE" in exc.value.detail


def test_first_ae_allowed(monkeypatch):
    _patch_ae_count(monkeypatch, 0)
    validate_role_assignment("ACCOUNTABLE_EXECUTIVE", "tenant-a")  # no raise


def test_ae_combined_with_operational_role_rejected(monkeypatch):
    _patch_ae_count(monkeypatch, 0)
    with pytest.raises(HTTPException) as exc:
        validate_role_assignment(
            "ACCOUNTABLE_EXECUTIVE", "tenant-a", existing_role="SAFETY_OFFICER"
        )
    assert exc.value.status_code == 400
    assert "operational" in exc.value.detail.lower()


def test_ae_multi_role_payload_rejected(monkeypatch):
    _patch_ae_count(monkeypatch, 0)
    with pytest.raises(HTTPException) as exc:
        validate_role_assignment(
            ["ACCOUNTABLE_EXECUTIVE", "DEPT_ADMIN"], "tenant-a"
        )
    assert exc.value.status_code == 400


def test_ae_without_tenant_rejected(monkeypatch):
    _patch_ae_count(monkeypatch, 0)
    with pytest.raises(HTTPException) as exc:
        validate_role_assignment("ACCOUNTABLE_EXECUTIVE", None)
    assert exc.value.status_code == 400


def test_caan_with_tenant_role_rejected():
    with pytest.raises(HTTPException) as exc:
        validate_role_assignment("CAAN_SMD", "tenant-a")
    assert exc.value.status_code == 400
    assert "tenant" in exc.value.detail.lower()


def test_caan_combined_with_tenant_role_rejected():
    with pytest.raises(HTTPException) as exc:
        validate_role_assignment("CAAN_SMD", None, existing_role="STAFF")
    assert exc.value.status_code == 400


def test_super_admin_combined_rejected():
    with pytest.raises(HTTPException) as exc:
        validate_role_assignment(["SUPER_ADMIN", "STAFF"], None)
    assert exc.value.status_code == 400
    assert "SUPER_ADMIN" in exc.value.detail


def test_super_admin_non_developer_rejected():
    with pytest.raises(HTTPException) as exc:
        validate_role_assignment("SUPER_ADMIN", None, is_developer=False)
    assert exc.value.status_code == 400


def test_super_admin_developer_allowed():
    validate_role_assignment("SUPER_ADMIN", None, is_developer=True)  # no raise


def test_tenant_role_without_tenant_rejected():
    with pytest.raises(HTTPException) as exc:
        validate_role_assignment("SAFETY_OFFICER", None)
    assert exc.value.status_code == 400


def test_normal_tenant_roles_allowed():
    validate_role_assignment("SAFETY_OFFICER", "tenant-a")  # no raise
    validate_role_assignment("SAG_MEMBER", "tenant-a")  # no raise


def test_create_user_service_invokes_validator(monkeypatch):
    """The user-creation service must reject a conflicting role (CAAN + tenant)
    before any Auth user is created."""
    from app.services import tenant_credentials

    monkeypatch.setattr(tenant_credentials, "_read_tenant", lambda tid: {"users": []})
    with pytest.raises(HTTPException) as exc:
        tenant_credentials.create_user_for_tenant(
            {"tenant_id": "tenant-a", "email": "x@example.com", "role": "CAAN_SMD"},
            {"uid": "admin", "email": "admin@example.com"},
        )
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# P1-29 — new canonical literals + aliases
# ---------------------------------------------------------------------------

def test_canonical_roles_include_new_literals():
    assert "ACCOUNTABLE_EXECUTIVE" in settings.CANONICAL_ROLES
    assert "SAG_MEMBER" in settings.CANONICAL_ROLES
    # REGULATORY_LIAISON deliberately folded into SAFETY_OFFICER (RBAC Q-R3).
    assert "REGULATORY_LIAISON" not in settings.CANONICAL_ROLES


def test_role_group_constants():
    assert settings.ACCOUNTABLE_EXECUTIVE_ROLES == ["ACCOUNTABLE_EXECUTIVE"]
    assert settings.SAG_MEMBER_ROLES == ["SAG_MEMBER"]
    assert settings.ROLE_ACCOUNTABLE_EXECUTIVE == "ACCOUNTABLE_EXECUTIVE"
    assert settings.ROLE_SAG_MEMBER == "SAG_MEMBER"


def test_normalize_legacy_role_new_literals():
    assert normalize_legacy_role("ACCOUNTABLE_EXECUTIVE") == "accountable_executive"
    assert normalize_legacy_role("SAG_MEMBER") == "sag_member"


def test_new_roles_have_permissions():
    from app.core.rbac import has_permission

    assert has_permission("accountable_executive", "module2")
    assert has_permission("sag_member", "module2")


# ---------------------------------------------------------------------------
# P1-30 — EIP CAP status
# ---------------------------------------------------------------------------

def test_cap_status_has_eip():
    assert CAPStatus.EIP.value == "EIP"
    assert "EIP" in {s.value for s in CAPStatus}


def test_cap_status_existing_values_preserved():
    values = {s.value for s in CAPStatus}
    for expected in ("In Progress", "Under Review", "Completed",
                     "Revision Required", "Overdue", "EIP"):
        assert expected in values
