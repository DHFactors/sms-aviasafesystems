# ============================================================================
# FILE: users.py
# PATH: backend/app/services/users.py
# PURPOSE: Mirror Firebase Auth users into the Postgres `users` table so
#          tenant-scoped queries are cheap and indexable. The table is
#          backfilled from Auth, maintained on register/claims updates, and
#          consumed by GET /api/v1/tenants/{tenantId}/users.
# ============================================================================

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

from app.db import pg
from app.db.db_models import UserProfile
from app.firebase import get_auth


def _parse_ms_timestamp(value: Any) -> Optional[datetime]:
    """Convert a Firebase Auth ms-epoch (int) or ISO string into a datetime."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
            except (ValueError, OSError):
                return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        except (ValueError, OSError):
            return None
    return None


def user_doc_from_auth_record(record: Any) -> Dict[str, Any]:
    """Map a firebase_admin.auth.UserRecord to the Firestore users/{uid} shape."""
    claims = record.custom_claims or {}
    meta = getattr(record, "user_metadata", None)
    created_at = _parse_ms_timestamp(getattr(meta, "creation_timestamp", None))
    last_login = (
        getattr(meta, "last_sign_in_at", None)
        or getattr(meta, "last_sign_in_timestamp", None)
    )
    last_login = _parse_ms_timestamp(last_login)
    return {
        "uid": record.uid,
        "email": record.email,
        "display_name": getattr(record, "display_name", None),
        "role": claims.get("role") or "USER",
        "tenant_id": claims.get("tenant_id"),
        "department": claims.get("department") or "",
        "modules": claims.get("modules"),
        "is_developer": bool(claims.get("is_developer")),
        "created_at": created_at,
        "last_login": last_login,
        "updated_at": datetime.now(timezone.utc),
    }


def upsert_user_doc(uid: str, data: Dict[str, Any]) -> None:
    """Best-effort write/merge of a user row. Never breaks the caller."""
    try:
        pg.upsert(UserProfile, "uid", uid, data)
    except Exception as e:
        logger.warning(f"Failed to upsert user row {uid}: {e}")


def backfill_users_from_auth(max_pages: Optional[int] = None) -> int:
    """Paginate Firebase Auth and upsert every user into the users table.

    Returns the number of user rows written. `max_pages` limits the scan (for
    sanity checks on large directories); by default all users are synced.
    """
    auth = get_auth()
    written = 0
    page_token = None
    pages = 0
    while True:
        page = auth.list_users(max_results=1000, page_token=page_token)
        for record in page.users:
            upsert_user_doc(record.uid, user_doc_from_auth_record(record))
            written += 1
        pages += 1
        page_token = page.next_page_token
        if not page_token or (max_pages and pages >= max_pages):
            break
    logger.info(f"User backfill complete: {written} users synced")
    return written


def _iso(value: Any) -> Optional[str]:
    """Render a stored timestamp (datetime or ISO string) back to ISO text."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def list_tenant_users(tenant_id: str) -> List[Dict[str, Any]]:
    """Query the users table for all users assigned to a tenant."""
    try:
        docs = pg.fetch_all(UserProfile, where=[UserProfile.tenant_id == tenant_id])
    except Exception as e:
        logger.warning(f"Failed to list users for tenant {tenant_id}: {e}")
        return []
    results = []
    for data in docs:
        results.append(
            {
                "uid": data.get("uid"),
                "email": data.get("email"),
                "displayName": data.get("display_name"),
                "role": data.get("role"),
                "department": data.get("department") or "",
                "createdAt": _iso(data.get("created_at")),
                "lastLogin": _iso(data.get("last_login")),
            }
        )
    results.sort(key=lambda u: (u["createdAt"] or "", u["email"] or ""))
    return results


def get_user_department(uid: Optional[str] = None, email: Optional[str] = None) -> str:
    """Resolve a user's department from the mirrored users table.

    Checks by uid first, then falls back to an email match. Returns an empty
    string when the user cannot be found or has no department assigned.
    """
    try:
        if uid:
            doc = pg.fetch_by(UserProfile, "uid", uid)
            if doc:
                return doc.get("department") or ""
        if email:
            doc = pg.fetch_by(UserProfile, "email", email)
            if doc:
                return doc.get("department") or ""
    except Exception as e:
        logger.warning(f"Failed to resolve department for uid={uid} email={email}: {e}")
    return ""
