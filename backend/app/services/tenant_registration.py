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

# Blocklist of disposable / temporary email providers. Registrations using
# these domains are rejected outright — self-service accounts must use a real
# corporate / organizational mailbox. The list is intentionally modest but
# covers the best-known throwaway providers; subdomains (e.g.
# mailinator.com aliases) are matched via a suffix check.
DISPOSABLE_EMAIL_DOMAINS = frozenset({
    "mailinator.com",
    "tempmail.com",
    "tempmail.net",
    "temp-mail.org",
    "temp-mail.io",
    "guerrillamail.com",
    "guerrillamail.net",
    "guerrillamail.org",
    "guerrillamail.biz",
    "guerrillamail.info",
    "grr.la",
    "10minutemail.com",
    "10minutemail.net",
    "yopmail.com",
    "yopmail.fr",
    "yopmail.net",
    "yopmail.org",
    "throwawaymail.com",
    "throwaway.email",
    "maildrop.cc",
    "getnada.com",
    "33mail.com",
    "trashmail.com",
    "mailnesia.com",
    "spamgourmet.com",
    "disposablemail.com",
    "mailtemp.net",
})

# Admin / developer email allowlist. These addresses bypass the corporate-email
# restriction (disposable AND consumer webmail domains) completely so the owner
# and any listed personal test addresses can self-register a tenant even when
# their mailbox uses a consumer provider.
ADMIN_EMAIL_ALLOWLIST = frozenset({
    "ghanshyamacharya@outlook.com",
    # Add any additional personal test addresses if needed
})

# Consumer webmail providers. Self-service registration targets corporate /
# organizational mailboxes, so these domains (and their subdomains) are treated
# as non-corporate and rejected unless the address is on ADMIN_EMAIL_ALLOWLIST.
CONSUMER_WEBMAIL_DOMAINS = frozenset({
    "gmail.com", "googlemail.com",
    "yahoo.com", "yahoo.co.uk", "ymail.com",
    "outlook.com", "hotmail.com", "live.com", "msn.com",
    "icloud.com", "me.com", "mac.com",
    "aol.com",
    "protonmail.com", "proton.me",
    "zoho.com",
    "mail.com", "gmx.com", "gmx.net",
})

# User-facing rejection message (mirrored in the frontend validation).
DISPOSABLE_EMAIL_MESSAGE = "Please provide a valid corporate or organizational email address."


class DisposableEmailError(ValueError):
    """Raised when a registration uses a disposable / temporary email domain.

    Subclasses ValueError so it can share the route-layer validation flow, but
    the auth routes map it to a 400 (not the generic 422) per the anti-spam
    contract. Catch it BEFORE the broad ValueError clause.
    """


def email_domain(email: str) -> str:
    """Return the lower-cased domain portion of an email address."""
    addr = str(email or "").strip().lower()
    return addr.rsplit("@", 1)[1] if "@" in addr else addr


def is_disposable_email(email: str) -> bool:
    """True when the email domain (or a subdomain of it) is on the blocklist."""
    domain = email_domain(email)
    if not domain:
        return False
    if domain in DISPOSABLE_EMAIL_DOMAINS:
        return True
    for blocked in DISPOSABLE_EMAIL_DOMAINS:
        if domain.endswith("." + blocked):
            return True
    return False


def is_admin_allowlisted(email: str) -> bool:
    """True when the email is on the admin/dev allowlist (bypasses the
    corporate-email restriction entirely)."""
    return str(email or "").strip().lower() in ADMIN_EMAIL_ALLOWLIST


def is_consumer_webmail(email: str) -> bool:
    """True when the email uses a consumer webmail provider (or a subdomain of
    one) rather than a corporate / organizational mailbox."""
    domain = email_domain(email)
    if not domain:
        return False
    if domain in CONSUMER_WEBMAIL_DOMAINS:
        return True
    for blocked in CONSUMER_WEBMAIL_DOMAINS:
        if domain.endswith("." + blocked):
            return True
    return False


def validate_corporate_email(email: str) -> None:
    """Reject disposable / consumer-webmail domains on self-service
    registration, unless the address is on the admin/dev allowlist."""
    if is_admin_allowlisted(email):
        return
    if is_disposable_email(email) or is_consumer_webmail(email):
        raise DisposableEmailError(DISPOSABLE_EMAIL_MESSAGE)


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


class DuplicateEmailError(ValueError):
    """Raised when the joining/registering email already exists in Firebase Auth."""


def _validate_password(password: str) -> None:
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one digit")


def _create_user(auth: Any, *, email: str, password: str, display_name: str) -> Any:
    """Create a Firebase Auth user, surfacing duplicate emails as an error."""
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
            raise DuplicateEmailError("An account with this email address already exists")
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
    validate_corporate_email(email)

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

    is_beta_env = (settings.ENVIRONMENT or "").strip().lower() in ("beta", "staging", "development")
    provided_key = (beta_access_key or "").strip()
    if is_beta_env:
        # Beta sandbox: the access key is optional; a provided key must match.
        if provided_key and provided_key != settings.BETA_ACCESS_KEY:
            raise PermissionError("Invalid beta access key")
    else:
        # Production gate: self-service registration is by invitation only — a
        # valid enterprise access code (admin-issued invite key) is mandatory.
        # Without it the public form can never provision a tenant.
        if provided_key != settings.BETA_ACCESS_KEY:
            raise PermissionError(
                "Invalid or missing beta access key. Self-service registration on the "
                "production portal is by invitation only — enter the enterprise access "
                "code provided by AviaSAFE, or contact info@aviasafesystems.com to "
                "request access."
            )

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
    sandbox_tags = {}
    if is_beta_env:
        # Beta sandbox marker: self-service tenants created on the beta portal
        # are flagged for periodic cleanup / evaluation.
        sandbox_tags = {"is_beta_sandbox": True, "auto_expire_days": 30}
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
            **sandbox_tags,
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


