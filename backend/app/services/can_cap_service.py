# ==============================================================================
# File: backend/app/services/can_cap_service.py
# Description: Multi-tenant repository and business logic for Corrective Action
#              Notices (CAN) and Corrective Action Plans (CAP), backed by
#              PostgreSQL (Supabase).
#
#              CanCapService(tenant_id) preserves the legacy sync API used by
#              the mounted can_cap router. Every method keeps its old
#              signature / return-shape (dicts with the Firestore-era keys the
#              route response helpers read) but persists to the `cans`/`caps`
#              tables via the async engine, dispatching through app.db.runner.
#
#              cans.hazard_id is a NOT NULL FK into hazards.id. CAN payloads
#              carry a business hazard reference (hazard_id text like
#              "FW-001-H-2026" or an opaque id). The reference is resolved to
#              the linked hazard row; an unresolved reference auto-creates a
#              minimal stub hazard row so issuance stays faithful to the legacy
#              behaviour of storing whatever reference the client sent.
# ==============================================================================

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import or_, select

from app.core.config import settings
from app.db.db_models import Can, Cap, Hazard
from app.db.ids import register_tenant, tenant_slug
from app.db.isolation import demo_scope
from app.db.runner import run
from app.db.session import session_scope
from app.services.hazard_service import HazardService
from app.services.repository import coerce_utc_datetime
from app.services.risk_matrix import (
    compute_risk_index,
    get_risk_level,
    risk_outcome,
    get_thresholds,
    get_tolerability_tier,
)
from app.services.users import get_user_department


def _dt(value: Any):
    """Coerce a payload timestamp (datetime or ISO string) to an aware datetime
    for asyncpg timestamptz columns (it rejects raw strings)."""
    return coerce_utc_datetime(value)


CAN_COLLECTION = "can_cap"
CAP_SUBCOLLECTION = "caps"


def generate_can_reference(tenant_id: str, sequence: int) -> str:
    year = datetime.now(timezone.utc).strftime("%y")
    return f"CAN-{year}-{sequence:03d}"


def generate_cap_reference(tenant_id: str, sequence: int) -> str:
    year = datetime.now(timezone.utc).strftime("%y")
    return f"CAP-{year}-{sequence:03d}"


_CAN_FIXED_COLUMNS = {"id", "tenant_id", "hazard_id", "can_reference", "is_demo", "created_at", "updated_at"}
_CAN_MUTABLE_COLUMNS = [
    c.name for c in Can.__table__.columns if c.name not in _CAN_FIXED_COLUMNS
]
_CAP_FIXED_COLUMNS = {
    "id", "tenant_id", "can_id", "cap_reference", "is_demo", "created_at", "updated_at",
    "submitted_by", "submitted_by_uid",
}
_CAP_MUTABLE_COLUMNS = [
    c.name for c in Cap.__table__.columns if c.name not in _CAP_FIXED_COLUMNS
]
_CAP_JSONB_COLUMNS = {
    "managerial_approval", "caa_acceptance", "residual_sra", "root_causes",
    "action_items", "sram_data",
}
_CAN_JSONB_COLUMNS = {"initial_sra"}

from sqlalchemy import DateTime

_CAN_DT_COLUMNS = {
    c.name for c in Can.__table__.columns if isinstance(c.type, DateTime)
}
_CAP_DT_COLUMNS = {
    c.name for c in Cap.__table__.columns if isinstance(c.type, DateTime)
}

_TIME_KEYS = (
    "created_at", "updated_at", "issued_at", "submitted_at", "reviewed_at",
    "target_completion_date", "revision_deadline", "sag_signed_at", "closed_at",
    "ae_signed_at", "ae_review_date", "escalated_at",
)


def _serialize_timestamps(data: dict) -> None:
    for key in _TIME_KEYS:
        if key in data and hasattr(data[key], "isoformat"):
            data[key] = data[key].isoformat()


