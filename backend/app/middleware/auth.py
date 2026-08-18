# ============================================================================
# FILE: auth.py
# PATH: backend/app/middleware/auth.py
# VERSION: 1.0.0
# DATE CREATED: 2026-07-03
# DATE REVISED: 2026-07-03
# PURPOSE: Authentication middleware for FastAPI routes.
#          Verifies Firebase ID tokens and extracts user claims.
# AUTHOR: Ghanshyam Acharya
# CODE OWNER: AviaSafeSystems
# ============================================================================

from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Any, Optional
from loguru import logger

from app.core.config import settings
from app.firebase import verify_firebase_token, get_db

security = HTTPBearer()


def _lookup_tenant_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Search all tenant documents for a safety_manager with matching email.

    This is a fallback when Firebase Auth custom claims are not available
    in the ID token (known Firebase propagation issue).
    """
    try:
        db = get_db()
        tenants = db.collection(settings.FIREBASE_COLLECTION_TENANTS).get()
        for t in tenants:
            td = t.to_dict()
            if not td:
                continue
            sm = td.get("safety_manager")
            if sm and sm.get("email") == email:
                return {"tenant_id": td.get("tenant_id") or t.id, "role": "AIRLINE_ADMIN"}
            # Also check for CAAN_SMD emails in a separate config
        return None
    except Exception as e:
        logger.warning(f"Tenant lookup failed for {email}: {e}")
        return None


def resolve_user_context(email: str, role: str, tenant_id: Optional[str]) -> Dict[str, Any]:
    """Normalize tenant_id and fall back to a Firestore email lookup when the
    ID token carries no custom claims (e.g. freshly-linked Google sign-ins)."""
    if tenant_id:
        normalized = tenant_id.replace('_', '-')
        if normalized != tenant_id:
            logger.info(f"Normalized tenant_id for {email}: '{tenant_id}' -> '{normalized}'")
            tenant_id = normalized

    if role == settings.ROLE_DEFAULT and not tenant_id and email:
        tenant_info = _lookup_tenant_by_email(email)
        if tenant_info:
            role = tenant_info["role"]
            tenant_id = tenant_info["tenant_id"]
            logger.info(f"Claims resolved via Firestore fallback for {email}: role={role}, tenant={tenant_id}")

    return {"role": role, "tenant_id": tenant_id}


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> Dict[str, Any]:
    token = credentials.credentials
    decoded_token = verify_firebase_token(token)

    if not decoded_token:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email = decoded_token.get('email', '')
    role = decoded_token.get('role', settings.ROLE_DEFAULT)
    tenant_id = decoded_token.get('tenant_id')
    department = decoded_token.get('department') or None

    resolved = resolve_user_context(email, role, tenant_id)
    role = resolved["role"]
    tenant_id = resolved["tenant_id"]

    logger.info(f"Authenticated user {email}: role={role}, tenant_id={tenant_id}")

    return {
        "uid": decoded_token['uid'],
        "email": email,
        "role": role,
        "tenant_id": tenant_id,
        "department": department,
        "claims": {"role": role, "tenant_id": tenant_id, "department": department},
    }


async def get_tenant_user(
    user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    if not user.get('tenant_id'):
        raise HTTPException(
            status_code=403,
            detail="User does not have tenant access"
        )
    return user


async def get_caan_user(
    user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    if user.get('role') not in settings.CROSS_TENANT_ROLES:
        raise HTTPException(
            status_code=403,
            detail="CAAN_SMD role required"
        )
    return user


async def get_admin_user(
    user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    if user.get('role') not in settings.SUPER_ADMIN_ROLES:
        raise HTTPException(
            status_code=403,
            detail="SUPER_ADMIN role required"
        )
    return user


async def get_safety_manager(
    user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    if user.get('role') not in settings.CROSS_TENANT_ROLES and user.get('role') != "AIRLINE_ADMIN":
        raise HTTPException(
            status_code=403,
            detail="Safety Manager or CAAN_SMD role required"
        )
    if user.get('role') == "AIRLINE_ADMIN" and not user.get('tenant_id'):
        raise HTTPException(
            status_code=403,
            detail="Tenant access required for AIRLINE_ADMIN"
        )
    return user


# Department accounts (email prefix) -> the single department they are scoped to.
# Used to restrict 145 / CAMO users to only their own department's CANs & CAPs.
DEPARTMENT_SCOPE_PREFIXES = {
    "145": "Part-145",
    "camo": "CAMO",
}


def get_department_scope(user: Dict[str, Any]) -> Optional[str]:
    """Return the department a user is restricted to based on their email prefix.

    Emails starting with ``145`` or ``camo`` belong to the Part-145 / CAMO
    departments and should only ever see CANs and CAPs for that department.
    Returns ``None`` for all other users (no restriction).
    """
    email = (user.get("email") or "").lower()
    for prefix, department in DEPARTMENT_SCOPE_PREFIXES.items():
        if email.startswith(prefix):
            return department
    return None


async def get_responsible_manager(
    user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    if user.get('role') not in settings.CROSS_TENANT_ROLES and user.get('role') not in ("AIRLINE_ADMIN", "USER"):
        raise HTTPException(
            status_code=403,
            detail="Responsible Manager, AIRLINE_ADMIN, or CAAN_SMD role required"
        )
    if not user.get('tenant_id') and user.get('role') not in settings.CROSS_TENANT_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Tenant access required"
        )
    return user


async def get_accountable_executive(
    user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    if user.get('role') not in settings.CROSS_TENANT_ROLES and user.get('role') != "AIRLINE_ADMIN":
        raise HTTPException(
            status_code=403,
            detail="Accountable Executive, AIRLINE_ADMIN, or CAAN_SMD role required"
        )
    if user.get('role') == "AIRLINE_ADMIN" and not user.get('tenant_id'):
        raise HTTPException(
            status_code=403,
            detail="Tenant access required for AIRLINE_ADMIN"
        )
    return user