from typing import Dict, Any, Optional
from datetime import datetime, timezone
import uuid

from loguru import logger

from app.db.abstract_repository import AbstractRepository
from app.db.firestore_repository import FirestoreRepository
from app.services.risk_matrix import compute_risk_index, get_risk_level, get_tolerability_tier


class HazardReportService:
    """Hazard Report creation with HFACS/ADREP/Nano-codes and risk calculation.

    Stores in tenants/{tenantId}/hazards/reports via AbstractRepository.
    Ensures tenant_id is included in all queries for isolation.
    """

    COLLECTION_TEMPLATE = "tenants/{tenant_id}/hazards"

    def __init__(self, repository: Optional[AbstractRepository] = None):
        self.repository: AbstractRepository = repository or FirestoreRepository()

    def _collection(self, tenant_id: str) -> str:
        return f"tenants/{tenant_id}/hazards"

    def _calculate_risk(self, severity: int, likelihood: int) -> Dict[str, Any]:
        risk_level_value = severity * likelihood
        level = get_risk_level(risk_level_value)
        tier = get_tolerability_tier(risk_level_value)
        return {
            "initial_risk_level_value": risk_level_value,
            "initial_risk_level": level,
            "tolerability_tier": tier,
            "severity": severity,
            "likelihood": likelihood,
        }

    async def create_hazard_report(
        self, tenant_id: str, data: Dict[str, Any], user_id: str
    ) -> Dict[str, Any]:
        """Create hazard report with HFACS/ADREP and auto-calculated risk."""
        if not tenant_id:
            raise ValueError("tenant_id is required for isolation")

        # Validate required fields
        required = ["title", "description", "hfacs_code", "adrep_code", "severity", "likelihood"]
        for field in required:
            if field not in data or data[field] is None:
                raise ValueError(f"Missing required field: {field}")

        severity = int(data["severity"])
        likelihood = int(data["likelihood"])
        if not 1 <= severity <= 5 or not 1 <= likelihood <= 5:
            raise ValueError("severity and likelihood must be 1-5")

        risk = self._calculate_risk(severity, likelihood)

        doc_data = {
            "tenant_id": tenant_id,
            "title": data["title"],
            "description": data["description"],
            "hfacs_code": data["hfacs_code"],
            "adrep_code": data["adrep_code"],
            "severity": severity,
            "likelihood": likelihood,
            "initial_risk_level": risk["initial_risk_level"],
            "initial_risk_level_value": risk["initial_risk_level_value"],
            "tolerability_tier": risk["tolerability_tier"],
            "residual_risk_level": None,
            "residual_risk_value": None,
            "status": "REPORTED",
            "created_by": user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        result = await self.repository.create(self._collection(tenant_id), doc_data)
        logger.info(f"Hazard report {result['id']} created for tenant {tenant_id} risk={risk['initial_risk_level']}")
        return result

    async def get_hazard_report(self, tenant_id: str, report_id: str) -> Optional[Dict[str, Any]]:
        if not tenant_id:
            raise ValueError("tenant_id required")
        return await self.repository.get(self._collection(tenant_id), report_id)

    async def query_hazards(self, tenant_id: str, filters: Optional[Dict[str, Any]] = None) -> list:
        """Query hazards with tenant isolation. Filters are merged with tenant_id."""
        if not tenant_id:
            raise ValueError("tenant_id required")
        # Ensure tenant_id filter is always present
        query_filters = [("tenant_id", "==", tenant_id)]
        if filters:
            for k, v in filters.items():
                query_filters.append((k, "==", v))
        return await self.repository.query(self._collection(tenant_id), filters=query_filters)

    def get_risk_matrix(self) -> Dict[str, Any]:
        """Return 5x5 matrix definition for visualization."""
        # Generate 5x5 color-coded matrix
        matrix = []
        for severity in range(5, 0, -1):  # 5 to 1
            row = []
            for likelihood in range(1, 6):  # 1 to 5
                risk_value = severity * likelihood
                level = get_risk_level(risk_value)
                color = {"Low": "green", "High": "yellow", "Very High": "red"}.get(level, "orange")
                # Refine to 4 colors: green/yellow/orange/red
                if risk_value <= 5:
                    color = "green"
                elif risk_value <= 9:
                    color = "yellow"
                elif risk_value <= 15:
                    color = "orange"
                else:
                    color = "red"
                row.append({
                    "severity": severity,
                    "likelihood": likelihood,
                    "risk_value": risk_value,
                    "risk_level": level,
                    "color": color,
                })
            matrix.append(row)
        return {"matrix": matrix, "severity_labels": [5,4,3,2,1], "likelihood_labels": [1,2,3,4,5]}
