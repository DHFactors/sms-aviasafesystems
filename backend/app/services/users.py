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
from uuid import UUID

from loguru import logger

from app.db import pg
from app.db.db_models import UserProfile
from app.db.ids import tenant_uuid
from app.firebase import get_auth
from app.services.dlq_service import DlqService


def _resolve_tenant_id(tenant_id: Any) -> Optional[UUID]:
    """Resolve a tenant reference to the canonical users.tenant_id UUID.

    Claims and request bodies carry the tenant SLUG (e.g. "annapurna-heli"),
    but the users.tenant_id column is a UUID FK to tenants.id whose value is
    the deterministic uuid5('tenant:'+slug). Pass through a value that is
    already a UUID and map a slug onto its canonical uuid.
    """
    if tenant_id is None:
        return None
    if isinstance(tenant_id, UUID):
        return tenant_id
    s = str(tenant_id)
    try:
        return UUID(s)
    except (ValueError, AttributeError):
        pass
    return UUID(tenant_uuid(s))


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
    """Map a firebase_admin.auth.UserRecord to the flat Postgres users row.

    Keys align with the flat ``users`` columns only (uid/email/role/tenant_id/
    department/is_developer/phone + timestamps incl. password_updated_at). The
    schemaless Firestore ``modules``/``claims``/``data`` bags are intentionally
    not written.
    """
    claims = record.custom_claims or {}
    meta = getattr(record, "user_metadata", None)
    created_at = _parse_ms_timestamp(getattr(meta, "creation_timestamp", None))
    last_login = (
        getattr(meta, "last_sign_in_at", None)
        or getattr(meta, "last_sign_in_timestamp", None)
    )
    last_login = _parse_ms_timestamp(last_login)
    # Firebase Admin SDK does not expose passwordUpdatedAt on UserRecord, so
    # this is usually None; the freshness marker is stamped explicitly at
    # password-set time (see tenant_credentials._create_auth_user).
    password_updated_at = (
        getattr(meta, "password_updated_at", None)
        or getattr(meta, "passwordUpdatedAt", None)
    )
    password_updated_at = _parse_ms_timestamp(password_updated_at)
    return {
        "uid": record.uid,
        "email": record.email,
        "display_name": getattr(record, "display_name", None),
        "role": claims.get("role") or "USER",
        "tenant_id": claims.get("tenant_id"),
        "department": claims.get("department") or "",
        "is_developer": bool(claims.get("is_developer")),
        "phone": getattr(record, "phone_number", None),
        "created_at": created_at,
        "last_login": last_login,
        "password_updated_at": password_updated_at,
    }


def _dlq_user_mirror(uid: str, error: str) -> None:
    """Enqueue a ``users_mirror`` dead-letter record. Never raises."""
    try:
        DlqService().quarantine(
            original_operation="users_mirror",
            payload={"uid": uid},
            error_message=error,
        )
    except Exception as e:
        logger.error(f"Failed to enqueue DLQ record for users_mirror {uid}: {e}")


def upsert_user_doc(
    uid: str,
    email: Optional[str] = None,
    role: str = "USER",
    tenant_id: Any = None,
    department: Optional[str] = None,
    display_name: Optional[str] = None,
    is_developer: bool = False,
    phone: Optional[str] = None,
    created_at: Any = None,
    last_login: Any = None,
    password_updated_at: Any = None,
) -> None:
    """Write/merge a flat user row and verify it landed.

    Mirrors the Firebase Auth record into the Postgres ``users`` table so
    tenant-scoped queries are cheap and indexable. ``tenant_id`` may be a slug
    or a UUID; the slug is resolved to its canonical uuid5 before the write.
    ``claims``/``data`` JSONB bags are never persisted.

    Unlike the original best-effort write, failures are loud: the exception is
    re-raised (surfacing the failure to the caller/UI) and a ``users_mirror``
    duplicate is preserved in the dead-letter queue so the record is never
    silently lost. The write is followed by a verify-after-upsert fetch that
    catches a silent no-op.
    """
    doc: Dict[str, Any] = {
        "uid": uid,
        "email": email,
        "role": role or "USER",
        "tenant_id": _resolve_tenant_id(tenant_id),
        "department": department,
        "display_name": display_name,
        "is_developer": bool(is_developer),
        "phone": phone,
        "updated_at": datetime.now(timezone.utc),
    }
    if created_at is not None:
        doc["created_at"] = created_at
    if last_login is not None:
        doc["last_login"] = last_login
    if password_updated_at is not None:
        doc["password_updated_at"] = password_updated_at
    try:
        pg.upsert(UserProfile, "uid", uid, doc)
    except Exception as e:
        _dlq_user_mirror(uid, str(e))
        logger.error(f"PG mirror upsert failed for {uid}: {e}")
        raise

    verify = pg.fetch_by(UserProfile, "uid", uid)
    if verify is None:
        _dlq_user_mirror(uid, "row missing after upsert")
        logger.error(f"PG mirror verification failed for {uid}")
        raise RuntimeError(f"User mirror verification failed: {uid}")


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
            try:
                upsert_user_doc(**user_doc_from_auth_record(record))
                written += 1
            except Exception as e:
                _dlq_user_mirror(record.uid, str(e))
                logger.error(f"Backfill skipped user {record.uid}: {e}")
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
    """Query the users table for all users assigned to a tenant.

    ``tenant_id`` may be a slug (the API-contract form) or UUID; it is
    resolved to the canonical users.tenant_id UUID before the query.
    """
    resolved = _resolve_tenant_id(tenant_id)
    if resolved is None:
        return []
    try:
        docs = pg.fetch_all(UserProfile, where=[UserProfile.tenant_id == resolved])
    except Exception as e:
        logger.warning(f"Failed to list users for tenant {tenant_id}: {e}")
        return []
    results = []
    for data in docs:
        results.append(
            {
                "uid": data.get("uid"),
                "email": data.get("email"),
                "display_name": data.get("display_name"),
                "role": data.get("role"),
                "department": data.get("department") or "",
                "phone": data.get("phone"),
                "tenant_id": str(data.get("tenant_id")) if data.get("tenant_id") else None,
                "created_at": _iso(data.get("created_at")),
                "last_login": _iso(data.get("last_login")),
                "password_updated_at": _iso(data.get("password_updated_at")),
            }
        )
    results.sort(key=lambda u: (u["created_at"] or "", u["email"] or ""))
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
