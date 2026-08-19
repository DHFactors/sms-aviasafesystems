# ============================================================================
# FILE: login_service.py
# PATH: backend/app/services/login_service.py
# PURPOSE: Server-side credential verification for POST /api/v1/auth/login.
#
#   verify_credentials():  verifies email/password against the Firebase
#                          Identity Toolkit REST API (the same backend the
#                          client SDK uses) using the public web API key.
#   mint_custom_token():   mints a short-lived custom token with the Firebase
#                          Admin SDK that the client exchanges via
#                          firebase.auth().signInWithCustomToken().
#
# Routing login through the backend lets us enforce a strict per-IP sliding
# window on *failed* attempts (see middleware/rate_limit.login_failures),
# which is impossible when the client talks to Firebase Auth directly.
#
# verify_credentials is monkeypatchable in tests; LoginProviderError is raised
# only for transport/provider failures (route -> 503), never for bad
# credentials (route -> 401 via a None return).
# ============================================================================

import httpx
from loguru import logger

from app.core.config import settings
from app.firebase import get_auth

IDENTITY_TOOLKIT_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"

_TIMEOUT_SECONDS = 8.0


class LoginProviderError(Exception):
    """Raised when the Identity Toolkit endpoint cannot be reached."""


def _api_key() -> str:
    return settings.FIREBASE_WEB_API_KEY


async def verify_credentials(email: str, password: str) -> dict | None:
    """Verify credentials against Firebase Identity Toolkit.

    Returns a small user dict ({uid, email, display_name}) on success and None
    on bad credentials. Raises LoginProviderError only for transport/provider
    failures so the route can degrade with a 503 (fail-closed).
    """
    url = f"{IDENTITY_TOOLKIT_URL}?key={_api_key()}"
    payload = {"email": email, "password": password, "returnSecureToken": True}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, json=payload)
    except Exception as e:  # noqa: BLE001 - transport-level failures are provider errors
        logger.warning(f"Identity Toolkit request failed for {email}: {e}")
        raise LoginProviderError("Identity Toolkit unreachable") from e

    if resp.status_code == 200:
        data = resp.json()
        return {
            "uid": data.get("localId"),
            "email": data.get("email"),
            "display_name": data.get("displayName"),
        }

    # 400 with a Firebase error message (INVALID_LOGIN_CREDENTIALS,
    # INVALID_PASSWORD, EMAIL_NOT_FOUND, USER_DISABLED, ...) -> bad credentials.
    logger.info(f"Identity Toolkit rejected sign-in for {email} ({resp.status_code})")
    return None


def mint_custom_token(uid: str) -> str:
    """Mint a short-lived Firebase custom token for the verified user."""
    token = get_auth().create_custom_token(uid)
    return token.decode("utf-8") if isinstance(token, bytes) else str(token)