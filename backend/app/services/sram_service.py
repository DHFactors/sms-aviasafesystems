from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import uuid

from loguru import logger

from app.db.abstract_repository import AbstractRepository
from app.db.firestore_repository import FirestoreRepository
from app.services.risk_matrix import compute_risk_index, get_risk_level


class SRAMService:
    """SRAM (Safety Risk Assessment Matrix) assessment flow.

    Stores in tenants/{tenantId}/sram_assessments via AbstractRepository.
    Supports Bow-Tie and Fish-Bone analysis tools.
    """

    COLLECTION_TEMPLATE = "tenants/{tenant_id}/sram_assessments"
    VALID_TOOLS = {"Bow-Tie", "Fish-Bone"}

    def __init__(self, repository: Optional[AbstractRepository] = None):
        self.repository: AbstractRepository = repository or FirestoreRepository()

    def _collection(self, tenant_id: str) -> str:
        return f"tenants/{tenant_id}/sram_assessments"

    async def create_assessment(
        self,
        tenant_id: str,
        hazard_id: str,
        reviewer_id: str,
        tool: str,
        barriers: Dict[str, List[str]],
        severity: int,
        likelihood: int,
    ) -> Dict[str, Any]:
        if not tenant_id:
            raise ValueError("tenant_id required")
        if tool not in self.VALID_TOOLS:
            raise ValueError(f"tool must be one of {self.VALID_TOOLS}")
        if not 1 <= severity <= 5 or not 1 <= likelihood <= 5:
            raise ValueError("severity/likelihood must be 1-5")

        final_risk_value = severity * likelihood
        final_risk_level = get_risk_level(final_risk_value)

        doc = {
            "tenant_id": tenant_id,
            "hazard_id": hazard_id,
            "reviewer_id": reviewer_id,
            "tool": tool,
            "preventive_barriers": barriers.get("preventive", []),
            "reactive_barriers": barriers.get("reactive", []),
            "severity": severity,
            "likelihood": likelihood,
            "final_risk_value": final_risk_value,
            "final_risk_level": final_risk_level,
            "status": "COMPLETED",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        result = await self.repository.create(self._collection(tenant_id), doc)
        logger.info(f"SRAM assessment {result['id']} for hazard {hazard_id} tenant {tenant_id} tool={tool} risk={final_risk_level}")
        return result

    async def get_assessment(self, tenant_id: str, assessment_id: str) -> Optional[Dict[str, Any]]:
        if not tenant_id:
            raise ValueError("tenant_id required")
        return await self.repository.get(self._collection(tenant_id), assessment_id)

    async def list_for_hazard(self, tenant_id: str, hazard_id: str) -> List[Dict[str, Any]]:
        if not tenant_id:
            raise ValueError("tenant_id required")
        return await self.repository.query(
            self._collection(tenant_id),
            filters=[("tenant_id", "==", tenant_id), ("hazard_id", "==", hazard_id)]
        )
