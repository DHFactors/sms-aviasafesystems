# ============================================================================
# FILE: sram_service.py
# PATH: backend/app/services/sram_service.py
# PURPOSE: Safety Risk Assessment & Mitigation (SRAM) persistence layer -
#          Bow-Tie analyses, threats, consequences, controls/barriers, risk
#          register and barrier register scoring.
#
#          Mirrors the hazard_service conventions: async methods that open a
#          session_scope(), tenant-isolate every query through
#          register_tenant(slug) and return plain dicts.
# ============================================================================

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.db_models import (
    BarrierRegisterEntry,
    BowTieAnalysis,
    BowTieConsequence,
    BowTieControl,
    BowTieThreat,
    Hazard,
    RiskRegisterEntry,
)
from app.db.ids import register_tenant, tenant_slug
from app.db.session import session_scope
from app.db.isolation import demo_scope
from app.services import risk_calculator


class SramNotFoundError(Exception):
    """Raised when a requested SRAM record does not exist in the tenant scope."""


CONTROL_TYPES = ("preventive", "recovery")
RISK_REGISTER_STATUSES = ("open", "in_progress", "closed")
BARRIER_IMPL_STATUSES = ("not_started", "in_progress", "implemented", "verified")

_BSV_ELEMENTS = tuple(risk_calculator.BSV_ELEMENT_WEIGHTS.keys())


# ----------------------------------------------------------------------------
# Serialization helpers
# ----------------------------------------------------------------------------

def _row_to_dict(row: Any) -> dict:
    data: Dict[str, Any] = {}
    for col in row.__table__.columns:
        value = getattr(row, col.name)
        if isinstance(value, uuid.UUID):
            value = str(value)
        elif isinstance(value, datetime):
            value = value.isoformat()
        elif hasattr(value, "isoformat"):
            value = value.isoformat()
        data[col.name] = value
    return data


def _barrier_to_dict(row: BarrierRegisterEntry) -> dict:
    data = _row_to_dict(row)
    data["barrier_type"] = data.get("barrier_type")
    return data


# ----------------------------------------------------------------------------
# Tenant helpers
# ----------------------------------------------------------------------------

def _tenant_uuid(tenant_slug_or_id: str) -> str:
    return register_tenant(tenant_slug_or_id)


def is_demo_row() -> bool:
    return demo_scope()


# ----------------------------------------------------------------------------
# Bow-Tie analysis
# ----------------------------------------------------------------------------

async def create_bowtie(hazard_id: str, data: dict, tenant_id: str, user: dict) -> dict:
    """Create (get-or-create) the Bow-Tie analysis for a hazard."""
    tid = _tenant_uuid(tenant_id)
    hazard = await _get_hazard(hazard_id, tid)
    top_event = (data or {}).get("top_event")
    description = (data or {}).get("description")

    async with session_scope() as session:
        existing = await _get_bowtie_by_hazard(session, hazard_id, tid)
        if existing:
            updated = False
            if top_event is not None and top_event != existing.top_event:
                existing.top_event = top_event
                updated = True
            if description is not None and description != existing.description:
                existing.description = description
                updated = True
            if updated:
                existing.updated_at = datetime.now(timezone.utc)
            row = existing
        else:
            row = BowTieAnalysis(
                tenant_id=uuid.UUID(tid),
                hazard_id=hazard_id,
                hazard_title=(hazard.title if hazard else hazard_id),
                top_event=top_event,
                description=description,
                status="In Progress",
                created_by=(user or {}).get("email"),
                is_demo=is_demo_row(),
            )
            session.add(row)
            await session.flush()

    result = _row_to_dict(row)
    result["tenant_id"] = tenant_slug(result["tenant_id"])
    return result


async def get_bowtie_by_hazard(hazard_id: str, tenant_id: str) -> dict:
    """Full Bow-Tie payload (head, threats, consequences, controls)."""
    tid = _tenant_uuid(tenant_id)
    async with session_scope() as session:
        bowtie = await _get_bowtie_by_hazard(session, hazard_id, tid)
        if not bowtie:
            raise SramNotFoundError(
                f"No Bow-Tie analysis found for hazard {hazard_id} in tenant {tenant_id}"
            )
        threats = await _get_threats(session, bowtie.id)
        consequences = await _get_consequences(session, bowtie.id)
        controls = await _get_controls(session, bowtie.id)
        register = await _get_risk_entry_by_hazard(session, hazard_id, tid)

    result = _row_to_dict(bowtie)
    result["tenant_id"] = tenant_slug(result["tenant_id"])
    result["threats"] = [_row_to_dict(t) for t in threats]
    result["consequences"] = [_row_to_dict(c) for c in consequences]
    result["controls"] = [_row_to_dict(c) for c in controls]
    result["risk_register"] = _row_to_dict(register) if register else None
    return result


