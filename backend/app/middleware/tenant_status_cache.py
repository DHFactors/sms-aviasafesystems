# ============================================================================
# FILE: tenant_status_cache.py
# PATH: backend/app/middleware/tenant_status_cache.py
# PURPOSE: Short-TTL in-memory cache for tenant status, consumed by the auth
#          suspension check (auth.py). Before this cache, every authenticated
#          request paid a `tenants` table lookup solely to test for SUSPENDED
#          status (~129 of the 129 slow `fetch_all:tenants` calls in profiling).
#          The cache collapses that to one query per TTL window per tenant.
#
#          Semantics match the auth contract: FAIL-OPEN on errors (a missing
#          row or DB error must never lock a user out) and a bounded stale
#          window by default (AVIASAFE_TENANT_STATUS_CACHE_TTL_SECONDS, 45s).
#          Writes that change tenant status/modules invalidate the entry
#          immediately (see admin_data_service._set_tenant), so the window is
#          only ever short-lived between TTL refreshes, never enforced.
# ============================================================================

from __future__ import annotations

import os
import threading
import time
from typing import Dict, Optional, Tuple

_TTL_SECONDS = float(os.getenv("AVIASAFE_TENANT_STATUS_CACHE_TTL_SECONDS", "45"))

# slug -> (status, expires_at_epoch). status is "" when the tenant row was not
# found (fail-open negative entry). Entries are never created on DB errors.
_cache: Dict[str, Tuple[str, float]] = {}
_lock = threading.Lock()


def _now() -> float:
    return time.monotonic()


def get_status(slug: str) -> Optional[str]:
    """Return the cached status for a tenant slug, or None on miss/expiry."""
    with _lock:
        entry = _cache.get(slug)
    if entry is None:
        return None
    status, expires = entry
    if _now() > expires:
        with _lock:
            _cache.pop(slug, None)
        return None
    return status


def set_status(slug: str, status: str) -> None:
    """Store a status (or "" for a not-found tenant) for the TTL window."""
    with _lock:
        _cache[slug] = (status, _now() + _TTL_SECONDS)


def invalidate(slug: str) -> None:
    """Drop a tenant's cached status so the next request re-reads the DB."""
    with _lock:
        _cache.pop(slug, None)