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
    "https://aerosafety-sms-prod.web.app",
    "https://sms-beta.web.app",
    # Public survey frontends (multi-tenant subdomains / portals)
    "https://smssurvey.gsacharya.com",
    "https://sms.nac.com.np",
    "https://ssp.caanepal.gov.np",
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
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, Authorization, X-Tenant-Id, X-Task-Key, X-Request-ID"
        )
        response.headers["Vary"] = "Origin"
        return response
