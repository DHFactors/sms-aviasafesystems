# ============================================================================
# FILE: ids.py
# PATH: backend/app/db/ids.py
# PURPOSE: Deterministic uuid5 identifiers used across the Postgres migration.
#          Row primary keys for migrated business entities are derived from the
#          Firestore document ids so lookups by `id` are stable across syncs.
# ============================================================================

from __future__ import annotations

import uuid
from typing import Dict, List

_NS = uuid.NAMESPACE_DNS

# In-process registry mapping slug <-> uuid so services can emit the WHOLE
# tenant slug (as the API contract expects) while Postgres stores the uuid.
_slug_by_uuid: Dict[str, str] = {}


def uuid5(*parts: object) -> str:
    """Version-5 (namespace DNS) UUID string over the given parts."""
    return str(uuid.uuid5(_NS, ":".join(str(p) for p in parts)))


def tenant_uuid(slug: str) -> str:
    """UUID of a tenant slug, e.g. 'fishtail-air' -> a7bc11b3-..."""
    return uuid5("tenant", slug)


def register_tenant(slug: str) -> str:
    """Remember a slug so tenant_uuid() output can be reversed later."""
    tid = tenant_uuid(slug)
    _slug_by_uuid[tid] = slug
    return tid


def tenant_slug(tenant_id: object) -> str:
    """Reverse a tenant uuid back to its slug (falls back to 'default')."""
    return _slug_by_uuid.get(str(tenant_id), "default")


def registered_slugs() -> List[str]:
    return list(_slug_by_uuid.values())


def clear_tenant_registry() -> None:
    _slug_by_uuid.clear()