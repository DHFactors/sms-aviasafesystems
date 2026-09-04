# ==============================================================================
# File: backend/app/services/hazard_service.py
# Description: Multi-tenant repository and business logic for Hazard tracking,
#              ICAO 5x5 risk evaluation, and HFACS RCA management, backed by
#              PostgreSQL (Supabase).
#
#              The class reconciles the two historical interfaces onto one
#              Postgres-backed service:
#                * HazardService(tenant_id)  - legacy sync API used by the
#                  mounted hazards router (create_hazard(payload, user), list,
#                  get, update, status, assign, stats). Sync methods dispatch
#                  onto the shared async engine via app.db.runner.
#                * HazardService(db=...)     - retained for backward
#                  compatibility (the unmounted hazard_analysis router). Its
#                  async methods (create_hazard(tenant_id, payload, user_info),
#                  add_rca_factor, record_assessment, add_capa) are likewise
#                  Postgres-backed, against the v2 RCA table set.
#              create_hazard() is a dispatcher: 2-arg calls (payload, user)
#              take the sync v1 path, 3-arg calls (tenant_id, payload, user)
#              take the async v2 path.
# ==============================================================================

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import or_, select

from app.core.config import settings
from app.db.db_models import (
    Hazard,
    HazardAssessment,
    HazardCapa,
    HazardRcaEntry,
    HazardRcaFactor,
)
from app.db.ids import get_tenant_shorthand, register_tenant, tenant_slug, tenant_uuid
from app.db.isolation import demo_scope
from app.db.runner import run
from app.db.schema_init import ensure_v2_schema_async
from app.db.session import session_scope
from app.services.risk_matrix import (
    classify_risk,
    compute_risk_index,
    get_thresholds,
    get_tolerability_tier,
    normalize_tolerability,
    risk_outcome,
)
from app.services.users import get_user_department
from app.db.abstract_repository import AbstractRepository
from app.db.firestore_repository import FirestoreRepository

# ICAO Doc 9859 Standard Risk Tolerability Lookups
TOLERABILITY_MATRIX = {
    ("A", 5): "intolerable", ("B", 5): "intolerable", ("C", 5): "intolerable", ("D", 5): "intolerable", ("E", 5): "intolerable",
    ("A", 4): "intolerable", ("B", 4): "intolerable", ("C", 4): "intolerable", ("D", 4): "tolerable",   ("E", 4): "tolerable",
    ("A", 3): "intolerable", ("B", 3): "intolerable", ("C", 3): "tolerable",   ("D", 3): "tolerable",   ("E", 3): "acceptable",
    ("A", 2): "tolerable",   ("B", 2): "tolerable",   ("C", 2): "tolerable",   ("D", 2): "acceptable",  ("E", 2): "acceptable",
    ("A", 1): "tolerable",   ("B", 1): "acceptable",  ("C", 1): "acceptable",  ("D", 1): "acceptable",  ("E", 1): "acceptable",
}

SEVERITY_LABELS = {5: "Catastrophic", 4: "Hazardous", 3: "Major", 2: "Minor", 1: "Negligible"}
PROBABILITY_LABELS = {"A": "Frequent", "B": "Occasional", "C": "Remote", "D": "Improbable", "E": "Extremely Improbable"}


def generate_hazard_id(tenant_code: str, priority: str, year: int, seq: int) -> str:
    """Generate the hazard reference per the CAAN SRM Procedure Manual format.

    Format: {TENANT_CODE}-{SEQ:03d}-{PRIORITY}-{YEAR}
    Example: FW-001-H-2026

    Args:
        tenant_code: 2-letter tenant code (FW, RW, AP, ST).
        priority: H, M, or L.
        year: 4-digit year (e.g. 2026).
        seq: Sequence number (e.g. 1, 2, 3).
    """
    priority_code = (priority or "M").upper()
    if priority_code not in ("H", "M", "L"):
        priority_code = "M"
    return f"{tenant_code.upper()}-{seq:03d}-{priority_code}-{year}"


_HZ_MUTABLE_COLUMNS = [
    c.name for c in Hazard.__table__.columns
    if c.name not in ("id", "tenant_id", "hazard_id", "is_demo", "created_at", "updated_at")
]