async def add_threat(bowtie_id: str, threat: str, tenant_id: str,
                     order: Optional[int] = None, probability: Optional[int] = None) -> dict:
    tid = _tenant_uuid(tenant_id)
    async with session_scope() as session:
        bowtie = await _get_bowtie(session, bowtie_id, tid)
        if not bowtie:
            raise SramNotFoundError(f"Bow-Tie {bowtie_id} not found for tenant {tenant_id}")

        order = order or await _next_order(
            session, BowTieThreat, bowtie_id, "threat_order"
        )
        row = BowTieThreat(
            tenant_id=uuid.UUID(tid),
            bowtie_id=bowtie.id,
            threat=threat,
            probability=probability,
            threat_order=order,
        )
        session.add(row)
        await session.flush()

    result = _row_to_dict(row)
    result["tenant_id"] = tenant_slug(result["tenant_id"])
    return result


async def add_consequence(bowtie_id: str, consequence: str, tenant_id: str,
                          order: Optional[int] = None,
                          severity: Optional[str] = "C") -> dict:
    tid = _tenant_uuid(tenant_id)
    async with session_scope() as session:
        bowtie = await _get_bowtie(session, bowtie_id, tid)
        if not bowtie:
            raise SramNotFoundError(f"Bow-Tie {bowtie_id} not found for tenant {tenant_id}")

        order = order or await _next_order(
            session, BowTieConsequence, bowtie_id, "consequence_order"
        )
        row = BowTieConsequence(
            tenant_id=uuid.UUID(tid),
            bowtie_id=bowtie.id,
            consequence=consequence,
            severity_level=str(severity or "C"),
            consequence_order=order,
        )
        session.add(row)
        await session.flush()

    result = _row_to_dict(row)
    result["tenant_id"] = tenant_slug(result["tenant_id"])
    return result


async def add_control(bowtie_id: str, control: str, control_type: str, tenant_id: str,
                      order: Optional[int] = None, owner: Optional[str] = None,
                      barrier_scores: Optional[dict] = None,
                      implementation_status: Optional[str] = None,
                      action_by: Optional[str] = None,
                      follow_up_date: Optional[str] = None) -> dict:
    """Register a preventive control or recovery barrier on the Bow-Tie.

    Also materialises the matching barrier_register row (same content) so the
    Barrier Register view lists every control; element scores, when provided,
    are scored and the BSV computed immediately.
    """
    if control_type not in CONTROL_TYPES:
        raise ValueError(f"control_type must be one of {CONTROL_TYPES}, got {control_type!r}")
    if implementation_status and implementation_status not in BARRIER_IMPL_STATUSES:
        raise ValueError(
            f"implementation_status must be one of {BARRIER_IMPL_STATUSES}, got {implementation_status!r}"
        )

    tid = _tenant_uuid(tenant_id)
    async with session_scope() as session:
        bowtie = await _get_bowtie(session, bowtie_id, tid)
        if not bowtie:
            raise SramNotFoundError(f"Bow-Tie {bowtie_id} not found for tenant {tenant_id}")

        order = order or await _next_order(
            session, BowTieControl, bowtie_id, "control_order", control_type=control_type
        )
        control_row = BowTieControl(
            tenant_id=uuid.UUID(tid),
            bowtie_id=bowtie.id,
            control=control,
            control_type=control_type,
            control_order=order,
            owner=owner,
            status="Planned",
        )
        session.add(control_row)
        await session.flush()

        bsv_value: Optional[float] = None
        bsv_result: Optional[dict] = None
        element_values: Dict[str, int] = {}
        if barrier_scores:
            bsv_result = risk_calculator.calculate_bsv(barrier_scores)
            bsv_value = bsv_result["bsv"]
            element_values = bsv_result["scores"]

        barrier_row = BarrierRegisterEntry(
            tenant_id=uuid.UUID(tid),
            bowtie_id=bowtie.id,
            control_id=control_row.id,
            hazard_id=bowtie.hazard_id,
            barrier=control,
            barrier_type=control_type,
            effectiveness=element_values.get("effectiveness"),
            cost_benefit=element_values.get("cost_benefit"),
            practicality=element_values.get("practicality"),
            acceptability=element_values.get("acceptability"),
            enforceability=element_values.get("enforceability"),
            durability=element_values.get("durability"),
            disinclination=element_values.get("disinclination"),
            bsv=bsv_value,
            implementation_status=implementation_status or "not_started",
            action_by=action_by,
            follow_up_date=_parse_dt(follow_up_date),
            is_demo=is_demo_row(),
        )
        session.add(barrier_row)
        await session.flush()

    result = _row_to_dict(control_row)
    result["tenant_id"] = tenant_slug(result["tenant_id"])
    result["barrier"] = _barrier_to_dict(barrier_row)
    if bsv_result:
        result["bsv"] = bsv_result
    return result


