from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from loguru import logger

from app.core.config import settings
from app.core.logging import setup_logging, RequestLoggingMiddleware
from app.core.metrics import router as metrics_router
from app.core.security import SecurityHeadersMiddleware, RateLimitMiddleware
from app.core.cors import ManualCORSMiddleware
from app.firebase import initialize_firebase, is_firebase_ready
from app.routes import reports, dashboard, auth, admin, hazards, can_cap, verification, reporting, flight_diversions, state_risk, surveys, tenants, regulators, contact, feedback, copilot

setup_logging()

# The application's own hosting frontends are always valid CORS origins. They are
# merged into whatever ALLOWED_ORIGINS is configured with so a stale or partial
# environment variable can never break the browser -> API calls (CORS preflight).
CANONICAL_ALLOWED_ORIGINS = (
    "https://sms.aviasafesystems.com",
    "https://betasms.aviasafesystems.com",
    "https://aerosafety-sms-prod.web.app",
    "https://sms-beta.web.app",
    "https://demo.aviasafesystems.com",
    # Public survey frontends (multi-tenant subdomains / portals)
    "https://smssurvey.gsacharya.com",
    "https://sms.nac.com.np",
    "https://ssp.caanepal.gov.np",
)


def _allowed_origins() -> list[str]:
    configured = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
    for origin in CANONICAL_ALLOWED_ORIGINS:
        if origin not in configured:
            configured.append(origin)
    return configured


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        initialize_firebase()
    except Exception as e:
        logger.warning(f"Firebase initialization failed at startup: {e}. Lazy init will retry on first request.")
    yield


app = FastAPI(
    title="AviaSAFE SMS API",
    description="Safety Climate Measurement System - ICAO Annex 19 Compliant",
    version=settings.API_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Guarantees Access-Control-Allow-Origin on actual (non-preflight) responses.
# See app/core/cors.py for why this is needed in addition to CORSMiddleware.
app.add_middleware(ManualCORSMiddleware)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)


def _req_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID", "")


def _cors_headers(request: Request) -> dict:
    """Mirror ManualCORSMiddleware so error responses stay CORS-visible.

    Without this, an unhandled exception returns a 500 with no
    Access-Control-Allow-Origin, and the browser hides the body behind a
    generic "Network error" instead of surfacing the real message.
    """
    try:
        from app.core.cors import _allowed_origins, ALLOWED_HEADERS
        origin = request.headers.get("origin")
        if origin and origin in _allowed_origins():
            return {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": ALLOWED_HEADERS,
                "Vary": "Origin",
            }
    except Exception:
        pass
    return {}


