# ============================================================================
# FILE: auth.py
# PATH: backend/app/routes/auth.py
# VERSION: 1.0.0
# DATE CREATED: 2026-07-03
# DATE REVISED: 2026-07-03
# PURPOSE: Authentication endpoints with Firebase Auth integration.
# AUTHOR: Ghanshyam Acharya
# CODE OWNER: AviaSafeSystems
# ============================================================================

from fastapi import APIRouter, HTTPException, Depends, Request, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime, timezone

from app.core.config import settings
from app.firebase import get_auth, get_db, verify_firebase_token, create_custom_claims
from app.middleware.rate_limit import rate_limit
from app.middleware.auth import resolve_user_context
from app.models.tenant_profile import OperationalScope
from app.services.audit_service import log_audit, request_context
from app.services.users import upsert_user_doc
from app.services.tenant_registration import (
    DEPARTMENT_LABELS,
    register_tenant,
    join_team,
    resolve_tenant,
    verify_invite,
    DuplicateEmailError,
)

router = APIRouter()


class LoginRequest(BaseModel):
    id_token: str


class LoginResponse(BaseModel):
    uid: str
    email: str
    role: str
    tenant_id: Optional[str]
    custom_claims: dict


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    organization: str
    role: str = settings.ROLE_DEFAULT_REGISTRATION
    tenant_id: Optional[str] = None


@router.post("/verify")
@rate_limit("auth_attempts")
async def verify_token(request: Request, body: LoginRequest):
    decoded_token = verify_firebase_token(body.id_token)
    if not decoded_token:
        raise HTTPException(status_code=401, detail="Invalid token")
    role = decoded_token.get('role', settings.ROLE_DEFAULT)
    tenant_id = decoded_token.get('tenant_id')
    resolved = resolve_user_context(decoded_token.get('email', ''), role, tenant_id)
    ip, request_id = request_context(request)
    log_audit(
        action="LOGIN",
        user=decoded_token.get('email', ''),
        tenant_id=resolved["tenant_id"],
        ip=ip,
        request_id=request_id,
    )
    return {
        "uid": decoded_token['uid'],
        "email": decoded_token.get('email', ''),
        "role": resolved["role"],
        "tenant_id": resolved["tenant_id"],
    }

@router.post("/register")
async def register_user(request: RegisterRequest):
    try:
        allowed_roles = {settings.ROLE_DEFAULT_REGISTRATION}
        if request.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Registration role must be one of: {', '.join(allowed_roles)}"
            )

        auth = get_auth()
        user = auth.create_user(
            email=request.email,
            password=request.password,
            display_name=request.full_name,
            email_verified=False,
        )

        claims = {"role": request.role}
        if request.tenant_id:
            claims["tenant_id"] = request.tenant_id

        auth.set_custom_user_claims(user.uid, claims)

        now = datetime.now(timezone.utc)
        upsert_user_doc(user.uid, {
            "uid": user.uid,
            "email": user.email,
            "display_name": request.full_name,
            "role": request.role,
            "tenant_id": request.tenant_id,
            "created_at": now,
            "updated_at": now,
        })

        ip, request_id = request_context(request)
        log_audit(
            action="REGISTER",
            user=request.email,
            tenant_id=request.tenant_id,
            ip=ip,
            request_id=request_id,
        )

        return {
            "success": True,
            "uid": user.uid,
            "email": user.email,
            "role": request.role,
            "tenant_id": request.tenant_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/refresh")
async def refresh_token(request: Request):
    """Refresh Firebase ID token."""
    # Client handles token refresh using Firebase SDK
    # This endpoint just returns a success response
    return {"success": True, "message": "Token refresh handled by client"}


class RegisterTenantRequest(BaseModel):
    organization_name: str = Field(..., min_length=2, max_length=120)
    classification: OperationalScope
    admin_full_name: str = Field(..., min_length=1)
    admin_title: str = Field(..., min_length=1)
    email: EmailStr
    password: str
    confirm_password: str
    beta_access_key: Optional[str] = None


@router.post("/register-tenant")
@rate_limit("auth_attempts")
async def register_tenant_endpoint(request: Request, body: RegisterTenantRequest):
    """Self-service tenant registration (beta portal).

    Provisions the primary administrator (AIRLINE_ADMIN / safety), initialises
    the operational profile at ``tenants/{tenant_id}/profile/operational`` and
    issues a unique team invite code for colleague onboarding.
    """
    if body.password != body.confirm_password:
        raise HTTPException(status_code=422, detail="Passwords do not match")
    try:
        result = register_tenant(
            organization_name=body.organization_name,
            classification=body.classification.value,
            admin_full_name=body.admin_full_name,
            admin_title=body.admin_title,
            email=body.email,
            password=body.password,
            beta_access_key=body.beta_access_key,
            request=request,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"success": True, **result}


@router.get("/verify-invite")
@rate_limit("auth_attempts")
async def verify_invite_endpoint(
    request: Request,
    code: Optional[str] = Query(None, description="Team invite code"),
):
    """Real-time invite-code verification for /join.html.

    Confirms the code belongs to an active tenant and returns the organization
    name, tenant id and operational category so the join form can greet the
    invitee. Deliberately reveals nothing about the tenant when the code is
    unknown or inactive.
    """
    try:
        result = verify_invite(get_db(), code)
    except LookupError:
        return JSONResponse(
            status_code=404,
            content={"valid": False, "error": "Invalid or expired invite code"},
        )
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"valid": False, "error": "Invalid or expired invite code"},
        )
    return result


class JoinTeamRequest(BaseModel):
    invite_code: Optional[str] = None
    tenant_id: Optional[str] = None
    full_name: str = Field(..., min_length=1)
    email: EmailStr
    password: str
    confirm_password: str
    department: str = Field(..., min_length=1)
    operational_role: Optional[str] = Field(None, max_length=100)


@router.post("/join-team")
@rate_limit("auth_attempts")
async def join_team_endpoint(request: Request, body: JoinTeamRequest):
    """Self-register a department postholder under an existing tenant."""
    if body.password != body.confirm_password:
        raise HTTPException(status_code=422, detail="Passwords do not match")
    try:
        result = join_team(
            invite_code=body.invite_code,
            tenant_id=body.tenant_id,
            full_name=body.full_name,
            email=body.email,
            password=body.password,
            department=body.department,
            operational_role=body.operational_role,
            request=request,
        )
    except DuplicateEmailError as e:
        raise HTTPException(
            status_code=409,
            detail="An account with this email address already exists.",
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"success": True, **result}


@router.get("/tenant-lookup")
async def tenant_lookup_endpoint(
    request: Request,
    code: Optional[str] = Query(None, description="Team invite code"),
    tenant_id: Optional[str] = Query(None, description="Tenant id / slug"),
):
    """Public tenant lookup for /join.html.

    Resolves a tenant from its invite code (or a ?tenant= tenant id) so the
    join form can render only the departments applicable to that
    classification. Reveals only the org name + department codes — the caller
    must already know the invite code to get this far.
    """
    try:
        tid, tenant_doc = resolve_tenant(get_db(), code, tenant_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    departments = tenant_doc.get("applicable_departments") or []
    return {
        "success": True,
        "tenant_id": tid,
        "tenant_name": tenant_doc.get("name"),
        "classification": tenant_doc.get("tenant_type") or tenant_doc.get("classification"),
        "operates_flights": tenant_doc.get("operates_flights"),
        "applicable_departments": [
            {"code": d, "label": DEPARTMENT_LABELS.get(d, d)} for d in departments
        ],
    }
