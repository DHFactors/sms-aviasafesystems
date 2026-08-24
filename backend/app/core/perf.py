"""Task 02 latency instrumentation — temporary, measurement only.

Logs ONE structured "[PERF]" log line per watched user-facing endpoint:

    [PERF] GET /api/v1/dashboard/caan/state status=200 total=1843ms uptime=52s firestore=1710ms

- `total`   = end-to-end server processing time for that request
- `uptime`  = seconds since this backend process started. Low uptime on a slow
              request is the signature of a cold start.
- component fields (`firestore=`, `gemini=`, `groq=`, `redis=`) are optional
  accumulators recorded by call sites via `note_current()` / `timed()`.

Removal: delete this file and remove PerfTimingMiddleware from app/main.py.
Silence without removal: set env var AVIASAFE_PERF=off. Non-watched paths do
one dict lookup per request and nothing else. No business logic is touched.
"""
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_PROCESS_START = time.time()
_PERF_OFF = lambda: os.getenv("AVIASAFE_PERF", "on").strip().lower() == "off"

# The endpoints normal users hit most (dashboards, report intake, AI).
# "METHOD path" pairs; legacy /api/* aliases intentionally excluded.
WATCHED_PATHS = {
    "GET /api/v1/dashboard/overview",
    "GET /api/v1/dashboard/master-register",
    "GET /api/v1/dashboard/caan/state",
    "GET /api/v1/dashboard/caan/sms-maturity-assessment",
    "GET /api/v1/reports",
    "POST /api/v1/reports/vsr",
    "POST /api/v1/reports/mor",
    "GET /api/v1/hazards",
    "POST /api/v1/surveys/",
    "POST /api/v1/copilot/chat",
}

_timings_ctx: ContextVar = ContextVar("aviasafe_perf_timings", default=None)


def note_current(label: str, ms: float) -> None:
    """Accumulate `ms` onto `label` for the request running in this context.

    No-op when no watched request is active (the common case), so call sites
    cost one function call outside instrumented flows.
    """
    timings = _timings_ctx.get()
    if timings is not None:
        timings[label] = round(timings.get(label, 0.0) + ms, 1)


@contextmanager
def timed(label: str):
    """`with timed('firestore'): do_work()` records elapsed ms for the label."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        note_current(label, (time.perf_counter() - t0) * 1000)


class PerfTimingMiddleware(BaseHTTPMiddleware):
    """Outermost middleware: measures total wall time for watched endpoints."""

    async def dispatch(self, request: Request, call_next):
        watch_key = f"{request.method} {request.url.path}"
        if _PERF_OFF() or watch_key not in WATCHED_PATHS:
            return await call_next(request)

        token = _timings_ctx.set({})
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            total_ms = (time.perf_counter() - t0) * 1000
            components = _timings_ctx.get() or {}
            _timings_ctx.reset(token)
            uptime_s = int(time.time() - _PROCESS_START)
            extra = "".join(f" {k}={v}ms" for k, v in components.items())
            logger.info(
                f"[PERF] {watch_key} total={total_ms:.0f}ms uptime={uptime_s}s{extra}"
            )
        return response
