# ============================================================================
# Transient DB connection retry (P2/Phase 3 stability fix).
# ============================================================================

import asyncio

import pytest

from app.db import session as session_mod
from app.db.session import is_transient_conn_error, session_scope_retry


class _TransientError(Exception):
    """Stands in for asyncpg ConnectionDoesNotExistError (name-matched)."""


_TransientError.__name__ = "ConnectionDoesNotExistError"


class _PermanentError(Exception):
    __name__ = "ValueError"


def test_is_transient_conn_error_matches_allowlist():
    assert is_transient_conn_error(_TransientError("dropped")) is True

    class InterfaceError(Exception):
        pass

    assert is_transient_conn_error(InterfaceError("closed")) is True

    class ProtocolError(Exception):
        pass

    assert is_transient_conn_error(ProtocolError("bad")) is True

    assert is_transient_conn_error(ValueError("nope")) is False


def test_is_transient_matches_connection_invalidated_and_cause():
    exc = ValueError("wrapper")
    exc.connection_invalidated = True
    assert is_transient_conn_error(exc) is True

    cause = _TransientError("inner")
    outer = RuntimeError("outer")
    outer.__cause__ = cause
    assert is_transient_conn_error(outer) is True


def test_session_scope_retries_on_transient(monkeypatch):
    calls = {"n": 0}

    class _Sess:
        async def commit(self):
            pass

        async def rollback(self):
            pass

        async def close(self):
            pass

    class _CM:
        def __init__(self, fail):
            self._fail = fail

        async def __aenter__(self):
            if self._fail and calls["n"] == 1:
                raise _TransientError("dropped")
            return _Sess()

        async def __aexit__(self, *a):
            return False

    def fake_scope():
        calls["n"] += 1
        return _CM(fail=True)

    monkeypatch.setattr(session_mod, "session_scope", fake_scope)

    async def _fake_dispose(*a, **k):
        return None

    monkeypatch.setattr(session_mod.get_engine, "dispose", _fake_dispose, raising=False) \
        if hasattr(session_mod.get_engine, "dispose") else None

    async def _run():
        async with session_scope_retry() as s:
            return s

    # First entry raises transient -> retried once -> second entry succeeds.
    got = asyncio.run(_run())
    assert got is not None
    assert calls["n"] == 2


def test_session_scope_does_not_retry_on_permanent(monkeypatch):
    calls = {"n": 0}

    class _CM:
        async def __aenter__(self):
            raise ValueError("permanent")

        async def __aexit__(self, *a):
            return False

    def fake_scope():
        calls["n"] += 1
        return _CM()

    monkeypatch.setattr(session_mod, "session_scope", fake_scope)

    async def _run():
        async with session_scope_retry() as s:
            return s

    with pytest.raises(ValueError):
        asyncio.run(_run())
    assert calls["n"] == 1  # no retry