# ----------------------------------------------------------------------------
# Risk assessment + acceptance
# ----------------------------------------------------------------------------

async def calculate_risk(hazard_id: str, assessment_data: dict, tenant_id: str) -> dict:
    """Compute current/resultant risk indices, tolerability and (optional)
    aggregate Barrier Strength Value, then upsert the risk register entry."""
    tid = _tenant_uuid(tenant_id)
    data = assessment_data or {}

    probability_current = risk_calculator.normalize_probability(data.get("probability_current"))
    severity_current = data.get("severity_current")
    if not severity_current:
        raise ValueError("severity_current is required")

    current = risk_calculator.get_risk_matrix(probability_current, severity_current)

    resultant_cell: Optional[dict] = None
    if data.get("probability_resultant") is not None or data.get("severity_resultant"):
        prob_res = data.get("probability_resultant")
        sev_res = data.get("severity_resultant")
        if prob_res is None or not sev_res:
            raise ValueError(
                "Both probability_resultant and severity_resultant are required together"
            )
        resultant_cell = risk_calculator.get_risk_matrix(prob_res, sev_res)

    bsv_calc: Optional[dict] = None
    if data.get("barrier_scores"):
        bsv_calc = risk_calculator.calculate_bsv(data["barrier_scores"])

    hazard = await _get_hazard(hazard_id, tid)

    async with session_scope() as session:
        existing = await _get_risk_entry_by_hazard(session, hazard_id, tid)
        bowtie = await _get_bowtie_by_hazard(session, hazard_id, tid)

        fields = {
            "probability_current": current["probability"],
            "severity_current": current["severity"],
            "risk_index_current": current["risk_index"],
            "tolerability_current": current["tolerability"],
            "probability_resultant": resultant_cell["probability"] if resultant_cell else None,
            "severity_resultant": resultant_cell["severity"] if resultant_cell else None,
            "risk_index_resultant": resultant_cell["risk_index"] if resultant_cell else None,
            "tolerability_resultant": resultant_cell["tolerability"] if resultant_cell else None,
            "hazard_title": (hazard.title if hazard else hazard_id),
        }

        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
            if existing.status == "open":
                existing.status = "in_progress"
            existing.updated_at = datetime.now(timezone.utc)
            row = existing
        else:
            row = RiskRegisterEntry(
                tenant_id=uuid.UUID(tid),
                bowtie_id=bowtie.id if bowtie else None,
                hazard_id=hazard_id,
                status=data.get("status", "in_progress"),
                is_demo=is_demo_row(),
                **fields,
            )
            session.add(row)
            await session.flush()

        if bowtie and bowtie.status == "In Progress":
            bowtie.status = "Assessed"
            bowtie.updated_at = datetime.now(timezone.utc)

    result = _row_to_dict(row)
    result["tenant_id"] = tenant_slug(result["tenant_id"])
    return {
        "risk_register": result,
        "current": current,
        "resultant": resultant_cell,
        "barrier_strength": bsv_calc,
        "matrix": risk_calculator.build_risk_matrix(),
    }


async def accept_risk(risk_id_or_hazard: str, acceptance_data: dict,
                      tenant_id: str, user: dict) -> dict:
    """Accept a risk with ALARP justification and sign-off details."""
    tid = _tenant_uuid(tenant_id)
    data = acceptance_data or {}
    justification = (data.get("alarp_justification") or "").strip()
    if len(justification) < 10:
        raise ValueError("alarp_justification must be at least 10 characters")

    async with session_scope() as session:
        row = await _resolve_risk_entry(session, risk_id_or_hazard, data, tid)
        if not row:
            raise SramNotFoundError(
                f"Risk register entry {risk_id_or_hazard!r} not found for tenant {tenant_id}"
            )

        row.accepted = True
        row.alarp_justification = justification
        row.accepted_by = (user or {}).get("email")
        row.accepted_on = datetime.now(timezone.utc)
        if data.get("review_date"):
            row.review_date = _parse_dt(data["review_date"])
        row.status = data.get("status") or ("closed" if row.status == "in_progress" else row.status)
        if row.status not in RISK_REGISTER_STATUSES:
            raise ValueError(f"status must be one of {RISK_REGISTER_STATUSES}")
        row.updated_at = datetime.now(timezone.utc)

        bowtie = await _get_bowtie_by_hazard(session, row.hazard_id, tid)
        if bowtie and bowtie.status != "Accepted":
            bowtie.status = "Accepted"
            bowtie.updated_at = datetime.now(timezone.utc)

    result = _row_to_dict(row)
    result["tenant_id"] = tenant_slug(result["tenant_id"])
    return result


