# ============================================================================
# FILE: invites.py
# PATH: backend/app/services/invites.py
# PURPOSE: Department-scoped team invites for the delegated admin hierarchy.
#
#   create_invite():   authenticated admin issues a department-scoped invite
#                      document keyed by its 6-char code in the top-level
#                      `invites` collection. RBAC:
#                        - TENANT_ADMIN / AIRLINE_ADMIN / SUPER_ADMIN may invite
#                          into ANY applicable department with roles
#                          DEPT_ADMIN / SAFETY_OFFICER / STAFF.
#                        - DEPT_ADMIN may only invite STAFF into their OWN
#                          department (cross-department or privilege escalation
#                          is rejected with PermissionError -> 403).
#   resolve_invite():  lookup an invite document by code (used by the public
#                      join flow to bind department + role).
#   list_invites():    tenant-scoped invite listing for the team page.
#
# Errors are raised as exceptions for the route layer to map to HTTP statuses:
#   PermissionError -> 403   (RBAC violation / privilege escalation)
#   ValueError      -> 422   (invalid department / role payload)
#   LookupError     -> 404   (unknown tenant)
#   RuntimeError    -> 500   (persistence failures)
# ============================================================================

import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

from app.core.config import settings
from app.firebase import get_db
from app.services.audit_service import log_audit, request_context
from app.services.tenant_registration import (
    DEPARTMENT_LABELS,
    INVITE_ALPHABET,
    INVITE_CODE_LENGTH,
)

# Canonical roles + assignable-role matrix for the delegated admin hierarchy.
ROLE_TENANT_ADMIN = settings.ROLE_TENANT_ADMIN
ROLE_DEPT_ADMIN = settings.ROLE_DEPT_ADMIN
ROLE_SAFETY_OFFICER = settings.ROLE_SAFETY_OFFICER
ROLE_STAFF = settings.ROLE_STAFF

# Roles a tenant admin (or SUPER_ADMIN) may assign via invite.
TENANT_ADMIN_ASSIGNABLE_ROLES = frozenset(
    {ROLE_DEPT_ADMIN, ROLE_SAFETY_OFFICER, ROLE_STAFF}
)
# Roles a department admin (HOD) may assign via invite.
DEPT_ADMIN_ASSIGNABLE_ROLES = frozenset({ROLE_STAFF})

# Roles that may issue invites at all.
INVITER_ROLES = frozenset(
    {"SUPER_ADMIN"} | set(settings.TENANT_ADMIN_ROLES) | set(settings.DEPT_ADMIN_ROLES)
)

# Human-readable role labels for the team-management UI.
ROLE_LABELS = {
    "SUPER_ADMIN": "Global Administrator",
    "TENANT_ADMIN": "Safety Manager (Tenant Admin)",
    "AIRLINE_ADMIN": "Safety Manager (Tenant Admin)",
    "DEPT_ADMIN": "Department Admin (HOD)",
    "SAFETY_OFFICER": "Safety Officer",
    "STAFF": "Staff / Employee",
    "USER": "Staff / Employee",
    "CAAN_SMD": "State Safety Regulator",
}


def department_label(code_or_label: str) -> str:
    """Return the canonical display label for a department code or label."""
    return DEPARTMENT_LABELS.get((code_or_label or "").strip(), code_or_label or "")


def department_to_code(value: Optional[str]) -> str:
    """Normalize a department code or display label to its canonical code."""
    v = (value or "").strip().lower()
    for code, label in DEPARTMENT_LABELS.items():
        if v == code.lower() or v == label.lower():
            return code
    return v or ""


def _invite_code_taken(db: Any, code: str) -> bool:
    """True when the code is already used by a tenant's team invite or an
    admin-issued department-scoped invite."""
    try:
        docs = (
            db.collection(settings.FIREBASE_COLLECTION_TENANTS)
            .where("team_invite_code", "==", code)
            .limit(1)
            .get()
        )
        if len(docs) > 0:
            return True
        snap = db.collection("invites").document(code).get()
        return snap is not None and getattr(snap, "exists", False)
    except Exception as e:
        logger.warning(f"Invite-code uniqueness check failed: {e}")
        return False


def generate_invite_code(db: Any) -> str:
    """Return a unique 6-character department-scoped invite code."""
    for _ in range(25):
        code = "".join(secrets.choice(INVITE_ALPHABET) for _ in range(INVITE_CODE_LENGTH))
        if not _invite_code_taken(db, code):
            return code
    raise RuntimeError("Unable to generate a unique invite code")


def resolve_invite(db: Any, code: Optional[str]) -> Optional[Dict[str, Any]]:
    """Look up a department-scoped invite document by its code.

    Returns None when the code is unknown. Callers decide whether to fall back
    to the legacy tenant-level team invite code.
    """
    if not code or not code.strip():
        return None
    try:
        snap = db.collection("invites").document(code.strip().upper()).get()
    except Exception as e:
        logger.warning(f"Invite lookup failed for code {code}: {e}")
        return None
    if snap is None or not getattr(snap, "exists", False):
        return None
    return snap.to_dict() or {}


