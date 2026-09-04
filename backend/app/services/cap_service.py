from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from loguru import logger

from app.db.abstract_repository import AbstractRepository
from app.db.firestore_repository import FirestoreRepository


class CAPService:
    """CAP creation and management. Uses AbstractRepository."""

    COLLECTION_TEMPLATE = "tenants/{tenant_id}/caps"

    def __init__(self, repository: Optional[AbstractRepository] = None):
        self.repository: AbstractRepository = repository or FirestoreRepository()

    def _collection(self, tenant_id: str) -> str:
        return f"tenants/{tenant_id}/caps"

    async def create_cap(
        self,
        tenant_id: str,
        can_id: str,
        action_items: List[Dict[str, Any]],
        responsible_party: str,
        target_date: str,
        created_by: str,
    ) -> Dict[str, Any]:
        if not tenant_id:
            raise ValueError("tenant_id required")
        if not can_id:
            raise ValueError("can_id required")
        if not action_items:
            raise ValueError("action_items required")
        if not responsible_party:
            raise ValueError("responsible_party required")

        doc = {
            "tenant_id": tenant_id,
            "can_id": can_id,
            "action_items": action_items,
            "responsible_party": responsible_party,
            "target_date": target_date,
            "status": "DRAFT",
            "created_by": created_by,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        result = await self.repository.create(self._collection(tenant_id), doc)
        logger.info(f"CAP {result['id']} created for CAN {can_id} tenant {tenant_id}")
        return result

    async def get_cap(self, tenant_id: str, cap_id: str) -> Optional[Dict[str, Any]]:
        if not tenant_id:
            raise ValueError("tenant_id required")
        return await self.repository.get(self._collection(tenant_id), cap_id)

    async def list_caps_for_can(self, tenant_id: str, can_id: str) -> List[Dict[str, Any]]:
        if not tenant_id:
            raise ValueError("tenant_id required")
        return await self.repository.query(
            self._collection(tenant_id),
            filters=[("tenant_id", "==", tenant_id), ("can_id", "==", can_id)]
        )

    async def update_status(self, tenant_id: str, cap_id: str, new_status: str) -> Dict[str, Any]:
        from app.services.state_machine import CAPStateMachine
        cap = await self.get_cap(tenant_id, cap_id)
        if not cap:
            raise ValueError("CAP not found")
        if not CAPStateMachine.can_transition(cap["status"], new_status):
            raise ValueError(f"Invalid CAP transition {cap['status']} -> {new_status}")
        return await self.repository.update(self._collection(tenant_id), cap_id, {"status": new_status, "updated_at": datetime.now(timezone.utc).isoformat()})
