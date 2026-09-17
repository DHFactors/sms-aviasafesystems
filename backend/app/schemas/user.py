# ============================================================================
# FILE: user.py
# PATH: backend/app/schemas/user.py
# PURPOSE: Pydantic schemas for the mirrored `users` table (flat, Supabase-
#          native columns). These are the canonical wire contract for user
#          profiles across the API: default reads expose no developer flag,
#          admin reads add it, and create/update/self-update payloads are PATCH
#          friendly.
# CODE OWNER: AviaSafeSystems
# ============================================================================

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class UserProfileBase(BaseModel):
    """Shared profile fields present on every user.

    ``role`` defaults to ``USER`` (LSP provisioning writes the role explicitly;
    the default keeps anonymous row construction safe).
    """

    email: str = Field(..., description="User email (must be unique)")
    display_name: Optional[str] = Field(None, description="Display name")
    role: str = Field("USER", description="App role (RBAC claim)")
    department: Optional[str] = Field(None, description="Department claim")
    phone: Optional[str] = Field(None, description="Contact phone")


class UserProfileCreate(UserProfileBase):
    """Create payload for a new user row.

    ``uid`` is optional because Firebase generates it during Auth creation
    (pre-assigned UIDs are accepted for backfill/restore flows).
    """

    uid: Optional[str] = Field(None, description="Firebase Auth UID (generated unless pre-assigned)")
    tenant_id: Optional[str] = Field(None, description="Tenant slug or UUID the user belongs to")
    is_developer: bool = Field(False, description="Developer flag (admin only)")


class UserProfileUpdate(BaseModel):
    """PATCH semantics: every field optional, only supplied fields are changed.

    Intentionally excludes ``uid`` and ``email`` (immutable identity fields).
    """

    display_name: Optional[str] = Field(None, description="Display name")
    role: Optional[str] = Field(None, description="App role (RBAC claim)")
    department: Optional[str] = Field(None, description="Department claim")
    phone: Optional[str] = Field(None, description="Contact phone")
    tenant_id: Optional[str] = Field(None, description="Tenant slug or UUID the user belongs to")


class UserProfileSelfUpdate(BaseModel):
    """Self-service profile update: only the fields an end user may change."""

    display_name: Optional[str] = Field(None, description="Display name")
    phone: Optional[str] = Field(None, description="Contact phone")


class UserProfileRead(UserProfileBase):
    """Default profile read response — never exposes the developer flag."""

    uid: str = Field(..., description="Firebase Auth UID")
    tenant_id: Optional[str] = Field(None, description="Tenant slug or UUID the user belongs to")
    password_updated_at: Optional[datetime] = Field(
        None, description="When the Firebase Auth password was last set/reset (PG mirror)"
    )


class UserProfileAdminRead(UserProfileRead):
    """Admin-strength profile read response — adds the developer flag."""

    is_developer: bool = Field(False, description="Developer flag (admin only)")


# ---------------------------------------------------------------------------
# Response wrappers — keep the existing envelope/wrapper wire shapes intact
# while surfacing the typed profile schemas in OpenAPI.
# ---------------------------------------------------------------------------

class AdminUserListResponse(BaseModel):
    """``GET /api/v1/admin/users`` — paginated admin user list."""

    users: List[UserProfileAdminRead] = Field(default_factory=list)
    count: int = Field(0, description="Number of users in this page")


class AdminUserUpdateResponse(BaseModel):
    """``PATCH /api/v1/admin/users`` — updated user payload."""

    success: bool = Field(default=True)
    user: UserProfileAdminRead


class TenantUserListData(BaseModel):
    """Body of the tenant user-list envelope."""

    tenant_id: str
    users: List[UserProfileRead] = Field(default_factory=list)


class TenantUserListResponse(BaseModel):
    """``GET /api/v1/tenants/{tenant_id}/users`` — standard API envelope."""

    status: str = Field("success")
    timestamp: datetime = Field(default_factory=datetime.now)
    data: TenantUserListData