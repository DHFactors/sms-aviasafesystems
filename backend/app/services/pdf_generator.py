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


class CaanPdfGenerator:
    """Build the CAAN SSP oversight PDF from a StateAggregateReport dict using
    ReportLab flowables with NumberedCanvas page numbering and CAR-19 disclaimers."""

    @staticmethod
    def build_ssp_report_pdf(report: dict) -> bytes:
        if not HAS_REPORTLAB:
            return _placeholder_pdf(report, "CAAN SSP Oversight", "")

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=50, rightMargin=50,
            topMargin=60, bottomMargin=60,
        )
        styles = getSampleStyleSheet()
        story: list = []

        title_style = ParagraphStyle(
            "CaanTitle", parent=styles["Title"],
            fontSize=20, spaceAfter=4, textColor=colors.HexColor("#002f6c"),
        )
        subtitle_style = ParagraphStyle(
            "CaanSubtitle", parent=styles["Normal"],
            fontSize=10, textColor=colors.HexColor("#64748b"), spaceAfter=14,
        )
        heading_style = ParagraphStyle(
            "CaanH2", parent=styles["Heading2"],
            fontSize=13, textColor=colors.HexColor("#002f6c"),
            spaceBefore=14, spaceAfter=6,
        )
        normal = styles["Normal"]
        small = ParagraphStyle(
            "CaanSmall", parent=normal, fontSize=8,
            textColor=colors.HexColor("#94a3b8"),
        )

        # ── Header banner ──
        story.append(Paragraph("CAAN State Safety Programme Oversight Report", title_style))
        story.append(Paragraph(
            "Civil Aviation Authority of Nepal — ICAO Annex 19 / CAR-19 Compliance",
            subtitle_style,
        ))

        year = report.get("reporting_year", "")
        quarter = report.get("reporting_quarter")
        period = f"{year}" + (f" Q{quarter}" if quarter else "")
        generated = report.get("generated_at", "")
        story.append(Paragraph(
            f"<b>Reporting Period:</b> {period} &nbsp;|&nbsp; "
            f"<b>Generated:</b> {generated}",
            normal,
        ))
        story.append(Spacer(1, 0.25 * inch))

        # ── Executive KPI grid ──
        story.append(Paragraph("Executive Summary", heading_style))
        kpi_data = [
            ("Total Operators", str(report.get("total_operators", 0))),
            ("Total Hazards", str(report.get("total_hazards", 0))),
            ("Total Reports", str(report.get("total_reports", 0))),
            ("Total CANs/CAPs", str(report.get("total_cans", 0))),
            ("Open CANs/CAPs", str(report.get("open_cans", 0))),
            ("Overdue CANs/CAPs", str(report.get("overdue_cans", 0))),
            ("Industry Risk Index", str(report.get("industry_risk_index", "N/A"))),
        ]
        kpi_table = Table(
            [[Paragraph(f"<b>{l}</b>", normal), Paragraph(v, normal)] for l, v in kpi_data],
            colWidths=[3 * inch, 2 * inch],
        )
        kpi_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(kpi_table)
        story.append(Spacer(1, 0.2 * inch))

        # ── HRC distribution table ──
        hrc = report.get("hrc_distribution", [])
        if hrc:
            story.append(Paragraph("High Risk Category Distribution", heading_style))
            hrc_header = [
                Paragraph("<b>Category</b>", normal),
                Paragraph("<b>Count</b>", normal),
                Paragraph("<b>High Risk</b>", normal),
                Paragraph("<b>Level II</b>", normal),
                Paragraph("<b>Level III</b>", normal),
                Paragraph("<b>Level IV</b>", normal),
                Paragraph("<b>% of Total</b>", normal),
            ]
            hrc_rows = [hrc_header]
            for item in hrc:
                if isinstance(item, dict):
                    hrc_rows.append([
                        Paragraph(str(item.get("category", "")), normal),
                        Paragraph(str(item.get("count", 0)), normal),
                        Paragraph(str(item.get("high_risk_count", 0)), normal),
                        Paragraph(str(item.get("level_ii_count", 0)), normal),
                        Paragraph(str(item.get("level_iii_count", 0)), normal),
                        Paragraph(str(item.get("level_iv_count", 0)), normal),
                        Paragraph(f"{item.get('percentage_of_total', 0):.1f}%", normal),
                    ])
            col_w = [1.2 * inch, 0.7 * inch, 0.8 * inch, 0.7 * inch, 0.8 * inch, 0.8 * inch, 0.9 * inch]
            hrc_table = Table(hrc_rows, colWidths=col_w)
            hrc_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002f6c")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]))
            story.append(hrc_table)
            story.append(Spacer(1, 0.2 * inch))

        # ── Operator surveillance table (paginated via KeepTogether chunks) ──
        operators = report.get("operator_summaries", [])
        if operators:
            story.append(Paragraph("Operator Surveillance Summary", heading_style))
            op_header = [
                Paragraph("<b>Operator</b>", normal),
                Paragraph("<b>Hazards</b>", normal),
                Paragraph("<b>Reports</b>", normal),
                Paragraph("<b>CANs</b>", normal),
                Paragraph("<b>Overdue</b>", normal),
                Paragraph("<b>Risk Index</b>", normal),
                Paragraph("<b>Compliance</b>", normal),
            ]
            op_rows = [op_header]
            for op in operators:
                if isinstance(op, dict):
                    op_rows.append([
                        Paragraph(str(op.get("operator_name", op.get("tenant_id", ""))), normal),
                        Paragraph(str(op.get("total_hazards", 0)), normal),
                        Paragraph(str(op.get("total_reports", 0)), normal),
                        Paragraph(str(op.get("total_cans", 0)), normal),
                        Paragraph(str(op.get("overdue_cans", 0)), normal),
                        Paragraph(str(op.get("risk_index", "N/A")), normal),
                        Paragraph(
                            f"{op.get('compliance_score', 0):.0f}%" if op.get("compliance_score") else "N/A",
                            normal,
                        ),
                    ])
            op_col_w = [1.6 * inch, 0.7 * inch, 0.7 * inch, 0.6 * inch, 0.7 * inch, 0.8 * inch, 0.8 * inch]
            # Paginate in chunks of 20 rows per KeepTogether
            chunk_size = 20
            for i in range(1, len(op_rows), chunk_size):
                chunk = op_rows[i : i + chunk_size]
                if i == 1:
                    chunk = [op_header] + chunk
                op_table = Table(chunk, colWidths=op_col_w)
                op_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002f6c")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                ]))
                from reportlab.platypus import KeepTogether
                story.append(KeepTogether([op_table, Spacer(1, 0.15 * inch)]))

        # ── Insights & recommendations ──
        insights = report.get("insights", [])
        if insights:
            story.append(Paragraph("Insights", heading_style))
            for ins in insights:
                story.append(Paragraph(f"\u2022 {ins}", normal))
                story.append(Spacer(1, 0.04 * inch))

        recommendations = report.get("recommendations", [])
        if recommendations:
            story.append(Paragraph("Recommendations", heading_style))
            for rec in recommendations:
                story.append(Paragraph(f"\u2022 {rec}", normal))
                story.append(Spacer(1, 0.04 * inch))

        # ── Inspector digital signature placeholder ──
        story.append(Spacer(1, 0.5 * inch))
        sig_label = ParagraphStyle(
            "SigLabel", parent=normal, fontSize=9, textColor=colors.HexColor("#475569"),
        )
        sig_line = "_" * 50
        from reportlab.platypus import KeepTogether
        story.append(KeepTogether([
            Paragraph("<b>Digital Signature — CAAN Inspector:</b>", sig_label),
            Spacer(1, 0.3 * inch),
            Paragraph(sig_line, normal),
            Spacer(1, 0.05 * inch),
            Paragraph("Name: ___________________________ &nbsp;&nbsp; Designation: ___________________________", sig_label),
            Spacer(1, 0.05 * inch),
            Paragraph("Date: ___________________________", sig_label),
        ]))

        from app.services.pdf_canvas import NumberedCanvas
        doc.build(story, canvasmaker=NumberedCanvas)
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
