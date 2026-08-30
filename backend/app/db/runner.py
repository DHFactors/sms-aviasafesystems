# ============================================================================
# FILE: runner.py
# PATH: backend/app/db/runner.py
# PURPOSE: Run async SQLAlchemy work to completion from synchronous service
#          code (the legacy Firestore-era service signatures are sync). A
#          single dedicated background event loop is kept for ordinary sync
#          threads; when a sync call happens to run inside an already-running
#          event loop (async test / uvicorn worker) the coroutine is executed
#          on a fresh loop instead.
#
#          Cross-loop safety: session.py builds the engine with NullPool so
#          each connection is created and closed inside the same loop that
#          awaited it - no asyncpg connection is ever shared between loops.
#          On a single-instance Render worker this also bounds the open
#          connection count to the number of requests currently in flight.
# ============================================================================

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Awaitable, TypeVar

T = TypeVar("T")

_BRIDGE_LOOP: "asyncio.AbstractEventLoop | None" = None
_BRIDGE_THREAD: "threading.Thread | None" = None
_BRIDGE_LOCK = threading.Lock()


def _bridge_loop() -> "asyncio.AbstractEventLoop":
    """Return the shared background loop, starting it on first use."""
    global _BRIDGE_LOOP, _BRIDGE_THREAD
    with _BRIDGE_LOCK:
        if _BRIDGE_LOOP is None or _BRIDGE_LOOP.is_closed():
            _BRIDGE_LOOP = asyncio.new_event_loop()
            _BRIDGE_THREAD = threading.Thread(
                target=_run_loop_forever,
                args=(_BRIDGE_LOOP,),
                name="pg-bridge-loop",
                daemon=True,
            )
            _BRIDGE_THREAD.start()
        return _BRIDGE_LOOP


def _run_loop_forever(loop: "asyncio.AbstractEventLoop") -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()


def run(coro: Awaitable[T], timeout: float = 60.0) -> T:
    """Execute an awaitable to completion and return its result.

    Always dispatch onto the dedicated bridge loop via
    run_coroutine_threadsafe. This is safe from any thread and any event-loop
    state: sync callers (FastAPI TestClient worker threads, uvicorn request
    threads, pytest sync tests) and even callers already inside a running
    asyncio loop (async pytest tests, asyncio.run mains) simply block on the
    future while the bridge thread owns the actual loop. A fresh per-call loop
    cannot be used here - Python forbids running a second loop in a thread that
    already has a running one.
    """
    future = asyncio.run_coroutine_threadsafe(coro, _bridge_loop())
    try:
        return future.result(timeout=timeout)
    except FutureTimeoutError:
        future.cancel()
        raise