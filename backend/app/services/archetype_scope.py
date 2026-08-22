# ============================================================================
# FILE: backend/app/services/archetype_scope.py
# PURPOSE: Virtual Tenant Mirroring — safe archetype tenant resolution for
#          data endpoints (Chunk 6).
#
# Data routes accept an optional `archetypeId` query parameter. Resolution is
# fail-safe for standard tenants:
#
#   * `archetypeId` starting with the reserved `demo-` prefix  -> that virtual
#     archetype tenant is used (demo datasets are public-read by design).
#   * otherwise                                                -> the caller's
#     own tenant_id (real operations data; cross-tenant access stays blocked).
#   * no tenant_id on the account                              -> "default".
#
# Because only `demo-*` values are ever honored, a caller can never read
# another real operator's data through this parameter.
# ============================================================================

ARCHETYPE_PREFIX = "demo-"
DEFAULT_TENANT = "default"


def is_archetype_id(value) -> bool:
    """True when the value targets a virtual archetype tenant."""
    return bool(value) and str(value).strip().startswith(ARCHETYPE_PREFIX)


def resolve_data_tenant(archetype_id, user: dict, default_tenant: str = DEFAULT_TENANT) -> str:
    """Resolve the effective tenant for a data query with safe fallback."""
    aid = str(archetype_id or "").strip()
    if aid.startswith(ARCHETYPE_PREFIX):
        return aid
    return (user or {}).get("tenant_id") or default_tenant