def _row_to_dict(row: Hazard) -> dict:
    data = {}
    for col in Hazard.__table__.columns:
        value = getattr(row, col.name)
        if isinstance(value, uuid.UUID):
            value = str(value)
        data[col.name] = value
    data["tenant_id"] = tenant_slug(row.tenant_id)
    _serialize_timestamps(data)
    return data


def _serialize_timestamps(data: dict) -> None:
    for key in ("created_at", "updated_at", "srm_date", "follow_up_date", "closed_at"):
        if key in data and hasattr(data[key], "isoformat"):
            data[key] = data[key].isoformat()


def _lookup_hazard_stmt(tenant_uuid_value: str, value: str):
    conds = [Hazard.hazard_id == str(value)]
    try:
        conds.append(Hazard.id == uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        pass
    scope = [Hazard.is_demo == demo_scope()]
    if tenant_uuid_value:
        return (
            select(Hazard)
            .where(Hazard.tenant_id == tenant_uuid_value, *scope, or_(*conds))
            .limit(1)
        )
    return select(Hazard).where(*scope, or_(*conds)).limit(1)


class HazardService:
    COLLECTION = "hazards"

    def __init__(
        self,
        tenant_id: Optional[str] = None,
        db: Any = None,
        repository: Optional[AbstractRepository] = None,
    ):
        self.tenant_id = tenant_id
        # `db` is accepted for backward compatibility with the unmounted
        # hazard_analysis router; all persistence is now PostgreSQL-backed.
        self.db = db
        # Migration-ready DAL: inject repository (defaults to Firestore for legacy
        # collections). All queries are tenant-isolated via tenant_id.
        self.repository: AbstractRepository = repository or FirestoreRepository()

    # ==========================================================================
    # create_hazard dispatcher
    # ==========================================================================

    def create_hazard(self, *args, **kwargs):
        if len(args) >= 3 or ("payload" in kwargs and "tenant_id" in kwargs):
            return self.create_hazard_v2(*args, **kwargs)
        return self.create_hazard_v1(*args, **kwargs)

    # ==========================================================================
    # v1 sync API (mounted routes)
    # ==========================================================================

    def create_hazard_v1(self, payload: dict, user: dict) -> dict:
        return run(self._create_hazard_v1_async(payload, user))

    async def _create_hazard_v1_async(self, payload: dict, user: dict) -> dict:
        now = datetime.now(timezone.utc)
        year = now.year

        severity = payload.get("severity")
        probability = payload.get("probability")
        risk_index = payload.get("risk_index")
        risk_level = payload.get("risk_level")
        risk_out = payload.get("risk_outcome")
        tolerability_tier = payload.get("tolerability_tier")

        if severity is not None and probability is not None:
            computed_risk_index = compute_risk_index(severity, probability)
            thresholds = get_thresholds(self.tenant_id)
            if risk_index is None:
                risk_index = computed_risk_index
            if risk_level is None:
                risk_level = classify_risk(computed_risk_index, thresholds)
            if risk_out is None:
                risk_out = risk_outcome(severity, probability, thresholds)
            if tolerability_tier is None:
                tolerability_tier = get_tolerability_tier(computed_risk_index, thresholds)
        elif risk_index is not None and risk_level is None:
            thresholds = get_thresholds(self.tenant_id)
            risk_level = classify_risk(risk_index, thresholds)
            tolerability_tier = get_tolerability_tier(risk_index, thresholds)

        if tolerability_tier is None and risk_level is not None:
            tolerability_tier = normalize_tolerability(risk_level)

        taxonomy = payload.get("taxonomy", "Other")
        tid = register_tenant(self.tenant_id)

        async with session_scope() as session:
            sequence = 1
            existing = await session.scalars(
                select(Hazard.hazard_id).where(
                    Hazard.tenant_id == tid,
                    Hazard.is_demo == demo_scope(),
                )
            )
            max_seq = 0
            for hid in existing:
                # FW-001-H-2026
                parts = hid.split("-")
                if len(parts) == 4 and parts[3] == str(year):
                    try:
                        seq = int(parts[1])
                        if seq > max_seq:
                            max_seq = seq
                    except ValueError:
                        pass
            sequence = max_seq + 1
            priority = payload.get("priority") or "M"
            tenant_code = get_tenant_shorthand(self.tenant_id)
            hazard_id = generate_hazard_id(tenant_code, priority, year, sequence)

            row = Hazard(
                tenant_id=tid,
                hazard_id=hazard_id,
                title=payload.get("title") or "",
                description=payload.get("description") or "",
                source=payload.get("source") or "",
                source_id=payload.get("source_id") or "",
                source_url=payload.get("source_url"),
                adrep_category=payload.get("adrep_category"),
                occurrence_type=payload.get("occurrence_type"),
                taxonomy=taxonomy,
                taxonomy_specific=payload.get("taxonomy_specific"),
                consequence=payload.get("consequence"),
                severity=severity,
                probability=probability,
                risk_index=risk_index,
                risk_level=risk_level,
                risk_outcome=risk_out,
                tolerability_tier=tolerability_tier,
                priority=payload.get("priority") or "M",
                recommended_action=payload.get("recommended_action"),
                corrective_action=payload.get("corrective_action"),
                assigned_to=payload.get("assigned_to"),
                assigned_to_uid=payload.get("assigned_to_uid"),
                department=payload.get("department")
                or (
                    get_user_department(
                        uid=payload.get("assigned_to_uid"), email=payload.get("assigned_to")
                    )
                    if payload.get("assigned_to_uid") or payload.get("assigned_to")
                    else ""
                ),
                srm_conducted=payload.get("srm_conducted", False),
                srm_date=payload.get("srm_date"),
                srm_status=payload.get("srm_status"),
                analysis_mode=payload.get("analysis_mode", "FISHBONE_ONLY"),
                sram_data=payload.get("sram_data"),
                status=payload.get("status", "Open"),
                follow_up_date=payload.get("follow_up_date"),
                closed_at=payload.get("closed_at"),
                closed_by=payload.get("closed_by"),
                remarks=payload.get("remarks"),
                is_demo=demo_scope(),
                created_by=user.get("uid"),
                created_at=payload.get("created_at") or now,
                updated_at=now,
            )
            session.add(row)
            await session.flush()
            row_id = str(row.id)

        doc_data = _row_to_dict(row)
        doc_data["id"] = row_id
        logger.info(f"Hazard {hazard_id} ({row_id}) created for tenant {self.tenant_id}")
        return doc_data

    def list_hazards(self, user: dict, filters: dict = None) -> List[dict]:
        return run(self._list_hazards_async(user, filters))

    async def _list_hazards_async(self, user: dict, filters: dict = None) -> List[dict]:
        filters = filters or {}
        try:
            limit = min(int(filters.get("limit") or 100), 500)
        except (TypeError, ValueError):
            limit = min(int(filters.get("page_size") or 100), 500)

        stmt = select(Hazard).where(Hazard.is_demo == demo_scope())
        if user.get("role") not in settings.CROSS_TENANT_ROLES:
            stmt = stmt.where(Hazard.tenant_id == register_tenant(self.tenant_id))

        clamp = {
            "status": Hazard.status,
            "priority": Hazard.priority,
            "source": Hazard.source,
            "taxonomy": Hazard.taxonomy,
            "department": Hazard.department,
        }
        for key, column in clamp.items():
            val = filters.get(key)
            if val:
                stmt = stmt.where(column == val)

        stmt = stmt.order_by(Hazard.created_at.desc()).limit(limit)

        async with session_scope() as session:
            rows = (await session.scalars(stmt)).all()

        results = []
        for row in rows:
            data = _row_to_dict(row)
            if filters.get("status") and data.get("status") != filters["status"]:
                continue
            if filters.get("priority") and data.get("priority") != filters["priority"]:
                continue
            if filters.get("source") and data.get("source") != filters["source"]:
                continue
            if filters.get("taxonomy") and data.get("taxonomy") != filters["taxonomy"]:
                continue
            if filters.get("tenant_id") and data.get("tenant_id") != filters["tenant_id"]:
                continue
            if filters.get("department") and (data.get("department") or "") != filters["department"]:
                continue
            if filters.get("search"):
                search = filters["search"].lower()
                hid = (data.get("hazard_id") or "").lower()
                title = (data.get("title") or "").lower()
                desc = (data.get("description") or "").lower()
                if search not in hid and search not in title and search not in desc:
                    continue
            results.append(data)
        return results

    def get_hazard_by_id(self, hazard_id_or_doc_id: str, user: dict) -> Optional[dict]:
        return run(self._get_hazard_by_id_async(hazard_id_or_doc_id, user))

    async def _get_hazard_by_id_async(self, hazard_id_or_doc_id: str, user: dict) -> Optional[dict]:
        tid = None
        if user.get("role") not in settings.CROSS_TENANT_ROLES:
            tid = register_tenant(self.tenant_id)
        stmt = _lookup_hazard_stmt(tid, hazard_id_or_doc_id)
        async with session_scope() as session:
            row = (await session.execute(stmt)).scalars().first()
        if not row:
            return None
        return _row_to_dict(row)

    def update_hazard(self, hazard_id: str, payload: dict, user: dict) -> Optional[dict]:
        return run(self._update_hazard_async(hazard_id, payload, user))

    async def _update_hazard_async(self, hazard_id: str, payload: dict, user: dict) -> Optional[dict]:
        tid = register_tenant(self.tenant_id)
        async with session_scope() as session:
            row = (await session.execute(_lookup_hazard_stmt(tid, hazard_id))).scalars().first()
            if not row:
                return None

            if "severity" in payload or "probability" in payload:
                sev = payload.get("severity", row.severity)
                prob = payload.get("probability", row.probability)
                if sev is not None and prob is not None:
                    thresholds = get_thresholds(self.tenant_id)
                    computed = compute_risk_index(sev, prob)
                    payload["risk_index"] = computed
                    payload["risk_level"] = classify_risk(computed, thresholds)
                    payload["risk_outcome"] = risk_outcome(sev, prob, thresholds)
                    payload["tolerability_tier"] = get_tolerability_tier(computed, thresholds)
            elif "risk_level" in payload:
                payload["tolerability_tier"] = normalize_tolerability(payload.get("risk_level"))

            if "assigned_to" in payload or "assigned_to_uid" in payload:
                new_uid = payload.get("assigned_to_uid", row.assigned_to_uid)
                new_email = payload.get("assigned_to", row.assigned_to)
                payload["department"] = get_user_department(uid=new_uid, email=new_email)

            for key, value in payload.items():
                if key in _HZ_MUTABLE_COLUMNS:
                    setattr(row, key, value)
            row.updated_at = datetime.now(timezone.utc)
            await session.flush()
            return _row_to_dict(row)

    def update_status(self, hazard_id: str, status: str, user: dict) -> Optional[dict]:
        return run(self._update_status_async(hazard_id, status, user))

    async def _update_status_async(self, hazard_id: str, status: str, user: dict) -> Optional[dict]:
        tid = register_tenant(self.tenant_id)
        now = datetime.now(timezone.utc)
        async with session_scope() as session:
            row = (await session.execute(_lookup_hazard_stmt(tid, hazard_id))).scalars().first()
            if not row:
                return None
            row.status = status
            row.updated_at = now
            if status == "Closed":
                row.closed_at = now
                row.closed_by = user.get("uid")
            await session.flush()
            return _row_to_dict(row)

    def assign_hazard(self, hazard_id: str, assigned_to: str, assigned_to_uid: str, user: dict) -> Optional[dict]:
        return run(self._assign_hazard_async(hazard_id, assigned_to, assigned_to_uid, user))

    async def _assign_hazard_async(
        self, hazard_id: str, assigned_to: str, assigned_to_uid: str, user: dict
    ) -> Optional[dict]:
        tid = register_tenant(self.tenant_id)
        async with session_scope() as session:
            row = (await session.execute(_lookup_hazard_stmt(tid, hazard_id))).scalars().first()
            if not row:
                return None
            row.assigned_to = assigned_to
            row.assigned_to_uid = assigned_to_uid
            row.department = get_user_department(uid=assigned_to_uid, email=assigned_to)
            row.updated_at = datetime.now(timezone.utc)
            await session.flush()
            return _row_to_dict(row)

    def get_hazard_stats(self, user: dict) -> dict:
        return run(self._get_hazard_stats_async(user))

    async def _get_hazard_stats_async(self, user: dict) -> dict:
        # For demo tenants (is_demo=True in Firestore), show demo data even in production
        # where demo_scope() is False. Query both is_demo states for the tenant and filter in Python,
        # or just not filter by is_demo for dashboard stats (show all for tenant).
        # To keep demo data visible in production, we do not filter by is_demo here.
        stmt = select(Hazard)
        if user.get("role") not in settings.CROSS_TENANT_ROLES:
            stmt = stmt.where(Hazard.tenant_id == register_tenant(self.tenant_id))

        async with session_scope() as session:
            rows = (await session.scalars(stmt)).all()

        status_stats = {"Open": 0, "Processing": 0, "Under Review": 0, "Closed": 0, "Reopened": 0}
        taxonomy_counts: Dict[str, int] = {}
        priority_counts = {"H": 0, "M": 0, "L": 0}
        risk_level_counts: Dict[str, int] = {}

        for row in rows:
            status = row.status or "Open"
            if status in status_stats:
                status_stats[status] += 1
            else:
                status_stats[status] = 1
            taxonomy = row.taxonomy or "Other"
            taxonomy_counts[taxonomy] = taxonomy_counts.get(taxonomy, 0) + 1
            priority = row.priority
            if priority in priority_counts:
                priority_counts[priority] += 1
            rl = row.risk_level
            if rl:
                risk_level_counts[rl] = risk_level_counts.get(rl, 0) + 1

        return {
            "by_status": status_stats,
            "by_taxonomy": taxonomy_counts,
            "by_priority": priority_counts,
            "by_risk_level": risk_level_counts,
            "total": sum(status_stats.values()),
        }

    # ==========================================================================
    # v2 async API (HazardService(db=...) backward-compatible / unmounted router)
    # ==========================================================================

    async def create_hazard_v2(
        self, tenant_id: str, payload: Dict[str, Any], user_info: Dict[str, Any]
    ) -> str:
        await ensure_v2_schema_async()
        resource_id = f"HAZ-{datetime.now(timezone.utc).strftime('%Y')}-{uuid.uuid4().hex[:6].upper()}"
        tid = register_tenant(tenant_id)
        now = datetime.now(timezone.utc)

        async with session_scope() as session:
            row = HazardRcaEntry(
                resource_id=resource_id,
                tenant_id=tid,
                title=payload["title"],
                description=payload["description"],
                source_type=payload["source_type"],
                source_reference_id=payload.get("source_reference_id"),
                functional_area=payload["functional_area"],
                status="under_assessment",
                risk_summary={
                    "initial_risk_index": None,
                    "initial_risk_level": None,
                    "residual_risk_index": None,
                    "residual_risk_level": None,
                },
                hfacs_summary={
                    "primary_category": None,
                    "tagged_codes": [],
                },
                identified_by=user_info,
                assigned_owner={"email": payload["assigned_owner_email"]},
                target_completion_date=payload.get("target_completion_date"),
                created_at=now,
                updated_at=now,
                closed_at=None,
            )
            session.add(row)
            await session.flush()
        return resource_id

    async def add_rca_factor(self, tenant_id: str, hazard_id: str, factor_data: Dict[str, Any]) -> str:
        await ensure_v2_schema_async()
        factor_id = f"rca_{uuid.uuid4().hex[:8]}"
        tid = register_tenant(tenant_id)
        now = datetime.now(timezone.utc)

        async with session_scope() as session:
            entry = (
                await session.scalars(
                    select(HazardRcaEntry).where(
                        HazardRcaEntry.tenant_id == tid,
                        HazardRcaEntry.resource_id == hazard_id,
                    )
                )
            ).first()
            if not entry:
                raise ValueError(f"Hazard {hazard_id} not found for tenant {tenant_id}")

            factor = HazardRcaFactor(
                tenant_id=tid,
                entry_id=entry.id,
                resource_id=factor_id,
                tier=factor_data.get("tier"),
                category=factor_data.get("category"),
                subcategory=factor_data.get("subcategory"),
                nanocode=factor_data.get("nanocode"),
                definition=factor_data.get("definition"),
                contributing_narrative=factor_data.get("contributing_narrative"),
                order_sequence=factor_data.get("order_sequence"),
                created_at=now,
            )
            session.add(factor)
            await session.flush()

            current_codes = list((entry.hfacs_summary or {}).get("tagged_codes", []))
            if factor_data.get("nanocode") not in current_codes:
                current_codes.append(factor_data["nanocode"])
                entry.hfacs_summary = {
                    **(entry.hfacs_summary or {}),
                    "tagged_codes": current_codes,
                    "primary_category": factor_data.get("category"),
                }
                entry.updated_at = now
            await session.flush()
        return factor_id

    async def record_assessment(
        self, tenant_id: str, hazard_id: str, asm_data: Dict[str, Any], assessor_email: str
    ) -> Dict[str, Any]:
        await ensure_v2_schema_async()
        asm_id = f"asm_{uuid.uuid4().hex[:8]}"
        tid = register_tenant(tenant_id)
        now = datetime.now(timezone.utc)

        p = asm_data["probability_score"]
        s = asm_data["severity_score"]
        index = f"{s}{p}"
        tolerability = TOLERABILITY_MATRIX.get((p, s), "tolerable")

        record = {
            "id": asm_id,
            "hazard_id": hazard_id,
            "assessment_type": asm_data["assessment_type"],
            "severity": {
                "score": s,
                "label": SEVERITY_LABELS.get(s, "Unknown"),
                "justification": asm_data["severity_justification"],
            },
            "probability": {
                "score": p,
                "label": PROBABILITY_LABELS.get(p, "Unknown"),
                "justification": asm_data["probability_justification"],
            },
            "risk_index": index,
            "tolerability": tolerability,
            "assessed_by": assessor_email,
            "assessed_at": now,
        }

        async with session_scope() as session:
            entry = (
                await session.scalars(
                    select(HazardRcaEntry).where(
                        HazardRcaEntry.tenant_id == tid,
                        HazardRcaEntry.resource_id == hazard_id,
                    )
                )
            ).first()
            if not entry:
                raise ValueError(f"Hazard {hazard_id} not found for tenant {tenant_id}")

            assessment = HazardAssessment(
                tenant_id=tid,
                entry_id=entry.id,
                resource_id=asm_id,
                assessment_type=asm_data["assessment_type"],
                severity=record["severity"],
                probability=record["probability"],
                risk_index=index,
                tolerability=tolerability,
                assessed_by=assessor_email,
                assessed_at=now,
            )
            session.add(assessment)
            await session.flush()

            summary = dict(entry.risk_summary or {})
            if asm_data["assessment_type"] == "initial":
                summary["initial_severity"] = s
                summary["initial_probability"] = p
                summary["initial_risk_index"] = index
                summary["initial_risk_level"] = tolerability
            elif asm_data["assessment_type"] == "residual":
                summary["residual_severity"] = s
                summary["residual_probability"] = p
                summary["residual_risk_index"] = index
                summary["residual_risk_level"] = tolerability
                if tolerability == "acceptable":
                    entry.status = "mitigated"
            entry.risk_summary = summary
            entry.updated_at = now
            await session.flush()
        return record

    async def add_capa(self, tenant_id: str, hazard_id: str, capa_data: Dict[str, Any]) -> str:
        await ensure_v2_schema_async()
        capa_id = f"capa_{uuid.uuid4().hex[:8]}"
        tid = register_tenant(tenant_id)
        now = datetime.now(timezone.utc)

        async with session_scope() as session:
            entry = (
                await session.scalars(
                    select(HazardRcaEntry).where(
                        HazardRcaEntry.tenant_id == tid,
                        HazardRcaEntry.resource_id == hazard_id,
                    )
                )
            ).first()
            if not entry:
                raise ValueError(f"Hazard {hazard_id} not found for tenant {tenant_id}")

            capa_data["id"] = capa_id
            capa_data["hazard_id"] = hazard_id
            capa_data["status"] = "pending_implementation"
            capa_data["created_at"] = now.isoformat()
            capa_data["implemented_at"] = None
            capa_data["verified_by"] = None

            capa = HazardCapa(
                tenant_id=tid,
                entry_id=entry.id,
                resource_id=capa_id,
                status="pending_implementation",
                implemented_at=None,
                verified_by=None,
                data=capa_data,
                created_at=now,
            )
            session.add(capa)
            await session.flush()
            entry.updated_at = now
            await session.flush()
        return capa_id