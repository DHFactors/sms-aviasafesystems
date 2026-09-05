# ============================================================================
# FILE: admin.py
# PATH: backend/app/routes/admin.py
# VERSION: 2.0.0
# DATE CREATED: 2026-07-03
# DATE REVISED: 2026-07-27
# PURPOSE: Admin and Safety Manager endpoints for system configuration.
# AUTHOR: Ghanshyam Acharya
# CODE OWNER: AviaSafeSystems
# ============================================================================

import secrets
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from loguru import logger
from datetime import datetime, timezone

from app.core.config import settings
from app.firebase import get_auth, get_db, verify_firebase_token
from app.middleware.auth import get_current_user, get_safety_manager, get_admin_user
from app.services.risk_matrix import (
    get_risk_matrix_config,
    set_risk_matrix_config,
    THRESHOLDS_DEFAULT,
)
from app.services.users import upsert_user_doc, user_doc_from_auth_record
from app.services.audit_service import log_audit, request_context

router = APIRouter()


def _verify_admin_setup(setup_key: str) -> None:
    """Second factor for admin provisioning endpoints.

    The setup key is a defense-in-depth secret loaded from the environment. It
    never grants access by itself — callers must also present a SUPER_ADMIN
    Firebase ID token (enforced via the `get_admin_user` dependency).
    """
    if not settings.SETUP_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin setup is not configured on this server",
        )
    if not setup_key or not secrets.compare_digest(setup_key, settings.SETUP_SECRET):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid setup key")


def verify_task_auth(request: Request) -> Dict[str, Any]:
    """Authenticate the internal scheduled-task endpoints.

    Accepts either a shared `X-Task-Key` header matching TASK_API_KEY (used by
    Cloud Scheduler) or a SUPER_ADMIN Firebase ID token in the Authorization
    header. Returns the acting user context.
    """
    header_key = request.headers.get("X-Task-Key")
    if header_key and settings.TASK_API_KEY and secrets.compare_digest(header_key, settings.TASK_API_KEY):
        return {"uid": "system", "email": "system", "role": "SUPER_ADMIN", "tenant_id": None}

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):]
        decoded = verify_firebase_token(token)
        if decoded and decoded.get("role") == "SUPER_ADMIN":
            return {
                "uid": decoded.get("uid", "system"),
                "email": decoded.get("email", "system"),
                "role": "SUPER_ADMIN",
                "tenant_id": decoded.get("tenant_id"),
            }

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Task authentication required (X-Task-Key header or SUPER_ADMIN token)",
    )


class RiskMatrixThresholds(BaseModel):
    low_max: int = Field(default=5, ge=1, le=25)
    medium_max: int = Field(default=9, ge=1, le=25)
    high_max: int = Field(default=15, ge=1, le=25)


class RiskMatrixConfig(BaseModel):
    thresholds: RiskMatrixThresholds
    updated_by: Optional[str] = None
    updated_at: Optional[str] = None


@router.get("/risk-matrix")
async def get_risk_matrix(
    user: Dict[str, Any] = Depends(get_safety_manager),
):
    """Get the ICAO risk matrix configuration for the user's tenant.

    Defaults to ICAO-aligned thresholds if not yet configured.
    """
    tenant_id = user.get("tenant_id")
    if not tenant_id and user.get("role") in ["CAAN_SMD", "SUPER_ADMIN"]:
        tenant_id = "default"
    config = get_risk_matrix_config(tenant_id)
    return config


@router.put("/risk-matrix", status_code=status.HTTP_200_OK)
async def update_risk_matrix(
    config: RiskMatrixConfig,
    user: Dict[str, Any] = Depends(get_safety_manager),
):
    """Update the ICAO risk matrix thresholds for the user's tenant.

    Thresholds define Low/Medium/High/Very High boundaries.
    All thresholds are inclusive max values for each level.
    Must satisfy: 1 <= low_max < medium_max < high_max <= 25.
    """
    t = config.thresholds
    if not (1 <= t.low_max < t.medium_max < t.high_max <= 25):
        raise HTTPException(
            status_code=400,
            detail="Thresholds must satisfy: 1 <= low_max < medium_max < high_max <= 25",
        )

    tenant_id = user.get("tenant_id")
    if not tenant_id and user.get("role") in ["CAAN_SMD", "SUPER_ADMIN"]:
        tenant_id = "default"

    now = datetime.now(timezone.utc).isoformat()
    data = {
        "thresholds": t.model_dump(),
        "updated_by": user["uid"],
        "updated_at": now,
    }
    set_risk_matrix_config(tenant_id, data, updated_by=user["uid"])
    logger.info(f"Risk matrix updated for tenant {tenant_id} by {user['uid']}")
    return data


class SetupClaimsRequest(BaseModel):
    setup_key: str
    users: List[dict]


