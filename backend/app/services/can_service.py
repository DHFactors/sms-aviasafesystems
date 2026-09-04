from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta

from loguru import logger

from app.db.abstract_repository import AbstractRepository
from app.db.firestore_repository import FirestoreRepository


class CANService:
    """CAN auto-generation and management. Uses AbstractRepository."""

    COLLECTION_TEMPLATE = "tenants/{tenant_id}/cans"
    # Risk levels that trigger CAN
    TRIGGER_LEVELS = {"High", "Very High", "Tolerable", "Unacceptable"}
    # Map legacy tolerability to trigger check
    TRIGGER_TIERS = {"HIGH", "VERY HIGH"}

    def __init__(self, repository: Optional[AbstractRepository] = None, tenant_config: Optional[Dict[str, str]] = None):
        self.repository: AbstractRepository = repository or FirestoreRepository()
        # tenant_id -> department mapping, e.g. {"fixedwing": "Flight Operations"}
        self.tenant_config = tenant_config or {}

    def _collection(self, tenant_id: str) -> str:
        return f"tenants/{tenant_id}/cans"

    def _due_date_for_priority(self, priority: str) -> str:
        now = datetime.now(timezone.utc)
        days = {"High": 7, "Medium": 14, "Low": 30}.get(priority, 14)
        return (now + timedelta(days=days)).isoformat()

    def _priority_from_risk(self, risk_level: str) -> str:
        if risk_level == "Very High":
            return "High"
        if risk_level == "High":
            return "Medium"
        return "Low"

    async def maybe_create_can(
        self,
        tenant_id: str,
        hazard: Dict[str, Any],
        risk_level: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Auto-generate CAN if risk is Unacceptable/Tolerable (High/Very High)."""
        if not tenant_id:
            raise ValueError("tenant_id required")
        # Normalize risk level
        norm = risk_level.strip() if risk_level else ""
        # Check trigger
        is_trigger = norm in self.TRIGGER_LEVELS or norm.upper() in self.TRIGGER_TIERS
        # Also handle "Unacceptable" -> Very High
        if norm.lower() == "unacceptable":
            is_trigger = True
        if not is_trigger:
            logger.info(f"CAN not triggered for hazard {hazard.get('id')} risk={risk_level}")
            return None

        priority = self._priority_from_risk(norm if norm in ("Very High", "High", "Low") else "High")
        department = self.tenant_config.get(tenant_id, "Safety")

        doc = {
            "tenant_id": tenant_id,
            "hazard_id": hazard.get("id") or hazard.get("hazard_id"),
            "title": title or f"CAN for hazard: {hazard.get('title', 'Untitled')}",
            "description": description or hazard.get("description", ""),
            "assigned_to": department,
            "due_date": self._due_date_for_priority(priority),
            "status": "DRAFT",
            "priority": priority,
            "risk_level": risk_level,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        result = await self.repository.create(self._collection(tenant_id), doc)
        logger.info(f"CAN {result['id']} auto-generated for hazard {hazard.get('id')} tenant {tenant_id} priority={priority}")
        return result

    async def get_can(self, tenant_id: str, can_id: str) -> Optional[Dict[str, Any]]:
        if not tenant_id:
            raise ValueError("tenant_id required")
        return await self.repository.get(self._collection(tenant_id), can_id)

    async def list_cans(self, tenant_id: str) -> List[Dict[str, Any]]:
        if not tenant_id:
            raise ValueError("tenant_id required")
        return await self.repository.query(self._collection(tenant_id), filters=[("tenant_id", "==", tenant_id)])

    async def update_status(self, tenant_id: str, can_id: str, new_status: str) -> Dict[str, Any]:
        from app.services.state_machine import CANStateMachine
        can = await self.get_can(tenant_id, can_id)
        if not can:
            raise ValueError("CAN not found")
        if not CANStateMachine.can_transition(can["status"], new_status):
            raise ValueError(f"Invalid CAN transition {can['status']} -> {new_status}")
        return await self.repository.update(self._collection(tenant_id), can_id, {"status": new_status, "updated_at": datetime.now(timezone.utc).isoformat()})
