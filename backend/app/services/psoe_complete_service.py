# ============================================================================
# FILE: psoe_complete_service.py
# PATH: backend/app/services/psoe_complete_service.py
# PURPOSE: CAA PSOE (Post-Safety Oversight Evaluation) persistence layer for
#          the SUPABASE-backed module. Implements the ICAO Annex 19 / CAAN
#          Appendix 10 surveillance workflow:
#
#            * assessment list / get / create / save-responses
#            * categorical scoring (Compliant / Partially Compliant /
#              Non-Compliant / Not Applicable) with component percentages
#              and 1-5 maturity levels
#            * findings CRUD, completion, and an HTML surveillance report
#
#          Mirrors the sram_service conventions: async methods that open a
#          session_scope(), tenant-isolate every query through
#          register_tenant(slug), raise SramNotFoundError-style custom
#          exceptions and return plain dicts.
#
#          NOTE: this is a NEW module — the legacy Firestore PSOE service
#          (backend/app/services/psoe_service.py) is intentionally untouched.
# ============================================================================

from __future__ import annotations

import html
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import Date, select

from app.db.db_models import PsoeAssessment, PsoeFinding, PsoeQuestion
from app.db.ids import register_tenant, tenant_slug
from app.db.isolation import demo_scope
from app.db.session import session_scope

COMPONENT_ORDER = (
    "Safety Management",
    "Risk Management",
    "Safety Assurance",
    "Safety Promotion",
)

RESPONSE_OPTIONS = (
    "Compliant",
    "Partially Compliant",
    "Non-Compliant",
    "Not Applicable",
)

FINDING_TYPES = ("Observation", "Finding", "Major Finding", "Critical Finding")
FINDING_STATUSES = ("open", "in_progress", "closed")

TEMPLATE_VERSION = "ICAO_Appendix_10_v1"

LEVELS = (
    (20, "Level 1 - Initial"),
    (40, "Level 2 - Developing"),
    (60, "Level 3 - Maturing"),
    (80, "Level 4 - Advanced"),
    (None, "Level 5 - World-Class"),
)


class PsoeNotFoundError(Exception):
    """Raised when an assessment / finding / question bank access fails."""


# ----------------------------------------------------------------------------
# Serialization helpers
# ----------------------------------------------------------------------------

def _row_to_dict(row: Any) -> dict:
    data: Dict[str, Any] = {}
    for col in row.__table__.columns:
        value = getattr(row, col.name)
        if isinstance(value, uuid.UUID):
            value = str(value)
        elif isinstance(value, (datetime, date)):
            value = value.isoformat()
        elif hasattr(value, "isoformat"):
            value = value.isoformat()
        data[col.name] = value
    return data


def _tenant_uuid(tenant_slug_or_id: str) -> str:
    return register_tenant(tenant_slug_or_id)


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    dt = _parse_dt(value)
    return dt.date() if dt else None


# ----------------------------------------------------------------------------
# Questions
# ----------------------------------------------------------------------------

async def get_questions() -> dict:
    """Full question bank grouped by component (ordered)."""
    async with session_scope() as session:
        rows = (await session.execute(
            select(PsoeQuestion).order_by(PsoeQuestion.component, PsoeQuestion.question_number)
        )).scalars().all()

    components = []
    for comp in COMPONENT_ORDER:
        comp_rows = [r for r in rows if r.component == comp]
        components.append({
            "name": comp,
            "questions": [
                {
                    "id": str(q.id),
                    "question_number": q.question_number,
                    "question_text": q.question_text,
                }
                for q in comp_rows
            ],
        })
    return {"template_version": TEMPLATE_VERSION, "components": components}


# ----------------------------------------------------------------------------
# Assessments
# ----------------------------------------------------------------------------

async def list_assessments(tenant_id: str, status: Optional[str] = None) -> dict:
    """Assessments for a tenant (newest first), optional status filter."""
    tid = _tenant_uuid(tenant_id)
    async with session_scope() as session:
        query = select(PsoeAssessment).where(PsoeAssessment.tenant_id == uuid.UUID(tid))
        if status:
            query = query.where(PsoeAssessment.status == status)
        query = query.order_by(PsoeAssessment.assessment_date.desc().nullslast(),
                               PsoeAssessment.created_at.desc())
        rows = (await session.execute(query)).scalars().all()

    out = []
    for r in rows:
        data = _row_to_dict(r)
        data["tenant_id"] = tenant_slug(data["tenant_id"])
        out.append(data)
    return {"rows": out}


