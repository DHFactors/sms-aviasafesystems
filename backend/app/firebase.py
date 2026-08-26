import firebase_admin
from firebase_admin import credentials, firestore, auth
from typing import Optional, Dict, Any
from loguru import logger

from app.core.config import settings

_firebase_app = None
_db = None


def initialize_firebase():
    global _firebase_app, _db

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
            _db = firestore.client(app=_firebase_app, database_id=settings.FIREBASE_DATABASE_ID)
            logger.info(f"Firebase Admin SDK initialized successfully (database={settings.FIREBASE_DATABASE_ID})")

        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
            raise
    else:
        _db = firestore.client(app=_firebase_app, database_id=settings.FIREBASE_DATABASE_ID)

    return _firebase_app


def get_db():
    if _db is None:
        initialize_firebase()
    return _db


def get_auth():
    if _firebase_app is None:
        initialize_firebase()
    return auth


def get_tenant_collection(tenant_id: str, collection: str):
    db = get_db()
    return db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tenant_id).collection(collection)


def get_cross_tenant_collection(collection: str):
    db = get_db()
    return db.collection_group(collection)


def get_tenant_metadata(tenant_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    doc = (
        db.collection(settings.FIREBASE_COLLECTION_TENANTS)
        .document(tenant_id)
        .collection(settings.FIREBASE_COLLECTION_METADATA)
        .document(settings.FIREBASE_DOCUMENT_INFO)
        .get()
    )
    if doc.exists:
        return doc.to_dict()
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
    return _db is not None


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
