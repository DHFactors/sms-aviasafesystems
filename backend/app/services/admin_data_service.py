# ============================================================================
# FILE: admin_data_service.py
# PATH: backend/app/services/admin_data_service.py
# PURPOSE: Super-Admin data-management helpers:
#            * Tenant lifecycle status (Trial / Active / Inactive) driven by
#              contract dates + payment status.
#            * Seed / unseed dummy operational data (VSR, MOR, CAN, CAP) for
#              one tenant or every tenant.
#          Every mutation is recorded in the `audit_logs` collection and any
#          doc written by the seeder carries the ADMIN_DEMO_SEED_VERSION marker
#          so an unseed only ever removes its own dummy data.
# AUTHOR: AviaSAFE Systems
# ============================================================================

import random
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

from app.core.config import settings
from app.firebase import get_db
from app.services.risk_matrix import compute_risk_index, get_risk_level
from app.services.production_seed import _audit, _validate_id

TENANT_STATUSES = {"Trial", "Active", "Inactive"}
PAYMENT_STATUSES = {"Paid", "Unpaid"}
DEMO_KINDS = {"vsr", "mor", "can", "cap"}

ADMIN_DEMO_SEED_VERSION = "admin-demo-1"
ADMIN_DEMO_CREATOR = "admin-seed"

_HAZARDS_COLLECTION = "hazards"
_CAN_CAP_COLLECTION = "can_cap"
_CAPS_SUBCOLLECTION = "caps"

_DEPARTMENTS = ["Flight Operations", "Maintenance & Engineering",
                "Ground Handling", "Cabin Crew", "Administration"]
_ICAO_CATEGORIES = ["LOCI", "CFIT", "RE", "RI", "MAC", "WX", "ENG", "SYS",
                    "FIRE", "BIRD", "GCOL", "CABIN", "ARC", "OTHER"]
_ICAO_TO_TAXONOMY = {
    "LOCI": "Organizational-Facilities", "CFIT": "Organizational-Facilities",
    "RE": "Organizational-Facilities", "RI": "Organizational-Facilities",
    "GCOL": "Organizational-Facilities", "MAC": "Technical", "ENG": "Technical",
    "SYS": "Technical", "FIRE": "Technical", "BIRD": "Wildlife",
    "CABIN": "Human Factors", "ARC": "Organizational-Documentation, Processes and Procedures",
    "PRO": "Organizational-Documentation, Processes and Procedures",
    "WX": "Environmental", "OTHER": "Other",
}

DEFAULT_SEED_COUNTS = {"vsr": 5, "mor": 3, "can": 3, "cap": 1}


def _tenant_ref(tenant_id: str):
    return get_db().collection(settings.FIREBASE_COLLECTION_TENANTS).document(tenant_id)


def _get_tenant(tenant_id: str) -> Dict[str, Any]:
    snap = _tenant_ref(tenant_id).get()
    if not snap.exists:
        raise ValueError(f"tenant not found: {tenant_id}")
    return snap.to_dict() or {}


# ============================================================================
# Tenant lifecycle status
# ============================================================================

def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError as e:
        raise ValueError(f"invalid date '{value}' (expected YYYY-MM-DD)") from e


def derive_tenant_status(contract: Optional[Dict[str, Any]],
                         payment_status: Optional[str] = None,
                         explicit: Optional[str] = None) -> str:
    """Compute the tenant lifecycle status.

    Rules (an explicit `status` wins over everything):
      * payment_status == 'Unpaid'           -> Inactive
      * today > contract.end_date            -> Inactive (contract expired)
      * today < contract.start_date          -> Trial (contract not yet started)
      * otherwise                            -> Active
    """
    if explicit:
        if explicit not in TENANT_STATUSES:
            raise ValueError(f"invalid status '{explicit}' (allowed: {sorted(TENANT_STATUSES)})")
        return explicit

    if payment_status == "Unpaid":
        return "Inactive"

    today = date.today()
    contract = contract or {}
    try:
        start = _parse_date(contract.get("start_date"))
        end = _parse_date(contract.get("end_date"))
    except ValueError:
        start = end = None
    if end and today > end:
        return "Inactive"
    if start and today < start:
        return "Trial"
    return "Active"