def verify_invite(db: Any, code: Optional[str]) -> Dict[str, Any]:
    """Real-time invite-code verification for /join.html.

    Resolves the tenant by invite code and confirms it is active. Accepts both
    legacy tenant-level team invite codes and admin-issued department-scoped
    invites (returning the assigned department + role). Returns a minimal
    public payload (no internal fields). Raises:
      ValueError  -> caller supplied no / blank code
      LookupError -> code unknown, or tenant is inactive/expired
    """
    if not code or not code.strip():
        raise ValueError("An invite code is required")

    from app.services.invites import resolve_invite, department_label

    raw = code.strip()
    invite = resolve_invite(db, raw)
    if invite:
        tid = invite.get("tenant_id")
        if not tid:
            raise LookupError("Invalid or expired invite code")
        tid, tenant_doc = resolve_tenant(db, None, tid)
        active = tenant_doc.get("active")
        status = str(tenant_doc.get("status") or "").lower()
        if active is False or status == "inactive":
            raise LookupError("Invalid or expired invite code")
        dept = invite.get("department")
        return {
            "valid": True,
            "organization_name": tenant_doc.get("name") or tid,
            "tenant_id": tid,
            "category": tenant_doc.get("tenant_type") or tenant_doc.get("classification"),
            "department": dept,
            "department_label": department_label(dept),
            "role": invite.get("role", settings.ROLE_DEFAULT),
        }

    tid, tenant_doc = resolve_tenant(db, raw, None)

    active = tenant_doc.get("active")
    status = str(tenant_doc.get("status") or "").lower()
    if active is False or status == "inactive":
        raise LookupError("Invalid or expired invite code")

    return {
        "valid": True,
        "organization_name": tenant_doc.get("name") or tid,
        "tenant_id": tid,
        "category": tenant_doc.get("tenant_type") or tenant_doc.get("classification"),
    }


def join_team(
    *,
    invite_code: Optional[str] = None,
    tenant_id: Optional[str] = None,
    full_name: str,
    email: str,
    password: str,
    department: str,
    operational_role: Optional[str] = None,
    request=None,
) -> Dict[str, Any]:
    """Self-register a department postholder under an existing tenant.

    Invitees are provisioned with the least-privilege 'USER' tier scoped to the
    tenant_id — they can never self-elevate to AIRLINE_ADMIN / tenant_admin;
    that requires a Safety Manager action in the admin console.
    """
    _validate_password(password)
    validate_corporate_email(email)

    db = get_db()
    auth = get_auth()
    now = datetime.now(timezone.utc)

    # Admin-issued department-scoped invites bind BOTH the department and the
    # role directly from the invite document. Legacy tenant-level invite codes
    # fall back to the previous behavior (invitee self-selects the department
    # and is provisioned with the least-privilege role).
    from app.services.invites import resolve_invite, department_label

    assigned_role = settings.ROLE_DEFAULT
    department_code: Optional[str] = None

    if invite_code and invite_code.strip():
        invite = resolve_invite(db, invite_code.strip())
        if invite:
            if str(invite.get("status") or "ACTIVE").strip().upper() != "ACTIVE":
                raise LookupError("Invalid or expired invite code")
            tid = invite.get("tenant_id")
            if not tid:
                raise LookupError("Invalid or expired invite code")
            try:
                tid, tenant_doc = resolve_tenant(db, None, tid)
            except LookupError:
                raise
            department_code = invite.get("department") or department.strip()
            assigned_role = str(invite.get("role") or settings.ROLE_DEFAULT).upper()

    if department_code is None:
        try:
            tid, tenant_doc = resolve_tenant(db, invite_code, tenant_id)
        except LookupError:
            raise
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise LookupError(str(e))
        department_code = department.strip()

    code = department_code
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
        {"role": assigned_role, "tenant_id": tid, "department": label},
    )

    user_doc = {
        "uid": user.uid,
        "email": email,
        "display_name": full_name,
        "role": assigned_role,
        "tenant_id": tid,
        "department": label,
        "status": "ACTIVE",
        "created_at": now,
        "updated_at": now,
    }
    if operational_role:
        user_doc["operational_role"] = operational_role.strip()[:100]
    upsert_user_doc(user.uid, user_doc)

    ip, request_id = request_context(request)
    log_audit(
        action="TEAM_MEMBER_JOINED",
        user=email,
        tenant_id=tid,
        target_type="tenant",
        target_id=tid,
        ip=ip,
        request_id=request_id,
        metadata={
            "department": code,
            "department_label": label,
            "role": assigned_role,
            "invite_scoped": department_code is not None,
        },
    )

    logger.info(
        f"Team member joined tenant {tid}: {email} -> {label} ({assigned_role})"
    )

    return {
        "tenant_id": tid,
        "tenant_name": tenant_doc.get("name") or tid,
        "classification": tenant_doc.get("tenant_type") or tenant_doc.get("classification"),
        "department": code,
        "department_label": label,
        "role": assigned_role,
        "admin_email": email,
        "created_at": now,
    }