@router.post("/setup-claims")
async def setup_test_user_claims(
    req: SetupClaimsRequest,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Set custom claims on users.

    Requires a SUPER_ADMIN Bearer token and the admin setup key (env).
    """
    _verify_admin_setup(req.setup_key)

    results = []
    auth = get_auth()
    for u in req.users:
        email = u.get("email")
        role = u.get("role", "USER")
        tenant_id = u.get("tenant_id")
        if not email:
            results.append({"email": email, "status": "error", "detail": "email required"})
            continue
        try:
            user_record = auth.get_user_by_email(email)
            claims = {"role": role}
            if tenant_id:
                claims["tenant_id"] = tenant_id
            uid = user_record.uid
            auth.update_user(uid, custom_claims=claims)
            upsert_user_doc(uid, user_doc_from_auth_record(auth.get_user(uid)))
            results.append({"email": email, "uid": uid, "role": role, "tenant_id": tenant_id, "status": "ok"})
            logger.info(f"Claims set for {email}: role={role}, tenant_id={tenant_id}")
        except Exception as e:
            results.append({"email": email, "status": "error", "detail": str(e)})
            logger.error(f"Failed to set claims for {email}: {e}")

    return {"success": True, "results": results}


class AdminSetupRequest(BaseModel):
    setup_key: str


AIRLINES = [
    {"id": "buddha-air", "name": "Buddha Air", "icao": "BHA", "email": "buddhaair@buddhaair.com"},
    {"id": "nepal-airlines", "name": "Nepal Airlines", "icao": "NAL", "email": "info@nac.com.np"},
    {"id": "shree-airlines", "name": "Shree Airlines", "icao": "SHA", "email": "info@shreeairlines.com"},
    {"id": "sita-air", "name": "Sita Air", "icao": "STA", "email": "info@sitaair.com"},
    {"id": "summit-air", "name": "Summit Air", "icao": "SMT", "email": "info@summitair.com.np"},
    {"id": "tara-air", "name": "Tara Air", "icao": "TRA", "email": "info@taraair.com"},
    {"id": "yeti-airlines", "name": "Yeti Airlines", "icao": "YET", "email": "info@yetiairlines.com"},
    {"id": "makalu-air", "name": "Makalu Air", "icao": "MKU", "email": "info@makaluair.com"},
    {"id": "himalaya-airlines", "name": "Himalaya Airlines", "icao": "HIM", "email": "info@himalaya-airlines.com"},
    {"id": "air-dynasty", "name": "Air Dynasty Heli Services", "icao": "ADH", "email": "info@airdynasty.com"},
    {"id": "altitude-air", "name": "Altitude Air", "icao": "ALT", "email": "info@altitudeair.com.np"},
    {"id": "annapurna-heli", "name": "Annapurna Helicopter", "icao": "ANH", "email": "info@annapurnaheli.com"},
    {"id": "fishtail-air", "name": "Fishtail Air", "icao": "FTA", "email": "info@fishtailair.com"},
    {"id": "heli-everest", "name": "Heli Everest", "icao": "HLE", "email": "info@helieverest.com"},
    {"id": "kailash-helicopter", "name": "Kailash Helicopter Services", "icao": "KHS", "email": "info@kailashhelicopter.com"},
    {"id": "manang-air", "name": "Manang Air", "icao": "MNA", "email": "info@manangair.com"},
    {"id": "mountain-helicopters", "name": "Mountain Helicopters", "icao": "MTH", "email": "info@mountainhelicopters.com"},
    {"id": "mustang-helicopter", "name": "Mustang Helicopter", "icao": "MSH", "email": "info@mustanghelicopter.com"},
    {"id": "prabhu-helicopters", "name": "Prabhu Helicopters", "icao": "PRB", "email": "info@prabhuhelicopters.com"},
    {"id": "simrik-air", "name": "Simrik Air", "icao": "SMK", "email": "info@simrikair.com"},
]

@router.post("/provision-airlines", status_code=status.HTTP_200_OK)
async def provision_20_airlines(
    req: AdminSetupRequest,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Batch-provision all 20 Nepali airlines: create Auth users, set claims, create Firestore tenants."""
    _verify_admin_setup(req.setup_key)

    if not settings.DEFAULT_PROVISION_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DEFAULT_PROVISION_PASSWORD is not configured on this server",
        )

    auth = get_auth()
    db = get_db()
    results = []
    now = datetime.now(timezone.utc).isoformat()

    for a in AIRLINES:
        tid = a["id"]
        email = a["email"]
        name = a["name"]
        icao = a["icao"]
        record = {"tenant_id": tid, "email": email, "name": name, "status": "pending"}

        try:
            try:
                user = auth.create_user(
                    email=email,
                    password=settings.DEFAULT_PROVISION_PASSWORD,
                    email_verified=True,
                    display_name=f"{name} Safety Manager",
                )
                record["action"] = "created"
            except Exception as create_err:
                if "email already exists" in str(create_err).lower():
                    user = auth.get_user_by_email(email)
                    record["action"] = "existing"
                else:
                    raise

            uid = user.uid
            auth.update_user(uid, custom_claims={"role": "AIRLINE_ADMIN", "tenant_id": tid})
            upsert_user_doc(uid, user_doc_from_auth_record(auth.get_user(uid)))

            tenant_ref = db.collection("tenants").document(tid)
            tenant_doc = tenant_ref.get()

            if not tenant_doc.exists:
                tenant_ref.set({
                    "tenant_id": tid,
                    "name": name,
                    "icao": icao,
                    "country": "Nepal",
                    "active": True,
                    "safety_manager": {
                        "email": email,
                        "name": f"{name} Safety Manager",
                        "uid": uid,
                    },
                    "survey_config": {
                        "open": True,
                        "open_date": "2026-08-01",
                        "close_date": "2026-08-31",
                    },
                    "created_at": now,
                    "updated_at": now,
                })
                record["tenant"] = "created"
            else:
                record["tenant"] = "exists"

            record["uid"] = uid
            record["status"] = "ok"
            logger.info(f"Provisioned {name} ({tid}) -> {email} / {uid}")

        except Exception as e:
            record["status"] = "error"
            record["detail"] = str(e)
            logger.error(f"Provision failed for {email}: {e}")

        results.append(record)

    summary = {
        "total": len(AIRLINES),
        "ok": sum(1 for r in results if r["status"] == "ok"),
        "skipped": sum(1 for r in results if r["status"] == "skipped"),
        "error": sum(1 for r in results if r["status"] == "error"),
    }

    return {"success": True, "summary": summary, "results": results}


