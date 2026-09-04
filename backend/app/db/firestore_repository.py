from typing import List, Dict, Optional, Any
from loguru import logger

from app.db.abstract_repository import AbstractRepository
from app.firebase import get_db


class FirestoreRepository(AbstractRepository):
    """Firestore implementation of AbstractRepository.

    Uses Firebase Admin SDK (synchronous) behind async interface for
    compatibility with the migration-ready DAL. All methods are async
    to match the Postgres implementation.
    """

    async def create(self, collection: str, data: dict) -> dict:
        """Create a document in the specified collection with auto-generated ID."""
        try:
            db = get_db()
            doc_ref = db.collection(collection).document()
            doc_ref.set(data)
            result = {"id": doc_ref.id, **data}
            logger.debug(f"Firestore create {collection}/{doc_ref.id}")
            return result
        except Exception as e:
            logger.error(f"Firestore create failed {collection}: {e}")
            raise

    async def get(self, collection: str, doc_id: str) -> Optional[dict]:
        """Get a document by ID. Returns None if not found."""
        try:
            db = get_db()
            doc = db.collection(collection).document(doc_id).get()
            if not doc.exists:
                return None
            result = doc.to_dict() or {}
            result["id"] = doc.id
            return result
        except Exception as e:
            logger.error(f"Firestore get failed {collection}/{doc_id}: {e}")
            raise

    async def query(
        self,
        collection: str,
        filters: Optional[List[tuple]] = None,
        order_by: Optional[List[tuple]] = None,
        limit: Optional[int] = None
    ) -> List[dict]:
        """Query documents with filters and ordering.

        filters: List of (field, op, value) e.g. [("status", "==", "active")]
        order_by: List of (field, direction) e.g. [("created_at", "desc")]
        """
        try:
            db = get_db()
            query = db.collection(collection)

            if filters:
                for field, op, value in filters:
                    query = query.where(field, op, value)

            if order_by:
                for field, direction in order_by:
                    # Firestore expects direction as string "ASCENDING"/"DESCENDING" or via constants
                    query = query.order_by(field, direction=direction)

            if limit is not None:
                query = query.limit(limit)

            docs = query.stream()
            results = []
            for doc in docs:
                data = doc.to_dict() or {}
                data["id"] = doc.id
                results.append(data)
            logger.debug(f"Firestore query {collection} returned {len(results)} docs")
            return results
        except Exception as e:
            logger.error(f"Firestore query failed {collection}: {e}")
            raise

    async def update(self, collection: str, doc_id: str, data: dict) -> dict:
        """Update a document. Returns updated document dict."""
        try:
            db = get_db()
            doc_ref = db.collection(collection).document(doc_id)
            doc_ref.update(data)
            # Fetch updated doc
            doc = doc_ref.get()
            result = doc.to_dict() or {}
            result["id"] = doc.id
            logger.debug(f"Firestore update {collection}/{doc_id}")
            return result
        except Exception as e:
            logger.error(f"Firestore update failed {collection}/{doc_id}: {e}")
            raise

    async def delete(self, collection: str, doc_id: str) -> bool:
        """Delete a document. Returns True if deleted, False if not found."""
        try:
            db = get_db()
            doc_ref = db.collection(collection).document(doc_id)
            # Check existence first for accurate return value
            doc = doc_ref.get()
            if not doc.exists:
                logger.debug(f"Firestore delete {collection}/{doc_id} not found")
                return False
            doc_ref.delete()
            logger.debug(f"Firestore delete {collection}/{doc_id}")
            return True
        except Exception as e:
            logger.error(f"Firestore delete failed {collection}/{doc_id}: {e}")
            raise
