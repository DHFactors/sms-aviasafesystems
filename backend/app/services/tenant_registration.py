# ============================================================================
# FILE: tenant_registration.py
# PATH: backend/app/services/tenant_registration.py
# PURPOSE: Self-service tenant registration + team-member onboarding for the
#          beta portal (betasms.aviasafesystems.com).
#
#   register_tenant():   creates a slugified tenant_id, provisions the primary
#                        administrator (AIRLINE_ADMIN / safety), initialises the
#                        operational profile under tenants/{tid}/profile/operational
#                        and issues a unique 6-char team invite code.
#   join_team():         self-registers a department postholder under an existing
#                        tenant via its invite code (or a ?tenant= tenant id).
#   resolve_tenant():    public lookup used by /join.html to render the dynamic
#                        department dropdown (and by /join-team).
#
# Errors are raised as exceptions for the route layer to map to HTTP statuses:
#   PermissionError -> 403   (beta access key mismatch)
#   ValueError      -> 422   (validation failures)
#   LookupError     -> 404   (unknown tenant / invite code)
#   RuntimeError    -> 500   (persistence failures)
# ============================================================================

import re
import secrets
import string
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from loguru import logger
from firebase_admin import auth as firebase_auth

from app.core.config import settings
from app.firebase import get_db, get_auth
from app.models.tenant_profile import OperationalScope
from app.services.audit_service import log_audit, request_context
from app.services.users import upsert_user_doc

# Classifications a self-registering organization may select. Regulators and
# ground-handling providers are not exposed on the public form.
REGISTRATION_SCOPES = (
    OperationalScope.AIRLINE_FIXED_WING,
    OperationalScope.AIRLINE_ROTARY,
    OperationalScope.AMO,
    OperationalScope.AERODROME,
)

# Human-readable operational category labels for the operational profile.
CATEGORY_LABELS = {
    OperationalScope.AIRLINE_FIXED_WING: "Fixed-Wing Airline",
    OperationalScope.AIRLINE_ROTARY: "Rotary-Wing / Helicopter Operator",
    OperationalScope.AMO: "Part-145 Maintenance Organization",
    OperationalScope.AERODROME: "Certified Airport / Aerodrome",
    OperationalScope.GROUND_HANDLING: "Ground Handling Services",
    OperationalScope.REGULATOR: "CAAN Directorates",
}

# Department code -> display label + the custom claim value assigned to a
# joining postholder. Labels align with the values the frontend already
# understands (getDepartmentLabel / getRoleDestination in public/js/firebase.js).
DEPARTMENT_LABELS = {
    "safety": "Safety",
    "flight_ops": "Flight Operations",
    "camo": "CAMO",
    "maintenance_145": "Part-145",
    "qa": "QA",
    "airside_ops": "Airside Operations",
    "arff": "ARFF (Rescue & Firefighting)",
    "ground_ops": "Ground Operations",
}

MIN_PASSWORD_LENGTH = 8

# Unambiguous 6-char alphabet for team invite codes (no 0/O or 1/I).
INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
INVITE_CODE_LENGTH = 6

_NON_SLUG_CHARS = re.compile(r"[^a-z0-9]+")
_REPEATED_HYPHENS = re.compile(r"-{2,}")


def slugify_organization(name: str) -> str:
    """Turn an organization name into a clean lowercase tenant slug."""
    slug = _NON_SLUG_CHARS.sub("-", str(name or "").strip().lower())
    slug = _REPEATED_HYPHENS.sub("-", slug).strip("-")
    return slug or "organization"


def _invite_code_taken(db: Any, code: str) -> bool:
    try:
        docs = (
            db.collection(settings.FIREBASE_COLLECTION_TENANTS)
            .where("team_invite_code", "==", code)
            .limit(1)
            .get()
        )
        return len(docs) > 0
    except Exception as e:
        logger.warning(f"Invite-code uniqueness check failed: {e}")
        return False