def update_tenant_status(tenant_id: str, actor: Dict[str, Any],
                         status: Optional[str] = None,
                         contract_start_date: Optional[str] = None,
                         contract_end_date: Optional[str] = None,
                         payment_status: Optional[str] = None) -> Dict[str, Any]:
    """Update a tenant's lifecycle status + contract/payment metadata.

    `status` may be set explicitly (Trial/Active/Inactive) or left None to
    derive it from the contract dates and payment status. Returns the updated
    tenant document.
    """
    tid = _validate_id(tenant_id, "tenant id")
    doc = _get_tenant(tid)

    if status is not None and status not in TENANT_STATUSES:
        raise ValueError(f"invalid status '{status}' (allowed: {sorted(TENANT_STATUSES)})")
    if payment_status is not None and payment_status not in PAYMENT_STATUSES:
        raise ValueError(f"invalid payment status '{payment_status}' (allowed: {sorted(PAYMENT_STATUSES)})")

    if contract_start_date:
        _parse_date(contract_start_date)
    if contract_end_date:
        _parse_date(contract_end_date)

    contract = dict(doc.get("contract") or {})
    if contract_start_date:
        contract["start_date"] = contract_start_date.strip()
    if contract_end_date:
        contract["end_date"] = contract_end_date.strip()

    resolved = derive_tenant_status(contract, payment_status or doc.get("payment_status"), status)
    now = datetime.now(timezone.utc)

    updates = {
        "status": resolved,
        "active": resolved == "Active",
        "contract": contract,
        "status_updated_at": now,
        "status_updated_by": actor.get("uid"),
        "updated_at": now,
    }
    if payment_status:
        updates["payment_status"] = payment_status

    _tenant_ref(tid).set(updates, merge=True)

    merged = dict(doc)
    merged.update(updates)
    _audit("TENANT_STATUS_UPDATED", actor, tid,
           f"Status set to {resolved} (contract start={contract.get('start_date') or 'n/a'}, "
           f"end={contract.get('end_date') or 'n/a'}, payment={updates.get('payment_status') or doc.get('payment_status') or 'n/a'})")
    logger.info(f"Tenant {tid} status -> {resolved} by {actor.get('uid')}")
    return merged


# ============================================================================
# Dummy data doc builders (marked so unseed only touches its own docs)
# ============================================================================

def _report_doc(tenant_id: str, report_type: str, idx: int, created_at: datetime) -> dict:
    severity = random.randint(2, 5)
    probability = random.randint(1, 4)
    risk_index = compute_risk_index(severity, probability)
    return {
        "tenant_id": tenant_id,
        "tenantId": tenant_id,
        "report_type": report_type,
        "status": "NEW",
        "ai_status": "PENDING",
        "narrative": f"Dummy {'voluntary' if report_type == 'voluntary' else 'mandatory'} safety report {idx + 1} for {tenant_id}.",
        "location": random.choice(["KTM", "Pokhara", "Bhairahawa", "In-flight", "Kathmandu Valley"]),
        "occurrence_type": "Report",
        "occurrence_category": random.choice(_ICAO_CATEGORIES),
        "severity": str(severity),
        "severity_level": severity,
        "probability": probability,
        "probability_level": probability,
        "risk_index": risk_index,
        "risk_level": get_risk_level(risk_index),
        "is_anonymous": random.random() < 0.5,
        "occurrence_date": created_at.isoformat(),
        "created_by": ADMIN_DEMO_CREATOR,
        "created_at": created_at,
        "updated_at": created_at,
        "seed_version": ADMIN_DEMO_SEED_VERSION,
        "admin_seed": True,
    }


def _hazard_doc(tenant_id: str, idx: int, created_at: datetime) -> dict:
    severity = random.randint(2, 4)
    probability = random.randint(2, 4)
    risk_index = compute_risk_index(severity, probability)
    cat = random.choice(_ICAO_CATEGORIES)
    return {
        "tenant_id": tenant_id,
        "hazard_id": f"{tenant_id}-HZ-DEMO-{idx + 1:03d}",
        "title": f"Dummy hazard {idx + 1} at {tenant_id}",
        "description": f"Dummy demonstration hazard {idx + 1} created by the Super-Admin seed tool.",
        "source": "Internal Audit",
        "occurrence_category": cat,
        "taxonomy": _ICAO_TO_TAXONOMY.get(cat, "Other"),
        "severity": severity,
        "probability": probability,
        "risk_index": risk_index,
        "risk_level": get_risk_level(risk_index),
        "priority": "H" if risk_index >= 12 else "M" if risk_index >= 6 else "L",
        "status": "Open",
        "created_by": ADMIN_DEMO_CREATOR,
        "created_at": created_at,
        "updated_at": created_at,
        "seed_version": ADMIN_DEMO_SEED_VERSION,
        "admin_seed": True,
    }


