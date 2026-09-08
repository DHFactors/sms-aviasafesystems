"""Task 02 latency instrumentation — endpoint + DB timing.

Logs structured "[PERF]" log lines:

    [PERF] GET /api/v1/dashboard/caan/state status=200 total=1843ms uptime=52s firestore=1710ms queries=14 db=412ms

- `total`   = end-to-end server processing time measured by the middleware
- `uptime`  = seconds since this backend process started (cold-start signature)
- `queries` = count of app/.db/pg.py calls made by this request
- `db`      = cumulative wall time across those pg.py calls
- component fields (`firestore=`, `gemini=`, `groq=`, `redis=`) are optional
  accumulators recorded by call sites via `note_current()` / `timed()`.

Watched endpoints log on every request; every other endpoint logs only when it
is slow (total or cumulative DB time >= AVIASAFE_PERF_SLOW_MS, default 1000),
so unsupervised endpoints become visible when they cross the 1s budget. The
pg.py timing wrapper records per-call durations, per-request totals and a
separate slow-query log ([PERF] slow_sql).

Removal: delete this file and remove PerfTimingMiddleware from app/main.py.
Silence without removal: set env var AVIASAFE_PERF=off.
"""
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_PROCESS_START = time.time()
_PERF_OFF = lambda: os.getenv("AVIASAFE_PERF", "on").strip().lower() == "off"
_SLOW_MS = float(os.getenv("AVIASAFE_PERF_SLOW_MS", "1000"))

# The endpoints normal users hit most (dashboards, report intake, AI).
# "METHOD path" pairs; legacy /api/* aliases intentionally excluded.
WATCHED_PATHS = set(os.getenv(
    "AVIASAFE_PERF_PATHS",
    "GET /api/v1/dashboard/overview|"
    "GET /api/v1/dashboard/master-register|"
    "GET /api/v1/dashboard/caan/state|"
    "GET /api/v1/dashboard/caan/sms-maturity-assessment|"
    "GET /api/v1/reports|"
    "POST /api/v1/reports/vsr|"
    "POST /api/v1/reports/mor|"
    "GET /api/v1/hazards|"
    "POST /api/v1/surveys/|"
    "POST /api/v1/copilot/chat",
).split("|"))

_timings_ctx: ContextVar = ContextVar("aviasafe_perf_timings", default=None)


def note_current(label: str, ms: float) -> None:
    """Accumulate `ms` onto `label` for the request running in this context.

    No-op when no request is active (e.g. background tasks), so call sites
    cost one function call outside instrumented requests.
    """
    timings = _timings_ctx.get()
    if timings is not None:
        timings[label] = round(timings.get(label, 0.0) + ms, 1)


def note_count(label: str, n: float = 1) -> None:
    """Increment an integer counter (`queries`, etc.) for this request."""
    timings = _timings_ctx.get()
    if timings is not None:
        timings[label] = timings.get(label, 0) + n


def note_append(label: str, item: Any) -> None:
    """Append `item` to a per-request list (e.g. slow-query traces)."""
    timings = _timings_ctx.get()
    if timings is not None:
        timings.setdefault(label, []).append(item)


@contextmanager
def timed(label: str):
    """`with timed('firestore'): do_work()` records elapsed ms for the label."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        note_current(label, (time.perf_counter() - t0) * 1000)


class PerfTimingMiddleware(BaseHTTPMiddleware):
    """Outermost middleware: measures total wall time per request.

    The timings context is installed for every request so the pg.py wrapper and
    AI call sites can report query counts / DB time even on unwatched paths.
    """

    async def dispatch(self, request: Request, call_next):
        if _PERF_OFF():
            return await call_next(request)

        watch_key = f"{request.method} {request.url.path}"
        watched = watch_key in WATCHED_PATHS
        reflect = request.headers.get("X-Perf", "").strip().lower() in ("1", "true", "yes", "on")
        token = _timings_ctx.set({})
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            total_ms = (time.perf_counter() - t0) * 1000
            components = _timings_ctx.get() or {}
            _timings_ctx.reset(token)
            uptime_s = int(time.time() - _PROCESS_START)
            if reflect and hasattr(response, "headers"):
                response.headers["X-Perf-Total-Ms"] = f"{total_ms:.0f}"
                response.headers["X-Perf-Uptime-S"] = str(uptime_s)
                if components.get("db_ms"):
                    response.headers["X-Perf-Db-Ms"] = f"{components['db_ms']:.0f}"
                if components.get("db_calls"):
                    response.headers["X-Perf-Queries"] = str(components["db_calls"])
                slow = components.get("slow_sql") or []
                if slow:
                    response.headers["X-Perf-Slow"] = ";".join(str(s) for s in slow[:8])
            if watched or total_ms >= _SLOW_MS or components.get("db_ms", 0) >= _SLOW_MS:
                extra = "".join(
                    f" {k}={v}ms" for k, v in components.items()
                    if k not in ("db_calls", "slow_sql") and not isinstance(v, (list, dict, tuple))
                )
                if components.get("db_calls"):
                    extra += f" queries={components['db_calls']}"
                status = getattr(response, "status_code", "-")
                logger.info(
                    f"[PERF] {watch_key} status={status} total={total_ms:.0f}ms "
                    f"uptime={uptime_s}s{extra}"
                )
        return response
