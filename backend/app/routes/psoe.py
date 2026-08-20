# ============================================================================
# FILE: psoe.py
# PATH: backend/app/routes/psoe.py
# PURPOSE: PSOE Audit & Surveillance endpoints (Phase 3 Step 2A/2C). Serves the
#          CAAN SMS Procedure Manual Appendix 10 checklist template and manages
#          tenant-scoped surveillance assessments. Assessments are stored in
#          the top-level ``psoe_assessments`` collection (each doc carries
#          ``tenant_id``) so CAAN_SMD can review assessments across operators.
#          Step 2C adds the export endpoint for PDF/HTML audit reports.
# ============================================================================

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request, Response
from loguru import logger

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import settings
from app.firebase import get_db
from app.middleware.auth import get_current_user, get_safety_manager
from app.models.psoe import (
    PSOEAnswer,
    PSOEAssessment,
    PSOEAssessmentCreate,
    PSOEAssessmentListItem,
    PSOEAssessmentUpdate,
)
from app.services.audit_service import log_audit, request_context
from app.services.psoe_service import (
    TEMPLATE_VERSION,
    load_template,
    score_assessment,
    overall_level,
)

router = APIRouter()

PSOE_COLLECTION = "psoe_assessments"


def _coll():
    return get_db().collection(PSOE_COLLECTION)


def _doc_to_assessment(snap) -> PSOEAssessment:
    data = dict(snap.to_dict() or {})
    data["id"] = data.get("id") or snap.id
    responses = data.get("responses") or []
    data["responses"] = [PSOEAnswer.model_validate(r) if isinstance(r, dict) else r for r in responses]
    return PSOEAssessment.model_validate(data)


def _effective_tenant(user: Dict[str, Any], requested: Optional[str]) -> str:
    """Resolve the tenant scope for a request.

    Cross-tenant roles (CAAN_SMD / SUPER_ADMIN) may scope to any tenant or
    browse all; tenant-bound roles are always locked to their own tenant.
    """
    role = user.get("role")
    if role in settings.CROSS_TENANT_ROLES:
        return requested or ""
    user_tenant = user.get("tenant_id")
    if not user_tenant:
        raise HTTPException(status_code=403, detail="Tenant access required")
    if requested and requested != user_tenant:
        raise HTTPException(status_code=403, detail="Cannot access another tenant's assessments")
    return user_tenant


@router.get("/template", response_model=dict)
async def get_template():
    """Return the standard CAAN Appendix 10 surveillance questions + weights."""
    template = load_template()
    return {
        "version": template.version,
        "source": template.source,
        "scoring_scale": template.scoring_scale,
        "total_weight": template.total_weight,
        "components": [c.model_dump() for c in template.components],
    }


