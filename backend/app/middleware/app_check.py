# ============================================================================
# FILE: app_check.py
# PATH: backend/app/middleware/app_check.py
# PURPOSE: Firebase App Check token verification for public (unauthenticated)
#          endpoints — self-service registration, team onboarding, invite
#          verification and guest copilot chat.
#
# Model: the header `X-Firebase-AppCheck` is verified server-side with
# firebase_admin.app_check.verify_app_check_token() whenever it is present;
# an invalid / expired / malformed token is rejected with 401. Absent tokens
# are allowed through so deployments where App Check (reCAPTCHA) is not yet
# provisioned keep working — they are still protected by per-IP rate limiting
# and the production access-key gate.
# ============================================================================

import asyncio
from typing import Optional

from fastapi import Request
from loguru import logger

APP_CHECK_HEADER = "X-Firebase-AppCheck"


def _verify_sync(token: str) -> Optional[object]:
    """Verify an App Check token with the Firebase Admin SDK (sync).

    Returns the verification result or None when the token is invalid.
    Raises are caught by the caller so the dependency degrades gracefully.
    """
    from firebase_admin import app_check

    return app_check.verify_app_check_token(token)


async def verify_app_check(request: Request) -> None:
    """FastAPI dependency: verify a supplied App Check token, if any.

    - Header absent   -> allow (App Check may not be provisioned).
    - Header invalid  -> HTTP 401 (defense against forged clients).
    - Admin SDK missing / app not initialized -> allow + log (graceful).
    """
    token = request.headers.get(APP_CHECK_HEADER)
    if not token:
        return

    try:
        result = await asyncio.to_thread(_verify_sync, token)
        if result is None:
            raise ValueError("App Check token rejected")
        logger.debug(
            "App Check verified (app_id=%s, type=%s)",
            getattr(result, "app_id", "?"),
            getattr(result, "token_type", "?"),
        )
    except Exception as e:  # noqa: BLE001 - deliberate degradation
        logger.warning("App Check verification failed: %s", e)
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="App Check verification failed") from e


async def verify_app_check_lenient(request: Request) -> None:
    """Lenient App Check dependency for public guest endpoints.

    Guest endpoints (e.g. copilot guest chat) are guarded primarily by per-IP
    rate limiting rather than App Check. In InPrivate / incognito browsing the
    browser's Tracking Prevention can block the reCAPTCHA provider's iframe
    storage, which either suppresses the token entirely or yields a stale /
    invalid one. A missing or invalid token must therefore NEVER hard-fail the
    request — log a warning and continue (the sliding-window rate limit still
    protects the endpoint).
    """
    token = request.headers.get(APP_CHECK_HEADER)
    if not token:
        return

    try:
        result = await asyncio.to_thread(_verify_sync, token)
        if result is None:
            logger.warning(
                "App Check token rejected (lenient mode — continuing without enforcement)"
            )
        else:
            logger.debug(
                "App Check verified (app_id=%s, type=%s)",
                getattr(result, "app_id", "?"),
                getattr(result, "token_type", "?"),
            )
    except Exception as e:  # noqa: BLE001 - deliberate degradation
        logger.warning(
            "App Check verification failed (lenient mode — continuing): %s", e
        )