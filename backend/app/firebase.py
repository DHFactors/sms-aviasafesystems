"""Firebase Admin — Auth-only.

Firestore data plane has been migrated to Postgres (Batches 0-3 and the
A-series cleanup). This module exposes ONLY Auth utilities (token verification,
custom claims, app init). The Firestore data-access helpers (get_db,
get_tenant_collection, get_cross_tenant_collection, get_tenant_metadata) are
fully removed and now raise NotImplementedError — the dummy Firestore client was
deleted in A1.

Ambiguous callers were given transitional stubs (routes/demo.py, routes/admin.py,
services/admin_data_service.py, workers/tenant_scheduler.py) that degrade to a
no-op / empty result instead of crashing. Any OTHER call that reaches these
functions is legacy Firestore wiring that must be cleaned up in the A-series
(A2/A3b/A5/A7/A8).
"""

import firebase_admin
from firebase_admin import credentials, auth
from typing import Optional, Dict, Any
from loguru import logger

from app.core.config import settings

_firebase_app = None


def initialize_firebase():
    global _firebase_app

    if not firebase_admin._apps:
        try:
            project_id = settings.FIREBASE_PROJECT_ID
            private_key = settings.FIREBASE_PRIVATE_KEY
            client_email = settings.FIREBASE_CLIENT_EMAIL

            if not all([project_id, private_key, client_email]):
                raise ValueError("Missing Firebase credentials in environment")

            cred_dict = {
                "type": "service_account",
                "project_id": project_id,
                "private_key": private_key.replace('\\n', '\n'),
                "client_email": client_email,
                "token_uri": settings.FIREBASE_TOKEN_URI,
            }

            cred = credentials.Certificate(cred_dict)
            _firebase_app = firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin SDK initialized (Auth-only, Firestore removed)")

        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
            raise
    return _firebase_app


def get_db():
    """Deprecated: Firestore removed from the data plane (A1). Raises.

    No dummy client exists anymore. Transitional stubs in routes/demo.py,
    routes/admin.py, services/admin_data_service.py and
    workers/tenant_scheduler.py catch this and degrade. Any other live caller
    is legacy Firestore wiring to be removed.
    """
    raise NotImplementedError(
        "firebase.get_db() is unavailable: Firestore was removed from the data plane (A1). "
        "Use app.db.pg for data access. Convert this call site to a transitional stub "
        "(routes/demo.py, routes/admin.py, services/admin_data_service.py, "
        "workers/tenant_scheduler.py) or remove it in the A-series cleanup."
    )


def get_auth():
    if _firebase_app is None:
        initialize_firebase()
    return auth


def get_tenant_collection(tenant_id: str, collection: str):
    """Deprecated: Firestore removed from the data plane (A1). Raises."""
    raise NotImplementedError(
        f"firebase.get_tenant_collection({tenant_id!r}, {collection!r}) is unavailable: "
        "Firestore was removed from the data plane (A1). Use app.db.pg for data access."
    )


def get_cross_tenant_collection(collection: str):
    """Deprecated: Firestore removed from the data plane (A1). Raises."""
    raise NotImplementedError(
        f"firebase.get_cross_tenant_collection({collection!r}) is unavailable: "
        "Firestore was removed from the data plane (A1). Use app.db.pg for data access."
    )


def get_tenant_metadata(tenant_id: str) -> Optional[Dict[str, Any]]:
    """Deprecated: Firestore removed from the data plane (A1). Raises."""
    raise NotImplementedError(
        f"firebase.get_tenant_metadata({tenant_id!r}) is unavailable: "
        "Firestore was removed from the data plane (A1). Use app.db.pg for data access."
    )


def verify_firebase_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        decoded_token = auth.verify_id_token(token, check_revoked=True)
        return decoded_token
    except firebase_admin.auth.ExpiredIdTokenError:
        logger.warning("Expired Firebase ID token")
        return None
    except firebase_admin.auth.RevokedIdTokenError:
        logger.warning("Revoked Firebase ID token")
        return None
    except firebase_admin.auth.InvalidIdTokenError:
        logger.warning("Invalid Firebase ID token")
        return None
    except Exception as e:
        logger.error(f"Token verification failed: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None


def is_firebase_ready() -> bool:
    return _firebase_app is not None


def create_custom_claims(uid: str, role: str, tenant_id: Optional[str] = None) -> bool:
    try:
        claims = {"role": role}
        if tenant_id:
            claims["tenant_id"] = tenant_id
        auth.update_user(uid, custom_claims=claims)
        logger.info(f"Custom claims set for user {uid}: {claims}")
        return True
    except Exception as e:
        logger.error(f"Failed to set custom claims: {e}")
        return False