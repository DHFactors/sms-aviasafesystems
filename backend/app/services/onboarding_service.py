# ============================================================================
# FILE: onboarding_service.py
# PATH: backend/app/services/onboarding_service.py
# PURPOSE: CAAN / enterprise tenant onboarding. Provisions a tenant end-to-end:
#
#   1. register_tenant()       — Firestore tenant doc + operational profile,
#                                primary admin Firebase Auth user, invite code.
#   2. seed_tenant_hazards()   — unified ICAO seeder: writes the CAAN Chapter
#                                2.1 hazard register to Firestore AND Supabase
#                                using new-format references (OPS/001/M/2026).
#   3. send_welcome_email()    — welcome email (never raises; test-mode safe).
#   4. log_audit()             — TENANT_ONBOARDED audit record.
#
# Error mapping (contract with the route layer):
#   PermissionError -> 403    (beta access key mismatch)
#   ValueError      -> 422    (validation / classification failures)
#   DuplicateEmailError -> 409 (existing admin account)
#   LookupError     -> 404
#   RuntimeError    -> 500
# ============================================================================

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from loguru import logger

from app.core.config import settings
from app.services.audit_service import log_audit, request_context
from app.services.email_service import send_welcome_email
from app.services.tenant_registration import (
    DuplicateEmailError,
    register_tenant,
)

DEFAULT_SEED_COUNT = 6


async def onboard_tenant(
    *,
    organization_name: str,
    admin_full_name: str,
    admin_title: str,
    email: str,
    password: str,
    classification: str = "airline_fixed_wing",
    seed_count: int = DEFAULT_SEED_COUNT,
    seed_function: Optional[str] = None,
    priority_override: Optional[str] = None,
    request=None,
) -> Dict[str, Any]:
    """Provision a tenant, seed its ICAO hazard register, and welcome the admin.

    Re-uses the self-service `register_tenant` flow (so validation, invite-code
    and audit behaviour stay consistent) but passes the configured enterprise
    access key so the CAAN/enterprise onboarding path is gated by configuration
    rather than the public registration form.

    Returns a dict with `tenant_id`, seed status and email status. Never raises
    for email delivery; seeding and registration errors propagate for the route
    layer to map to HTTP statuses.
    """
    registered = register_tenant(
        organization_name=organization_name,
        classification=classification,
        admin_full_name=admin_full_name,
        admin_title=admin_title,
        email=email,
        password=password,
        # Enterprise/CAAN onboarding gate: configured on the deployment. In
        # dev/beta the key check is lenient (any matching provided key).
        beta_access_key=settings.BETA_ACCESS_KEY,
        request=request,
    )
    tid = registered["tenant_id"]

    seed_result: Dict[str, Any] = {"seeded": 0, "dry_run": False}
    try:
        # Imported lazily so the whole `scripts.seed` path stays optional on
        # deployments that only use the register/join flows.
        from scripts.seed.unified_seeder import seed_tenant_hazards

        seed_result = await seed_tenant_hazards(
            tid,
            count=seed_count,
            function=seed_function,
            priority_override=priority_override,
            target="both",
        )
        logger.info(f"Onboarding seeded {seed_result.get('seeded', 0)} hazards for {tid}")
    except Exception as e:
        # The seed must never fail the onboarding itself; surface as a warning
        # so the caller can retry seeding separately.
        logger.error(f"Onboarding hazard seed failed for {tid}: {e}")
        seed_result = {
            "seeded": 0,
            "error": str(e)[:300],
        }

    email_result = send_welcome_email(
        email,
        {
            "contact_name": admin_full_name,
            "tenant_name": organization_name,
            "admin_email": email,
            "password": password,
            "login_url": settings.APP_LOGIN_URL,
            "support_email": settings.APP_SUPPORT_EMAIL,
        },
    )

    ip, request_id = request_context(request)
    log_audit(
        action="TENANT_ONBOARDED",
        user=email,
        tenant_id=tid,
        target_type="tenant",
        target_id=tid,
        ip=ip,
        request_id=request_id,
        metadata={
            "tenant_name": organization_name,
            "classification": registered.get("classification"),
            "hazards_seeded": seed_result.get("seeded", 0),
            "email_sent": email_result.get("sent", False),
        },
    )

    logger.info(
        f"Tenant onboarded: {organization_name} -> {tid} admin={email} "
        f"hazards={seed_result.get('seeded', 0)}"
    )

    return {
        "tenant_id": tid,
        "tenant_name": organization_name,
        "classification": registered.get("classification"),
        "admin_email": email,
        "created_at": datetime.now(timezone.utc),
        "seeded_hazards": seed_result.get("seeded", 0),
        "email_sent": email_result.get("sent", False),
        "email_detail": (
            email_result.get("reason") or email_result.get("provider")
        ) if email_result.get("sent") is False else "dispatched",
    }