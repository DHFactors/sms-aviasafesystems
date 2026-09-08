# ============================================================================
# FILE: pg_cache.py
# PATH: backend/app/services/pg_cache.py
# PURPOSE: Short-TTL in-memory cache for slowly-changing Postgres reads that
#          are otherwise re-fetched on every dashboard request (tenant slug
#          registry, tenant rows, flight-diversion rows). Each such row-set is
#          stable in practice, so a 45s window removes one ~880ms pooler query
#          per request without meaningful staleness. Writes that compete with a
#          cached key invalidate explicitly (see clear/clear_prefix).
# ============================================================================

from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable, Dict, Optional

_DEFAULT_TTL_SECONDS = float(os.getenv("AVIASAFE_PG_CACHE_TTL_SECONDS", "45"))

_cache: Dict[str, Any] = {}
_expiry: Dict[str, float] = {}
_lock = threading.Lock()


def get(key: str) -> Optional[Any]:
    with _lock:
        exp = _expiry.get(key)
        if exp is None:
            return None
        if time.monotonic() > exp:
            _cache.pop(key, None)
            _expiry.pop(key, None)
            return None
        return _cache.get(key)


def set(key: str, value: Any, ttl_seconds: Optional[float] = None) -> Any:
    ttl = _DEFAULT_TTL_SECONDS if ttl_seconds is None else ttl_seconds
    with _lock:
        _cache[key] = value
        _expiry[key] = time.monotonic() + ttl
    return value


def get_or_set(key: str, factory: Callable[[], Any], ttl_seconds: Optional[float] = None) -> Any:
    value = get(key)
    if value is not None:
        return value
    value = factory()
    return set(key, value, ttl_seconds)


def clear() -> None:
    with _lock:
        _cache.clear()
        _expiry.clear()


def clear_prefix(prefix: str) -> None:
    with _lock:
        for key in [k for k in _cache if k.startswith(prefix)]:
            _cache.pop(key, None)
            _expiry.pop(key, None)