async def get_assessment(assessment_id: str, tenant_id: str) -> dict:
    """A single assessment with its findings (deep payload for the editor)."""
    tid = _tenant_uuid(tenant_id)
    async with session_scope() as session:
        row = (await session.execute(
            select(PsoeAssessment).where(
                PsoeAssessment.id == uuid.UUID(assessment_id),
                PsoeAssessment.tenant_id == uuid.UUID(tid),
            )
        )).scalar_one_or_none()
        if not row:
            raise PsoeNotFoundError(
                f"Assessment {assessment_id} not found for tenant {tenant_id}"
            )
        findings = (await session.execute(
            select(PsoeFinding)
            .where(PsoeFinding.assessment_id == row.id)
            .order_by(PsoeFinding.created_at.desc())
        )).scalars().all()

    data = _row_to_dict(row)
    data["tenant_id"] = tenant_slug(data["tenant_id"])
    data["findings"] = [_row_to_dict(f) for f in findings]
    return data


async def create_assessment(data: dict, tenant_id: str, user: dict) -> dict:
    """Create a draft PSOE assessment with an empty response set."""
    tid = _tenant_uuid(tenant_id)
    now = datetime.now(timezone.utc)
    async with session_scope() as session:
        row = PsoeAssessment(
            tenant_id=uuid.UUID(tid),
            title=(data.get("title") or "").strip() or "PSOE Assessment",
            status="draft",
            department=data.get("department"),
            scope=data.get("scope"),
            auditor_name=data.get("auditor_name"),
            assessor_email=data.get("assessor_email"),
            assessment_date=_parse_dt(data.get("assessment_date")),
            template_version=data.get("template_version") or TEMPLATE_VERSION,
            responses=data.get("responses") or {},
            component_scores=None,
            overall_score_pct=None,
            overall_level=None,
            notes=data.get("notes"),
            is_demo=demo_scope(),
            created_by=(user or {}).get("email"),
            created_by_uid=(user or {}).get("uid"),
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        await session.flush()

    result = _row_to_dict(row)
    result["tenant_id"] = tenant_slug(result["tenant_id"])
    result["findings"] = []
    return result


async def save_responses(assessment_id: str, responses: dict, tenant_id: str) -> dict:
    """Persist the categorical response set without recomputing scores."""
    tid = _tenant_uuid(tenant_id)
    normalized = _normalize_responses(responses)
    async with session_scope() as session:
        row = await _get_assessment(session, assessment_id, tid)
        if not row:
            raise PsoeNotFoundError(
                f"Assessment {assessment_id} not found for tenant {tenant_id}"
            )
        row.responses = normalized
        row.updated_at = datetime.now(timezone.utc)

    result = _row_to_dict(row)
    result["tenant_id"] = tenant_slug(result["tenant_id"])
    return result


async def calculate_scores(assessment_id: str, tenant_id: str) -> dict:
    """Compute component percentages + overall score/level from the responses
    using the CAA Appendix 10 formula:
        component pct = Compliant / answered  (Not Applicable excluded)
        overall      = mean of the 4 component percentages
    0-20% L1 Initial, 21-40% L2 Developing, 41-60% L3 Maturing,
    61-80% L4 Advanced, 81-100% L5 World-Class."""
    tid = _tenant_uuid(tenant_id)
    async with session_scope() as session:
        row = await _get_assessment(session, assessment_id, tid)
        if not row:
            raise PsoeNotFoundError(
                f"Assessment {assessment_id} not found for tenant {tenant_id}"
            )
        questions = (await session.execute(
            select(PsoeQuestion).order_by(PsoeQuestion.question_number)
        )).scalars().all()

        responses = row.responses or {}
        component_scores: Dict[str, dict] = {}
        percentages: List[float] = []
        for comp in COMPONENT_ORDER:
            comp_questions = [q for q in questions if q.component == comp]
            answered = 0
            compliant = 0
            comp_breakdown = []
            for q in comp_questions:
                entry = _entry_for(responses, q.question_number)
                entry["question_number"] = q.question_number
                entry["question_text"] = q.question_text
                entry["component"] = comp
                comp_breakdown.append(entry)
                value = entry["response"]
                if value == "Not Applicable" or not value:
                    continue
                answered += 1
                if value == "Compliant":
                    compliant += 1
            pct = round((compliant / answered) * 100, 1) if answered else 0.0
            if answered:
                percentages.append(pct)
            component_scores[comp] = {
                "compliant": compliant,
                "answered": answered,
                "percentage": pct,
            }

        overall = round(sum(percentages) / len(percentages), 1) if percentages else 0.0
        level = _level_name(overall)

        row.component_scores = component_scores
        row.overall_score_pct = overall
        row.overall_level = level
        row.updated_at = datetime.now(timezone.utc)

    result = _row_to_dict(row)
    result["tenant_id"] = tenant_slug(result["tenant_id"])
    return {
        "assessment": result,
        "scores": {
            "components": component_scores,
            "overall_score_pct": overall,
            "overall_level": level,
        },
        "breakdown": _breakdown(questions, responses),
    }


async def complete_assessment(assessment_id: str, tenant_id: str, user: dict) -> dict:
    """Finalise an assessment: (re)compute scores and mark it completed."""
    tid = _tenant_uuid(tenant_id)
    async with session_scope() as session:
        row = await _get_assessment(session, assessment_id, tid)
        if not row:
            raise PsoeNotFoundError(
                f"Assessment {assessment_id} not found for tenant {tenant_id}"
            )
        questions = (await session.execute(
            select(PsoeQuestion).order_by(PsoeQuestion.question_number)
        )).scalars().all()
        component_scores, overall, level = _score(responses=row.responses or {}, questions=questions)

        row.status = "completed"
        row.component_scores = component_scores
        row.overall_score_pct = overall
        row.overall_level = level
        row.updated_at = datetime.now(timezone.utc)

    result = _row_to_dict(row)
    result["tenant_id"] = tenant_slug(result["tenant_id"])
    return {
        "assessment": result,
        "scores": {
            "components": component_scores,
            "overall_score_pct": overall,
            "overall_level": level,
        },
    }


# ----------------------------------------------------------------------------
# Findings
# ----------------------------------------------------------------------------

async def add_finding(assessment_id: str, data: dict, tenant_id: str, user: dict) -> dict:
    """Raise a finding on an assessment. finding_type defaults to 'Finding'."""
    tid = _tenant_uuid(tenant_id)
    finding_type = data.get("finding_type") or "Finding"
    if finding_type not in FINDING_TYPES:
        raise ValueError(f"finding_type must be one of {FINDING_TYPES}, got {finding_type!r}")
    if not (data.get("description") or "").strip():
        raise ValueError("description is required")

    now = datetime.now(timezone.utc)
    async with session_scope() as session:
        assessment = await _get_assessment(session, assessment_id, tid)
        if not assessment:
            raise PsoeNotFoundError(
                f"Assessment {assessment_id} not found for tenant {tenant_id}"
            )
        row = PsoeFinding(
            assessment_id=assessment.id,
            finding_type=finding_type,
            description=(data.get("description") or "").strip(),
            corrective_action=data.get("corrective_action"),
            status=data.get("status") or "open",
            target_date=_parse_date(data.get("target_date")),
            closed_date=_parse_date(data.get("closed_date")),
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        await session.flush()

    result = _row_to_dict(row)
    result["assessment_id"] = str(result["assessment_id"])
    return result


async def update_finding(finding_id: str, data: dict, tenant_id: str) -> dict:
    """Update a finding (type, description, action, status, dates)."""
    tid = _tenant_uuid(tenant_id)
    async with session_scope() as session:
        row = (await session.execute(
            select(PsoeFinding)
            .join(PsoeAssessment, PsoeAssessment.id == PsoeFinding.assessment_id)
            .where(
                PsoeFinding.id == uuid.UUID(finding_id),
                PsoeAssessment.tenant_id == uuid.UUID(tid),
            )
        )).scalar_one_or_none()
        if not row:
            raise PsoeNotFoundError(
                f"Finding {finding_id} not found for tenant {tenant_id}"
            )

        if data.get("finding_type") is not None:
            finding_type = data["finding_type"]
            if finding_type not in FINDING_TYPES:
                raise ValueError(f"finding_type must be one of {FINDING_TYPES}")
            row.finding_type = finding_type
        if data.get("description") is not None:
            description = (data.get("description") or "").strip()
            if not description:
                raise ValueError("description cannot be empty")
            row.description = description
        if data.get("corrective_action") is not None:
            row.corrective_action = data["corrective_action"]
        if data.get("status") is not None:
            status = data["status"]
            if status not in FINDING_STATUSES:
                raise ValueError(f"status must be one of {FINDING_STATUSES}")
            row.status = status
            if status == "closed" and not row.closed_date:
                row.closed_date = date.today()
        if data.get("target_date") is not None:
            row.target_date = _parse_date(data["target_date"])
        if data.get("closed_date") is not None:
            row.closed_date = _parse_date(data["closed_date"])
        row.updated_at = datetime.now(timezone.utc)

    result = _row_to_dict(row)
    result["assessment_id"] = str(result["assessment_id"])
    return result


async def delete_finding(finding_id: str, tenant_id: str) -> dict:
    """Delete a finding that belongs to one of the tenant's assessments."""
    tid = _tenant_uuid(tenant_id)
    async with session_scope() as session:
        row = (await session.execute(
            select(PsoeFinding)
            .join(PsoeAssessment, PsoeAssessment.id == PsoeFinding.assessment_id)
            .where(
                PsoeFinding.id == uuid.UUID(finding_id),
                PsoeAssessment.tenant_id == uuid.UUID(tid),
            )
        )).scalar_one_or_none()
        if not row:
            raise PsoeNotFoundError(
                f"Finding {finding_id} not found for tenant {tenant_id}"
            )
        await session.delete(row)

    return {"deleted": True, "id": finding_id}


# ----------------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------------

async def generate_report(assessment_id: str, tenant_id: str) -> dict:
    """Build the HTML surveillance report (score summary + findings)."""
    tid = _tenant_uuid(tenant_id)
    async with session_scope() as session:
        row = (await session.execute(
            select(PsoeAssessment).where(
                PsoeAssessment.id == uuid.UUID(assessment_id),
                PsoeAssessment.tenant_id == uuid.UUID(tid),
            )
        )).scalar_one_or_none()
        if not row:
            raise PsoeNotFoundError(
                f"Assessment {assessment_id} not found for tenant {tenant_id}"
            )
        questions = (await session.execute(
            select(PsoeQuestion).order_by(PsoeQuestion.question_number)
        )).scalars().all()
        findings = (await session.execute(
            select(PsoeFinding)
            .where(PsoeFinding.assessment_id == row.id)
            .order_by(PsoeFinding.created_at.desc())
        )).scalars().all()

    component_scores = row.component_scores or {}
    breakdown = _breakdown(questions, row.responses or {})

    component_rows = []
    for comp in COMPONENT_ORDER:
        scores = component_scores.get(comp, {})
        component_rows.append(
            f"<tr><td>{html.escape(comp)}</td>"
            f"<td>{scores.get('compliant', 0)}</td>"
            f"<td>{scores.get('answered', 0)}</td>"
            f"<td>{scores.get('percentage', 0)}%</td></tr>"
        )

    finding_rows = []
    for f in findings:
        finding_rows.append(
            f"<tr><td>{html.escape(f.finding_type or 'Finding')}</td>"
            f"<td>{html.escape(f.description)}</td>"
            f"<td>{html.escape(f.corrective_action or '—')}</td>"
            f"<td>{html.escape(f.status)}</td></tr>"
        )

    response_rows = []
    for comp in COMPONENT_ORDER:
        items = [b for b in breakdown if b["component"] == comp]
        if not items:
            continue
        response_rows.append(
            f"<tr><td colspan=3 style='background:#eef3f9;font-weight:bold'>"
            f"{html.escape(comp)}</td></tr>"
        )
        for b in items:
            response_rows.append(
                f"<tr><td>Q{b['question_number']}</td>"
                f"<td>{html.escape(b['question_text'])}</td>"
                f"<td>{html.escape(b['response'] or 'Not Answered')}</td></tr>"
            )

    title = html.escape(row.title or "PSOE Assessment Report")
    notes = html.escape(row.notes or "")
    html_doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>{title}</title>
<style>
 body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #1f2937; margin: 40px auto; max-width: 900px; }}
 h1 {{ color: #0f3d63; border-bottom: 3px solid #0f3d63; padding-bottom: 8px; }}
 h2 {{ color: #0f3d63; margin-top: 28px; }}
 table {{ border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 13px; }}
 th, td {{ border: 1px solid #cbd5e1; padding: 6px 8px; text-align: left; vertical-align: top; }}
 th {{ background: #0f3d63; color: #fff; }}
 .score {{ font-size: 18px; font-weight: bold; color: #0f3d63; }}
 .meta {{ color: #475569; }}
 footer {{ margin-top: 40px; border-top: 1px solid #cbd5e1; padding-top: 10px; color: #64748b; font-size: 12px; }}
</style></head><body>
<h1>{title}</h1>
<p class=meta>Tenant: {html.escape(tenant_slug(str(row.tenant_id)))} &nbsp;|&nbsp;
Status: {html.escape(row.status)} &nbsp;|&nbsp;
Auditor: {html.escape(row.auditor_name or '—')} &nbsp;|&nbsp;
Date: {row.assessment_date.isoformat() if row.assessment_date else '—'}</p>
<p class=meta>Template: {html.escape(row.template_version)}</p>
<p class=score>Overall: {row.overall_score_pct}% — {html.escape(row.overall_level or '—')}</p>
<h2>Component Scores</h2>
<table><tr><th>Component</th><th>Compliant</th><th>Answered</th><th>Percentage</th></tr>
{''.join(component_rows)}</table>
<h2>Responses</h2>
<table><tr><th>#</th><th>Question</th><th>Response</th></tr>
{''.join(response_rows)}</table>
<h2>Findings &amp; Observations</h2>
<table><tr><th>Type</th><th>Description</th><th>Corrective Action</th><th>Status</th></tr>
{''.join(finding_rows) or '<tr><td colspan=4>No findings recorded.</td></tr>'}</table>
<h2>Notes</h2>
<p>{notes or '—'}</p>
<footer>Generated {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')} • CAAN PSOE Module</footer>
</body></html>"""

    return {"html": html_doc, "filename": f"psoe-report-{assessment_id[:8]}.html"}


# ----------------------------------------------------------------------------
# Scoring helpers
# ----------------------------------------------------------------------------

def _normalize_responses(responses: Any) -> Dict[str, dict]:
    """Accept a plain list of {'question_number': n, 'response': ...} or an
    object {n: {'response': ...}}; always return {str(n): {...}}."""
    out: Dict[str, dict] = {}
    if isinstance(responses, list):
        for item in responses:
            if not isinstance(item, dict):
                continue
            number = item.get("question_number")
            if number is None:
                continue
            out[str(number)] = {
                "response": item.get("response"),
                "evidence": item.get("evidence") or "",
                "findings": item.get("findings") or "",
            }
    elif isinstance(responses, dict):
        for key, item in responses.items():
            number = key.get("question_number") if isinstance(key, dict) else key
            if number is None:
                continue
            if isinstance(item, dict):
                out[str(number)] = {
                    "response": item.get("response"),
                    "evidence": item.get("evidence") or "",
                    "findings": item.get("findings") or "",
                }
            else:
                out[str(number)] = {"response": item, "evidence": "", "findings": ""}
    return out


def _entry_for(responses: Dict[str, dict], question_number: int) -> dict:
    entry = responses.get(str(question_number)) or {}
    return {
        "response": entry.get("response"),
        "evidence": entry.get("evidence") or "",
        "findings": entry.get("findings") or "",
    }


def _score(responses: Dict[str, dict], questions: List[PsoeQuestion]) -> tuple[dict, float, Optional[str]]:
    responses = _normalize_responses(responses)
    component_scores: Dict[str, dict] = {}
    percentages: List[float] = []
    for comp in COMPONENT_ORDER:
        comp_questions = [q for q in questions if q.component == comp]
        answered = 0
        compliant = 0
        for q in comp_questions:
            value = _entry_for(responses, q.question_number)["response"]
            if value == "Not Applicable" or not value:
                continue
            answered += 1
            if value == "Compliant":
                compliant += 1
        pct = round((compliant / answered) * 100, 1) if answered else 0.0
        if answered:
            percentages.append(pct)
        component_scores[comp] = {
            "compliant": compliant,
            "answered": answered,
            "percentage": pct,
        }
    overall = round(sum(percentages) / len(percentages), 1) if percentages else 0.0
    return component_scores, overall, _level_name(overall)


def _level_name(overall_pct: float) -> str:
    for ceiling, label in LEVELS:
        if ceiling is None or overall_pct <= ceiling:
            return label
    return "Level 5 - World-Class"


def _breakdown(questions: List[PsoeQuestion], responses: Dict[str, dict]) -> List[dict]:
    responses = _normalize_responses(responses)
    out = []
    for q in questions:
        entry = _entry_for(responses, q.question_number)
        entry["question_number"] = q.question_number
        entry["question_text"] = q.question_text
        entry["component"] = q.component
        out.append(entry)
    return out


async def _get_assessment(session: Any, assessment_id: str, tid: str) -> Optional[PsoeAssessment]:
    return (await session.execute(
        select(PsoeAssessment).where(
            PsoeAssessment.id == uuid.UUID(assessment_id),
            PsoeAssessment.tenant_id == uuid.UUID(tid),
        )
    )).scalar_one_or_none()