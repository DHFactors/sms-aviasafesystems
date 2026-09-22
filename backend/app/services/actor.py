# ============================================================================
# FILE: actor.py
# PATH: backend/app/services/actor.py
# PURPOSE: Resolve an authenticated request user to the Postgres `users.id`
#          UUID so Module B services can populate FK columns (process_by,
#          triaged_by, published_by, created_by, ...). The auth user dict
#          carries the Firebase uid (text) and email, not the users.id.
# ============================================================================

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy import select

from app.db.db_models import UserProfile
from app.db.session import session_scope


async def resolve_actor_uuid(user: Optional[Dict[str, Any]]) -> Optional[uuid.UUID]:
    """Return the users.id UUID for the acting user (uid, then email).

    Falls back to parsing the uid as a UUID; returns None when unresolved so a
    caller never writes a non-UUID string into a UUID column.
    """
    if not user:
        return None
    uid_text = str(user.get("uid") or "").strip()
    email = str(user.get("email") or "").strip()
    if not uid_text and not email:
        return None
    try:
        async with session_scope() as session:
            if uid_text:
                row = (await session.execute(
                    select(UserProfile.id).where(UserProfile.uid == uid_text)
                )).scalar_one_or_none()
                if row:
                    return row
            if email:
                row = (await session.execute(
                    select(UserProfile.id).where(UserProfile.email == email)
                )).scalar_one_or_none()
                if row:
                    return row
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"resolve_actor_uuid lookup failed for {uid_text or email}: {e}")
    try:
        return uuid.UUID(uid_text)
    except (ValueError, TypeError, AttributeError):
        return None
