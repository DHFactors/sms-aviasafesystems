from __future__ import annotations

import io
from typing import Any, Dict, Optional

from loguru import logger

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import inch, mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, KeepTogether,
    )
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

TENANT_FOOTER = (
    "CONFIDENTIAL - Internal Airline SMS Data - "
    "Protected under ICAO Annex 19 Attachment B"
)

_SEV_COLORS = {
    "1": colors.HexColor("#22c55e"),
    "2": colors.HexColor("#22c55e"),
    "3": colors.HexColor("#f59e0b"),
    "4": colors.HexColor("#f59e0b"),
    "5": colors.HexColor("#dc2626"),
}


class TenantSrbPdfCanvas:
    """Custom canvas for tenant SRB reports with CONFIDENTIAL footer.

    Uses the standard page-state replay pattern: each page's canvas state is
    captured during showPage(), then all pages are replayed at save() time
    with the CONFIDENTIAL footer annotation."""

    def __init__(self, *args, **kwargs):
        self._footer = kwargs.pop("footer_text", TENANT_FOOTER)
        self._saved_page_states: list = []
        from reportlab.pdfgen.canvas import Canvas
        self._canvas = Canvas(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._canvas, name)

    def showPage(self):
        self._saved_page_states.append(dict(self._canvas.__dict__))
        self._canvas._startPage()

    def save(self):
        w, h = A4
        num_pages = len(self._saved_page_states)
        for i, state in enumerate(self._saved_page_states, start=1):
            self._canvas.__dict__.update(state)
            self._canvas.saveState()
            self._canvas.setFont("Helvetica", 8)
            self._canvas.setFillColorRGB(0.45, 0.45, 0.45)
            self._canvas.drawCentredString(w / 2, 20 * mm, f"Page {i} of {num_pages}")
            self._canvas.setFont("Helvetica-Oblique", 6.5)
            self._canvas.setFillColorRGB(0.55, 0.55, 0.55)
            text_obj = self._canvas.beginText(50, 32 * mm)
            text_obj.textLine(self._footer)
            self._canvas.drawText(text_obj)
            self._canvas.restoreState()
            self._canvas.showPage()
        self._canvas.save()


