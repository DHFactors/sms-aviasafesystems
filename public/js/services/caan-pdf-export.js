/* ============================================================================
   FILE: caan-pdf-export.js
   PATH: public/js/services/caan-pdf-export.js
   VERSION: 1.0.0
   PURPOSE: Client-side multi-page PDF fallback export using jsPDF + jspdf-autotable
            for the CAAN SSP oversight workspace.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

const CaanPdfExport = (function () {
  'use strict';

  function _ensureLibraries() {
    if (typeof window.jspdf === 'undefined') {
      console.warn('[CaanPdfExport] jsPDF not loaded. Include jsPDF via CDN.');
      return false;
    }
    return true;
  }

  function _buildReportDoc(report) {
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });
    const pageWidth = doc.internal.pageSize.getWidth();
    const margin = 15;

    doc.setFont('helvetica', 'bold');
    doc.setFontSize(16);
    doc.setTextColor(0, 47, 108);
    doc.text('CAAN State Safety Programme Oversight Report', margin, 20);

    doc.setFont('helvetica', 'normal');
    doc.setFontSize(9);
    doc.setTextColor(100, 116, 139);
    const period = report.reporting_quarter
      ? `${report.reporting_year} Q${report.reporting_quarter}`
      : `${report.reporting_year}`;
    doc.text(`Reporting Period: ${period}  |  Generated: ${report.generated_at || new Date().toISOString()}`, margin, 28);

    let y = 38;

    const kpis = [
      ['Total Operators', String(report.total_operators || 0)],
      ['Total Hazards', String(report.total_hazards || 0)],
      ['Total Reports', String(report.total_reports || 0)],
      ['Total CANs/CAPs', String(report.total_cans || 0)],
      ['Open CANs/CAPs', String(report.open_cans || 0)],
      ['Overdue CANs/CAPs', String(report.overdue_cans || 0)],
      ['Industry Risk Index', String(report.industry_risk_index || 'N/A')],
    ];

    doc.setFontSize(11);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(0, 47, 108);
    doc.text('Executive Summary', margin, y);
    y += 6;

    doc.autoTable({
      startY: y,
      head: [['Metric', 'Value']],
      body: kpis,
      theme: 'grid',
      headStyles: { fillColor: [0, 47, 108], fontSize: 8 },
      bodyStyles: { fontSize: 8 },
      margin: { left: margin, right: margin },
      styles: { cellPadding: 2 },
    });

    y = doc.lastAutoTable.finalY + 10;

    const hrcDist = report.hrc_distribution || [];
    if (hrcDist.length > 0) {
      if (y > 170) { doc.addPage(); y = 20; }
      doc.setFontSize(11);
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(0, 47, 108);
      doc.text('High Risk Category Distribution', margin, y);
      y += 6;

      doc.autoTable({
        startY: y,
        head: [['Category', 'Count', 'High Risk', 'Level II', 'Level III', 'Level IV']],
        body: hrcDist.map(h => [
          h.category || h.icoc_category || '',
          String(h.count || 0),
          String(h.high_risk_count || 0),
          String(h.level_ii_count || 0),
          String(h.level_iii_count || 0),
          String(h.level_iv_count || 0),
        ]),
        theme: 'grid',
        headStyles: { fillColor: [0, 47, 108], fontSize: 8 },
        bodyStyles: { fontSize: 7 },
        margin: { left: margin, right: margin },
        styles: { cellPadding: 2 },
      });
      y = doc.lastAutoTable.finalY + 10;
    }

    const operators = report.operator_summaries || [];
    if (operators.length > 0) {
      if (y > 150) { doc.addPage(); y = 20; }
      doc.setFontSize(11);
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(0, 47, 108);
      doc.text('Operator Surveillance Summary', margin, y);
      y += 6;

      doc.autoTable({
        startY: y,
        head: [['Operator', 'Hazards', 'Reports', 'CANs', 'Overdue', 'Risk Index', 'Compliance']],
        body: operators.map(op => [
          op.operator_name || op.tenant_id || '',
          String(op.total_hazards || 0),
          String(op.total_reports || 0),
          String(op.total_cans || 0),
          String(op.overdue_cans || 0),
          String(op.risk_index ?? 'N/A'),
          op.compliance_score != null ? `${op.compliance_score}%` : 'N/A',
        ]),
        theme: 'grid',
        headStyles: { fillColor: [0, 47, 108], fontSize: 8 },
        bodyStyles: { fontSize: 7 },
        margin: { left: margin, right: margin },
        styles: { cellPadding: 2 },
        didDrawPage: function (data) {
          const pageCount = doc.internal.getNumberOfPages();
          doc.setFontSize(7);
          doc.setTextColor(150);
          doc.text(
            `Page ${doc.internal.getCurrentPageInfo().pageNumber} of ${pageCount}`,
            pageWidth / 2, doc.internal.pageSize.getHeight() - 8,
            { align: 'center' }
          );
        },
      });
    }

    const totalPages = doc.internal.getNumberOfPages();
    for (let i = 1; i <= totalPages; i++) {
      doc.setPage(i);
      doc.setFontSize(7);
      doc.setTextColor(150);
      doc.text(
        `Page ${i} of ${totalPages}`,
        pageWidth / 2, doc.internal.pageSize.getHeight() - 8,
        { align: 'center' }
      );
      doc.text(
        'ICAO Annex 19 / CAR-19 — Confidential Safety Data',
        margin, doc.internal.pageSize.getHeight() - 8
      );
    }

    return doc;
  }

  function exportToPdf(report, filename) {
    if (!_ensureLibraries()) return null;
    filename = filename || `CAAN_SSP_Report_${report.reporting_year || ''}.pdf`;
    const doc = _buildReportDoc(report);
    doc.save(filename);
    return filename;
  }

  return { exportToPdf };
})();

window.CaanPdfExport = CaanPdfExport;
