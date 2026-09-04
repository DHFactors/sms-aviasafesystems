from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Dict

from app.core.rbac import has_permission, is_regulator

# Module mapping for endpoints
ENDPOINT_MODULE_MAP = {
    "/api/v1/maturity": "module1",
    "/api/v1/survey": "module1",
    "/api/v1/hazards": "module2",
    "/api/v1/sram": "module2",
    "/api/v1/cans": "module2",
    "/api/v1/caps": "module2",
    "/api/v1/reports": "module2",
    "/api/v1/regulator": "module5",
    "/api/v1/aggregation": "module5",
    "/api/v1/industry": "module5",
    "/api/v1/benchmark": "module5",
}

def get_module_for_path(path: str) -> str:
    for prefix, module in ENDPOINT_MODULE_MAP.items():
        if path.startswith(prefix):
            return module
    return ""

async def rbac_middleware(request: Request, call_next):
    # Extract user from request state (set by auth middleware)
    user: Dict = getattr(request.state, "user", None)
    if not user:
        # No user, let auth middleware handle it
        return await call_next(request)
    
    module = get_module_for_path(request.url.path)
    if not module:
        # Not a module-protected endpoint
        return await call_next(request)
    
    role = user.get("role", "employee")
    # Normalize legacy roles
    from app.core.rbac import normalize_legacy_role
    normalized = normalize_legacy_role(role) if role in ["AIRLINE_ADMIN", "CAAN_SMD", "DEPT_ADMIN", "USER", "STAFF"] else role
    
    if not has_permission(normalized, module):
        raise HTTPException(status_code=403, detail=f"Insufficient permissions: role {role} cannot access {module}")
    
    # Tenant isolation
    tenant_id = user.get("tenant_id")
    request_tenant = request.query_params.get("tenant_id") or request.path_params.get("tenant_id")
    
    if is_regulator(normalized):
        # Regulator can only access aggregated data (module5)
        if module != "module5":
            raise HTTPException(status_code=403, detail="Regulator can only access Module 5 (aggregated data)")
        # Regulator should not see tenant-specific data
        if request_tenant and request_tenant != "aggregated":
            # Allow but log - aggregated view
            pass
    else:
        # Tenant users can only access their own tenant
        if request_tenant and tenant_id and request_tenant != tenant_id:
            raise HTTPException(status_code=403, detail="Tenant isolation: cannot access other tenant data")
        # Ensure tenant_id is set for queries
        if not tenant_id and module in ["module1", "module2", "module3"]:
            # Allow but will be filtered to empty
            pass
    
    return await call_next(request)

class RBACMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        return await rbac_middleware(request, call_next)

def has_permission_for_user(user: Dict, module: str) -> bool:
    from app.core.rbac import has_permission, normalize_legacy_role
    role = user.get("role", "employee")
    normalized = normalize_legacy_role(role) if role in ["AIRLINE_ADMIN", "CAAN_SMD", "DEPT_ADMIN", "USER", "STAFF"] else role
    return has_permission(normalized, module)
