"""Firebase Admin — Auth-only.

Firestore data plane has been migrated to Postgres (Batches 0-3). This module
now exposes ONLY Auth utilities (token verification, custom claims, app init).
Firestore helpers (get_db, get_tenant_collection, etc.) are retained as
deprecated no-op stubs so best-effort mirror writes do not crash, but they log
a warning and return a dummy client. New code must use app.db.pg.
"""

import firebase_admin
from firebase_admin import credentials, auth
from typing import Optional, Dict, Any
from loguru import logger

from app.core.config import settings

_firebase_app = None


class _DummyFirestoreDoc:
    exists = False
    id = "dummy"
    def to_dict(self): return {}
    def get(self, *a, **kw): return self
    def set(self, *a, **kw): return None
    def update(self, *a, **kw): return None
    def delete(self, *a, **kw): return None
    def collection(self, *a, **kw): return _DummyFirestoreCollection()
    @property
    def reference(self): return self


class _DummyFirestoreCollection:
    def document(self, *a, **kw): return _DummyFirestoreDoc()
    def collection(self, *a, **kw): return _DummyFirestoreCollection()
    def collection_group(self, *a, **kw): return _DummyFirestoreCollection()
    def where(self, *a, **kw): return self
    def order_by(self, *a, **kw): return self
    def limit(self, *a, **kw): return self
    def start_after(self, *a, **kw): return self
    def stream(self, *a, **kw): return []
    def get(self, *a, **kw): return []
    def add(self, *a, **kw): return (None, _DummyFirestoreDoc())
    def count(self): 
        class _C: 
            def get(self): return []
        return _C()


class _DummyFirestoreClient:
    def collection(self, *a, **kw): return _DummyFirestoreCollection()
    def collection_group(self, *a, **kw): return _DummyFirestoreCollection()
    def document(self, *a, **kw): return _DummyFirestoreDoc()
    def batch(self):
        class _B:
            def set(self, *a, **kw): pass
            def update(self, *a, **kw): pass
            def delete(self, *a, **kw): pass
            def commit(self): pass
        return _B()


_dummy_db = _DummyFirestoreClient()


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
            logger.info("Firebase Admin SDK initialized (Auth-only, Firestore deprecated)")

        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
            raise
    return _firebase_app


def get_db():
    """Deprecated: Firestore removed. Returns dummy client that no-ops."""
    logger.warning("get_db() called — Firestore is deprecated, returning dummy (no-op)")
    if _firebase_app is None:
        try:
            initialize_firebase()
        except Exception:
            pass
    return _dummy_db


def get_auth():
    if _firebase_app is None:
        initialize_firebase()
    return auth


def get_tenant_collection(tenant_id: str, collection: str):
    logger.warning(f"get_tenant_collection({tenant_id}/{collection}) — Firestore deprecated, returning dummy")
    return _dummy_db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tenant_id).collection(collection)


def get_cross_tenant_collection(collection: str):
    logger.warning(f"get_cross_tenant_collection({collection}) — Firestore deprecated, returning dummy")
    return _dummy_db.collection_group(collection)


def get_tenant_metadata(tenant_id: str) -> Optional[Dict[str, Any]]:
    logger.warning(f"get_tenant_metadata({tenant_id}) — Firestore deprecated")
    return None


def verify_firebase_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        decoded_token = auth.verify_id_token(token, check_revoked=False)
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
