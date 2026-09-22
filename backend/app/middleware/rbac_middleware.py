from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.rbac import has_permission
from app.firebase import verify_firebase_token

# Route prefix -> canonical module. Only the clearly-canonical Module A/B/C
# surfaces are gated here; per-tenant SPI/N-HRC stay ungated at the module level
# (their own tenant-scope dependencies enforce access).
ENDPOINT_MODULE_MAP = {
    "/api/v1/surveys": "module1",
    "/api/v1/sms-maturity": "module1",
    "/api/v1/hazards": "module2",
    "/api/v1/reports": "module2",
    "/api/v1/cans": "module2",
    "/api/v1/caps": "module2",
    "/api/v1/regulator": "module5",
    "/api/v1/psoe": "module5",
    "/api/v1/spi/state": "module5",
    "/api/v1/nhrc/state": "module5",
}

# Canonical module -> tenant module-flag keys. The roadmap flags the naming as
# an OPEN item (RBAC Q-R5 / Dashboard Q-D6), so several aliases are accepted and
# an absent flag means "enabled" (never deny on missing config).
MODULE_FLAG_KEYS: Dict[str, Tuple[str, ...]] = {
    "module1": ("module_a_survey", "module_1", "module1"),
    "module2": ("module_b_srm", "module_b_can_cap", "module_2", "module2"),
    "module5": ("module_c_regulator", "module_3", "module3"),
}

# Cache tenant module flags to avoid a DB hit per request.
_FLAG_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_FLAG_TTL_SECONDS = 60.0

_NORMALIZE_ROLES = {
    "AIRLINE_ADMIN", "CAAN_SMD", "DEPT_ADMIN", "USER", "STAFF",
    "ACCOUNTABLE_EXECUTIVE", "SAG_MEMBER", "TENANT_ADMIN", "SAFETY_OFFICER",
}


def get_module_for_path(path: str) -> str:
    for prefix, module in ENDPOINT_MODULE_MAP.items():
        if path.startswith(prefix):
            return module
    return ""


def _normalize(role: Optional[str]) -> str:
    from app.core.rbac import normalize_legacy_role

    role = role or "employee"
    return normalize_legacy_role(role) if role in _NORMALIZE_ROLES else role


def _user_from_request(request: Request) -> Optional[Dict[str, Any]]:
    """Resolve the caller from request.state.user or the verified Bearer token."""
    state_user = getattr(request.state, "user", None)
    if state_user:
        return state_user
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    try:
        decoded = verify_firebase_token(token)
    except Exception:
        return None
    if not decoded:
        return None
    return {
        "uid": decoded.get("uid"),
        "email": decoded.get("email"),
        "role": decoded.get("role", settings.ROLE_DEFAULT),
        "tenant_id": decoded.get("tenant_id"),
    }


def _tenant_module_enabled(tenant_slug: str, module: str) -> bool:
    keys = MODULE_FLAG_KEYS.get(module, ())
    now = time.time()
    cached = _FLAG_CACHE.get(tenant_slug)
    if cached and now - cached[0] < _FLAG_TTL_SECONDS:
        flags = cached[1]
    else:
        flags: Dict[str, Any] = {}
        try:
            from app.db import pg
            from app.db.db_models import Tenant

            row = pg.fetch_by(Tenant, "slug", tenant_slug)
            if row:
                flags = {**(row.get("module_access") or {}), **(row.get("modules") or {})}
        except Exception:
            flags = {}
        _FLAG_CACHE[tenant_slug] = (now, flags)
    for key in keys:
        if key in flags:
            return bool(flags[key])
    return True


def _forbidden(detail: str) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": detail})


async def rbac_middleware(request: Request, call_next):
    user = _user_from_request(request)
    if not user:
        return await call_next(request)

    module = get_module_for_path(request.url.path)
    if not module:
        return await call_next(request)

    role = user.get("role")
    # Cross-tenant roles bypass the module gate (but not tenant isolation).
    if role not in settings.CROSS_TENANT_ROLES:
        if not has_permission(_normalize(role), module):
            return _forbidden(f"Insufficient permissions: role {role} cannot access {module}")
        tenant_id = user.get("tenant_id")
        if tenant_id and not _tenant_module_enabled(tenant_id, module):
            return _forbidden(f"Module {module} is not enabled for tenant {tenant_id}")
        request_tenant = (
            request.query_params.get("tenant_id")
            or request.path_params.get("tenant_id")
        )
        if request_tenant and tenant_id and request_tenant != tenant_id:
            return _forbidden("Tenant isolation: cannot access other tenant data")

    return await call_next(request)


class RBACMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        return await rbac_middleware(request, call_next)


def has_permission_for_user(user: Dict[str, Any], module: str) -> bool:
    return has_permission(_normalize(user.get("role")), module)