def _can_doc(tenant_id: str, hazard_id: str, idx: int, created_at: datetime) -> dict:
    priority = random.choice(["High", "Medium", "Low"])
    return {
        "can_reference": f"CAN-DEMO-{idx + 1:03d}",
        "hazard_id": hazard_id,
        "title": f"Dummy corrective action {idx + 1}",
        "description": f"Dummy corrective action notice {idx + 1} for {tenant_id}.",
        "required_action": "Implement the agreed corrective action and report back.",
        "target_completion_date": (created_at + timedelta(days=random.randint(14, 60))).date().isoformat(),
        "assigned_to": "admin-seed",
        "assigned_to_uid": "admin-seed",
        "department": random.choice(_DEPARTMENTS),
        "priority": priority,
        "status": "Open",
        "issued_by": ADMIN_DEMO_CREATOR,
        "issued_by_uid": ADMIN_DEMO_CREATOR,
        "issued_at": created_at,
        "tenant_id": tenant_id,
        "created_by": ADMIN_DEMO_CREATOR,
        "created_at": created_at,
        "updated_at": created_at,
        "seed_version": ADMIN_DEMO_SEED_VERSION,
        "admin_seed": True,
    }


def _cap_doc(can_reference: str, idx: int, created_at: datetime) -> dict:
    return {
        "cap_reference": f"{can_reference}-CAP-{idx + 1:03d}",
        "action_plan": "Dummy corrective/preventive action plan describing the mitigation steps.",
        "timeline": f"{random.randint(30, 90)} days",
        "resources_required": "Manpower and materials per the plan",
        "implementation_plan": "Phase the work, verify effectiveness, and close out.",
        "target_completion_date": (created_at + timedelta(days=random.randint(30, 90))).date().isoformat(),
        "status": "In Progress",
        "submitted_by": ADMIN_DEMO_CREATOR,
        "submitted_by_uid": ADMIN_DEMO_CREATOR,
        "submitted_at": created_at,
        "created_at": created_at,
        "updated_at": created_at,
        "seed_version": ADMIN_DEMO_SEED_VERSION,
        "admin_seed": True,
    }


# ============================================================================
# Seed / unseed dummy data
# ============================================================================

def _normalize_kinds(kinds: List[str]) -> List[str]:
    out = []
    for k in kinds or []:
        k = (k or "").strip().lower()
        if k not in DEMO_KINDS:
            raise ValueError(f"invalid demo-data kind '{k}' (allowed: {sorted(DEMO_KINDS)})")
        if k not in out:
            out.append(k)
    if not out:
        raise ValueError("at least one kind is required (vsr, mor, can, cap)")
    return out


def seed_tenant_demo_data(tenant_id: str, kinds: List[str], actor: Dict[str, Any]) -> Dict[str, Any]:
    """Seed dummy VSR/MOR/CAN/CAP documents for one tenant."""
    tid = _validate_id(tenant_id, "tenant id")
    _get_tenant(tid)  # 404 if missing
    kinds = _normalize_kinds(kinds)

    now = datetime.now(timezone.utc)
    ref = _tenant_ref(tid)
    counts = {k: 0 for k in kinds}

    if "vsr" in kinds or "mor" in kinds:
        if "vsr" in kinds:
            for i in range(DEFAULT_SEED_COUNTS["vsr"]):
                ref.collection(settings.FIREBASE_COLLECTION_REPORTS).add(
                    _report_doc(tid, "voluntary", i, now - timedelta(days=i)))
            counts["vsr"] = DEFAULT_SEED_COUNTS["vsr"]
        if "mor" in kinds:
            for i in range(DEFAULT_SEED_COUNTS["mor"]):
                ref.collection(settings.FIREBASE_COLLECTION_REPORTS).add(
                    _report_doc(tid, "mandatory", i, now - timedelta(days=i)))
            counts["mor"] = DEFAULT_SEED_COUNTS["mor"]

    if "can" in kinds or "cap" in kinds:
        n = DEFAULT_SEED_COUNTS["can"]
        hazard_ids = []
        for i in range(n):
            hz = ref.collection(_HAZARDS_COLLECTION).add(
                _hazard_doc(tid, i, now - timedelta(days=i)))
            hazard_ids.append(hz[1].id)
        for i, hazard_id in enumerate(hazard_ids):
            ref.collection(_CAN_CAP_COLLECTION).add(_can_doc(tid, hazard_id, i, now - timedelta(days=i)))
        counts["can"] = n

        if "cap" in kinds:
            can_docs = ref.collection(_CAN_CAP_COLLECTION).where("seed_version", "==", ADMIN_DEMO_SEED_VERSION).get()
            for i, snap in enumerate(can_docs):
                data = snap.to_dict() or {}
                snap.reference.collection(_CAPS_SUBCOLLECTION).add(_cap_doc(data.get("can_reference", f"CAN-DEMO-{i + 1:03d}"), i, now - timedelta(days=i)))
            counts["cap"] = len(can_docs)

    _audit("DEMO_DATA_SEED", actor, tid,
           f"Seeded {', '.join(f'{k}={counts[k]}' for k in kinds)} for tenant {tid}")
    logger.info(f"Demo data seeded for {tid}: {counts}")
    return {"tenant_id": tid, "seeded": counts}