def create_invite(
    *,
    caller: Dict[str, Any],
    department: str,
    role: str,
    request=None,
) -> Dict[str, Any]:
    """Issue a department-scoped invite under the caller's tenant.

    RBAC (enforced strictly):
      - TENANT_ADMIN / AIRLINE_ADMIN / SUPER_ADMIN: any applicable department,
        assignable roles DEPT_ADMIN / SAFETY_OFFICER / STAFF.
      - DEPT_ADMIN: target department MUST equal the caller's department and
        the role MUST be STAFF (no cross-department invites, no escalation).
    """
    db = get_db()
    tid = caller.get("tenant_id")
    if not tid:
        raise PermissionError("An authenticated tenant is required to issue invites")

    caller_role = caller.get("role")
    if caller_role not in INVITER_ROLES:
        raise PermissionError("You do not have permission to issue team invites")

    role = (role or "").strip().upper()
    dept_code = department_to_code(department)
    dept_label = department_label(dept_code)

    tenant_ref = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tid)
    try:
        tenant_snap = tenant_ref.get()
    except Exception as e:
        logger.warning(f"Tenant lookup failed for invite ({tid}): {e}")
        raise RuntimeError("Tenant storage unavailable")
    if tenant_snap is None or not getattr(tenant_snap, "exists", False):
        raise LookupError(f"Unknown tenant: {tid}")
    tenant_doc = tenant_snap.to_dict() or {}
    applicable = tenant_doc.get("applicable_departments") or []

    if caller_role in ("SUPER_ADMIN",) or caller_role in settings.TENANT_ADMIN_ROLES:
        if dept_code not in applicable:
            raise ValueError(
                f"Department '{dept_code}' is not applicable to tenant {tid}. "
                f"Allowed: {', '.join(applicable) or 'none'}"
            )
        if role not in TENANT_ADMIN_ASSIGNABLE_ROLES:
            raise PermissionError(
                f"Role '{role}' cannot be assigned by a Safety Manager. "
                f"Assignable: {', '.join(sorted(TENANT_ADMIN_ASSIGNABLE_ROLES))}"
            )
    elif caller_role in settings.DEPT_ADMIN_ROLES:
        caller_code = department_to_code(caller.get("department"))
        if caller_code != dept_code:
            raise PermissionError(
                "Department Admins may only invite members into their own department"
            )
        if role not in DEPT_ADMIN_ASSIGNABLE_ROLES:
            raise PermissionError(
                f"Role '{role}' cannot be assigned by a Department Admin. "
                f"Assignable: {', '.join(sorted(DEPT_ADMIN_ASSIGNABLE_ROLES))}"
            )
    else:  # pragma: no cover - guarded by INVITER_ROLES above
        raise PermissionError("You do not have permission to issue team invites")

    if dept_code not in applicable:
        raise ValueError(
            f"Department '{dept_code}' is not applicable to tenant {tid}. "
            f"Allowed: {', '.join(applicable) or 'none'}"
        )

    code = generate_invite_code(db)
    now = datetime.now(timezone.utc)
    doc = {
        "code": code,
        "tenant_id": tid,
        "department": dept_code,
        "department_label": dept_label,
        "role": role,
        "created_by": caller.get("uid") or caller.get("email"),
        "created_by_email": caller.get("email"),
        "created_at": now,
        "status": "ACTIVE",
    }
    try:
        db.collection("invites").document(code).set(doc)
    except Exception as e:
        logger.error(f"Failed to persist invite {code} for tenant {tid}: {e}")
        raise RuntimeError("Failed to persist the invite")

    ip, request_id = request_context(request)
    log_audit(
        action="TEAM_INVITE_CREATED",
        user=caller.get("email"),
        tenant_id=tid,
        target_type="invite",
        target_id=code,
        ip=ip,
        request_id=request_id,
        metadata={"department": dept_code, "role": role},
    )

    logger.info(
        f"Team invite issued for tenant {tid}: code={code} dept={dept_code} "
        f"role={role} by={caller.get('email')}"
    )

    return {
        "code": code,
        "tenant_id": tid,
        "department": dept_code,
        "department_label": dept_label,
        "role": role,
        "status": "ACTIVE",
        "created_at": now,
    }


def list_invites(
    *,
    caller: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """List department-scoped invites for the caller's tenant.

    DEPT_ADMIN sees only their own department's invites; tenant admins and
    SUPER_ADMIN see every invite for the tenant.
    """
    tid = caller.get("tenant_id")
    if not tid:
        raise PermissionError("An authenticated tenant is required to list invites")
    db = get_db()
    try:
        snapshots = (
            db.collection("invites").where("tenant_id", "==", tid).get()
        )
    except Exception as e:
        logger.warning(f"Failed to list invites for tenant {tid}: {e}")
        raise RuntimeError("Failed to list invites")

    caller_code = None
    if caller.get("role") in settings.DEPT_ADMIN_ROLES:
        caller_code = department_to_code(caller.get("department"))

    rows = []
    for snap in snapshots:
        data = snap.to_dict() or {}
        dept = data.get("department") or department_to_code(data.get("department_label"))
        if caller_code and department_to_code(dept) != caller_code:
            continue
        rows.append(
            {
                "code": data.get("code") or snap.id,
                "tenant_id": data.get("tenant_id"),
                "department": dept,
                "department_label": department_label(dept),
                "role": data.get("role"),
                "role_label": ROLE_LABELS.get(data.get("role"), data.get("role")),
                "created_by": data.get("created_by_email") or data.get("created_by"),
                "status": data.get("status", "ACTIVE"),
                "created_at": (
                    data.get("created_at").isoformat()
                    if hasattr(data.get("created_at"), "isoformat")
                    else data.get("created_at")
                ),
            }
        )
    rows.sort(key=lambda r: (r["created_at"] or "", r["code"] or ""))
    return rows