# ----------------------------------------------------------------------------
# Registers
# ----------------------------------------------------------------------------

async def get_barrier_register(hazard_id: str, tenant_id: str) -> dict:
    """All barriers/controls for a hazard, with element scores + BSV."""
    tid = _tenant_uuid(tenant_id)
    async with session_scope() as session:
        result = (await session.execute(
            select(BarrierRegisterEntry)
            .where(
                BarrierRegisterEntry.tenant_id == uuid.UUID(tid),
                BarrierRegisterEntry.hazard_id == hazard_id,
            )
            .order_by(BarrierRegisterEntry.barrier_type, BarrierRegisterEntry.created_at)
        )).scalars().all()

    hazard = await _get_hazard(hazard_id, tid)
    rows = [_barrier_to_dict(r) for r in result]
    return {
        "hazard_id": hazard_id,
        "hazard_title": hazard.title if hazard else None,
        "barriers": rows,
    }


async def get_barriers_all(tenant_id: str) -> dict:
    """Every barrier across the tenant's hazards (Barrier Register view)."""
    tid = _tenant_uuid(tenant_id)
    async with session_scope() as session:
        rows = (await session.execute(
            select(BarrierRegisterEntry)
            .where(BarrierRegisterEntry.tenant_id == uuid.UUID(tid))
            .order_by(BarrierRegisterEntry.created_at.desc())
        )).scalars().all()
        hazard_rows = (await session.execute(
            select(Hazard.hazard_id, Hazard.title).where(
                Hazard.tenant_id == uuid.UUID(tid)
            )
        )).all()

    titles = {hazard_id: title for hazard_id, title in hazard_rows}
    out = []
    for r in rows:
        data = _barrier_to_dict(r)
        data["hazard_title"] = titles.get(r.hazard_id)
        out.append(data)
    return {"rows": out}


async def get_risk_register(tenant_id: str) -> dict:
    """All risk register entries for a tenant, newest first."""
    tid = _tenant_uuid(tenant_id)
    async with session_scope() as session:
        result = (await session.execute(
            select(RiskRegisterEntry)
            .where(RiskRegisterEntry.tenant_id == uuid.UUID(tid))
            .order_by(RiskRegisterEntry.updated_at.desc())
        )).scalars().all()

    rows = []
    for r in result:
        data = _row_to_dict(r)
        data["tenant_id"] = tenant_slug(data["tenant_id"])
        rows.append(data)
    return {"rows": rows}


# ----------------------------------------------------------------------------
# Barrier upkeep helpers used by the register views
# ----------------------------------------------------------------------------

async def update_barrier(barrier_id: str, update_data: dict, tenant_id: str) -> dict:
    """Update one barrier's implementation status / action / scoring."""
    tid = _tenant_uuid(tenant_id)
    async with session_scope() as session:
        row = (await session.execute(
            select(BarrierRegisterEntry).where(
                BarrierRegisterEntry.id == uuid.UUID(barrier_id),
                BarrierRegisterEntry.tenant_id == uuid.UUID(tid),
            )
        )).scalar_one_or_none()
        if not row:
            raise SramNotFoundError(f"Barrier {barrier_id} not found for tenant {tenant_id}")

        scores = update_data.get("barrier_scores")
        element_values: Dict[str, int] = {}
        if scores:
            bsv_result = risk_calculator.calculate_bsv(scores)
            element_values = bsv_result["scores"]
            row.bsv = bsv_result["bsv"]
        for element, value in element_values.items():
            setattr(row, element, value)

        if update_data.get("implementation_status") is not None:
            status = update_data["implementation_status"]
            if status not in BARRIER_IMPL_STATUSES:
                raise ValueError(f"implementation_status must be one of {BARRIER_IMPL_STATUSES}")
            row.implementation_status = status
        if update_data.get("action_by") is not None:
            row.action_by = update_data["action_by"]
        if update_data.get("follow_up_date"):
            row.follow_up_date = _parse_dt(update_data["follow_up_date"])
        if update_data.get("notes") is not None:
            row.notes = update_data["notes"]
        row.updated_at = datetime.now(timezone.utc)

    return _barrier_to_dict(row)


