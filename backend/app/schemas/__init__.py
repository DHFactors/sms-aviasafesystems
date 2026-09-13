"""Canonical API schemas."""

from app.schemas.user import (
    AdminUserListResponse,
    AdminUserUpdateResponse,
    TenantUserListData,
    TenantUserListResponse,
    UserProfileAdminRead,
    UserProfileBase,
    UserProfileCreate,
    UserProfileRead,
    UserProfileSelfUpdate,
    UserProfileUpdate,
)

__all__ = [
    "AdminUserListResponse",
    "AdminUserUpdateResponse",
    "TenantUserListData",
    "TenantUserListResponse",
    "UserProfileAdminRead",
    "UserProfileBase",
    "UserProfileCreate",
    "UserProfileRead",
    "UserProfileSelfUpdate",
    "UserProfileUpdate",
]