def _error_body(
    request: Request,
    status_code: int,
    message: str,
    detail=None,
    errors=None,
) -> dict:
    """Structured error envelope.

    The primary `error` object carries the machine-readable contract
    (code / message / timestamp / requestId). Legacy top-level fields
    (`success`, `detail`, `errors`, `request_id`) are preserved so existing
    frontend clients keep parsing error messages unchanged.
    """
    request_id = _req_id(request)
    return {
        "error": {
            "code": status_code,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "requestId": request_id,
        },
        "success": False,
        "detail": detail if detail is not None else message,
        "errors": errors,
        "request_id": request_id,
    }


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    errors = None
    if isinstance(detail, dict):
        message = detail.get("message") or "Request failed"
        errors = detail.get("errors")
    else:
        message = detail if isinstance(detail, str) else str(detail)
    request_id = _req_id(request)
    logger.error(f"HTTP {exc.status_code} for {request.method} {request.url.path} (request_id={request_id}): {message}")
    return JSONResponse(
        status_code=exc.status_code,
        headers={**_cors_headers(request), **(exc.headers or {})},
        content=_error_body(request, exc.status_code, message, detail=message, errors=errors),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        errors.append({
            "field": " -> ".join(str(loc) for loc in err.get("loc", [])),
            "message": err.get("msg", str(err)),
        })
    request_id = _req_id(request)
    logger.error(f"Validation error for {request.method} {request.url.path} (request_id={request_id}): {errors}")
    return JSONResponse(
        status_code=422,
        headers=_cors_headers(request),
        content=_error_body(
            request,
            422,
            "Validation error",
            detail=str(exc),
            errors=errors,
        ),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = _req_id(request)
    logger.error(f"Unhandled exception (request_id={request_id}): {exc}")
    logger.exception("Unhandled exception traceback:")
    return JSONResponse(
        status_code=500,
        headers=_cors_headers(request),
        content=_error_body(
            request,
            500,
            "Internal server error",
            detail=str(exc) if settings.DEBUG else None,
        ),
    )

app.include_router(auth.router, prefix=settings.API_PREFIX_AUTH, tags=["Authentication"])
app.include_router(reports.router, prefix=settings.API_PREFIX_REPORTS, tags=["Reports"])
app.include_router(dashboard.router, prefix=settings.API_PREFIX_DASHBOARD, tags=["Dashboard"])
app.include_router(admin.router, prefix=settings.API_PREFIX_ADMIN, tags=["Admin"])
app.include_router(hazards.router, prefix=settings.API_PREFIX_HAZARDS, tags=["Hazards"])
app.include_router(can_cap.router, prefix=settings.API_PREFIX_CAN_CAP, tags=["CAN/CAP"])

app.include_router(auth.router, prefix=settings.API_PREFIX_AUTH_LEGACY, tags=["Authentication (Legacy)"], include_in_schema=False)
app.include_router(reports.router, prefix=settings.API_PREFIX_REPORTS_LEGACY, tags=["Reports (Legacy)"], include_in_schema=False)
app.include_router(dashboard.router, prefix=settings.API_PREFIX_DASHBOARD_LEGACY, tags=["Dashboard (Legacy)"], include_in_schema=False)
app.include_router(admin.router, prefix=settings.API_PREFIX_ADMIN_LEGACY, tags=["Admin (Legacy)"], include_in_schema=False)
app.include_router(hazards.router, prefix=settings.API_PREFIX_HAZARDS_LEGACY, tags=["Hazards (Legacy)"], include_in_schema=False)
app.include_router(can_cap.router, prefix=settings.API_PREFIX_CAN_CAP_LEGACY, tags=["CAN/CAP (Legacy)"], include_in_schema=False)

app.include_router(verification.router, prefix=settings.API_PREFIX_VERIFICATION, tags=["Verification & Closure"])
app.include_router(verification.router, prefix=settings.API_PREFIX_VERIFICATION_LEGACY, tags=["Verification & Closure (Legacy)"], include_in_schema=False)

app.include_router(reporting.router, prefix=settings.API_PREFIX_REPORTING, tags=["Reporting"])
app.include_router(reporting.router, prefix=settings.API_PREFIX_REPORTING_LEGACY, tags=["Reporting (Legacy)"], include_in_schema=False)

app.include_router(flight_diversions.router, prefix=settings.API_PREFIX_FLIGHT_DIVERSIONS, tags=["Flight Diversions"])
app.include_router(flight_diversions.router, prefix=settings.API_PREFIX_FLIGHT_DIVERSIONS_LEGACY, tags=["Flight Diversions (Legacy)"], include_in_schema=False)

app.include_router(state_risk.router, prefix=settings.API_PREFIX_STATE_RISK, tags=["State Risk Register"])
app.include_router(state_risk.router, prefix=settings.API_PREFIX_STATE_RISK_LEGACY, tags=["State Risk Register (Legacy)"], include_in_schema=False)

app.include_router(surveys.router, prefix=settings.API_PREFIX_SURVEYS, tags=["Surveys"])
app.include_router(surveys.router, prefix=settings.API_PREFIX_SURVEYS_LEGACY, tags=["Surveys (Legacy)"], include_in_schema=False)

app.include_router(tenants.router, prefix=settings.API_PREFIX_TENANTS, tags=["Tenants"])
app.include_router(tenants.router, prefix=settings.API_PREFIX_TENANTS_LEGACY, tags=["Tenants (Legacy)"], include_in_schema=False)

app.include_router(regulators.router, prefix=settings.API_PREFIX_REGULATORS, tags=["Regulators"])

app.include_router(contact.router, prefix=settings.API_PREFIX_CONTACT, tags=["Contact"])

app.include_router(feedback.router, prefix=settings.API_PREFIX_FEEDBACK, tags=["Feedback"])
app.include_router(copilot.router, prefix=settings.API_PREFIX_COPILOT, tags=["Copilot"])

app.include_router(metrics_router, prefix="", tags=["Metrics"])

@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    return {
        "message": "AviaSAFE SMS API is running",
        "version": settings.API_VERSION,
        "status": "operational"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "firebase": "connected" if is_firebase_ready() else "unavailable",
        "service": "AviaSAFE SMS API",
        "version": settings.API_VERSION,
    }

@app.get("/live")
async def liveness_probe():
    return {"status": "alive"}

@app.get("/ready")
async def readiness_probe():
    fb = is_firebase_ready()
    return {
        "status": "ready" if fb else "not_ready",
        "firebase": "connected" if fb else "unavailable",
    }