def unseed_tenant_demo_data(tenant_id: str, kinds: List[str], actor: Dict[str, Any]) -> Dict[str, Any]:
    """Remove only the Super-Admin-seeded dummy docs for one tenant."""
    tid = _validate_id(tenant_id, "tenant id")
    _get_tenant(tid)
    kinds = _normalize_kinds(kinds)

    ref = _tenant_ref(tid)
    counts = {k: 0 for k in kinds}

    if "vsr" in kinds or "mor" in kinds:
        report_types = []
        if "vsr" in kinds:
            report_types.append("voluntary")
        if "mor" in kinds:
            report_types.append("mandatory")
        for snap in ref.collection(settings.FIREBASE_COLLECTION_REPORTS).get():
            data = snap.to_dict() or {}
            if data.get("seed_version") == ADMIN_DEMO_SEED_VERSION and data.get("report_type") in report_types:
                snap.reference.delete()
                counts["vsr" if data.get("report_type") == "voluntary" else "mor"] += 1

    if "can" in kinds or "cap" in kinds:
        seeded_cans = []
        for snap in ref.collection(_CAN_CAP_COLLECTION).get():
            data = snap.to_dict() or {}
            if data.get("seed_version") == ADMIN_DEMO_SEED_VERSION:
                seeded_cans.append(snap)

        if "cap" in kinds and "can" not in kinds:
            # Remove only the CAPs, keep the CANs and their hazards.
            for snap in seeded_cans:
                caps = list(snap.reference.collection(_CAPS_SUBCOLLECTION).get())
                for cap in caps:
                    cap.reference.delete()
                counts["cap"] += len(caps)
        elif "can" in kinds:
            # Full CAN (+CAP) unseed: remove CAPs, then CANs, then the hazards
            # created for those CANs (tagged admin_seed only).
            removed_cans = 0
            removed_caps = 0
            for snap in seeded_cans:
                caps = list(snap.reference.collection(_CAPS_SUBCOLLECTION).get())
                for cap in caps:
                    cap.reference.delete()
                removed_caps += len(caps)
                snap.reference.delete()
                removed_cans += 1
            counts["can"] = removed_cans
            if "cap" in kinds:
                counts["cap"] = removed_caps
            for snap in ref.collection(_HAZARDS_COLLECTION).get():
                data = snap.to_dict() or {}
                if data.get("admin_seed") and data.get("seed_version") == ADMIN_DEMO_SEED_VERSION:
                    snap.reference.delete()

    _audit("DEMO_DATA_UNSEED", actor, tid,
           f"Removed {', '.join(f'{k}={counts[k]}' for k in kinds)} dummy docs for tenant {tid}")
    logger.info(f"Demo data unseeded for {tid}: {counts}")
    return {"tenant_id": tid, "removed": counts}


def demo_data_scope(tenant_ids: Optional[List[str]] = None, all_tenants: bool = True) -> List[str]:
    """Resolve the target tenant ids for a seed/unseed action."""
    if tenant_ids:
        return [_validate_id(t, "tenant id") for t in tenant_ids]
    if all_tenants:
        try:
            return [d.id for d in get_db().collection(settings.FIREBASE_COLLECTION_TENANTS).get()]
        except Exception as e:
            logger.error(f"Failed to list tenants for demo-data scope: {e}")
            return []
    return []
