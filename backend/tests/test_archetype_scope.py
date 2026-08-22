"""Chunk 6 — archetype resolution with safe fallback on data endpoints.

Locks the contract that `archetypeId` only ever scopes to virtual demo-*
tenants, and that standard tenants fall back to their own tenant_id.
"""

from app.services.archetype_scope import (
    is_archetype_id,
    resolve_data_tenant,
)


def test_archetype_ids_are_demo_prefixed_only():
    assert is_archetype_id("demo-fixed-wing") is True
    assert is_archetype_id("demo-rotary-wing") is True
    assert is_archetype_id(" demo-fixed-wing ") is True  # trimmed
    for bad in ("buddha-air", "yeti-airlines", "caan", "", None, "DEMO-x"):
        assert is_archetype_id(bad) is False, bad


def test_resolve_prefers_archetype_when_valid():
    user = {"tenant_id": "buddha-air", "role": "AIRLINE_ADMIN"}
    assert resolve_data_tenant("demo-fixed-wing", user) == "demo-fixed-wing"
    assert resolve_data_tenant("demo-rotary-wing", user) == "demo-rotary-wing"


def test_resolve_falls_back_to_caller_tenant():
    user = {"tenant_id": "buddha-air", "role": "AIRLINE_ADMIN"}
    # Non-demo values are ignored (cannot cross into another real tenant).
    assert resolve_data_tenant("yeti-airlines", user) == "buddha-air"
    assert resolve_data_tenant(None, user) == "buddha-air"
    assert resolve_data_tenant("", user) == "buddha-air"


def test_resolve_default_tenant_without_tenant_id():
    assert resolve_data_tenant(None, {}) == "default"
    assert resolve_data_tenant(None, {"tenant_id": ""}) == "default"
    assert resolve_data_tenant("demo-rotary-wing", {}) == "demo-rotary-wing"


def test_resolve_custom_default():
    assert resolve_data_tenant(None, {"tenant_id": None}, default_tenant="t1") == "t1"


def test_caan_smd_archetype_request_scopes_to_demo_tenant():
    """Even cross-tenant roles scope down to the requested archetype."""
    smd = {"tenant_id": "caan", "role": "CAAN_SMD"}
    assert resolve_data_tenant("demo-fixed-wing", smd) == "demo-fixed-wing"