def _json_safe(value: Any) -> Any:
    """Deep-convert datetimes inside dict/list payloads to ISO strings so the
    JSONB bind processor can serialise them (json.dumps cannot handle datetime)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return str(value)


def _can_to_dict(row: Can, hazard_id_ref: Optional[str] = None) -> dict:
    data = {}
    for col in Can.__table__.columns:
        value = getattr(row, col.name)
        if isinstance(value, uuid.UUID):
            value = str(value)
        data[col.name] = value
    data["tenant_id"] = tenant_slug(row.tenant_id)
    data["hazard_id"] = hazard_id_ref or str(row.hazard_id)
    _serialize_timestamps(data)
    return data


def _cap_to_dict(
    row: Cap,
    can_row: Optional[Can] = None,
    hazard_id_ref: Optional[str] = None,
) -> dict:
    data = {}
    for col in Cap.__table__.columns:
        value = getattr(row, col.name)
        if isinstance(value, uuid.UUID):
            value = str(value)
        data[col.name] = value
    data["tenant_id"] = tenant_slug(row.tenant_id)
    if can_row is not None:
        data["can_reference"] = can_row.can_reference
        data["can_issued_at"] = (
            can_row.issued_at.isoformat() if getattr(can_row, "issued_at", None) else None
        )
        data["priority"] = can_row.priority
        data["hazard_id"] = hazard_id_ref or str(can_row.hazard_id)
    _serialize_timestamps(data)
    return data


def _can_lookup_stmt(tid: Optional[str], can_id: str):
    conds = [Can.can_reference == str(can_id)]
    try:
        conds.append(Can.id == uuid.UUID(str(can_id)))
    except (ValueError, TypeError, AttributeError):
        pass
    scope = [Can.is_demo == demo_scope()]
    if tid:
        return select(Can).where(Can.tenant_id == tid, *scope, or_(*conds)).limit(1)
    return select(Can).where(*scope, or_(*conds)).limit(1)


def _cap_lookup_stmt(tid: Optional[str], cap_id: str):
    conds = [Cap.cap_reference == str(cap_id)]
    try:
        conds.append(Cap.id == uuid.UUID(str(cap_id)))
    except (ValueError, TypeError, AttributeError):
        pass
    scope = [Cap.is_demo == demo_scope()]
    if tid:
        return select(Cap).where(Cap.tenant_id == tid, *scope, or_(*conds)).limit(1)
    return select(Cap).where(*scope, or_(*conds)).limit(1)


async def _resolve_hazard(session, tid: str, ref: str, now: datetime) -> Hazard:
    """Resolve a business hazard reference to a Hazard row, auto-creating a
    minimal stub when the reference does not exist (the legacy service stored
    whatever reference the CAN payload carried)."""
    ref = str(ref or "").strip()
    conds: list = []
    if ref:
        conds.append(Hazard.hazard_id == ref)
        try:
            conds.append(Hazard.id == uuid.UUID(ref))
        except (ValueError, TypeError, AttributeError):
            pass
    if conds:
        row = (
            await session.execute(
                select(Hazard).where(
                    Hazard.tenant_id == tid,
                    Hazard.is_demo == demo_scope(),
                    or_(*conds),
                ).limit(1)
            )
        ).scalars().first()
        if row:
            return row

    stub_ref = ref or f"CAN-STUB-{uuid.uuid4().hex[:8]}"
    stub = Hazard(
        tenant_id=tid,
        hazard_id=stub_ref,
        title=f"Linked hazard reference {stub_ref}",
        description=(
            f"Auto-created hazard for a CAN issued against the unresolved "
            f"reference '{ref}'. Complete the details from the associated CAN."
        ),
        source="CAN",
        source_id=stub_ref,
        taxonomy="Other",
        priority="M",
        status="Open",
        is_demo=demo_scope(),
        created_by="system",
        created_at=now,
        updated_at=now,
    )
    session.add(stub)
    await session.flush()
    return stub


async def _hazard_ref(session, can_row: Can) -> str:
    """Business hazard_id text echoed on serialised CAN/CAP output."""
    hazard = (
        await session.execute(select(Hazard).where(Hazard.id == can_row.hazard_id))
    ).scalars().first()
    return hazard.hazard_id if hazard else str(can_row.hazard_id)


class CanCapService:
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    def _safety_manager_email(self) -> Optional[str]:
        """Resolve the tenant Safety Manager notification email from the
        Firestore tenant document (safety_manager.email). Returns None when the
        tenant document or email is unavailable (email is then skipped, never
        raising into the workflow)."""
        try:
            from app.firebase import get_db
            doc = get_db().collection(settings.FIREBASE_COLLECTION_TENANTS).document(self.tenant_id).get()
            if not doc.exists:
                return None
            sm = (doc.to_dict() or {}).get("safety_manager") or {}
            return sm.get("email") or None
        except Exception as e:
            logger.warning(f"Failed to resolve Safety Manager email for {self.tenant_id}: {e}")
            return None

    # ── SRA (Safety Risk Assessment) helpers ──

    SEVERITY_LETTERS = ["A", "B", "C", "D", "E"]

    @classmethod
    def classify_sra(cls, severity, probability, thresholds=None):
        """Server-side canonical SRA classification (Risk Index, Level, Outcome).

        Authority lives here (not the client) so stored risk states always
        reflect the tenant's configured 5x5 matrix thresholds.
        """
        if severity is None or probability is None:
            return None
        try:
            sev = int(severity)
            prob = int(probability)
        except (TypeError, ValueError):
            return None
        if not (1 <= sev <= 5 and 1 <= prob <= 5):
            return None
        index = compute_risk_index(sev, prob)
        level = get_risk_level(index, thresholds)
        outcome = risk_outcome(sev, prob, thresholds)
        return {
            "severity": sev,
            "severity_letter": cls.SEVERITY_LETTERS[sev - 1],
            "probability": prob,
            "risk_index": index,
            "risk_level": level,
            "risk_outcome": outcome,
            "tolerability_tier": get_tolerability_tier(index, thresholds),
        }

    def _sra_block(self, severity, probability, assessed_by=None, assessed_at=None, provided=None):
        """Merge canonical SRA classification with any provided audit fields."""
        thresholds = get_thresholds(self.tenant_id)
        classified = self.classify_sra(severity, probability, thresholds)
        if classified is None:
            return None
        provided = provided or {}
        classified["assessed_by"] = provided.get("assessed_by") or assessed_by
        classified["assessed_at"] = provided.get("assessed_at") or assessed_at
        return classified

    # ── CAN CRUD ──

    def issue_can(self, payload: dict, user: dict) -> dict:
        data = run(self._issue_can_async(payload, user))
        try:
            from app.services.email_service import send_can_issued_email
            send_can_issued_email(data, to=payload.get("assigned_to"))
        except Exception as e:
            logger.warning(
                f"CAN issued notification failed for {data.get('can_reference')}: {e}"
            )
        return data

    async def _issue_can_async(self, payload: dict, user: dict) -> dict:
        now = datetime.now(timezone.utc)
        tid = register_tenant(self.tenant_id)

        async with session_scope() as session:
            refs = (
                await session.scalars(
                    select(Can.can_reference).where(
                        Can.tenant_id == tid,
                        Can.is_demo == demo_scope(),
                    )
                )
            ).all()
            year = now.strftime("%y")
            max_seq = 0
            for ref in refs:
                # CAN-YY-NNN
                parts = ref.split("-")
                if len(parts) == 3 and parts[0] == "CAN" and parts[1] == year:
                    try:
                        seq = int(parts[2])
                        if seq > max_seq:
                            max_seq = seq
                    except (IndexError, ValueError):
                        pass
            can_reference = generate_can_reference(self.tenant_id, max_seq + 1)

            hazard = await _resolve_hazard(session, tid, payload["hazard_id"], now)

            severity = payload.get("initial_severity")
            probability = payload.get("initial_probability")
            initial_sra = self._sra_block(
                severity,
                probability,
                assessed_by=user.get("email", user["uid"]),
                assessed_at=now,
                provided=payload.get("initial_sra"),
            )

            init = {
                "initial_severity": severity,
                "initial_probability": probability,
                "initial_risk_index": payload.get("initial_risk_index"),
                "initial_risk_level": payload.get("initial_risk_level"),
                "initial_risk_outcome": payload.get("initial_risk_outcome"),
                "initial_tolerability_tier": payload.get("initial_tolerability_tier"),
                "initial_sra": _json_safe(payload.get("initial_sra")),
            }
            if initial_sra:
                init["initial_severity"] = initial_sra["severity"]
                init["initial_probability"] = initial_sra["probability"]
                init["initial_risk_index"] = initial_sra["risk_index"]
                init["initial_risk_level"] = initial_sra["risk_level"]
                init["initial_risk_outcome"] = initial_sra["risk_outcome"]
                init["initial_tolerability_tier"] = initial_sra["tolerability_tier"]
                init["initial_sra"] = _json_safe(initial_sra)
            elif payload.get("initial_risk_index"):
                # Back-compat: legacy clients that only sent an index get a level too.
                thresholds = get_thresholds(self.tenant_id)
                init["initial_risk_level"] = get_risk_level(payload["initial_risk_index"], thresholds)
                init["initial_risk_outcome"] = risk_outcome(
                    payload.get("initial_severity") or 1,
                    payload.get("initial_probability") or 1,
                    thresholds,
                )
                init["initial_tolerability_tier"] = get_tolerability_tier(
                    payload["initial_risk_index"], thresholds
                )

            row = Can(
                tenant_id=tid,
                can_reference=can_reference,
                hazard_id=hazard.id,
                title=payload["title"],
                description=payload["description"],
                required_action=payload["required_action"],
                target_completion_date=_dt(payload["target_completion_date"]),
                assigned_to=payload["assigned_to"],
                assigned_to_uid=payload.get("assigned_to_uid") or "",
                department=payload.get("department")
                or (
                    get_user_department(
                        uid=payload.get("assigned_to_uid"), email=payload.get("assigned_to")
                    )
                    if payload.get("assigned_to_uid") or payload.get("assigned_to")
                    else ""
                ),
                priority=payload["priority"],
                status="Open",
                is_demo=demo_scope(),
                issued_by=user.get("email", user["uid"]),
                issued_by_uid=user["uid"],
                issued_at=payload.get("issued_at") or now,
                created_by=user["uid"],
                created_at=now,
                updated_at=now,
                # Buddha Air FORM SMSM 8.8.2 — CAN issuance block (all optional)
                copies_to=payload.get("copies_to"),
                requested_function=payload.get("requested_function"),
                addressed_function=payload.get("addressed_function"),
                classification_type=payload.get("classification_type"),
                classification_level=payload.get("classification_level"),
                psoe_assessment_id=payload.get("psoe_assessment_id"),
                **init,
            )
            session.add(row)
            await session.flush()

            # Update hazard status to Processing
            await self._set_hazard_status(session, hazard.id, "Processing", now)

            data = _can_to_dict(row, hazard_id_ref=hazard.hazard_id)
        data["id"] = str(row.id)
        logger.info(f"CAN {can_reference} issued by {user['uid']}")
        return data

    async def _set_hazard_status(
        self, session, hazard_id: uuid.UUID, status: str, now: datetime
    ):
        hazard = (
            await session.execute(select(Hazard).where(Hazard.id == hazard_id))
        ).scalars().first()
        if not hazard:
            return
        hazard.status = status
        hazard.updated_at = now

    def get_can(self, can_id: str, user: dict) -> Optional[dict]:
        return run(self._get_can_async(can_id, user))

    async def _get_can_async(self, can_id: str, user: dict) -> Optional[dict]:
        tid = None
        if user.get("role") not in settings.CROSS_TENANT_ROLES:
            tid = register_tenant(self.tenant_id)
        async with session_scope() as session:
            row = (await session.execute(_can_lookup_stmt(tid, can_id))).scalars().first()
            if not row:
                return None
            cap_row = (
                await session.scalars(
                    select(Cap)
                    .where(Cap.can_id == row.id)
                    .order_by(Cap.created_at.desc())
                    .limit(1)
                )
            ).first()
            hazard_ref = await _hazard_ref(session, row)
            data = _can_to_dict(row, hazard_id_ref=hazard_ref)
            data["latest_cap"] = None
            if cap_row:
                data["latest_cap"] = _cap_to_dict(
                    cap_row, can_row=row, hazard_id_ref=hazard_ref
                )
            return data

    def list_cans(self, user: dict, filters: dict = None) -> List[dict]:
        return run(self._list_cans_async(user, filters))

    async def _list_cans_async(self, user: dict, filters: dict = None) -> List[dict]:
        filters = filters or {}
        tid = None
        if user.get("role") not in settings.CROSS_TENANT_ROLES:
            tid = register_tenant(self.tenant_id)

        try:
            limit = min(int(filters.get("limit") or filters.get("page_size") or 100), 500)
        except (TypeError, ValueError):
            limit = 100

        stmt = (
            select(Can)
            .join(Hazard, Can.hazard_id == Hazard.id)
            .where(Can.is_demo == demo_scope(), Hazard.is_demo == demo_scope())
        )
        if tid:
            stmt = stmt.where(Can.tenant_id == tid)
            for key, column in [
                ("status", Can.status),
                ("priority", Can.priority),
                ("assigned_to", Can.assigned_to),
                ("department", Can.department),
            ]:
                val = filters.get(key)
                if val:
                    stmt = stmt.where(column == val)
            if filters.get("hazard_id"):
                stmt = stmt.where(Hazard.hazard_id == str(filters["hazard_id"]))
            if filters.get("days"):
                try:
                    cutoff = datetime.now(timezone.utc) - timedelta(days=int(filters["days"]))
                    stmt = stmt.where(Can.created_at >= cutoff)
                except (TypeError, ValueError):
                    pass

        async with session_scope() as session:
            rows = (
                await session.execute(stmt.order_by(Can.created_at.desc()).limit(limit))
            ).scalars().all()
            ref_map: Dict[str, str] = {}
            for r in rows:
                ref_map[str(r.hazard_id)] = await _hazard_ref(session, r)

        results = []
        for row in rows:
            data = _can_to_dict(row, hazard_id_ref=ref_map.get(str(row.hazard_id)))
            if filters.get("search"):
                s = filters["search"].lower()
                ref = (data.get("can_reference") or "").lower()
                title = (data.get("title") or "").lower()
                if s not in ref and s not in title:
                    continue
            results.append(data)
        return results

    def update_can(self, can_id: str, payload: dict, user: dict) -> Optional[dict]:
        return run(self._update_can_async(can_id, payload, user))

    async def _update_can_async(self, can_id: str, payload: dict, user: dict) -> Optional[dict]:
        tid = register_tenant(self.tenant_id)
        async with session_scope() as session:
            row = (await session.execute(_can_lookup_stmt(tid, can_id))).scalars().first()
            if not row:
                return None

            if "assigned_to" in payload or "assigned_to_uid" in payload:
                new_uid = payload.get("assigned_to_uid", row.assigned_to_uid)
                new_email = payload.get("assigned_to", row.assigned_to)
                payload["department"] = get_user_department(uid=new_uid, email=new_email)

            for key, value in payload.items():
                if key in _CAN_MUTABLE_COLUMNS:
                    if key in _CAN_JSONB_COLUMNS:
                        value = _json_safe(value)
                    elif key in _CAN_DT_COLUMNS:
                        value = _dt(value)
                    setattr(row, key, value)
            row.updated_at = datetime.now(timezone.utc)
            await session.flush()
            return _can_to_dict(row, hazard_id_ref=await _hazard_ref(session, row))

    def update_can_status(self, can_id: str, status: str, user: dict) -> Optional[dict]:
        return run(self._update_can_status_async(can_id, status, user))

    async def _update_can_status_async(
        self, can_id: str, status: str, user: dict
    ) -> Optional[dict]:
        tid = register_tenant(self.tenant_id)
        now = datetime.now(timezone.utc)
        async with session_scope() as session:
            row = (await session.execute(_can_lookup_stmt(tid, can_id))).scalars().first()
            if not row:
                return None
            row.status = status
            row.updated_at = now
            await session.flush()
            return _can_to_dict(row, hazard_id_ref=await _hazard_ref(session, row))

    def delete_can(self, can_id: str) -> bool:
        return run(self._delete_can_async(can_id))

    async def _delete_can_async(self, can_id: str) -> bool:
        tid = register_tenant(self.tenant_id)
        async with session_scope() as session:
            row = (await session.execute(_can_lookup_stmt(tid, can_id))).scalars().first()
            if not row:
                return False
            # Bulk delete caps first (no ORM relationship() exists, so the unit
            # of work cannot order the deletes; explicit order avoids FK errors).
            from sqlalchemy import delete as _sql_delete
            await session.execute(_sql_delete(Cap).where(Cap.can_id == row.id))
            await session.delete(row)
            logger.info(f"CAN {can_id} deleted")
            return True

    # ── CAP CRUD ──

    def submit_cap(self, can_id: str, payload: dict, user: dict) -> dict:
        data = run(self._submit_cap_async(can_id, payload, user))
        sm_email = self._safety_manager_email()
        if not sm_email:
            sm_email = payload.get("assigned_to")
        try:
            from app.services.email_service import send_cap_submitted_email
            send_cap_submitted_email(data, to=sm_email)
        except Exception as e:
            logger.warning(
                f"CAP submitted notification failed for {data.get('cap_reference')}: {e}"
            )
        return data

    async def _submit_cap_async(self, can_id: str, payload: dict, user: dict) -> dict:
        now = datetime.now(timezone.utc)
        tid = register_tenant(self.tenant_id)

        async with session_scope() as session:
            can_row = (await session.execute(_can_lookup_stmt(tid, can_id))).scalars().first()
            if not can_row:
                raise ValueError("CAN not found")

            cap_refs = (
                await session.scalars(
                    select(Cap.cap_reference).where(
                        Cap.tenant_id == tid,
                        Cap.is_demo == demo_scope(),
                    )
                )
            ).all()
            year = now.strftime("%y")
            max_seq = 0
            for ref in cap_refs:
                # CAP-YY-NNN
                parts = ref.split("-")
                if len(parts) == 3 and parts[0] == "CAP" and parts[1] == year:
                    try:
                        seq = int(parts[2])
                        if seq > max_seq:
                            max_seq = seq
                    except (IndexError, ValueError):
                        pass
            cap_reference = generate_cap_reference(self.tenant_id, max_seq + 1)

            residual_sra = self._sra_block(
                payload.get("residual_severity"),
                payload.get("residual_probability"),
                assessed_by=user.get("email", user["uid"]),
                assessed_at=now,
                provided=payload.get("residual_sra"),
            )

            res: Dict[str, Any] = {
                "residual_severity": payload.get("residual_severity"),
                "residual_probability": payload.get("residual_probability"),
                "residual_risk_index": payload.get("residual_risk_index"),
                "residual_risk_level": payload.get("residual_risk_level"),
                "residual_risk_outcome": payload.get("residual_risk_outcome"),
                "residual_tolerability_tier": payload.get("residual_tolerability_tier"),
                "residual_sra": _json_safe(payload.get("residual_sra")),
            }
            if residual_sra:
                res["residual_severity"] = residual_sra["severity"]
                res["residual_probability"] = residual_sra["probability"]
                res["residual_risk_index"] = residual_sra["risk_index"]
                res["residual_risk_level"] = residual_sra["risk_level"]
                res["residual_risk_outcome"] = residual_sra["risk_outcome"]
                res["residual_tolerability_tier"] = residual_sra["tolerability_tier"]
                res["residual_sra"] = _json_safe(residual_sra)
            elif payload.get("residual_risk_index"):
                thresholds = get_thresholds(self.tenant_id)
                res["residual_risk_level"] = get_risk_level(payload["residual_risk_index"], thresholds)
                res["residual_risk_outcome"] = risk_outcome(
                    payload.get("residual_severity") or 1,
                    payload.get("residual_probability") or 1,
                    thresholds,
                )
                res["residual_tolerability_tier"] = get_tolerability_tier(
                    payload["residual_risk_index"], thresholds
                )

            rca_method = payload.get("rca_method")
            if rca_method not in ("bow_tie", "fishbone"):
                rca_method = None

            row = Cap(
                tenant_id=tid,
                can_id=can_row.id,
                cap_reference=cap_reference,
                department=payload.get("department") or can_row.department or "",
                action_plan=payload["action_plan"],
                timeline=payload["timeline"],
                resources_required=payload.get("resources_required") or "",
                implementation_plan=payload.get("implementation_plan") or "",
                target_completion_date=_dt(payload["target_completion_date"]),
                status="In Progress",
                is_demo=demo_scope(),
                submitted_by=user.get("email", user["uid"]),
                submitted_by_uid=user["uid"],
                submitted_at=payload.get("submitted_at") or now,
                created_at=now,
                updated_at=now,
                # Buddha Air FORM SMSM 8.8.2 — CAP submission block (all optional)
                company_name=payload.get("company_name"),
                base_location=payload.get("base_location"),
                area_system_of_interest=payload.get("area_system_of_interest"),
                finding_number=payload.get("finding_number"),
                file_ref=payload.get("file_ref"),
                factual_review=payload.get("factual_review"),
                rca=payload.get("rca"),
                short_term_ca=payload.get("short_term_ca"),
                long_term_ca=payload.get("long_term_ca"),
                implementation_timeline=payload.get("implementation_timeline"),
                managerial_approval=_json_safe(payload.get("managerial_approval")),
                caa_acceptance=_json_safe(payload.get("caa_acceptance")),
                # Structured RCA (Fishbone / Ishikawa 5M + Management)
                root_causes=_json_safe(payload.get("root_causes")),
                action_items=_json_safe(payload.get("action_items")),
                # Selected RCA methodology ('bow_tie' | 'fishbone')
                rca_method=rca_method,
                process_owner=payload.get("process_owner"),
                # CAAN CAR-19 SRM (Bow-Tie) block
                sram_data=_json_safe(payload.get("sram_data")),
                **res,
            )
            session.add(row)
            await session.flush()

            # Update CAN status to Under Review
            can_row.status = "Under Review"
            can_row.updated_at = now

            data = _cap_to_dict(row, can_row=can_row, hazard_id_ref=await _hazard_ref(session, can_row))
            logger.info(f"CAP {cap_reference} submitted for CAN {can_row.can_reference}")
        data["id"] = str(row.id)
        return data

    def list_caps(self, can_id: str, user: dict) -> List[dict]:
        return run(self._list_caps_async(can_id, user))

    async def _list_caps_async(self, can_id: str, user: dict) -> List[dict]:
        tid = None
        if user.get("role") not in settings.CROSS_TENANT_ROLES:
            tid = register_tenant(self.tenant_id)
        async with session_scope() as session:
            can_row = (await session.execute(_can_lookup_stmt(tid, can_id))).scalars().first()
            if not can_row:
                return []
            rows = (
                await session.scalars(
                    select(Cap).where(Cap.can_id == can_row.id).order_by(Cap.created_at.desc())
                )
            ).all()
            hazard_ref = await _hazard_ref(session, can_row)
            return [
                _cap_to_dict(r, can_row=can_row, hazard_id_ref=hazard_ref)
                for r in rows
            ]

    def list_all_caps(self, user: dict, filters: dict = None) -> List[dict]:
        return run(self._list_all_caps_async(user, filters))

    async def _list_all_caps_async(self, user: dict, filters: dict = None) -> List[dict]:
        filters = filters or {}
        tid = None
        if user.get("role") not in settings.CROSS_TENANT_ROLES:
            tid = register_tenant(self.tenant_id)

        try:
            limit = min(int(filters.get("limit") or filters.get("page_size") or 100), 500)
        except (TypeError, ValueError):
            limit = 100

        stmt = (
            select(Cap, Can, Hazard)
            .join(Can, Cap.can_id == Can.id)
            .join(Hazard, Can.hazard_id == Hazard.id)
            .where(
                Cap.is_demo == demo_scope(),
                Can.is_demo == demo_scope(),
                Hazard.is_demo == demo_scope(),
            )
        )
        if tid:
            stmt = stmt.where(Cap.tenant_id == tid)
        if filters.get("status"):
            stmt = stmt.where(Cap.status == filters["status"])
        if filters.get("department"):
            dept = str(filters["department"])
            stmt = stmt.where(
                or_(Cap.department == dept, Can.department == dept)
            )
        can_id_f = filters.get("can_id")
        if can_id_f:
            conds = [Can.can_reference == str(can_id_f)]
            try:
                conds.append(Can.id == uuid.UUID(str(can_id_f)))
            except (ValueError, TypeError, AttributeError):
                pass
            stmt = stmt.where(Cap.can_id.in_(
                select(Can.id).where(
                    or_(*conds),
                    Can.is_demo == demo_scope(),
                )
            ))
        if filters.get("days"):
            try:
                cutoff = datetime.now(timezone.utc) - timedelta(days=int(filters["days"]))
                stmt = stmt.where(Cap.created_at >= cutoff)
            except (TypeError, ValueError):
                pass

        async with session_scope() as session:
            rows = (
                await session.execute(stmt.order_by(Cap.created_at.desc()).limit(limit))
            ).all()
            results = []
            for cap_row, can_row, hazard_row in rows:
                data = _cap_to_dict(cap_row, can_row=can_row, hazard_id_ref=hazard_row.hazard_id)
                if filters.get("search"):
                    hay = " ".join(str(v) for v in [
                        data.get("cap_reference", ""),
                        data.get("can_reference", ""),
                        data.get("action_plan", ""),
                        data.get("status", ""),
                    ]).lower()
                    if filters["search"].lower() not in hay:
                        continue
                results.append(data)
        results.sort(
            key=lambda r: r.get("submitted_at") or r.get("created_at") or datetime.min,
            reverse=True,
        )
        return results[:limit]

    def get_cap(self, cap_id: str, user: dict) -> Optional[dict]:
        return run(self._get_cap_async(cap_id, user))

    async def _get_cap_async(self, cap_id: str, user: dict) -> Optional[dict]:
        tid = None
        if user.get("role") not in settings.CROSS_TENANT_ROLES:
            tid = register_tenant(self.tenant_id)
        async with session_scope() as session:
            row = (await session.execute(_cap_lookup_stmt(tid, cap_id))).scalars().first()
            if not row:
                return None
            return _cap_to_dict(row)

    def update_cap(self, cap_id: str, payload: dict, user: dict) -> Optional[dict]:
        return run(self._update_cap_async(cap_id, payload, user))

    async def _update_cap_async(self, cap_id: str, payload: dict, user: dict) -> Optional[dict]:
        tid = register_tenant(self.tenant_id)
        async with session_scope() as session:
            row = (await session.execute(_cap_lookup_stmt(tid, cap_id))).scalars().first()
            if not row:
                return None
            for key, value in payload.items():
                if key in _CAP_MUTABLE_COLUMNS:
                    if key in _CAP_JSONB_COLUMNS:
                        value = _json_safe(value)
                    elif key in _CAP_DT_COLUMNS:
                        value = _dt(value)
                    setattr(row, key, value)
            row.updated_at = datetime.now(timezone.utc)
            await session.flush()
            return _cap_to_dict(row)

    def review_cap(self, cap_id: str, review: dict, user: dict) -> Optional[dict]:
        return run(self._review_cap_async(cap_id, review, user))

    async def _review_cap_async(self, cap_id: str, review: dict, user: dict) -> Optional[dict]:
        tid = register_tenant(self.tenant_id)
        now = datetime.now(timezone.utc)

        async with session_scope() as session:
            row = (await session.execute(_cap_lookup_stmt(tid, cap_id))).scalars().first()
            if not row:
                return None
            can_row = (
                await session.execute(select(Can).where(Can.id == row.can_id))
            ).scalars().first()

            changes: Dict[str, Any] = {
                "status": review["status"],
                "reviewed_by": user.get("email", user["uid"]),
                "reviewed_by_uid": user["uid"],
                "reviewed_at": now,
                "review_comments": review.get("comments"),
                # Buddha Air FORM SMSM 8.8.2 — review / sign-off block
                "managerial_approval": _json_safe(review.get("managerial_approval")),
                "caa_acceptance": _json_safe(review.get("caa_acceptance")),
                "rca": review.get("rca"),
                "residual_severity": review.get("residual_severity"),
                "residual_probability": review.get("residual_probability"),
                "residual_risk_index": review.get("residual_risk_index"),
                "residual_risk_level": review.get("residual_risk_level"),
                "residual_risk_outcome": review.get("residual_risk_outcome"),
                "residual_tolerability_tier": review.get("residual_tolerability_tier"),
                "residual_sra": _json_safe(review.get("residual_sra")),
                "root_causes": _json_safe(review.get("root_causes")),
                "action_items": _json_safe(review.get("action_items")),
                "ca_acceptance": review.get("ca_acceptance"),
                "manager_approval": review.get("manager_approval"),
                "manager_confirmation": review.get("manager_confirmation"),
                "closing_remarks": review.get("closing_remarks"),
                "sag_sign": review.get("sag_sign"),
                # Governance escalation (Accountable Executive review)
                "escalated_to_ae": review.get("escalated_to_ae"),
                "escalated_by": review.get("escalated_by"),
                "escalation_reason": review.get("escalation_reason"),
                # Formal AE risk-acceptance sign-off record
                "ae_signature": review.get("ae_signature"),
                "ae_review_interval_days": review.get("ae_review_interval_days"),
            }

            # Server-side Residual SRA canonicalisation on review.
            residual_sra = self._sra_block(
                review.get("residual_severity"),
                review.get("residual_probability"),
                assessed_by=user.get("email", user["uid"]),
                assessed_at=now,
                provided=review.get("residual_sra"),
            )
            if residual_sra:
                changes["residual_sra"] = _json_safe(residual_sra)
                changes["residual_severity"] = residual_sra["severity"]
                changes["residual_probability"] = residual_sra["probability"]
                changes["residual_risk_index"] = residual_sra["risk_index"]
                changes["residual_risk_level"] = residual_sra["risk_level"]
                changes["residual_risk_outcome"] = residual_sra["risk_outcome"]
                changes["residual_tolerability_tier"] = residual_sra["tolerability_tier"]
            elif review.get("residual_risk_index"):
                thresholds = get_thresholds(self.tenant_id)
                changes["residual_risk_level"] = get_risk_level(
                    review["residual_risk_index"], thresholds
                )
                changes["residual_risk_outcome"] = risk_outcome(
                    review.get("residual_severity") or 1,
                    review.get("residual_probability") or 1,
                    thresholds,
                )
                changes["residual_tolerability_tier"] = get_tolerability_tier(
                    review["residual_risk_index"], thresholds
                )
            if review.get("sag_sign"):
                changes["sag_signed_by"] = review.get("sag_signed_by")
                changes["sag_signed_at"] = _dt(review.get("sag_signed_at")) or now
            if review.get("revision_deadline"):
                changes["revision_deadline"] = _dt(review["revision_deadline"])

            if review.get("escalated_to_ae"):
                changes["escalated_at"] = _dt(review.get("escalated_at")) or now

            # AE risk-acceptance: stamp decision time + mandatory review date
            # derived from the chosen interval.
            if review.get("ae_signature"):
                changes["ae_signed_at"] = _dt(review.get("ae_signed_at")) or now
                interval = review.get("ae_review_interval_days")
                if interval:
                    changes["ae_review_date"] = now + timedelta(days=int(interval))

            if review["status"] == "Completed":
                changes["closed_by"] = review.get("closed_by") or user.get("email", user["uid"])
                changes["closed_at"] = _dt(review.get("closed_at")) or now
                changes["closed_signature"] = review.get("closed_signature")

            for key, value in changes.items():
                if key in _CAP_MUTABLE_COLUMNS:
                    setattr(row, key, value)
            row.updated_at = now

            can_data = None
            # Update CAN status and hazard if accepted
            if review["status"] == "Completed" and can_row is not None:
                can_row.status = "Closed"
                can_row.updated_at = now
                await self._set_hazard_status(
                    session, can_row.hazard_id, "Under Review", now
                )
            await session.flush()
            if can_row is not None:
                return _cap_to_dict(
                    row, can_row=can_row, hazard_id_ref=await _hazard_ref(session, can_row)
                )
            return _cap_to_dict(row)

    # ── Stats ──

    def get_can_stats(self, user: dict, department: Optional[str] = None) -> Dict[str, Any]:
        return run(self._get_can_stats_async(user, department))

    async def _get_can_stats_async(
        self, user: dict, department: Optional[str] = None
    ) -> Dict[str, Any]:
        stmt = select(Can).where(Can.is_demo == demo_scope())
        if user.get("role") not in settings.CROSS_TENANT_ROLES:
            stmt = stmt.where(Can.tenant_id == register_tenant(self.tenant_id))
        if department:
            stmt = stmt.where(Can.department == department)

        async with session_scope() as session:
            rows = (await session.scalars(stmt)).all()

        stats = {"Open": 0, "Under Review": 0, "Closed": 0}
        priority_counts = {"High": 0, "Medium": 0, "Low": 0}
        for row in rows:
            status = row.status or "Open"
            if status in stats:
                stats[status] += 1
            pri = row.priority
            if pri in priority_counts:
                priority_counts[pri] += 1

        return {
            "by_status": stats,
            "by_priority": priority_counts,
            "total": len(rows),
        }

    def get_cap_stats(self, user: dict, department: Optional[str] = None) -> Dict[str, Any]:
        return run(self._get_cap_stats_async(user, department))

    async def _get_cap_stats_async(
        self, user: dict, department: Optional[str] = None
    ) -> Dict[str, Any]:
        stmt = (
            select(Cap)
            .join(Can, Cap.can_id == Can.id)
            .where(Cap.is_demo == demo_scope(), Can.is_demo == demo_scope())
        )
        if user.get("role") not in settings.CROSS_TENANT_ROLES:
            stmt = stmt.where(Cap.tenant_id == register_tenant(self.tenant_id))
        if department:
            stmt = stmt.where(or_(Cap.department == department, Can.department == department))

        async with session_scope() as session:
            rows = (await session.scalars(stmt)).all()

        stats = {"In Progress": 0, "Under Review": 0, "Completed": 0, "Revision Required": 0, "Overdue": 0}
        for row in rows:
            status = row.status or "In Progress"
            if status in stats:
                stats[status] += 1

        return {"by_status": stats, "total": len(rows)}

    # ── Hazard integration ──

    def _update_hazard_status(self, hazard_id: str, status: str):
        try:
            service = HazardService(self.tenant_id)
            user = {"uid": "system", "role": "AIRLINE_ADMIN", "tenant_id": self.tenant_id}
            service.update_status(hazard_id, status, user)
            logger.info(f"Hazard {hazard_id} status updated to {status} via CAN/CAP")
        except Exception as e:
            logger.warning(f"Failed to update hazard {hazard_id} status: {e}")