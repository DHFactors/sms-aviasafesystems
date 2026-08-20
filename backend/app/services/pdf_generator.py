import io
from typing import Optional
from loguru import logger

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import inch, mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, ListFlowable, ListItem
    )
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

REPORT_TITLE = "AviaSAFE SMS Platform"
SUBTITLE = "Safety Management System — ICAO Annex 19 Compliant"


def generate_report_pdf(report_data: dict, report_type: str,
                        period: str, tenant_name: Optional[str] = None) -> bytes:
    if not HAS_REPORTLAB:
        logger.warning("reportlab not installed — returning placeholder PDF bytes")
        return _placeholder_pdf(report_data, report_type, period, tenant_name)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=50, rightMargin=50,
        topMargin=50, bottomMargin=50,
    )
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle(
        "ReportTitle", parent=styles["Title"],
        fontSize=22, spaceAfter=6, textColor=colors.HexColor("#002f6c"),
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle", parent=styles["Normal"],
        fontSize=11, textColor=colors.HexColor("#64748b"), spaceAfter=20,
    )
    heading_style = ParagraphStyle(
        "ReportH2", parent=styles["Heading2"],
        fontSize=14, textColor=colors.HexColor("#002f6c"), spaceBefore=16, spaceAfter=8,
    )
    normal = styles["Normal"]

    entity = tenant_name or "Industry-wide (CAAN)"

    story.append(Paragraph(REPORT_TITLE, title_style))
    story.append(Paragraph(SUBTITLE, subtitle_style))
    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph(
        f"<b>Report Type:</b> {report_type.upper()} Report &nbsp;|&nbsp; "
        f"<b>Period:</b> {period} &nbsp;|&nbsp; "
        f"<b>Entity:</b> {entity}",
        normal
    ))
    story.append(Spacer(1, 0.3 * inch))

    summary = report_data.get("summary", {})

    # ===== Executive Summary =====
    story.append(Paragraph("Executive Summary", heading_style))
    summary_lines = [
        ("Total Hazards", str(summary.get("total_hazards", 0))),
        ("New Hazards (Period)", str(summary.get("new_hazards", summary.get("hazards_opened", 0)))),
        ("Closed Hazards", str(summary.get("closed_hazards", summary.get("hazards_closed", 0)))),
        ("Closure Rate", f"{summary.get('closure_rate', 0)}%"),
    ]
    if "can_cap_total" in summary:
        summary_lines.append(("CAN/CAP Total", str(summary["can_cap_total"])))
    if "avg_closure_days" in summary:
        summary_lines.append(("Avg Closure Days", str(summary["avg_closure_days"])))

    summary_table = Table(
        [[Paragraph(f"<b>{l[0]}</b>", normal), Paragraph(l[1], normal)] for l in summary_lines],
        colWidths=[3 * inch, 1.5 * inch],
    )
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.2 * inch))

    data = report_data.get("data", {})

    # ===== Risk Distribution =====
    risk_dist = data.get("risk_distribution", {})
    if risk_dist:
        story.append(Paragraph("Risk Distribution", heading_style))
        risk_rows = [[Paragraph("<b>Level</b>", normal), Paragraph("<b>Count</b>", normal)]]
        for level in ["Low", "High", "Very High"]:
            risk_rows.append([
                Paragraph(level, normal),
                Paragraph(str(risk_dist.get(level, 0)), normal),
            ])
        risk_table = Table(risk_rows, colWidths=[3 * inch, 1.5 * inch])
        risk_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002f6c")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(risk_table)
        story.append(Spacer(1, 0.2 * inch))

    # ===== Top Risks =====
    top_risks = data.get("top_risks", [])
    if top_risks:
        story.append(Paragraph("Top Risks", heading_style))
        top_rows = [[Paragraph("<b>Category</b>", normal), Paragraph("<b>Count</b>", normal)]]
        for r in top_risks[:10]:
            top_rows.append([
                Paragraph(r.get("category", "N/A"), normal),
                Paragraph(str(r.get("count", 0)), normal),
            ])
        top_table = Table(top_rows, colWidths=[3 * inch, 1.5 * inch])
        top_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002f6c")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(top_table)
        story.append(Spacer(1, 0.2 * inch))

    # ===== CAN/CAP Status =====
    can_cap = data.get("can_cap_status") or data.get("can_cap_summary", {})
    if can_cap:
        story.append(Paragraph("Corrective Action Status", heading_style))
        if "total" in can_cap:
            cc_lines = [
                ("Total CANs", str(can_cap.get("total", 0))),
                ("Closed", str(can_cap.get("closed", 0))),
                ("Open", str(can_cap.get("open", 0))),
                ("Compliance Rate", f"{can_cap.get('compliance_rate', 0)}%"),
            ]
        else:
            cc_lines = [
                ("Open CANs", str(can_cap.get("Open", 0))),
                ("Under Review", str(can_cap.get("Under Review", 0))),
                ("Closed", str(can_cap.get("Closed", 0))),
            ]
        cc_table = Table(
            [[Paragraph(f"<b>{l[0]}</b>", normal), Paragraph(l[1], normal)] for l in cc_lines],
            colWidths=[3 * inch, 1.5 * inch],
        )
        cc_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(cc_table)
        story.append(Spacer(1, 0.2 * inch))

    # ===== SSP Indicators (Annual) =====
    ssp = data.get("ssp_indicators", {})
    if ssp:
        story.append(Paragraph("SSP Performance Indicators", heading_style))
        ssp_lines = [
            ("Hazard Identification Rate", f"{ssp.get('hazard_identification_rate', 0)}%"),
            ("Hazard Closure Rate", f"{ssp.get('closure_rate', 0)}%"),
            ("CAN/CAP Compliance Rate", f"{ssp.get('can_cap_compliance_rate', 0)}%"),
        ]
        ssp_table = Table(
            [[Paragraph(f"<b>{l[0]}</b>", normal), Paragraph(l[1], normal)] for l in ssp_lines],
            colWidths=[3 * inch, 1.5 * inch],
        )
        ssp_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(ssp_table)
        story.append(Spacer(1, 0.2 * inch))

    # ===== Insights & Recommendations =====
    insights = data.get("insights", [])
    if insights:
        story.append(Paragraph("Insights", heading_style))
        for ins in insights:
            story.append(Paragraph(f"• {ins}", normal))
            story.append(Spacer(1, 0.05 * inch))

    strategic = data.get("strategic_recommendations", [])
    if strategic:
        story.append(Paragraph("Strategic Recommendations", heading_style))
        for rec in strategic:
            story.append(Paragraph(f"• {rec}", normal))
            story.append(Spacer(1, 0.05 * inch))

    operational = data.get("operational_recommendations", [])
    if operational:
        story.append(Paragraph("Operational Recommendations", heading_style))
        for rec in operational:
            story.append(Paragraph(f"• {rec}", normal))
            story.append(Spacer(1, 0.05 * inch))

    # ===== Footer =====
    story.append(Spacer(1, 0.5 * inch))
    footer_style = ParagraphStyle(
        "Footer", parent=normal, fontSize=8, textColor=colors.HexColor("#94a3b8"),
        alignment=1,
    )
    story.append(Paragraph(
        f"Generated by AviaSAFE SMS Platform | {period} | {entity}",
        footer_style,
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def _placeholder_pdf(report_data: dict, report_type: str,
                     period: str, tenant_name: Optional[str] = None) -> bytes:
    lines = [
        f"AviaSAFE SMS Platform — {report_type.upper()} Report",
        f"Period: {period}",
        f"Entity: {tenant_name or 'Industry-wide (CAAN)'}",
        "",
    ]
    summary = report_data.get("summary", {})
    for k, v in summary.items():
        lines.append(f"{k}: {v}")
    lines.append("")
    lines.append("--- Data ---")
    data = report_data.get("data", {})
    for k, v in data.items():
        if isinstance(v, (str, int, float, bool)):
            lines.append(f"{k}: {v}")
    content = "\n".join(lines)
    return content.encode("utf-8")
