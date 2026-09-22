# ============================================================================
# FILE: role_validation.py
# PATH: backend/app/services/role_validation.py
# PURPOSE: Role-assignment validator enforcing the RBAC_MODEL.md §7 conflict
#          rules (AE exclusivity + combination, CAAN vs tenant, SUPER_ADMIN
#          exclusivity) at the API layer. The DB partial unique index
#          `ux_users_one_ae_per_tenant` is the belt to this validator's braces.
# ============================================================================

from typing import Iterable, List, Optional, Union

from fastapi import HTTPException, status

from app.core.config import settings
from app.db import pg
from app.db.db_models import UserProfile
from app.db.ids import tenant_uuid

# Roles that cannot be combined with ACCOUNTABLE_EXECUTIVE (RBAC §7).
_OPERATIONAL_ROLES = set(
    settings.TENANT_ADMIN_ROLES
    + settings.DEPT_ADMIN_ROLES
    + settings.SAFETY_OFFICER_ROLES
)

# Tenant-scoped roles (a user holding one of these must have a tenant).
_TENANT_SCOPED_ROLES = (
    set(settings.TENANT_ADMIN_ROLES)
    | set(settings.DEPT_ADMIN_ROLES)
    | set(settings.SAFETY_OFFICER_ROLES)
    | set(settings.STAFF_ROLES)
    | set(settings.ACCOUNTABLE_EXECUTIVE_ROLES)
    | set(settings.SAG_MEMBER_ROLES)
)


def _as_roles(role: Union[str, Iterable[str], None]) -> List[str]:
    if role is None:
        return []
    if isinstance(role, str):
        return [role.strip()] if role.strip() else []
    return [str(r).strip() for r in role if str(r).strip()]


def ae_count(tenant_id: str, exclude_uid: Optional[str] = None) -> int:
    """Count Accountable Executives already assigned to a tenant.

    ``exclude_uid`` ignores the user being updated so re-saving the existing AE
    does not trip the one-per-tenant rule.
    """
    tid = tenant_uuid(tenant_id)
    rows = pg.fetch_all(
        UserProfile,
        where=[
            UserProfile.tenant_id == tid,
            UserProfile.role == settings.ROLE_ACCOUNTABLE_EXECUTIVE,
        ],
    )
    return sum(1 for r in rows if str(r.get("uid")) != str(exclude_uid))


def validate_role_assignment(
    role: Union[str, Iterable[str], None],
    tenant_id: Optional[str] = None,
    *,
    existing_role: Optional[str] = None,
    is_developer: Optional[bool] = None,
    exclude_uid: Optional[str] = None,
) -> None:
    """Validate a role assignment against RBAC_MODEL.md §7.

    Raises ``HTTPException(400)`` with a clear message on any conflict. ``role``
    may be a single role or an iterable (multi-role attempt); ``existing_role``
    is the user's current role, so a change that would combine conflicting roles
    is rejected too.
    """
    combined = set(_as_roles(role))
    if existing_role:
        combined.add(existing_role)

    # SUPER_ADMIN is exclusive (developer-only) and platform-scoped.
    if "SUPER_ADMIN" in combined:
        if is_developer is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="SUPER_ADMIN is reserved for platform developers",
            )
        if len(combined) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="SUPER_ADMIN cannot be combined with any other role",
            )
        if tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="SUPER_ADMIN is platform-scoped and cannot hold a tenant",
            )

    # CAAN_SMD cannot hold (or be combined with) any tenant role.
    if "CAAN_SMD" in combined:
        if tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CAAN_SMD cannot hold a tenant role",
            )
        if combined - {"CAAN_SMD"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CAAN_SMD cannot be combined with tenant roles",
            )

    # Accountable Executive: one per tenant, not combinable with operational roles.
    if "ACCOUNTABLE_EXECUTIVE" in combined:
        clash = combined & _OPERATIONAL_ROLES
        if clash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "ACCOUNTABLE_EXECUTIVE cannot be combined with operational "
                    f"roles: {sorted(clash)}"
                ),
            )
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ACCOUNTABLE_EXECUTIVE requires a tenant_id",
            )
        if ae_count(tenant_id, exclude_uid=exclude_uid) > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"tenant '{tenant_id}' already has an ACCOUNTABLE_EXECUTIVE",
            )

    # Tenant-scoped roles require a tenant.
    if (combined & _TENANT_SCOPED_ROLES) and not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant-scoped roles require a tenant_id",
        )