class TenantPdfGenerator:
    """Generate monthly SRB safety committee PDF for a tenant operator."""

    @staticmethod
    def build_srb_report_pdf(report: dict) -> bytes:
        if not HAS_REPORTLAB:
            logger.warning("reportlab not installed — returning placeholder bytes")
            return TenantPdfGenerator._placeholder(report)

        from app.services.pdf_canvas import NumberedCanvas

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=50, rightMargin=50,
            topMargin=60, bottomMargin=60,
        )
        styles = getSampleStyleSheet()
        story: list = []

        title_style = ParagraphStyle(
            "SrbTitle", parent=styles["Title"],
            fontSize=20, spaceAfter=4, textColor=colors.HexColor("#002f6c"),
        )
        subtitle_style = ParagraphStyle(
            "SrbSubtitle", parent=styles["Normal"],
            fontSize=10, textColor=colors.HexColor("#64748b"), spaceAfter=14,
        )
        heading_style = ParagraphStyle(
            "SrbH2", parent=styles["Heading2"],
            fontSize=13, textColor=colors.HexColor("#002f6c"),
            spaceBefore=14, spaceAfter=6,
        )
        normal = styles["Normal"]
        small = ParagraphStyle(
            "SrbSmall", parent=normal, fontSize=8, textColor=colors.HexColor("#94a3b8"),
        )

        # ── Header banner with operator branding ──
        operator = report.get("operator_name", "Operator")
        aoc = report.get("aoc_number", "")
        tier_badge = report.get("active_tier", "")
        story.append(Paragraph(f"{operator} — Monthly Safety Review Board Report", title_style))
        story.append(Paragraph(
            f"AOC: {aoc} &nbsp;|&nbsp; SMS Tier: {tier_badge} &nbsp;|&nbsp; "
            f"ICAO Annex 19 / Doc 9859 Compliant",
            subtitle_style,
        ))

        year = report.get("reporting_year", "")
        month = report.get("reporting_month", "")
        story.append(Paragraph(
            f"<b>Reporting Period:</b> {year}-{month:02d} &nbsp;|&nbsp; "
            f"<b>Generated:</b> {report.get('generated_at', '')}",
            normal,
        ))
        story.append(Spacer(1, 0.25 * inch))

        # ══════════════════════════════════════════════════════════════════
        # PAGE 1 — Executive Safety Briefing
        # ══════════════════════════════════════════════════════════════════
        story.append(Paragraph("1. Executive Safety Briefing", heading_style))

        kpi_data = [
            ("Flight Hours Logged", f"{report.get('flight_hours_logged', 0):.1f}"),
            ("Total Flights", str(report.get("total_flights", 0))),
            ("Safety Reports Submitted", str(report.get("safety_reports_submitted", 0))),
            ("Safety Culture Index", str(report.get("safety_culture_index", "N/A"))),
            ("Total Active Hazards", str(report.get("total_hazards", 0))),
            ("Open Hazards", str(report.get("open_hazards", 0))),
            ("Intolerable Risks", str(report.get("intolerable_risks", 0))),
        ]
        kpi_table = Table(
            [[Paragraph(f"<b>{l}</b>", normal), Paragraph(v, normal)] for l, v in kpi_data],
            colWidths=[3.2 * inch, 2 * inch],
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

        # ── 5x5 Risk Heatmap Distribution Table ──
        heatmap = report.get("risk_heatmap", [])
        if heatmap:
            story.append(Paragraph("5x5 Risk Heatmap Distribution", heading_style))
            header_row = [
                Paragraph("<b>Severity \\ Likelihood</b>", normal),
                Paragraph("<b>E (Ext. Improbable)</b>", normal),
                Paragraph("<b>D (Improbable)</b>", normal),
                Paragraph("<b>C (Remote)</b>", normal),
                Paragraph("<b>B (Occasional)</b>", normal),
                Paragraph("<b>A (Frequent)</b>", normal),
            ]
            matrix_rows = {cell.get("severity", ""): {} for cell in heatmap}
            for cell in heatmap:
                sev = cell.get("severity", "")
                like = cell.get("likelihood", "")
                matrix_rows.setdefault(sev, {})[like] = cell.get("hazard_count", 0)

            sev_order = ["5_CATASTROPHIC", "4_HAZARDOUS", "3_MAJOR", "2_MINOR", "1_NEGLIGIBLE"]
            like_order = ["E_EXTREMELY_IMPROBABLE", "D_IMPROBABLE", "C_REMOTE", "B_OCCASIONAL", "A_FREQUENT"]
            table_data = [header_row]
            for sev in sev_order:
                row = [Paragraph(f"<b>{sev.split('_')[1]}</b>", normal)]
                for like in like_order:
                    count = matrix_rows.get(sev, {}).get(like, 0)
                    row.append(Paragraph(str(count) if count else "-", normal))
                table_data.append(row)

            heatmap_table = Table(table_data, colWidths=[1.4 * inch] + [0.9 * inch] * 5)
            heatmap_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002f6c")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]))
            story.append(heatmap_table)
            story.append(Spacer(1, 0.2 * inch))

        # ── SPI Trajectory Summary ──
        spi_metrics = report.get("spi_metrics", [])
        if spi_metrics:
            story.append(Paragraph("SPI Trajectory Summary", heading_style))
            spi_header = [
                Paragraph("<b>SPI Name</b>", normal),
                Paragraph("<b>Current</b>", normal),
                Paragraph("<b>Target</b>", normal),
                Paragraph("<b>Status</b>", normal),
                Paragraph("<b>Trend</b>", normal),
            ]
            spi_rows = [spi_header]
            for spi in spi_metrics:
                on_target = spi.get("is_on_target")
                status_text = "On Target" if on_target else "Off Target" if on_target is not None else "N/A"
                spi_rows.append([
                    Paragraph(spi.get("name", ""), normal),
                    Paragraph(str(spi.get("current_value", "N/A")), normal),
                    Paragraph(str(spi.get("target_value", "N/A")), normal),
                    Paragraph(status_text, normal),
                    Paragraph(spi.get("trend", "stable"), normal),
                ])
            spi_table = Table(spi_rows, colWidths=[1.8 * inch, 0.9 * inch, 0.9 * inch, 0.9 * inch, 0.9 * inch])
            spi_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002f6c")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]))
            story.append(spi_table)
            story.append(Spacer(1, 0.2 * inch))

        # ══════════════════════════════════════════════════════════════════
        # PAGE 2 — CAPA & Safety Action Register
        # ══════════════════════════════════════════════════════════════════
        story.append(PageBreak())
        story.append(Paragraph("2. CAPA & Safety Action Register", heading_style))

        capas = report.get("open_capas", [])
        if capas:
            capa_header = [
                Paragraph("<b>Ref</b>", normal),
                Paragraph("<b>Description</b>", normal),
                Paragraph("<b>Responsible</b>", normal),
                Paragraph("<b>Target Date</b>", normal),
                Paragraph("<b>Status</b>", normal),
                Paragraph("<b>Priority</b>", normal),
            ]
            capa_rows = [capa_header]
            for capa in capas:
                target = capa.get("target_close_out_date", "")
                capa_rows.append([
                    Paragraph(str(capa.get("source_reference", "")), normal),
                    Paragraph(str(capa.get("description", ""))[:80], normal),
                    Paragraph(str(capa.get("responsible_post_holder", "")), normal),
                    Paragraph(str(target), normal),
                    Paragraph(str(capa.get("implementation_status", "OPEN")), normal),
                    Paragraph(str(capa.get("priority", "MEDIUM")), normal),
                ])
            capa_table = Table(
                capa_rows,
                colWidths=[0.7 * inch, 2.0 * inch, 1.0 * inch, 0.85 * inch, 0.85 * inch, 0.7 * inch],
            )
            capa_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002f6c")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
            ]))
            story.append(capa_table)
        else:
            story.append(Paragraph("No open CAPA items for this reporting period.", normal))
        story.append(Spacer(1, 0.3 * inch))

        # ── Insights & Recommendations ──
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

        # ══════════════════════════════════════════════════════════════════
        # Accountable Manager Endorsement Block
        # ══════════════════════════════════════════════════════════════════
        story.append(Spacer(1, 0.5 * inch))
        sig_label = ParagraphStyle(
            "SigLabel", parent=normal, fontSize=9, textColor=colors.HexColor("#475569"),
        )
        story.append(KeepTogether([
            Paragraph(
                "<b>Accountable Manager Endorsement</b> — ICAO SMS Element 1.2 "
                "(Safety Policy & Objectives — Internal Safety Resource Allocation)",
                heading_style,
            ),
            Spacer(1, 0.15 * inch),
            Paragraph(
                "I confirm that the safety resources described herein are allocated and that "
                "the organisation's Safety Management System operates in accordance with ICAO "
                "Annex 19 and the national regulations of the Civil Aviation Authority of Nepal.",
                normal,
            ),
            Spacer(1, 0.3 * inch),
            Paragraph("Safety Manager:", sig_label),
            Spacer(1, 0.2 * inch),
            Paragraph("_" * 50, normal),
            Spacer(1, 0.05 * inch),
            Paragraph("Name: ___________________________ &nbsp;&nbsp; Date: ___________________________", sig_label),
            Spacer(1, 0.25 * inch),
            Paragraph("Accountable Manager:", sig_label),
            Spacer(1, 0.2 * inch),
            Paragraph("_" * 50, normal),
            Spacer(1, 0.05 * inch),
            Paragraph("Name: ___________________________ &nbsp;&nbsp; Date: ___________________________", sig_label),
        ]))

        from app.services.pdf_canvas import NumberedCanvas
        doc.build(story, canvasmaker=NumberedCanvas)
        buffer.seek(0)
        return buffer.getvalue()

    @staticmethod
    def _placeholder(report: dict) -> bytes:
        lines = [
            f"Tenant SRB Report — {report.get('operator_name', 'Operator')}",
            f"Period: {report.get('reporting_year', '')}-{report.get('reporting_month', ''):02d}",
            f"Flight Hours: {report.get('flight_hours_logged', 0)}",
            f"Total Hazards: {report.get('total_hazards', 0)}",
            f"Open CAPAs: {len(report.get('open_capas', []))}",
        ]
        return "\n".join(lines).encode("utf-8")
