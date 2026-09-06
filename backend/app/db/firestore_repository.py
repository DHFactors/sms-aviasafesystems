"""Firestore repository — DEPRECATED stub.

Firestore data plane migrated to Postgres (Batches 0-4). This stub remains
solely so legacy imports (e.g. hazard_service, regulator_dashboard) do not
crash. All methods are no-ops that log a warning and return empty results.
New code must use app.db.pg.
"""

from typing import List, Dict, Optional, Any
from loguru import logger

from app.db.abstract_repository import AbstractRepository


class FirestoreRepository(AbstractRepository):
    """Deprecated no-op Firestore repository."""

    def __init__(self, *args, **kwargs):
        logger.warning("FirestoreRepository instantiated — Firestore deprecated, returning no-op stub")

    async def create(self, collection: str, data: dict) -> dict:
        logger.warning(f"FirestoreRepository.create({collection}) — deprecated, no-op")
        return {"id": "dummy", **data}

    async def get(self, collection: str, doc_id: str) -> Optional[dict]:
        logger.warning(f"FirestoreRepository.get({collection}/{doc_id}) — deprecated, returning None")
        return None

    async def query(
        self,
        collection: str,
        filters: Optional[List[tuple]] = None,
        order_by: Optional[List[tuple]] = None,
        limit: Optional[int] = None
    ) -> List[dict]:
        logger.warning(f"FirestoreRepository.query({collection}) — deprecated, returning []")
        return []

    async def update(self, collection: str, doc_id: str, data: dict) -> dict:
        logger.warning(f"FirestoreRepository.update({collection}/{doc_id}) — deprecated, no-op")
        return data

    async def delete(self, collection: str, doc_id: str) -> bool:
        logger.warning(f"FirestoreRepository.delete({collection}/{doc_id}) — deprecated, no-op")
        return True

    # Legacy sync helpers used by some services — keep as no-ops
    def create_sync(self, *a, **kw): return self.create(*a, **kw)
    def get_sync(self, *a, **kw): return self.get(*a, **kw)
