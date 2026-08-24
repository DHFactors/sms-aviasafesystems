"""
Manual CORS middleware.

The Starlette ``CORSMiddleware`` correctly answers the CORS *preflight*
(OPTIONS) request but, in some deployments, fails to echo
``Access-Control-Allow-Origin`` on the *actual* (non-OPTIONS) responses.
Because the browser only reads the body when that header is present on the
real response, every authenticated cross-origin call (the SPA always sends
``Authorization`` / ``X-Tenant-Id``) was being blocked with a "Network error".

This middleware runs *outside* ``CORSMiddleware`` and guarantees the CORS
response headers are present on every response for an allow-listed origin.
It mirrors the request ``Origin`` (never ``*``) so credentials stay allowed.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.config import settings

# Always-trusted first-party frontends. Merged with the configured
# ALLOWED_ORIGINS so a stale environment variable can never break the
# browser -> API calls.
CANONICAL_ALLOWED_ORIGINS = (
    "https://sms.aviasafesystems.com",
    "https://betasms.aviasafesystems.com",
    "https://aerosafety-sms-prod.web.app",
    "https://aerosafety-sms-beta.web.app",
    "https://sms-beta.web.app",
    "https://demo.aviasafesystems.com",
    # Public survey frontends (multi-tenant subdomains / portals)
    "https://smssurvey.gsacharya.com",
    "https://sms.nac.com.np",
    "https://ssp.caanepal.gov.np",
    # Local development / static file servers (5005 = firebase serve hosting emulator for the local Docker demo)
    "http://localhost:5000",
    "http://localhost:5005",
    "http://127.0.0.1:5005",
    "http://localhost:8000",
    "http://127.0.0.1:5500",
)

# Every header the frontend (and the multi-tenant demo/routing layer) sends on
# cross-origin calls. Must cover all case variants actually emitted by the SPA,
# because browsers compare the request header name against this list verbatim.
# "X-User-Department" and "X-Tenant-Id" are the tenant-routing headers added by
# public/js/api/client.js; "X-Task-Key" / "X-Request-ID" are server-driven;
# "X-Firebase-AppCheck" carries the App Check token from the SPA.
ALLOWED_HEADERS = (
    "Content-Type, Authorization, "
    "X-Firebase-AppCheck, x-firebase-appcheck, "
    "X-Requested-With, Accept, Origin, "
    "X-Tenant-Id, X-Tenant-ID, x-tenant-id, "
    "X-User-Department, x-user-department, "
    "X-Task-Key, X-Request-ID"
)

# Headers the browser may read off cross-origin responses. The sliding-window
# rate limiter and the anti-spam guardrails communicate back-off state through
# these, so they must be exposed or the SPA can never see them.
EXPOSE_HEADERS = (
    "Retry-After, X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset"
)


def _allowed_origins() -> list:
    configured = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
    for origin in CANONICAL_ALLOWED_ORIGINS:
        if origin not in configured:
            configured.append(origin)
    return configured


class ManualCORSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        response = await call_next(request)

        if not origin:
            return response

        if origin not in _allowed_origins():
            return response

        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = (
            "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        )
        response.headers["Access-Control-Allow-Headers"] = ALLOWED_HEADERS
        response.headers["Access-Control-Expose-Headers"] = EXPOSE_HEADERS
        response.headers["Vary"] = "Origin"
        return response
