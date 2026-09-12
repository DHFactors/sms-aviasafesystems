"""Unified seeder regression tests (FIX 1a: Firestore-removed PG-only guard).

Covers the guard added to ``seed_tenant_hazards`` so the Postgres half always
runs to completion when the Firestore backend is unavailable (``get_db`` raises
``NotImplementedError`` after Firestore was removed from the data plane).
"""

import asyncio
import uuid
from unittest.mock import patch

import scripts.seed.unified_seeder as seeder
from scripts.seed.unified_seeder import seed_tenant_hazards


class _FakeSession:
    def add(self, *args, **kwargs):
        pass


class _FakeSessionScope:
    async def __aenter__(self):
        return _FakeSession()

    async def __aexit__(self, *exc):
        return False


def _run(coro):
    return asyncio.run(coro)


def test_seed_firestore_only_does_not_raise_when_firestore_removed():
    with patch.object(seeder, "get_db", side_effect=NotImplementedError("removed")):
        result = _run(seed_tenant_hazards("unit-fs", count=2, target="firestore"))
    assert result["seeded"] == 2
    assert result["firestore"] == 0


def test_seed_both_runs_postgres_half_when_firestore_removed():
    with patch.object(seeder, "get_db", side_effect=NotImplementedError("removed")), \
         patch.object(seeder, "session_scope", return_value=_FakeSessionScope()), \
         patch.object(seeder, "register_tenant", return_value=uuid.uuid4()):
        result = _run(seed_tenant_hazards("unit-both", count=2, target="both"))
    assert result["supabase"] == 2
    assert result["firestore"] == 0
    assert result["seeded"] == 2


def test_seed_logs_pg_only_warning():
    lines = []
    sink = seeder.logger.add(lambda m: lines.append(m), level="WARNING", format="{message}")
    try:
        with patch.object(seeder, "get_db", side_effect=NotImplementedError("removed")), \
             patch.object(seeder, "session_scope", return_value=_FakeSessionScope()), \
             patch.object(seeder, "register_tenant", return_value=uuid.uuid4()):
            _run(seed_tenant_hazards("unit-log", count=1, target="both"))
    finally:
        seeder.logger.remove(sink)
    assert any("Firestore removed" in line for line in lines)