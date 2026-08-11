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
from app.middleware.auth import get_safety_manager, get_admin_user
from app.services.risk_matrix import (
    get_risk_matrix_config,
    set_risk_matrix_config,
    THRESHOLDS_DEFAULT,
)
from app.services.users import upsert_user_doc, user_doc_from_auth_record

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
    """Create seed users in Firebase Auth (skips users that already exist)."""
    if settings.DISABLE_DESTRUCTIVE_ENDPOINTS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint disabled")
    _verify_admin_setup(req.setup_key)
    from seed.users import create_all_users
    try:
        created = create_all_users(get_auth())
        return {"success": True, "created": len(created), "users": created}
    except Exception as e:
        logger.error(f"Create seed users failed: {e}")
        return {"success": False, "error": str(e)}


@router.post("/seed-demo-data", status_code=status.HTTP_200_OK)
async def seed_demo_data(
    req: AdminSetupRequest,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Run the demo data seeder against production Firestore."""
    if settings.DISABLE_DESTRUCTIVE_ENDPOINTS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint disabled")
    _verify_admin_setup(req.setup_key)
    from seed.runner import run
    try:
        result = run(db=get_db(), auth=get_auth(), force=True)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Seed failed: {e}")
        return {"success": False, "error": str(e)}


# ============================================================================
# Super-Admin web seeding panel (production-setup.html)
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


class SeedDeployRequest(BaseModel):
    setup_key: str
    force: bool = False


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
    """List every State Regulator (SUPER_ADMIN)."""
    from app.services.production_seed import list_regulators_admin
    return {"success": True, "regulators": list_regulators_admin()}


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
    """List all operator tenants with per-subcollection counts (SUPER_ADMIN)."""
    from app.services.production_seed import list_tenants_admin
    return {"success": True, "tenants": list_tenants_admin()}


@router.get("/seed/preview", status_code=status.HTTP_200_OK)
async def admin_seed_preview(
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Preview the CAAN demo seed plan against the current database (SUPER_ADMIN)."""
    from app.services.production_seed import preview_seed
    try:
        plan = preview_seed(actor=user)
        return {"success": True, **plan}
    except Exception as e:
        logger.error(f"Seed preview failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/seed/deploy", status_code=status.HTTP_200_OK)
async def admin_seed_deploy(
    req: SeedDeployRequest,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Deploy the CAAN demo seed plan (SUPER_ADMIN + setup key).

    Writes the regulator, tags the operator tenants, and seeds surveys +
    hazards + reports. Runs against the backend's configured database
    (beta -> sms-db-beta, production -> sms-db).
    """
    _verify_admin_setup(req.setup_key)
    from app.services import production_seed
    try:
        result = production_seed.deploy_seed(force=req.force, actor=user)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Seed deploy failed: {e}")
        production_seed._audit("SEED_DEPLOY", user, "caan", f"Deploy failed: {str(e)}", result="error")
        raise HTTPException(status_code=500, detail=str(e))


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
# Tenant lifecycle status + demo-data seeding (production-setup.html)
# ============================================================================

class TenantStatusRequest(BaseModel):
    setup_key: str
    status: Optional[str] = None
    contract_start_date: Optional[str] = None
    contract_end_date: Optional[str] = None
    payment_status: Optional[str] = None


class DemoDataRequest(BaseModel):
    setup_key: str
    action: str = "seed"
    all: bool = True
    tenant_ids: Optional[List[str]] = None
    kinds: List[str] = ["vsr", "mor", "can", "cap"]


@router.post("/tenants/{tenant_id}/status", status_code=status.HTTP_200_OK)
async def admin_update_tenant_status(
    tenant_id: str,
    req: TenantStatusRequest,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Update a tenant's lifecycle status (Trial/Active/Inactive).

    `status` may be set explicitly or derived from the contract dates and
    payment status. Requires a SUPER_ADMIN token + admin setup key.
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


@router.post("/demo-data", status_code=status.HTTP_200_OK)
async def admin_demo_data(
    req: DemoDataRequest,
    user: Dict[str, Any] = Depends(get_admin_user),
):
    """Seed or unseed dummy operational data (VSR/MOR/CAN/CAP).

    Targets one tenant (tenant_ids) or every tenant (all=True). Unseed only
    removes documents created by this seeder (marked admin-demo-1).
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

    fn = seed_tenant_demo_data if req.action == "seed" else unseed_tenant_demo_data
    results = []
    for tid in tenant_ids:
        try:
            results.append(fn(tid, req.kinds, user))
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
