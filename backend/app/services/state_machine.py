from typing import Dict, Any

# CAN state machine: DRAFT → ISSUED → ACKNOWLEDGED → IN_PROGRESS → COMPLETED → VERIFIED
CAN_TRANSITIONS = {
    "DRAFT": ["ISSUED"],
    "ISSUED": ["ACKNOWLEDGED"],
    "ACKNOWLEDGED": ["IN_PROGRESS"],
    "IN_PROGRESS": ["COMPLETED"],
    "COMPLETED": ["VERIFIED"],
    "VERIFIED": [],
}

# CAP state machine: DRAFT → IN_PROGRESS → UNDER_REVIEW → APPROVED → IMPLEMENTED
CAP_TRANSITIONS = {
    "DRAFT": ["IN_PROGRESS"],
    "IN_PROGRESS": ["UNDER_REVIEW"],
    "UNDER_REVIEW": ["APPROVED"],
    "APPROVED": ["IMPLEMENTED"],
    "IMPLEMENTED": [],
}

class CANStateMachine:
    @staticmethod
    def can_transition(current: str, next_state: str) -> bool:
        return next_state in CAN_TRANSITIONS.get(current, [])

    @staticmethod
    def allowed_transitions(state: str):
        return CAN_TRANSITIONS.get(state, [])

class CAPStateMachine:
    @staticmethod
    def can_transition(current: str, next_state: str) -> bool:
        return next_state in CAP_TRANSITIONS.get(current, [])

    @staticmethod
    def allowed_transitions(state: str):
        return CAP_TRANSITIONS.get(state, [])


async def update_hazard_register(
    repository,
    tenant_id: str,
    hazard_id: str,
    cap: Dict[str, Any],
) -> Dict[str, Any]:
    """Auto-update hazard register after CAP completion.

    Updates risk level, documents effectiveness, closes loop.
    Uses repository to ensure tenant isolation.
    """
    # Fetch hazard
    hazard = await repository.get(f"tenants/{tenant_id}/hazards", hazard_id)
    if not hazard:
        raise ValueError("Hazard not found for register update")

    # Example: reduce risk based on CAP effectiveness
    # In real flow, SRAM residual risk would be used; here we simulate
    new_risk = cap.get("residual_risk_level") or "Low"
    updates = {
        "residual_risk_level": new_risk,
        "status": "CLOSED" if cap.get("status") == "IMPLEMENTED" else hazard.get("status"),
        "cap_id": cap.get("id"),
        "effectiveness_notes": cap.get("effectiveness_notes", "Controls implemented per CAP"),
        "updated_at": cap.get("updated_at"),
        "tenant_id": tenant_id,  # ensure isolation
    }

    updated = await repository.update(f"tenants/{tenant_id}/hazards", hazard_id, updates)
    return updated