def generate_invite_code(db: Any) -> str:
    """Return a unique 6-character alphanumeric team invite code."""
    for _ in range(25):
        code = "".join(secrets.choice(INVITE_ALPHABET) for _ in range(INVITE_CODE_LENGTH))
        if not _invite_code_taken(db, code):
            return code
    raise RuntimeError("Unable to generate a unique team invite code")


def _unique_tenant_id(db: Any, organization_name: str) -> str:
    """Slugify the organization name and guarantee Firestore-document uniqueness."""
    base = slugify_organization(organization_name)
    candidate = base
    suffix = 2
    while True:
        ref = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(candidate)
        try:
            exists = ref.get().exists
        except Exception as e:
            logger.warning(f"Tenant-id existence check failed for {candidate}: {e}")
            exists = False
        if not exists:
            return candidate
        candidate = f"{base}-{suffix}"
        suffix += 1
        if suffix > 1000:  # pragma: no cover - defensive only
            raise RuntimeError("Unable to allocate a unique tenant id")


def _validate_password(password: str) -> None:
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")


def _create_user(auth: Any, *, email: str, password: str, display_name: str) -> Any:
    """Create a Firebase Auth user, surfacing duplicate emails as a ValueError."""
    try:
        return auth.create_user(
            email=email,
            password=password,
            display_name=display_name,
            email_verified=False,
        )
    except Exception as e:
        duplicate = isinstance(e, firebase_auth.EmailAlreadyExistsError) or (
            "email already" in str(e).lower() or "already in use" in str(e).lower()
        )
        if duplicate:
            raise ValueError("An account with this email already exists")
        raise RuntimeError(str(e))


def register_tenant(
    *,
    organization_name: str,
    classification: str,
    admin_full_name: str,
    admin_title: str,
    email: str,
    password: str,
    beta_access_key: Optional[str] = None,
    request=None,
) -> Dict[str, Any]:
    """Provision a brand-new self-service tenant + primary administrator."""
    _validate_password(password)

    try:
        scope = OperationalScope(classification)
    except ValueError:
        raise ValueError(
            "classification must be one of: "
            + ", ".join(s.value for s in REGISTRATION_SCOPES)
        )
    if scope not in REGISTRATION_SCOPES:
        raise ValueError(
            "classification must be one of: "
            + ", ".join(s.value for s in REGISTRATION_SCOPES)
        )

    provided_key = (beta_access_key or "").strip()
    if provided_key and provided_key != settings.BETA_ACCESS_KEY:
        raise PermissionError("Invalid beta access key")

    db = get_db()
    auth = get_auth()
    now = datetime.now(timezone.utc)
    tid = _unique_tenant_id(db, organization_name)

    user = _create_user(
        auth,
        email=email,
        password=password,
        display_name=admin_full_name,
    )
    auth.set_custom_user_claims(
        user.uid,
        {"role": "AIRLINE_ADMIN", "tenant_id": tid, "department": "safety"},
    )

    operates_flights = scope.operates_flights
    applicable_departments = list(scope.departments)
    invite_code = generate_invite_code(db)

    tenant_ref = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tid)
    tenant_ref.set(
        {
            "tenant_id": tid,
            "name": organization_name,
            "tenant_type": scope.value,
            "classification": scope.value,
            "operates_flights": operates_flights,
            "applicable_departments": applicable_departments,
            "team_invite_code": invite_code,
            "active": True,
            "status": "Active",
            "safety_manager": {
                "email": email,
                "name": admin_full_name,
                "title": admin_title,
                "uid": user.uid,
            },
            "config": {"survey_rate_limit": settings.SURVEY_RATE_LIMIT},
            "created_at": now,
            "updated_at": now,
        }
    )

    tenant_ref.collection("profile").document("operational").set(
        {
            "tenant_id": tid,
            "slug": tid,
            "tenant_name": organization_name,
            "email": email,
            "category": CATEGORY_LABELS.get(scope, scope.value),
            "scope": scope.value,
            "tenant_type": scope.value,
            "operates_flights": operates_flights,
            "applicable_departments": applicable_departments,
            "created_at": now,
        }
    )

    upsert_user_doc(
        user.uid,
        {
            "uid": user.uid,
            "email": email,
            "display_name": admin_full_name,
            "role": "AIRLINE_ADMIN",
            "tenant_id": tid,
            "department": "safety",
            "created_at": now,
            "updated_at": now,
        },
    )

    ip, request_id = request_context(request)
    log_audit(
        action="TENANT_REGISTERED",
        user=email,
        tenant_id=tid,
        target_type="tenant",
        target_id=tid,
        ip=ip,
        request_id=request_id,
        metadata={
            "tenant_name": organization_name,
            "classification": scope.value,
            "operates_flights": operates_flights,
        },
    )

    logger.info(
        f"Self-service tenant registered: {organization_name} -> {tid} "
        f"({scope.value}) admin={email}"
    )

    return {
        "tenant_id": tid,
        "tenant_name": organization_name,
        "classification": scope.value,
        "operates_flights": operates_flights,
        "applicable_departments": applicable_departments,
        "team_invite_code": invite_code,
        "admin_email": email,
        "created_at": now,
    }