@router.get("/assessments", response_model=List[PSOEAssessmentListItem])
async def list_assessments(
    tenant_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """List PSOE assessments for the caller's tenant (all tenants for CAAN_SMD)."""
    effective = _effective_tenant(user, tenant_id)
    try:
        docs = _coll().get()
    except Exception as e:
        logger.error(f"Failed to list PSOE assessments: {e}")
        raise HTTPException(status_code=500, detail="Assessment storage unavailable")

    items = []
    for snap in docs:
        data = snap.to_dict() or {}
        if effective and data.get("tenant_id") != effective:
            continue
        if status and data.get("status") != status:
            continue
        items.append(PSOEAssessmentListItem(
            id=data.get("id") or snap.id,
            tenant_id=data.get("tenant_id", ""),
            title=data.get("title", ""),
            status=data.get("status", "draft"),
            department=data.get("department"),
            scope=data.get("scope"),
            template_version=data.get("template_version"),
            overall_score_pct=data.get("overall_score_pct"),
            overall_level=data.get("overall_level"),
            assessment_date=data.get("assessment_date"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        ))
    items.sort(key=lambda i: i.created_at or datetime.min, reverse=True)
    return items


@router.post("/assessments", response_model=PSOEAssessment, status_code=status.HTTP_201_CREATED)
async def create_assessment(
    payload: PSOEAssessmentCreate,
    user: Dict[str, Any] = Depends(get_safety_manager),
):
    """Draft a new PSOE assessment (TENANT_ADMIN / AIRLINE_ADMIN / CAAN_SMD)."""
    if user.get("role") in settings.CROSS_TENANT_ROLES:
        tenant_id = payload.tenant_id or (user.get("tenant_id") or "")
        if not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required for CAAN_SMD assessments")
    else:
        tenant_id = user.get("tenant_id") or ""
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Tenant access required")
        if payload.tenant_id and payload.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="Cannot create assessments for another tenant")

    scores = score_assessment(payload.responses)
    now = datetime.now(timezone.utc)
    doc = {
        "tenant_id": tenant_id,
        "title": payload.title,
        "status": "draft",
        "department": payload.department,
        "scope": payload.scope,
        "auditor_name": payload.auditor_name,
        "assessor_email": payload.assessor_email,
        "assessment_date": payload.assessment_date,
        "template_version": payload.template_version or TEMPLATE_VERSION,
        "responses": [r.model_dump() for r in payload.responses],
        "component_scores": scores["component_scores"],
        "overall_score_pct": scores["overall_score_pct"],
        "overall_level": scores["overall_level"],
        "created_by": user.get("email"),
        "created_by_uid": user.get("uid"),
        "created_at": now,
        "updated_at": now,
        "notes": payload.notes,
    }

    try:
        result = _coll().add(doc)
        doc_id = result[1].id if isinstance(result, tuple) else result.id
        doc["id"] = doc_id
        _coll().document(doc_id).update({"id": doc_id})
    except Exception as e:
        logger.error(f"Failed to persist PSOE assessment: {e}")
        raise HTTPException(status_code=500, detail="Failed to persist assessment")

    log_audit(
        action="PSOE_ASSESSMENT_CREATED",
        user=user.get("email"),
        tenant_id=tenant_id,
        target_type="psoe_assessment",
        target_id=doc_id,
        metadata={"title": payload.title, "status": "draft", "overall_score_pct": scores["overall_score_pct"]},
    )

    return PSOEAssessment.model_validate(doc)


@router.get("/assessments/{assessment_id}", response_model=PSOEAssessment)
async def get_assessment(
    assessment_id: str,
    tenant_id: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Return a single PSOE assessment with its responses and scores."""
    effective = _effective_tenant(user, tenant_id)
    try:
        snap = _coll().document(assessment_id).get()
    except Exception as e:
        logger.error(f"Failed to read PSOE assessment {assessment_id}: {e}")
        raise HTTPException(status_code=500, detail="Assessment storage unavailable")
    if snap is None or not snap.exists:
        raise HTTPException(status_code=404, detail="Assessment not found")

    data = snap.to_dict() or {}
    if effective and data.get("tenant_id") != effective:
        raise HTTPException(status_code=403, detail="Cannot access another tenant's assessment")
    return _doc_to_assessment(snap)


@router.patch("/assessments/{assessment_id}", response_model=PSOEAssessment)
async def update_assessment(
    assessment_id: str,
    payload: PSOEAssessmentUpdate,
    tenant_id: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(get_safety_manager),
):
    """Update an existing PSOE assessment (TENANT_ADMIN / AIRLINE_ADMIN / CAAN_SMD)."""
    effective = _effective_tenant(user, tenant_id)
    try:
        snap = _coll().document(assessment_id).get()
    except Exception as e:
        logger.error(f"Failed to read PSOE assessment {assessment_id}: {e}")
        raise HTTPException(status_code=500, detail="Assessment storage unavailable")
    if snap is None or not snap.exists:
        raise HTTPException(status_code=404, detail="Assessment not found")

    data = snap.to_dict() or {}
    if effective and data.get("tenant_id") != effective:
        raise HTTPException(status_code=403, detail="Cannot access another tenant's assessment")

    updates: Dict[str, Any] = {}
    for field in ("title", "department", "scope", "auditor_name", "assessor_email",
                  "assessment_date", "status", "notes"):
        if payload.model_fields_set and field in payload.model_fields_set:
            updates[field] = getattr(payload, field)

    if payload.responses is not None:
        updates["responses"] = [r.model_dump() for r in payload.responses]
        scores = score_assessment(payload.responses)
        updates["component_scores"] = scores["component_scores"]
        updates["overall_score_pct"] = scores["overall_score_pct"]
        updates["overall_level"] = scores["overall_level"]

    updates["updated_at"] = datetime.now(timezone.utc)
    try:
        _coll().document(assessment_id).update(updates)
    except Exception as e:
        logger.error(f"Failed to update PSOE assessment {assessment_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update assessment")

    log_audit(
        action="PSOE_ASSESSMENT_UPDATED",
        user=user.get("email"),
        tenant_id=data.get("tenant_id", ""),
        target_type="psoe_assessment",
        target_id=assessment_id,
        metadata={"updated_fields": sorted(updates.keys())},
    )

    merged = dict(data)
    merged.update(updates)
    merged["id"] = assessment_id
    responses = merged.get("responses") or []
    merged["responses"] = [PSOEAnswer.model_validate(r) if isinstance(r, dict) else r for r in responses]
    return PSOEAssessment.model_validate(merged)


# ── Step 2C: Export PDF/HTML Report ─────────────────────────────────────────

_JINJA_ENV = Environment(
    loader=FileSystemLoader(searchpath=None),
    autoescape=select_autoescape(['html', 'xml']),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _render_report_template(assessment: PSOEAssessment, template: Any) -> str:
    """Render the PDF report HTML using a Jinja2 inline template."""
    # Build component score lookup
    comp_scores = assessment.component_scores or {}
    overall_pct = assessment.overall_score_pct or 0.0
    overall_level_val = assessment.overall_level or overall_level(overall_pct)

    # Non-compliant findings (scores 0 or 1)
    non_compliant = []
    responses = assessment.responses or []
    for resp in responses:
        if not resp.is_na and resp.score is not None and resp.score in (0, 1):
            # Find the question text from template
            q_text = ""
            q_id = resp.question_id
            non_compliant.append({
                "question_id": q_id,
                "score": resp.score,
                "observation": resp.comment or "",
                "evidence": resp.evidence or "",
            })

    # Component weighting mapping (mirrors CAAN Appendix 10)
    component_map = {
        "component_1": {"name": "Safety Policy & Objectives", "weight": 10},
        "component_2": {"name": "Safety Risk Management", "weight": 40},
        "component_3": {"name": "Safety Assurance", "weight": 30},
        "component_4": {"name": "Safety Promotion", "weight": 20},
    }

    template_dir = getattr(settings, 'report_template_dir', None)
    env = _JINJA_ENV
    if template_dir:
        env = Environment(
            loader=FileSystemLoader(searchpath=template_dir),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    template_str = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>PSOE Audit Report — {{ assessment.title }}</title>
    <style>
        body { font-family: 'Inter', system-ui, -apple-serif, sans-serif; margin: 0; padding: 0; background: #fff; color: #0b2a42; }
        .page { margin: 1rem; }
        .header { border-bottom: 2px solid #1a6b8a; padding-bottom: 1rem; margin-bottom: 1.5rem; }
        .h1 { color: #1a6b8a; font-size: 1.8rem; font-weight: 700; margin: 0; }
        .h2 { color: #1a6b8a; font-size: 1.2rem; font-weight: 700; margin-top: 0.5rem; }
        .summary-table { width: 100%; border-collapse: collapse; margin: 1rem 0; }
        .summary-table th, .summary-table td { border: 1px solid #e2e8f0; padding: 0.5rem 0.75rem; font-size: 0.85rem; }
        .summary-table th { background: #f8f9fa; font-weight: 600; width: 40%; }
        .summary-table td { text-align: center; }
        .score-badge { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 4px; font-weight: 700; font-size: 0.75rem; }
        .badge-excellent { background: #e8f5e9; color: #1e7e34; }
        .badge-good { background: #e3f2fd; color: #1565c0; }
        .badge-fair { background: #fff3e0; color: #f57c00; }
        .badge-poor { background: #ffebee; color: #c62828; }
        .finding-table { width: 100%; border-collapse: collapse; margin: 1rem 0; }
        .finding-table th, .finding-table td { border: 1px solid #e2e8f0; padding: 0.5rem; font-size: 0.8rem; }
        .finding-table th { background: #f8f9fa; font-weight: 600; width: 15%; white-space: nowrap; }
        .finding-table td { vertical-align: top; }
        .signoff { margin-top: 3rem; border-top: 1px solid #e2e8f0; padding-top: 1.5rem; }
        .print-only { display: none; }
        @media print {
            body { background: #fff; }
            .page { margin: 0.5rem; }
            .print-only { display: block; text-align: center; margin-bottom: 1rem; font-size: 1.1rem; font-weight: 700; }
            .no-print { display: none; }
        }
    </style>
</head>
<body>
<div class="page">
    <div class="header no-print">
        <h1>PSOE Audit & Surveillance Report</h1>
        <div style="font-size:0.8rem;color:#64748b;">CAAN SMS Procedure Manual — Appendix 10</div>
    </div>

    <div class="header">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
            <div>
                <div>Operator / Tenant: {{ assessment.tenant_name or assessment.tenant_id or '—' }}</div>
                <div style="font-size:0.85rem;color:#64748b;">Assessment Date: {{ assessment.assessment_date or '—' }}</div>
            </div>
            <div>
                <div>Lead Auditor: {{ assessment.auditor_name or '—' }}</div>
                <div style="font-size:0.85rem;color:#64748b;">State Ref: CAAN CAR-19 / SMS Manual</div>
            </div>
        </div>

        <div class="summary-table">
            <thead>
            <tr>
                <th>Component</th>
                <th>Score %</th>
                <th>Points</th>
                <th>Weight</th>
                <th>Maturity</th>
            </tr>
            </thead>
            <tbody>
            {{ component_rows|safe }}
            </tbody>
        </div>

        <div style="margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid #e2e8f0;">
            <div style="font-size:0.85rem;color:#64748b;">Overall Weighted Score: <strong>{{ "%.1f"|format(overall_pct) }}%</strong></div>
            <div style="font-size:0.85rem;color:#64748b; margin-top:0.3rem;">Final Maturity Stage: <span class="score-badge {{ level_class(overall_pct) }}">{{ overall_level_val }}</span></div>
        </div>
    </div>

    <div class="no-print" style="margin-top: 2rem;">
        <div class="print-only">PSOE Audit Report — CAAN Appendix 10 — {{ assessment.assessment_date or today() }}</div>
    </div>

    <div class="signoff" style="margin-top: 3rem; padding-top: 1.5rem; border-top: 1px solid #e2e8f0;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 1rem;">
            <div>
                <div>Lead Auditor Signature</div>
                <div style="font-size:0.7rem;color:#64748b;">________________________________________</div>
            </div>
            <div>
                <div>Accountable Executive Review</div>
                <div style="font-size:0.7rem;color:#64748b;">________________________________________</div>
            </div>
            <div>
                <div>Safety Manager Review</div>
                <div style="font-size:0.7rem;color:#64748b;">________________________________________</div>
            </div>
        </div>
        <div style="margin-top: 1rem; font-size:0.75rem; color:#64748b;">
            The above sign-offs confirm review of this PSOE audit report per CAAN CAR-19 requirements.
        </div>
    </div>
</div>
</body>
</html>"""

    from datetime import date
    from urllib.parse import quote

    comp_rows = []
    for comp_key in ["component_1", "component_2", "component_3", "component_4"]:
        if comp_key in comp_scores:
            cs = comp_scores[comp_key]
            comp_name = component_map.get(comp_key, {}).get("name", comp_key)
            score_pct = cs.get("score_pct", 0.0)
            weight = component_map.get(comp_key, {}).get("weight", 0)
            max_score = cs.get("max_score", 0)
            score_pts = cs.get("score", 0)
            # Determine maturity level
            if score_pct >= 90:
                level = "Fully Effective"
                cls = "badge-excellent"
            elif score_pct >= 70:
                level = "Suitable / Operating"
                cls = "badge-good"
            elif score_pct >= 40:
                level = "Present"
                cls = "badge-fair"
            else:
                level = "Non-Compliant / Deficient"
                cls = "badge-poor"
            comp_rows.append(
                f"<tr>"
                f"  <td>{comp_name}</td>"
                f"  <td><span class='score-badge {cls}'>{'%.1f'|format(score_pct)}%</span></td>"
                f"  <td>{score_pts}/{max_score}</td>"
                f"  <td>{weight}%</td>"
                f"  <td>{level}</td>"
                f"</tr>"
            )
    else:
        comp_rows = [
            "<tr><td colspan='5' style='text-align:center;padding:2rem;color:#64748b;'>No component scores available</td></tr>"
        ]

    html = template_str.replace("{{ component_rows|safe }}", "\n".join(comp_rows))
    html = html.replace("{{ overall_level_val }}", overall_level_val)
    html = html.replace("{{ assessment.assessment_date or '—' }}", assessment.assessment_date or "—")
    html = html.replace("{{ assessment.auditor_name or '—' }}", assessment.auditor_name or "—")
    html = html.replace("{{ assessment.tenant_name or assessment.tenant_id or '—' }}", assessment.tenant_id or "—")
    html = html.replace("{{ today() }}", str(date.today()))

    return html


def _pdf_from_html(html: str) -> bytes:
    """Convert HTML string to PDF bytes using reportlab's SimpleDocTemplate."""
    buffer = __import__('io').BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=LETTER, rightMargin=0.6*inch, leftMargin=0.6*inch, topMargin=0.6*inch, bottomMargin=0.6*inch)
    styles = getSampleStyleSheet()

    # Parse the HTML and build story (simplified: just generate a basic PDF)
    # For full fidelity we'd use weasyprint/playwright, but reportlab shapes work for core layout.
    story = []

    # Header
    header_style = ParagraphStyle('Header', parent=styles['Normal'], fontSize=16, textColor='#1a6b8a', spaceAfter=4)
    story.append(Paragraph("PSOE Audit & Surveillance Report", header_style))
    story.append(Paragraph("CAAN SMS Procedure Manual — Appendix 10", ParagraphStyle('Sub', parent=styles['Normal'], fontSize=9, textColor='#64748b', spaceAfter=12)))
    story.append(Spacer(1, 6))

    # Assessment metadata
    meta_style = ParagraphStyle('Meta', parent=styles['Normal'], fontSize=9, textColor='#0b2a42', spaceAfter=2)
    tenant_name = "—"
    assessment_date = "—"
    auditor_name = "—"
    # We'll embed these in the story via simple paragraphs
    story.append(Paragraph(f"Operator / Tenant: {tenant_name}", meta_style))
    story.append(Paragraph(f"Assessment Date: {assessment_date}", meta_style))
    story.append(Paragraph(f"Lead Auditor: {auditor_name}", meta_style))
    story.append(Spacer(1, 4))

    # Summary table as reportlab Table
    summary_data = [["Component", "Score %", "Points", "Weight", "Maturity"]]
    for comp_key in ["component_1", "component_2", "component_3", "component_4"]:
        if comp_key in comp_scores:
            cs = comp_scores[comp_key]
            score_pct = cs.get("score_pct", 0.0)
            score_pts = cs.get("score", 0)
            max_score = cs.get("max_score", 0)
            weight = cs.get("weight", 0)
            if score_pct >= 90:
                level = "Fully Effective"
                color = colors.green
            elif score_pct >= 70:
                level = "Suitable / Operating"
                color = colors.blue
            elif score_pct >= 40:
                level = "Present"
                color = colors.orange
            else:
                level = "Non-Compliant / Deficient"
                color = colors.red
            summary_data.append([comp_key.replace("component_", ""), f"{score_pct:.1f}%", f"{score_pts}/{max_score}", f"{weight}%", level])
        else:
            summary_data.append(["—", "—", "—", "—", "—"])

    summary_table = Table(summary_data, colWidths=[1.5*inch, 1*inch, 1*inch, 0.8*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a6b8a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Inter'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 8))

    # Non-compliant findings
    story.append(Paragraph("Non‑Compliant Findings (Scores 0‑1)", ParagraphStyle('Section', parent=styles['Normal'], fontSize=9, textColor='#1a6b8a', spaceAfter=4)))
    findings = assessment.responses or []
    nc = [r for r in findings if not r.is_na and r.score is not None and r.score in (0, 1)]
    if nc:
        fc_data = [["Question ID", "Score", "Observation", "Evidence", "CAN/CAP"]]
        for r in nc:
            fc_data.append([r.question_id, str(r.score), (r.comment or "")[:40], (r.evidence or "")[:40], "—"])
        fc_table = Table(fc_data, colWidths=[0.8*inch, 0.6*inch, 2*inch, 2*inch, 1*inch])
        fc_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc3545')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, -1), 'Inter'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(fc_table)
    else:
        story.append(Paragraph("No non‑compliant findings.", ParagraphStyle('None', parent=styles['Normal'], fontSize=8, textColor='#64748b')))

    story.append(Spacer(1, 8))

    # Sign-off section
    story.append(Paragraph("Sign‑Off", ParagraphStyle('Section', parent=styles['Normal'], fontSize=9, textColor='#1a6b8a', spaceAfter=4)))
    story.append(Paragraph("Lead Auditor Signature: ________________________________________", ParagraphStyle('Sig', parent=styles['Normal'], fontSize=8, spaceAfter=2)))
    story.append(Paragraph("Accountable Executive Review: ________________________________________", ParagraphStyle('Sig', parent=styles['Normal'], fontSize=8, spaceAfter=2)))
    story.append(Paragraph("Safety Manager Review: ________________________________________", ParagraphStyle('Sig', parent=styles['Normal'], fontSize=8, spaceAfter=2)))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


@router.get("/assessments/{assessment_id}/export", include_in_schema=False)
async def export_assessment_report(
    assessment_id: str,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
    tenant_id: Optional[str] = Query(None),
):
    """Export a PDF audit report for a PSOE assessment.

    Returns a PDF document formatted to CAAN SMS Audit Checklist / Appendix 10 specifications.
    The endpoint supports both browser preview (HTML) and direct PDF download.
    Query param ?format=pdf forces PDF download; HTML preview by default.
    """
    effective = _effective_tenant(user, tenant_id)
    try:
        snap = _coll().document(assessment_id).get()
    except Exception as e:
        logger.error(f"Failed to read PSOE assessment {assessment_id}: {e}")
        raise HTTPException(status_code=500, detail="Assessment storage unavailable")
    if snap is None or not snap.exists:
        raise HTTPException(status_code=404, detail="Assessment not found")

    data = snap.to_dict() or {}
    if effective and data.get("tenant_id") != effective:
        raise HTTPException(status_code=403, detail="Cannot access another tenant's assessment")

    assessment = _doc_to_assessment(snap)
    template = await load_template()

    # Determine format from Accept header or query param
    accept = request.headers.get("accept", "")
    if "text/html" in accept or "text/html" in (request.query_params.get("format") or "") or "export" not in accept.lower():
        # Render HTML report
        html = _render_report_template(assessment, template)
        return Response(content=html, media_type="text/html", headers={"Content-Disposition": f'inline; filename="psoe_audit_report_{assessment_id}.html"'})
    else:
        # Generate PDF
        html = _render_report_template(assessment, template)
        pdf_bytes = _pdf_from_html(html)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=\"psoe_audit_report_{assessment_id}.pdf\""},
        )

    log_audit(
        action="PSOE_REPORT_EXPORTED",
        user=user.get("email"),
        tenant_id=data.get("tenant_id", ""),
        target_type="psoe_assessment",
        target_id=assessment_id,
        metadata={"format": "pdf", "assessment_title": assessment.title},
    )