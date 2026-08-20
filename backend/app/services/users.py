# ============================================================================
# FILE: users.py
# PATH: backend/app/services/users.py
# PURPOSE: Mirror Firebase Auth users into a Firestore `users` collection so
#          tenant-scoped queries are cheap and indexable. The collection is
#          backfilled from Auth, maintained on register/claims updates, and
#          consumed by GET /api/v1/tenants/{tenantId}/users.
# ============================================================================

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

from app.core.config import settings
from app.firebase import get_db, get_auth


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
        "is_developer": bool(claims.get("is_developer")),
        "created_at": created_at,
        "last_login": last_login,
        "updated_at": datetime.now(timezone.utc),
    }


def upsert_user_doc(uid: str, data: Dict[str, Any]) -> None:
    """Best-effort write/merge of a user doc. Never breaks the caller."""
    try:
        get_db().collection(settings.FIREBASE_COLLECTION_USERS).document(uid).set(
            data, merge=True
        )
    except Exception as e:
        logger.warning(f"Failed to upsert user doc {uid}: {e}")


def backfill_users_from_auth(max_pages: Optional[int] = None) -> int:
    """Paginate Firebase Auth and upsert every user into the users collection.

    Returns the number of user docs written. `max_pages` limits the scan (for
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


def list_tenant_users(tenant_id: str) -> List[Dict[str, Any]]:
    """Query the users collection for all users assigned to a tenant."""
    snapshots = (
        get_db()
        .collection(settings.FIREBASE_COLLECTION_USERS)
        .where("tenant_id", "==", tenant_id)
        .get()
    )
    results = []
    for snap in snapshots:
        data = snap.to_dict() or {}
        results.append(
            {
                "uid": data.get("uid") or snap.id,
                "email": data.get("email"),
                "displayName": data.get("display_name"),
                "role": data.get("role"),
                "department": data.get("department") or "",
                "createdAt": data.get("created_at").isoformat() if data.get("created_at") else None,
                "lastLogin": data.get("last_login").isoformat() if data.get("last_login") else None,
            }
        )
    results.sort(key=lambda u: (u["createdAt"] or "", u["email"] or ""))
    return results


def get_user_department(uid: Optional[str] = None, email: Optional[str] = None) -> str:
    """Resolve a user's department from the mirrored users collection.

    Checks by uid first, then falls back to an email match. Returns an empty
    string when the user cannot be found or has no department assigned.
    """
    try:
        db = get_db()
        if uid:
            snap = db.collection(settings.FIREBASE_COLLECTION_USERS).document(uid).get()
            if snap.exists:
                return (snap.to_dict() or {}).get("department") or ""
        if email:
            docs = (
                db.collection(settings.FIREBASE_COLLECTION_USERS)
                .where("email", "==", email)
                .limit(1)
                .get()
            )
            for d in docs:
                return (d.to_dict() or {}).get("department") or ""
    except Exception as e:
        logger.warning(f"Failed to resolve department for uid={uid} email={email}: {e}")
    return ""