def resolve_tenant(
    db: Any,
    invite_code: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Locate a tenant doc by invite code or tenant id.

    Returns (tenant_id, tenant_doc). Raises LookupError when not found and
    ValueError when neither locator was supplied.
    """
    if tenant_id:
        tid = tenant_id.strip()
        snap = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tid).get()
        if not snap.exists:
            raise LookupError(f"Unknown tenant: {tid}")
        data = snap.to_dict() or {}
        if invite_code and invite_code.strip().upper() != str(data.get("team_invite_code") or "").upper():
            raise LookupError(f"Invite code does not match tenant {tid}")
        return tid, data

    if invite_code:
        code = invite_code.strip().upper()
        docs = (
            db.collection(settings.FIREBASE_COLLECTION_TENANTS)
            .where("team_invite_code", "==", code)
            .limit(1)
            .get()
        )
        for snap in docs:
            return snap.id, snap.to_dict() or {}
        raise LookupError(f"No tenant matches invite code: {code}")

    raise ValueError("An invite code or tenant id is required")


def join_team(
    *,
    invite_code: Optional[str] = None,
    tenant_id: Optional[str] = None,
    full_name: str,
    email: str,
    password: str,
    department: str,
    request=None,
) -> Dict[str, Any]:
    """Self-register a department postholder under an existing tenant."""
    _validate_password(password)

    db = get_db()
    auth = get_auth()
    now = datetime.now(timezone.utc)

    try:
        tid, tenant_doc = resolve_tenant(db, invite_code, tenant_id)
    except LookupError:
        raise
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise LookupError(str(e))

    code = department.strip()
    allowed = tenant_doc.get("applicable_departments") or []
    if code not in allowed:
        raise ValueError(
            f"Department '{code}' is not applicable to tenant {tid}. "
            f"Allowed: {', '.join(allowed) or 'none'}"
        )

    label = DEPARTMENT_LABELS.get(code, code)

    user = _create_user(
        auth,
        email=email,
        password=password,
        display_name=full_name,
    )
    auth.set_custom_user_claims(
        user.uid,
        {"role": "USER", "tenant_id": tid, "department": label},
    )

    upsert_user_doc(
        user.uid,
        {
            "uid": user.uid,
            "email": email,
            "display_name": full_name,
            "role": "USER",
            "tenant_id": tid,
            "department": label,
            "created_at": now,
            "updated_at": now,
        },
    )

    ip, request_id = request_context(request)
    log_audit(
        action="TEAM_MEMBER_JOINED",
        user=email,
        tenant_id=tid,
        target_type="tenant",
        target_id=tid,
        ip=ip,
        request_id=request_id,
        metadata={"department": code, "department_label": label},
    )

    logger.info(f"Team member joined tenant {tid}: {email} -> {label}")

    return {
        "tenant_id": tid,
        "tenant_name": tenant_doc.get("name") or tid,
        "classification": tenant_doc.get("tenant_type") or tenant_doc.get("classification"),
        "department": code,
        "department_label": label,
        "admin_email": email,
        "created_at": now,
    }