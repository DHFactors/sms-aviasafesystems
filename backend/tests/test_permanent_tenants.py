# ============================================================================
# Permanent pilot tenant guard (B.1).
#
# Sita Air, Air Dynasty, Saurya Airlines and CAAN are PERMANENT pilot
# tenants: no test, seed, reset or purge operation may delete them.
# These tests are DB-free (pure guard logic + fixture refusal).
# ============================================================================

import pathlib

import pytest

from app.db.isolation import (
    PERMANENT_TENANT_SLUGS,
    is_permanent_tenant_slug,
    pilot_slug_exclusion,
)


def test_permanent_slug_list_is_complete():
    assert PERMANENT_TENANT_SLUGS == frozenset({
        "sita-air",
        "air-dynasty",
        "saurya-airlines",
        "caan",
    })
    for slug in ("sita-air", "air-dynasty", "saurya-airlines", "caan"):
        assert is_permanent_tenant_slug(slug) is True
    # Ephemeral test artifacts (hash slugs) are NOT permanent.
    assert is_permanent_tenant_slug("ae-a859ab8c58") is False
    assert is_permanent_tenant_slug("mat-056f5c791b") is False
    assert is_permanent_tenant_slug("") is False
    assert is_permanent_tenant_slug(None) is False


def test_reset_to_virgin_skips_pilot_tenants():
    """The reset script must exclude pilot tenants in every delete phase."""
    # 1. The exclusion builder used by the reset script covers all 4 slugs.
    fragment, params = pilot_slug_exclusion("slug")
    assert "NOT IN" in fragment
    assert sorted(params) == sorted(PERMANENT_TENANT_SLUGS)
    fragment_t, _ = pilot_slug_exclusion("tenant_id")
    assert "tenant_id NOT IN" in fragment_t

    # 2. The reset script wires the guard (static check: importing
    #    reset_to_virgin requires psycopg2, which test envs may lack).
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    source = (repo_root / "backend" / "scripts" / "reset_to_virgin.py").read_text(
        encoding="utf-8")
    assert "PERMANENT_TENANT_SLUGS" in source
    assert "SKIP (permanent pilot tenant)" in source
    # Tenant/ regulator/ scoped-table deletes all carry the exclusion.
    assert "slug NOT IN" in source
    assert "tenant_id NOT IN" in source

    # 3. Test fixtures refuse permanent slugs without touching the DB.
    import _mbb

    calls = []
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(_mbb, "run", lambda coro: calls.append(coro))
    try:
        for slug in sorted(PERMANENT_TENANT_SLUGS):
            _mbb.cleanup(slug)  # must not raise, must not run any DELETE
    finally:
        monkeypatch.undo()
    assert calls == []