# ----------------------------------------------------------------------------
# Internal query helpers
# ----------------------------------------------------------------------------

async def _get_hazard(hazard_id: str, tid: str) -> Optional[Hazard]:
    async with session_scope() as session:
        row = (await session.execute(
            select(Hazard).where(
                Hazard.tenant_id == uuid.UUID(tid),
                Hazard.hazard_id == hazard_id,
            )
        )).scalar_one_or_none()
    return row


async def _get_bowtie(session: AsyncSession, bowtie_id: str, tid: str) -> Optional[BowTieAnalysis]:
    return (await session.execute(
        select(BowTieAnalysis).where(
            BowTieAnalysis.id == uuid.UUID(bowtie_id),
            BowTieAnalysis.tenant_id == uuid.UUID(tid),
        )
    )).scalar_one_or_none()


async def _get_bowtie_by_hazard(session: AsyncSession, hazard_id: str,
                                tid: str) -> Optional[BowTieAnalysis]:
    return (await session.execute(
        select(BowTieAnalysis).where(
            BowTieAnalysis.tenant_id == uuid.UUID(tid),
            BowTieAnalysis.hazard_id == hazard_id,
        )
    )).scalar_one_or_none()


async def _get_threats(session: AsyncSession, bowtie_id: uuid.UUID) -> List[BowTieThreat]:
    return list((await session.execute(
        select(BowTieThreat)
        .where(BowTieThreat.bowtie_id == bowtie_id)
        .order_by(BowTieThreat.threat_order)
    )).scalars().all())


async def _get_consequences(session: AsyncSession, bowtie_id: uuid.UUID) -> List[BowTieConsequence]:
    return list((await session.execute(
        select(BowTieConsequence)
        .where(BowTieConsequence.bowtie_id == bowtie_id)
        .order_by(BowTieConsequence.consequence_order)
    )).scalars().all())


async def _get_controls(session: AsyncSession, bowtie_id: uuid.UUID) -> List[BowTieControl]:
    return list((await session.execute(
        select(BowTieControl)
        .where(BowTieControl.bowtie_id == bowtie_id)
        .order_by(BowTieControl.control_type, BowTieControl.control_order)
    )).scalars().all())


async def _get_risk_entry_by_hazard(session: AsyncSession, hazard_id: str,
                                    tid: str) -> Optional[RiskRegisterEntry]:
    return (await session.execute(
        select(RiskRegisterEntry).where(
            RiskRegisterEntry.tenant_id == uuid.UUID(tid),
            RiskRegisterEntry.hazard_id == hazard_id,
        )
    )).scalar_one_or_none()


async def _resolve_risk_entry(session: AsyncSession, risk_id_or_hazard: str,
                              data: dict, tid: str) -> Optional[RiskRegisterEntry]:
    if data.get("risk_id"):
        return (await session.execute(
            select(RiskRegisterEntry).where(
                RiskRegisterEntry.id == uuid.UUID(data["risk_id"]),
                RiskRegisterEntry.tenant_id == uuid.UUID(tid),
            )
        )).scalar_one_or_none()
    if data.get("hazard_id"):
        return await _get_risk_entry_by_hazard(session, data["hazard_id"], tid)
    try:
        return (await session.execute(
            select(RiskRegisterEntry).where(
                RiskRegisterEntry.id == uuid.UUID(risk_id_or_hazard),
                RiskRegisterEntry.tenant_id == uuid.UUID(tid),
            )
        )).scalar_one_or_none()
    except (ValueError, TypeError):
        return await _get_risk_entry_by_hazard(session, risk_id_or_hazard, tid)


async def _next_order(session: AsyncSession, model: Any, bowtie_id: str,
                      order_column: str,
                      control_type: Optional[str] = None) -> int:
    order_col = getattr(model, order_column)
    query = select(func.coalesce(func.max(order_col), 0)).where(
        model.bowtie_id == uuid.UUID(bowtie_id)
    )
    if control_type and model is BowTieControl:
        query = query.where(BowTieControl.control_type == control_type)
    return int((await session.execute(query)).scalar() or 0) + 1


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None