@router.post("/fix-tenant-ids", status_code=status.HTTP_200_OK)
async def fix_tenant_id_mismatch(
    req: AdminSetupRequest,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Fix tenant_id mismatch: provisioned users use hyphens but seed data uses underscores."""
    _verify_admin_setup(req.setup_key)

    auth = get_auth()
    FIXES = {
        "buddhaair@buddhaair.com": "buddha_air",
        "info@sitaair.com": "sita_air",
        "info@summitair.com.np": "summit_air",
        "info@yetiairlines.com": "yeti_airlines",
        "info@airdynasty.com": "air_dynasty",
        "info@simrikair.com": "simrik_air",
    }
    results = []
    for email, correct_tid in FIXES.items():
        try:
            user = auth.get_user_by_email(email)
            existing = user.custom_claims or {}
            existing["tenant_id"] = correct_tid
            auth.update_user(user.uid, custom_claims=existing)
            results.append({"email": email, "tenant_id": correct_tid, "status": "ok"})
            logger.info(f"Fixed tenant_id for {email}: {correct_tid}")
        except Exception as e:
            results.append({"email": email, "status": "error", "detail": str(e)})
    return {"success": True, "results": results}


@router.post("/create-seed-users", status_code=status.HTTP_200_OK)
async def create_seed_users(
    req: AdminSetupRequest,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Legacy hardcoded seed-user path — removed.

    Auth-user provisioning is now achieved data-driven from the Production
    Setup panel (Step 2 user rows / the tenant-credentials wizard), not from a
    hardcoded operator list.
    """
    raise HTTPException(status_code=404, detail="Endpoint removed — use the Production Setup tenant flow")


@router.post("/seed-demo-data", status_code=status.HTTP_200_OK)
async def seed_demo_data(
    req: AdminSetupRequest,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Legacy hardcoded demo-data path — removed.

    Operational dummy data (VSR/MOR/CAN/CAP/Survey) is now seeded data-driven
    from the Production Setup Step 5 tool into PostgreSQL (is_demo=true).
    """
    raise HTTPException(status_code=404, detail="Endpoint removed — use Production Setup Step 5 (Dummy Data)")


# ============================================================================
# Super-Admin web seeding panel (admin/dashboard.html)
# ============================================================================

class RegulatorCreate(BaseModel):
    id: str
    name: str
    short_name: Optional[str] = None
    country: Optional[str] = None
    country_name: Optional[str] = None
    domain: Optional[str] = None
    operator_tenant_ids: Optional[List[str]] = None
    active: bool = True


class TenantCreate(BaseModel):
    tenant_id: str
    name: str
    icao: Optional[str] = None
    country: Optional[str] = "Nepal"
    active: bool = True
    regulator_id: Optional[str] = None
    safety_manager: Optional[Dict[str, Any]] = None
    survey_config: Optional[Dict[str, Any]] = None
    contact: Optional[Dict[str, Any]] = None
    contract: Optional[Dict[str, Any]] = None
    users: Optional[List[Dict[str, Any]]] = None
    status: Optional[str] = "active"


class TenantBulkRequest(BaseModel):
    setup_key: str
    records: Optional[List[TenantCreate]] = None
    csv: Optional[str] = None


class RegulatorSetupRequest(BaseModel):
    setup_key: str
    regulator: RegulatorCreate


class TenantSetupRequest(BaseModel):
    setup_key: str
    tenant: TenantCreate


@router.post("/regulators", status_code=status.HTTP_200_OK)
async def admin_create_regulator(
    req: RegulatorSetupRequest,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Create a State Regulator document (SUPER_ADMIN + setup key)."""
    _verify_admin_setup(req.setup_key)
    from app.services.production_seed import create_regulator
    try:
        doc = create_regulator(req.regulator.model_dump(), user)
        return {"success": True, "regulator": doc}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Create regulator failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/regulators", status_code=status.HTTP_200_OK)
async def admin_list_regulators(
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """List every State Regulator (SUPER_ADMIN), enriched with operator_count/status."""
    from app.services.regulator_service import list_regulators
    return {"success": True, "regulators": list_regulators()}


@router.post("/tenants", status_code=status.HTTP_200_OK)
async def admin_create_tenant(
    req: TenantSetupRequest,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Create one operator tenant (SUPER_ADMIN + setup key).

    When `tenant.users` is provided the tenant is created together with its
    Firebase Auth users (AIRLINE_ADMIN etc.) and the generated passwords are
    returned exactly once (never persisted).
    """
    _verify_admin_setup(req.setup_key)
    data = req.tenant.model_dump()
    if data.get("users"):
        from app.services.tenant_credentials import create_tenant_with_credentials
        try:
            result = create_tenant_with_credentials(data, user)
            return {"success": True, **result}
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except Exception as e:
            logger.error(f"Create tenant with credentials failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    from app.services.production_seed import create_tenant
    try:
        doc = create_tenant(data, user)
        return {"success": True, "tenant": doc}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Create tenant failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tenants/bulk", status_code=status.HTTP_200_OK)
async def admin_bulk_create_tenants(
    req: TenantBulkRequest,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Bulk-import tenants from a JSON list or CSV text (SUPER_ADMIN + setup key)."""
    _verify_admin_setup(req.setup_key)
    from app.services.production_seed import bulk_create_tenants

    records: List[Dict[str, Any]] = []
    if req.records:
        records = [r.model_dump() for r in req.records]
    elif req.csv:
        import csv as _csv
        import io
        reader = _csv.DictReader(io.StringIO(req.csv))
        for row in reader:
            rec = {k.strip(): (v or "").strip() for k, v in row.items() if k}
            if not rec.get("tenant_id") and rec.get("id"):
                rec["tenant_id"] = rec.pop("id")
            if not rec.get("tenant_id"):
                continue
            records.append(rec)
    else:
        raise HTTPException(status_code=400, detail="Provide 'records' (JSON) or 'csv' text")

    if not records:
        raise HTTPException(status_code=400, detail="No valid tenant records provided")

    try:
        result = bulk_create_tenants(records, user)
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"Bulk tenant import failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tenants", status_code=status.HTTP_200_OK)
async def admin_list_tenants(
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """List all operator tenants with counts (SUPER_ADMIN).

    Counts come from PostgreSQL when configured (keyed by the deterministic
    tenant uuid) and fall back to Firestore subcollections otherwise.
    """
    from app.services.production_seed import list_tenants_admin_pg
    return {"success": True, "tenants": await list_tenants_admin_pg()}


@router.get("/seed/logs", status_code=status.HTTP_200_OK)
async def admin_seed_logs(
    limit: int = Query(50, ge=1, le=200),
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Recent seeding/admin audit log entries (SUPER_ADMIN)."""
    from app.services.production_seed import list_audit_logs
    return {"success": True, "logs": list_audit_logs(limit=limit)}


# ============================================================================
# Scheduled tasks (internal; Cloud Scheduler / task runners)
# ============================================================================

class CheckOverdueRequest(BaseModel):
    tenant_id: Optional[str] = None


@router.post("/tasks/check-overdue", status_code=status.HTTP_200_OK)
async def admin_check_overdue(
    req: CheckOverdueRequest,
    request: Request,
):
    """Run the overdue/escalation scan across all tenants (or one tenant).

    Intended to be invoked daily by Cloud Scheduler with the X-Task-Key header
    (TASK_API_KEY) or a SUPER_ADMIN token. Escalates past-due CANs to
    "Escalated" and past-due CAPs to "Overdue", logging every change.
    """
    verify_task_auth(request)
    from app.services.escalation_service import check_all_overdue
    try:
        result = check_all_overdue(tenant_id=req.tenant_id or None)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Overdue check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Overdue check failed: {str(e)}")


# ============================================================================
# Tenant credentials management (tenant-credentials.html)
# ============================================================================

class CheckEmailRequest(BaseModel):
    setup_key: str
    email: str


class TenantIdSetupRequest(BaseModel):
    setup_key: str
    tenant_id: str


@router.post("/tenants/check-email", status_code=status.HTTP_200_OK)
async def admin_check_email(
    req: CheckEmailRequest,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Check whether an email is already registered in Firebase Auth (SUPER_ADMIN + setup key)."""
    _verify_admin_setup(req.setup_key)
    from app.services.tenant_credentials import check_email_available
    try:
        return {"success": True, **check_email_available(req.email)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Email availability check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tenants/{tenant_id}/credentials", status_code=status.HTTP_200_OK)
async def admin_get_tenant_credentials(
    tenant_id: str,
    setup_key: str = Query("", description="Admin setup key (SETUP_SECRET)"),
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Get a tenant's stored credential metadata (SUPER_ADMIN + setup key).

    Never returns passwords — those are generated, applied to Firebase Auth,
    surfaced once, and never persisted.
    """
    _verify_admin_setup(setup_key)
    from app.services.tenant_credentials import get_tenant_credentials
    try:
        return {"success": True, "credentials": get_tenant_credentials(tenant_id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Get tenant credentials failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tenants/{tenant_id}/reset-password", status_code=status.HTTP_200_OK)
async def admin_reset_tenant_password(
    tenant_id: str,
    req: AdminSetupRequest,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Reset a tenant's admin password (SUPER_ADMIN + setup key).

    The new password is returned exactly once and is never stored.
    """
    _verify_admin_setup(req.setup_key)
    from app.services.tenant_credentials import reset_admin_password
    try:
        return {"success": True, **reset_admin_password(tenant_id, user)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Reset tenant password failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tenants/{tenant_id}/send-welcome", status_code=status.HTTP_200_OK)
async def admin_send_tenant_welcome(
    tenant_id: str,
    req: AdminSetupRequest,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Set a fresh temporary password and email it to the tenant admin.

    Requires an email provider (EMAIL_PROVIDER=smtp|sendgrid). With the default
    'none' provider the message is rendered, logged, and returned as a preview.
    """
    _verify_admin_setup(req.setup_key)
    from app.services.tenant_credentials import send_welcome_email_for_tenant
    try:
        return {"success": True, **send_welcome_email_for_tenant(tenant_id, user)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Send welcome email failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Tenant lifecycle status + demo-data seeding (admin/dashboard.html)
# ============================================================================

class TenantStatusRequest(BaseModel):
    setup_key: str
    status: Optional[str] = None
    contract_start_date: Optional[str] = None
    contract_end_date: Optional[str] = None
    payment_status: Optional[str] = None
    trial_end_date: Optional[str] = None
    from_date: Optional[str] = Field(None, description="Commercial lifecycle start (YYYY-MM-DD), alias for contract_start_date")
    to_date: Optional[str] = Field(None, description="Commercial lifecycle end (YYYY-MM-DD), alias for contract_end_date")


class DemoDataRequest(BaseModel):
    setup_key: str
    action: str = "seed"
    all: bool = True
    tenant_ids: Optional[List[str]] = None
    kinds: List[str] = ["vsr", "mor", "can", "cap", "survey"]
    counts: Optional[Dict[str, int]] = None


class PsoeSetupRequest(BaseModel):
    setup_key: str
    all: bool = True
    tenant_ids: Optional[List[str]] = None
    force: bool = False


class StateRiskSetupRequest(BaseModel):
    setup_key: str


class PurgeDemoDataRequest(BaseModel):
    setup_key: str


@router.post("/tenants/{tenant_id}/status", status_code=status.HTTP_200_OK)
async def admin_update_tenant_status(
    tenant_id: str,
    req: TenantStatusRequest,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Update a tenant's commercial lifecycle status + date range.

    Supports demo, trial, active, suspended, retired, cancelled (and legacy
    inactive). from_date/to_date are commercial aliases for contract
    start/end and are stored at top-level plus inside contract. Requires
    SUPER_ADMIN + setup key and is audit-logged.
    """
    _verify_admin_setup(req.setup_key)
    from app.services.admin_data_service import update_tenant_status
    try:
        doc = update_tenant_status(
            tenant_id,
            user,
            status=req.status,
            contract_start_date=req.contract_start_date,
            contract_end_date=req.contract_end_date,
            payment_status=req.payment_status,
            trial_end_date=req.trial_end_date,
            from_date=req.from_date,
            to_date=req.to_date,
        )
        return {"success": True, "tenant": doc}
    except ValueError as e:
        msg = str(e)
        raise HTTPException(
            status_code=404 if "not found" in msg else 400,
            detail=msg,
        )
    except Exception as e:
        logger.error(f"Update tenant status failed ({tenant_id}): {e}")
        raise HTTPException(status_code=500, detail=str(e))


class RegulatorStatusRequest(BaseModel):
    setup_key: str = Field(..., description="Admin setup key (SETUP_SECRET)")
    status: Optional[str] = Field(None, description="Lifecycle status: demo, trial, active, suspended, retired, cancelled, inactive")
    from_date: Optional[str] = Field(None, description="Commercial start (YYYY-MM-DD)")
    to_date: Optional[str] = Field(None, description="Commercial end (YYYY-MM-DD)")
    contract_start_date: Optional[str] = Field(None, description="Alias for from_date")
    contract_end_date: Optional[str] = Field(None, description="Alias for to_date")


@router.post("/regulators/{regulator_id}/status", status_code=status.HTTP_200_OK)
async def admin_update_regulator_status(
    regulator_id: str,
    req: RegulatorStatusRequest,
    request: Request,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Update a regulator's commercial lifecycle status + date range.

    Supports demo, trial, active, suspended, retired, cancelled. from_date/to_date
    are stored at top-level and inside contract. Requires SUPER_ADMIN + setup key,
    audit-logged as REGULATOR_STATUS_UPDATED.
    """
    _verify_admin_setup(req.setup_key)
    from app.services.regulator_service import update_regulator_status

    # Normalize aliases
    from_d = req.from_date or req.contract_start_date
    to_d = req.to_date or req.contract_end_date
    try:
        doc = update_regulator_status(
            regulator_id,
            user,
            status=req.status,
            from_date=from_d,
            to_date=to_d,
            contract_start_date=req.contract_start_date,
            contract_end_date=req.contract_end_date,
        )
    except ValueError as e:
        msg = str(e)
        raise HTTPException(status_code=404 if "not found" in msg.lower() else 400, detail=msg)
    except Exception as e:
        logger.error(f"Update regulator status failed ({regulator_id}): {e}")
        raise HTTPException(status_code=500, detail=str(e))

    ip, request_id = request_context(request)
    log_audit(
        action="REGULATOR_STATUS_UPDATED",
        user=user.get("email"),
        tenant_id=regulator_id,
        target_type="regulator",
        target_id=regulator_id,
        ip=ip,
        request_id=request_id,
        metadata={
            "status": doc.get("status"),
            "from_date": from_d,
            "to_date": to_d,
            "by_uid": user.get("uid"),
        },
    )
    logger.info(f"Regulator {regulator_id} status -> {doc.get('status')} by {user.get('email')}")
    return {"success": True, "regulator": doc}


@router.post("/demo-data", status_code=status.HTTP_200_OK)
async def admin_demo_data(
    req: DemoDataRequest,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Seed or unseed dummy operational data (VSR/MOR/CAN/CAP/Survey).

    Targets one tenant (tenant_ids) or every tenant (all=True) and writes to
    PostgreSQL with is_demo=true. Unseed only removes rows created by this
    seeder (marked admin-demo-1).
    """
    _verify_admin_setup(req.setup_key)
    from app.services.admin_data_service import (
        demo_data_scope,
        seed_tenant_demo_data,
        unseed_tenant_demo_data,
    )

    if req.action not in ("seed", "unseed"):
        raise HTTPException(status_code=400, detail="action must be 'seed' or 'unseed'")

    tenant_ids = demo_data_scope(req.tenant_ids, all_tenants=req.all)
    if not tenant_ids:
        raise HTTPException(
            status_code=400,
            detail="No tenants to target — create tenants first or pass tenant_ids",
        )

    results = []
    for tid in tenant_ids:
        try:
            if req.action == "seed":
                results.append(await seed_tenant_demo_data(tid, req.kinds, user, counts=req.counts))
            else:
                results.append(await unseed_tenant_demo_data(tid, req.kinds, user))
        except ValueError as e:
            results.append({"tenant_id": tid, "error": str(e)})
        except Exception as e:
            logger.error(f"Demo data {req.action} failed for {tid}: {e}")
            results.append({"tenant_id": tid, "error": str(e)})

    return {
        "success": True,
        "action": req.action,
        "kinds": req.kinds,
        "results": results,
    }


@router.post("/purge-demo-data", status_code=status.HTTP_200_OK)
async def admin_purge_demo_data(
    req: PurgeDemoDataRequest,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Delete ALL demo data cluster-wide (is_demo = true).

    Irreversible. Removes demo rows from every Postgres table carrying the
    is_demo flag, plus FK-scoped child rows (verifications, closures,
    corrective actions, flight diversions, safety deficiencies, RCA subtree,
    PSOE findings, bow-tie children). Real tenant data (is_demo = false) and
    the global psoe_questions reference bank are never touched. Returns
    per-table deletion counts.
    """
    _verify_admin_setup(req.setup_key)
    from app.services.admin_data_service import purge_all_demo_data

    try:
        return await purge_all_demo_data(user)
    except Exception as e:
        logger.error(f"Purge demo data failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/psoe", status_code=status.HTTP_200_OK)
async def admin_seed_psoe(
    req: PsoeSetupRequest,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Seed PSOE baseline assessments (COMPLETED + DRAFT) data-driven.

    Targets one tenant (tenant_ids) or every Step-2 tenant (all=True). Existing
    assessments are skipped unless ``force`` replaces them. Data-driven — there
    is no hardcoded tenant list.
    """
    _verify_admin_setup(req.setup_key)
    from app.services.admin_data_service import demo_data_scope
    from app.services.seed_surfaces import seed_psoe_all, seed_psoe_tenant

    tenant_ids = demo_data_scope(req.tenant_ids, all_tenants=req.all)
    if not tenant_ids:
        raise HTTPException(
            status_code=400,
            detail="No tenants to target — create tenants first (Step 2) or pass tenant_ids",
        )

    if len(tenant_ids) == 1 and not req.all:
        try:
            result = await seed_psoe_tenant(tenant_ids[0], user, force=req.force)
            return {"success": True, "results": [result]}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
    result = await seed_psoe_all(tenant_ids, user, force=req.force)
    return {"success": True, "results": result["results"]}


@router.post("/state-risk", status_code=status.HTTP_200_OK)
async def admin_seed_state_risk(
    req: StateRiskSetupRequest,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Write the ICAO state-risk reference categories (global reference data)."""
    _verify_admin_setup(req.setup_key)
    from app.services.seed_surfaces import seed_state_risk_reference
    try:
        result = await seed_state_risk_reference(user)
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"State risk reference seed failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedback")
async def list_feedback(
    limit: int = Query(default=50, ge=1, le=200),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """List in-product feedback submissions for review.

    Restricted to CROSS-TENANT (SUPER_ADMIN / CAAN_SMD) roles. Returns the most
    recent feedback first, with the submitter's email, role, tenant, page
    context, optional 1-5 rating, and message body.
    """
    if user.get("role") not in settings.CROSS_TENANT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SUPER_ADMIN or CAAN_SMD role required to review feedback",
        )

    try:
        db = get_db()
        query = db.collection("feedback")
        if status_filter:
            query = query.where("status", "==", status_filter)
        docs = sorted(
            query.limit(limit).stream(),
            key=lambda d: (d.to_dict() or {}).get("created_at"),
            reverse=True,
        )
    except Exception as e:
        logger.error(f"Failed to list feedback for {user.get('email')}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not retrieve feedback at this time.",
        )

    items = []
    for d in docs:
        x = d.to_dict() or {}
        ts = x.get("created_at")
        items.append(
            {
                "id": d.id,
                "uid": x.get("uid"),
                "email": x.get("email"),
                "role": x.get("role"),
                "tenant_id": x.get("tenant_id"),
                "subject": x.get("subject"),
                "message": x.get("message"),
                "rating": x.get("rating"),
                "page": x.get("page"),
                "created_at": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "status": x.get("status", "new"),
            }
        )

    return {"feedback": items, "count": len(items)}


# ============================================================================
# Developer / SuperAdmin tenant governance (admin/dashboard.html)
# ============================================================================
# Governance statuses control whether a tenant's users can authenticate. They
# live on the tenant document's `status` field (ACTIVE / SUSPENDED /
# PENDING_REVIEW); `get_current_user` in middleware/auth.py rejects users whose
# tenant is SUSPENDED with HTTP 403. The access gate is SUPER_ADMIN role OR the
# developer email allowlist (defense in depth — never rely on role alone).

GOVERNANCE_STATUSES = {"ACTIVE", "SUSPENDED", "PENDING_REVIEW"}
DEVELOPER_EMAIL_ALLOWLIST = {"ghanshyamacharya@outlook.com"}


async def get_developer_user(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Gate for tenant governance endpoints: SUPER_ADMIN role or developer email."""
    if user.get("role") in settings.SUPER_ADMIN_ROLES:
        return user
    if (user.get("email") or "").strip().lower() in DEVELOPER_EMAIL_ALLOWLIST:
        return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="SUPER_ADMIN or developer access required",
    )


class TenantGovernanceStatusRequest(BaseModel):
    status: str


def _governance_row(snap: Any) -> Dict[str, Any]:
    """Normalize one tenant document into the governance list row shape."""
    x = snap.to_dict() or {}
    raw_status = str(x.get("status") or "ACTIVE").strip().upper()
    if raw_status not in GOVERNANCE_STATUSES:
        raw_status = "ACTIVE"
    created_at = x.get("created_at")
    return {
        "tenant_id": x.get("tenant_id") or snap.id,
        "name": x.get("name") or x.get("tenant_name") or snap.id,
        "classification": x.get("classification") or x.get("tenant_type") or "",
        "admin_email": (x.get("safety_manager") or {}).get("email") or "",
        "status": raw_status,
        "created_at": (
            created_at.isoformat() if hasattr(created_at, "isoformat") else (str(created_at) if created_at else None)
        ),
        "is_beta_sandbox": bool(x.get("is_beta_sandbox", False)),
    }


@router.get("/tenants/governance", status_code=status.HTTP_200_OK)
async def admin_list_tenant_governance(
    user: Dict[str, Any] = Depends(get_developer_user),
):
    """List every tenant for governance review (SUPER_ADMIN / developer).

    Returns a clean summary: tenant_id, name, classification, admin_email,
    status (default ACTIVE when unset), created_at and is_beta_sandbox.
    """
    try:
        docs = get_db().collection(settings.FIREBASE_COLLECTION_TENANTS).get()
    except Exception as e:
        logger.error(f"Failed to list tenant governance for {user.get('email')}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not retrieve tenants at this time.",
        )

    rows = [_governance_row(d) for d in docs]
    rows.sort(key=lambda r: (r["name"] or "").lower())
    return {"tenants": rows, "count": len(rows)}


@router.patch("/tenants/{tenant_id}/status", status_code=status.HTTP_200_OK)
async def admin_update_tenant_governance_status(
    tenant_id: str,
    req: TenantGovernanceStatusRequest,
    request: Request,
    user: Dict[str, Any] = Depends(get_developer_user),
):
    """Set a tenant's governance status (ACTIVE / SUSPENDED / PENDING_REVIEW).

    Users belonging to a SUSPENDED tenant are blocked at authentication
    (middleware/auth.py -> get_current_user) with HTTP 403.
    """
    new_status = (req.status or "").strip().upper()
    if new_status not in GOVERNANCE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"status must be one of: {sorted(GOVERNANCE_STATUSES)}",
        )

    db = get_db()
    ref = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tenant_id)
    try:
        doc = ref.get()
    except Exception as e:
        logger.error(f"Failed to read tenant {tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not read the tenant at this time.",
        )
    if doc is None or not doc.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found",
        )

    now = datetime.now(timezone.utc).isoformat()
    updates = {
        "status": new_status,
        "active": new_status == "ACTIVE",
        "status_updated_at": now,
        "status_updated_by": user.get("uid"),
        "updated_at": now,
    }
    try:
        ref.update(updates)
    except Exception as e:
        logger.error(f"Failed to update tenant {tenant_id} status: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not update the tenant status at this time.",
        )

    ip, request_id = request_context(request)
    log_audit(
        action="TENANT_GOVERNANCE_STATUS_UPDATED",
        user=user.get("email"),
        tenant_id=tenant_id,
        target_type="tenant",
        target_id=tenant_id,
        ip=ip,
        request_id=request_id,
        metadata={"status": new_status, "by_uid": user.get("uid")},
    )
    logger.info(f"Tenant {tenant_id} governance status -> {new_status} by {user.get('email')}")

    return {
        "success": True,
        "tenant": {
            **{"tenant_id": tenant_id},
            **_governance_row(doc),
            "status": new_status,
        },
    }


# ============================================================================
# User management — SUPER_ADMIN user deletion / purge
# ============================================================================

class UserDeleteRequest(BaseModel):
    setup_key: str = Field(..., description="Admin setup key (SETUP_SECRET)")
    email: Optional[str] = Field(None, description="User email to delete")
    uid: Optional[str] = Field(None, description="User UID to delete")
    tenant_id: Optional[str] = Field(None, description="Optional tenant scope hint")


SUPER_ADMIN_PROTECTED_EMAILS = {"ezondiza.dhf@gmail.com", "ghanshyamacharya@outlook.com"}


@router.get("/users", status_code=status.HTTP_200_OK)
async def admin_list_users(
    tenant_id: Optional[str] = Query(None, description="Filter by tenant_id slug"),
    limit: int = Query(100, ge=1, le=1000, description="Max users to return (paginated, 1-1000)"),
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """List Firebase Auth users for Super Admin cleanup (SUPER_ADMIN).

    Returns email, uid, display_name, role, tenant_id, department, disabled
    state. Supports optional tenant_id filter and limit. SUPER_ADMIN-only.
    """
    auth = get_auth()
    db = get_db()
    users: List[Dict[str, Any]] = []
    try:
        # Iterate with pagination — list_users uses page token internally.
        page = auth.list_users(max_results=min(limit, 1000))
        count = 0
        while page and count < limit:
            for rec in page.users:
                if count >= limit:
                    break
                email = getattr(rec, "email", "") or ""
                uid = getattr(rec, "uid", "") or ""
                claims = getattr(rec, "custom_claims", None) or {}
                # Firebase Admin may store claims as dict or None
                if not isinstance(claims, dict):
                    try:
                        claims = dict(claims)
                    except Exception:
                        claims = {}
                role = claims.get("role") or ""
                t = claims.get("tenant_id") or ""
                dept = claims.get("department") or ""
                if tenant_id and str(t).lower() != str(tenant_id).lower():
                    continue
                users.append({
                    "uid": uid,
                    "email": email,
                    "display_name": getattr(rec, "display_name", "") or "",
                    "role": role,
                    "tenant_id": t,
                    "department": dept,
                    "disabled": bool(getattr(rec, "disabled", False)),
                    "email_verified": bool(getattr(rec, "email_verified", False)),
                })
                count += 1
            page = page.get_next_page() if hasattr(page, "get_next_page") else None
            if page is None:
                break
        # Sort by tenant then email for stable UI
        users.sort(key=lambda u: ((u.get("tenant_id") or "").lower(), (u.get("email") or "").lower()))
    except Exception as e:
        logger.error(f"Failed to list users for {user.get('email')}: {e}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not list users at this time.")
    return {"users": users, "count": len(users)}


@router.delete("/users", status_code=status.HTTP_200_OK)
async def admin_delete_user(
    request: Request,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Delete a Firebase Auth user completely (SUPER_ADMIN + setup key).

    Accepts email or uid (email preferred). Verifies SUPER_ADMIN role and
    SETUP_SECRET, blocks deletion of protected super-admin accounts, removes
    the Auth record and any Firestore `users/{uid}` doc, and writes an audit
    log entry with actor/target/timestamp for compliance.

    Robust to DELETE body drop (proxies/FastAPI): extracts from JSON body
    OR query params, returns explicit non-2xx errors (never soft 200 with
    success:false).
    """
    # Robust extraction: DELETE with JSON body can be dropped by proxies;
    # fall back to query params so the call never silently resolves to empty.
    body: Dict[str, Any] = {}
    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}
    qp = request.query_params
    email = (body.get("email") or qp.get("email") or "").strip() if isinstance(body, dict) else (qp.get("email") or "").strip()
    uid = (body.get("uid") or qp.get("uid") or "").strip() if isinstance(body, dict) else (qp.get("uid") or "").strip()
    setup_key = (body.get("setup_key") or qp.get("setup_key") or "").strip() if isinstance(body, dict) else (qp.get("setup_key") or "").strip()
    tenant_hint = (body.get("tenant_id") or qp.get("tenant_id") or "").strip() if isinstance(body, dict) else (qp.get("tenant_id") or "").strip()

    if not setup_key:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="setup_key is required")
    _verify_admin_setup(setup_key)

    if not email and not uid:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Provide email or uid of user to delete")

    auth = get_auth()
    db = get_db()

    # Resolve UID + email + tenant for audit and protection checks
    target_email = email
    target_uid = uid
    target_tenant = tenant_hint
    try:
        if target_uid and not target_email:
            rec = auth.get_user(target_uid)
            target_email = getattr(rec, "email", "") or target_email
            claims = getattr(rec, "custom_claims", {}) or {}
            if isinstance(claims, dict):
                target_tenant = target_tenant or claims.get("tenant_id") or ""
        elif target_email:
            rec = auth.get_user_by_email(target_email)
            target_uid = getattr(rec, "uid", "") or target_uid
            target_email = getattr(rec, "email", "") or target_email
            claims = getattr(rec, "custom_claims", {}) or {}
            if isinstance(claims, dict):
                target_tenant = target_tenant or claims.get("tenant_id") or ""
            # If uid was also supplied but mismatched, prefer the email-resolved uid
            if uid and uid != target_uid:
                logger.warning(f"UID mismatch for {target_email}: supplied {uid} vs resolved {target_uid}")
    except Exception as e:
        # Firebase throws UserNotFoundError / ValueError when not found
        msg = str(e).lower()
        if "not found" in msg or "no user" in msg or "does not exist" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User not found: {email or uid}")
        logger.error(f"Failed to resolve user {email or uid}: {e}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not resolve user at this time.")

    # Protect super-admin / developer accounts from accidental purge
    if (target_email or "").strip().lower() in {e.lower() for e in SUPER_ADMIN_PROTECTED_EMAILS}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Protected account cannot be deleted: {target_email}")

    # Prevent self-deletion
    if (target_email and target_email.lower() == (user.get("email") or "").lower()) or (target_uid and target_uid == user.get("uid")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Self-deletion is not allowed")

    try:
        auth.delete_user(target_uid)
        logger.info(f"Auth user deleted: {target_email} ({target_uid}) by {user.get('email')}")
    except Exception as e:
        msg = str(e).lower()
        if "not found" in msg or "does not exist" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User not found: {target_email or target_uid}")
        logger.error(f"Failed to delete Auth user {target_email} ({target_uid}): {e}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not delete user at this time.")

    # Best-effort Firestore cleanup: users/{uid}
    try:
        db.collection(settings.FIREBASE_COLLECTION_USERS).document(target_uid).delete()
    except Exception as e:
        logger.warning(f"Firestore user doc delete failed for {target_uid}: {e}")

    # Also try legacy lookup doc keyed by email if present (no-op if missing)
    if target_email:
        try:
            # Some deployments mirror by email as doc id — attempt without failing
            for doc in db.collection(settings.FIREBASE_COLLECTION_USERS).where("email", "==", target_email).limit(1).stream():
                try:
                    doc.reference.delete()
                except Exception:
                    pass
        except Exception:
            pass

    ip, request_id = request_context(request)
    log_audit(
        action="USER_DELETED",
        user=user.get("email"),
        tenant_id=target_tenant or None,
        target_type="user",
        target_id=target_uid,
        ip=ip,
        request_id=request_id,
        metadata={
            "target_email": target_email,
            "target_uid": target_uid,
            "target_tenant_id": target_tenant,
            "by_uid": user.get("uid"),
            "by_role": user.get("role"),
        },
    )
    logger.info(f"USER_DELETED audit: {target_email} ({target_uid}) by {user.get('email')}")
    # Explicit confirmation flags expected by frontend: success:true + deleted:true + uid/email
    return {
        "success": True,
        "deleted": True,
        "uid": target_uid,
        "email": target_email,
        "tenant_id": target_tenant,
        "deleted_user": {"uid": target_uid, "email": target_email, "tenant_id": target_tenant},
        # Back-compat: keep deleted as object for older clients that expect it
        "deleted_obj": {"uid": target_uid, "email": target_email, "tenant_id": target_tenant},
    }


@router.post("/users/delete", status_code=status.HTTP_200_OK)
async def admin_delete_user_post(
    req: UserDeleteRequest,
    request: Request,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """POST alias for DELETE /api/v1/admin/users — supports setups where DELETE with body is blocked.

    Uses Pydantic body (reliable for POST) and mirrors DELETE logic exactly,
    including explicit non-2xx errors and audit logging.
    """
    _verify_admin_setup(req.setup_key)
    email = (req.email or "").strip()
    uid = (req.uid or "").strip()
    if not email and not uid:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Provide email or uid of user to delete")
    auth = get_auth()
    db = get_db()
    target_email = email
    target_uid = uid
    target_tenant = req.tenant_id or ""
    try:
        if target_uid and not target_email:
            rec = auth.get_user(target_uid)
            target_email = getattr(rec, "email", "") or target_email
            claims = getattr(rec, "custom_claims", {}) or {}
            if isinstance(claims, dict):
                target_tenant = target_tenant or claims.get("tenant_id") or ""
        elif target_email:
            rec = auth.get_user_by_email(target_email)
            target_uid = getattr(rec, "uid", "") or target_uid
            target_email = getattr(rec, "email", "") or target_email
            claims = getattr(rec, "custom_claims", {}) or {}
            if isinstance(claims, dict):
                target_tenant = target_tenant or claims.get("tenant_id") or ""
            if req.uid and req.uid != target_uid:
                logger.warning(f"UID mismatch for {target_email}: supplied {req.uid} vs resolved {target_uid}")
    except Exception as e:
        msg = str(e).lower()
        if "not found" in msg or "no user" in msg or "does not exist" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User not found: {email or uid}")
        logger.error(f"Failed to resolve user {email or uid}: {e}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not resolve user at this time.")
    if (target_email or "").strip().lower() in {e.lower() for e in SUPER_ADMIN_PROTECTED_EMAILS}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Protected account cannot be deleted: {target_email}")
    if (target_email and target_email.lower() == (user.get("email") or "").lower()) or (target_uid and target_uid == user.get("uid")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Self-deletion is not allowed")
    try:
        auth.delete_user(target_uid)
        logger.info(f"Auth user deleted: {target_email} ({target_uid}) by {user.get('email')}")
    except Exception as e:
        msg = str(e).lower()
        if "not found" in msg or "does not exist" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User not found: {target_email or target_uid}")
        logger.error(f"Failed to delete Auth user {target_email} ({target_uid}): {e}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not delete user at this time.")
    try:
        db.collection(settings.FIREBASE_COLLECTION_USERS).document(target_uid).delete()
    except Exception as e:
        logger.warning(f"Firestore user doc delete failed for {target_uid}: {e}")
    if target_email:
        try:
            for doc in db.collection(settings.FIREBASE_COLLECTION_USERS).where("email", "==", target_email).limit(1).stream():
                try:
                    doc.reference.delete()
                except Exception:
                    pass
        except Exception:
            pass
    ip, request_id = request_context(request)
    log_audit(
        action="USER_DELETED",
        user=user.get("email"),
        tenant_id=target_tenant or None,
        target_type="user",
        target_id=target_uid,
        ip=ip,
        request_id=request_id,
        metadata={"target_email": target_email, "target_uid": target_uid, "target_tenant_id": target_tenant, "by_uid": user.get("uid"), "by_role": user.get("role")},
    )
    logger.info(f"USER_DELETED audit: {target_email} ({target_uid}) by {user.get('email')}")
    return {
        "success": True,
        "deleted": True,
        "uid": target_uid,
        "email": target_email,
        "tenant_id": target_tenant,
        "deleted_user": {"uid": target_uid, "email": target_email, "tenant_id": target_tenant},
        "deleted_obj": {"uid": target_uid, "email": target_email, "tenant_id": target_tenant},
    }
