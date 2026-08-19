# ============================================================================
# FILE: auth.py
# PATH: backend/app/routes/auth.py
# VERSION: 1.0.0
# DATE CREATED: 2026-07-03
# DATE REVISED: 2026-08-19
# PURPOSE: Authentication endpoints with Firebase Auth integration.
# AUTHOR: Ghanshyam Acharya
# CODE OWNER: AviaSafeSystems
# ============================================================================

import asyncio
from fastapi import APIRouter, HTTPException, Depends, Request, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime, timezone

from app.core.config import settings
from app.firebase import get_auth, get_db, verify_firebase_token, create_custom_claims
from app.middleware.rate_limit import (
    rate_limit,
    enforce_login_rate_limit,
    record_login_failure,
    clear_login_failures,
)
from app.middleware.auth import resolve_user_context
from app.middleware.app_check import verify_app_check
from app.models.tenant_profile import OperationalScope
from app.services.audit_service import log_audit, request_context
from app.services.users import upsert_user_doc
from app.services import login_service, gmail_dispatcher
from app.services.tenant_registration import (
    DEPARTMENT_LABELS,
    DISPOSABLE_EMAIL_MESSAGE,
    DisposableEmailError,
    validate_corporate_email,
    register_tenant,
    join_team,
    resolve_tenant,
    verify_invite,
    DuplicateEmailError,
)

router = APIRouter()


class LoginRequest(BaseModel):
    id_token: str


class LoginCredentials(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    uid: str
    email: str
    role: str
    tenant_id: Optional[str]
    custom_claims: dict


@router.post("/login")
async def login_endpoint(
    request: Request,
    body: LoginCredentials,
    _app_check: None = Depends(verify_app_check),
):
    """Server-side credential verification with anti-credential-stuffing lockout.

    Verifies the email/password against Firebase Identity Toolkit (the same
    backend that powers client-side sign-in), then returns a one-time custom
    token the client exchanges through the Firebase SDK. Failed attempts are
    tracked in a per-IP sliding window (5 failures / 15 minutes); the 6th
    attempt is rejected with 429 + Retry-After before the provider is even
    contacted.
    """
    await enforce_login_rate_limit(request)

    try:
        user = await login_service.verify_credentials(body.email, body.password)
    except login_service.LoginProviderError:
        raise HTTPException(
            status_code=503,
            detail="Authentication provider unavailable. Please try again shortly.",
        )

    if not user:
        await record_login_failure(request)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    await clear_login_failures(request)
    custom_token = await asyncio.to_thread(login_service.mint_custom_token, user["uid"])

    ip, request_id = request_context(request)
    log_audit(
        action="LOGIN",
        user=user.get("email") or body.email,
        tenant_id=None,
        ip=ip,
        request_id=request_id,
    )
    return {
        "success": True,
        "custom_token": custom_token,
        "uid": user["uid"],
        "email": user.get("email") or body.email,
    }


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
@rate_limit("register")
async def register_user(
    request: Request,
    body: RegisterRequest,
    _app_check: None = Depends(verify_app_check),
):
    try:
        allowed_roles = {settings.ROLE_DEFAULT_REGISTRATION}
        if body.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Registration role must be one of: {', '.join(allowed_roles)}"
            )
        try:
            validate_corporate_email(body.email)
        except DisposableEmailError:
            raise HTTPException(status_code=400, detail=DISPOSABLE_EMAIL_MESSAGE)

        auth = get_auth()
        user = auth.create_user(
            email=body.email,
            password=body.password,
            display_name=body.full_name,
            email_verified=False,
        )

        claims = {"role": body.role}
        if body.tenant_id:
            claims["tenant_id"] = body.tenant_id

        auth.set_custom_user_claims(user.uid, claims)

        now = datetime.now(timezone.utc)
        upsert_user_doc(user.uid, {
            "uid": user.uid,
            "email": user.email,
            "display_name": body.full_name,
            "role": body.role,
            "tenant_id": body.tenant_id,
            "created_at": now,
            "updated_at": now,
        })

        ip, request_id = request_context(request)
        log_audit(
            action="REGISTER",
            user=body.email,
            tenant_id=body.tenant_id,
            ip=ip,
            request_id=request_id,
        )

        return {
            "success": True,
            "uid": user.uid,
            "email": user.email,
            "role": body.role,
            "tenant_id": body.tenant_id,
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
@rate_limit("register_tenant")
async def register_tenant_endpoint(
    request: Request,
    body: RegisterTenantRequest,
    background_tasks: BackgroundTasks,
    _app_check: None = Depends(verify_app_check),
):
    """Self-service tenant registration (beta portal).

    Provisions the primary administrator (AIRLINE_ADMIN / safety), initialises
    the operational profile at ``tenants/{tenant_id}/profile/operational`` and
    issues a unique team invite code for colleague onboarding.

    After honeypot validation (frontend), the disposable-email check and
    database provisioning have all passed, a Gmail acknowledgment is scheduled
    in the background — SMTP problems never block or roll back a valid record.
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
    except DisposableEmailError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Provisioning succeeded: schedule the registration acknowledgment. It runs
    # after the response is sent and never raises, so a mail outage cannot
    # surface an error to the applicant or roll back the tenant.
    background_tasks.add_task(
        gmail_dispatcher.send_registration_acknowledgment_async,
        body.email,
        body.admin_full_name,
        body.organization_name,
    )

    return {"success": True, **result}


@router.get("/verify-invite")
@rate_limit("verify_invite")
async def verify_invite_endpoint(
    request: Request,
    code: Optional[str] = Query(None, description="Team invite code"),
    _app_check: None = Depends(verify_app_check),
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
@rate_limit("join_team")
async def join_team_endpoint(
    request: Request,
    body: JoinTeamRequest,
    _app_check: None = Depends(verify_app_check),
):
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
    except DisposableEmailError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"success": True, **result}


@router.get("/tenant-lookup")
@rate_limit("auth_attempts")
async def tenant_lookup_endpoint(
    request: Request,
    code: Optional[str] = Query(None, description="Team invite code"),
    tenant_id: Optional[str] = Query(None, description="Tenant id / slug"),
    _app_check: None = Depends(verify_app_check),
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
