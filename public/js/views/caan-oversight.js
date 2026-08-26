/* ============================================================================
   FILE: caan-oversight.js
   PATH: public/js/views/caan-oversight.js
   VERSION: 1.0.0
   PURPOSE: AviaSDCPSCaanOversight controller — loads aggregate data, mounts charts,
            binds PDF export, email dispatch prompt, and audit log table.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

const AviaSDCPSCaanOversight = (function () {
  'use strict';

  let currentReport = null;

  async function init() {
    loadOversightData();
    bindActions();
  }

  async function loadOversightData() {
    const loadingEl = document.getElementById('oversightLoading');
    const contentEl = document.getElementById('oversightContent');

    try {
      const year = new Date().getFullYear();
      const quarter = Math.ceil((new Date().getMonth() + 1) / 3);
      const response = await window.AviaSDCPSApi.get(
        `/state-risk/aggregate?year=${year}&quarter=${quarter}`
      );

      currentReport = response.report || response;

      if (loadingEl) loadingEl.style.display = 'none';
      if (contentEl) contentEl.style.display = 'block';

      renderKpiStrip(currentReport);
      mountCharts(currentReport);
      loadAuditLogs();
    } catch (err) {
      console.error('[CaanOversight] Failed to load oversight data:', err);
      if (loadingEl) {
        loadingEl.innerHTML = `<div class="oversight-empty">
          <i class="fa-solid fa-triangle-exclamation"></i>
          <p>Failed to load oversight data: ${err.message}</p>
        </div>`;
      }
    }
  }

  function renderKpiStrip(report) {
    const strip = document.getElementById('kpiMetricStrip');
    if (!strip) return;

    const kpis = [
      { label: 'Operators', value: report.total_operators || 0, trend: '' },
      { label: 'Hazards', value: report.total_hazards || 0, trend: '' },
      { label: 'Reports', value: report.total_reports || 0, trend: '' },
      { label: 'Total CANs/CAPs', value: report.total_cans || 0, trend: '' },
      { label: 'Open CANs/CAPs', value: report.open_cans || 0, trend: '' },
      { label: 'Overdue', value: report.overdue_cans || 0, trend: report.overdue_cans > 0 ? 'up' : 'stable' },
      { label: 'Risk Index', value: report.industry_risk_index ?? 'N/A', trend: '' },
    ];

    strip.innerHTML = kpis.map(k => `
      <div class="kpi-card">
        <span class="kpi-label">${k.label}</span>
        <span class="kpi-value">${k.value}</span>
        ${k.trend ? `<span class="kpi-trend ${k.trend}">${k.trend === 'up' ? '&#9650; Attention' : k.trend === 'down' ? '&#9660; Improving' : '&#9644; Stable'}</span>` : ''}
      </div>
    `).join('');
  }

  function mountCharts(report) {
    if (typeof window.CaanChartFactory === 'undefined') {
      console.warn('[CaanOversight] CaanChartFactory not loaded');
      return;
    }

    const hrcData = report.hrc_distribution || [];
    if (hrcData.length > 0) {
      window.CaanChartFactory.createHrcDoughnut('caanHrcChart', hrcData);
    }

    const spiData = report.spi_metrics || [];
    if (spiData.length > 0) {
      window.CaanChartFactory.createSpiControlChart('caanSpiControlChart', spiData);
      window.CaanChartFactory.createDomainComplianceBar('caanDomainComplianceChart', spiData);
    }

    const opData = report.operator_summaries || [];
    if (opData.length > 0) {
      window.CaanChartFactory.createOperatorRiskScatter('caanOperatorRiskChart', opData);
    }
  }

  async function loadAuditLogs() {
    const tbody = document.getElementById('auditLogBody');
    if (!tbody) return;

    try {
      const response = await window.AviaSDCPSApi.get('/state-risk/audit-logs?limit=20');
      const logs = response.logs || [];

      if (logs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="table-loading">No dispatch audit records found.</td></tr>';
        return;
      }

      tbody.innerHTML = logs.map(log => `
        <tr>
          <td><code>${log.audit_id || log.id || '—'}</code></td>
          <td>${log.regulator_id || '—'}</td>
          <td>${log.reporting_year || '—'}${log.reporting_quarter ? ' Q' + log.reporting_quarter : ''}</td>
          <td>${(log.recipients || []).length} recipient(s)</td>
          <td><span class="status-badge ${log.status || 'pending'}">${log.status || 'pending'}</span></td>
          <td>${log.pdf_sha256_checksum ? log.pdf_sha256_checksum.substring(0, 12) + '...' : '—'}</td>
        </tr>
      `).join('');
    } catch (err) {
      console.error('[CaanOversight] Failed to load audit logs:', err);
      tbody.innerHTML = `<tr><td colspan="6" class="table-loading text-danger">Error: ${err.message}</td></tr>`;
    }
  }

  function bindActions() {
    const exportBtn = document.getElementById('btnExportPdf');
    if (exportBtn) {
      exportBtn.addEventListener('click', handlePdfExport);
    }

    const dispatchBtn = document.getElementById('btnDispatchEmail');
    if (dispatchBtn) {
      dispatchBtn.addEventListener('click', showDispatchPrompt);
    }
  }

  function handlePdfExport() {
    if (!currentReport) {
      alert('No report data loaded. Please wait for data to load.');
      return;
    }
    if (typeof window.CaanPdfExport !== 'undefined') {
      window.CaanPdfExport.exportToPdf(currentReport);
    } else if (typeof window.AviaSDCPSApi !== 'undefined') {
      const year = currentReport.reporting_year || new Date().getFullYear();
      const quarter = currentReport.reporting_quarter || Math.ceil((new Date().getMonth() + 1) / 3);
      window.open(
        `${window.AviaSDCPSApi.getBaseUrl()}/state-risk/export-pdf?year=${year}&quarter=${quarter}`,
        '_blank'
      );
    }
  }

  function showDispatchPrompt() {
    if (!currentReport) {
      alert('No report data loaded. Please wait for data to load.');
      return;
    }

    const existing = document.querySelector('.dispatch-prompt-overlay');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.className = 'dispatch-prompt-overlay';
    overlay.innerHTML = `
      <div class="dispatch-prompt-card">
        <h3><i class="fa-solid fa-envelope"></i> Dispatch SSP Report</h3>
        <p style="font-size:0.8rem;color:#64748b;margin:0 0 12px">
          Enter the recipient email for the ${currentReport.reporting_year} Q${currentReport.reporting_quarter || ''} report.
        </p>
        <input type="email" id="dispatchRecipientInput" placeholder="regulator@caanepal.gov.np" />
        <div class="prompt-actions">
          <button class="aviasdcps-btn aviasdcps-btn-secondary" id="dispatchCancelBtn">Cancel</button>
          <button class="aviasdcps-btn aviasdcps-btn-primary" id="dispatchConfirmBtn">
            <i class="fa-solid fa-paper-plane"></i> Send
          </button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    document.getElementById('dispatchCancelBtn').addEventListener('click', () => overlay.remove());
    document.getElementById('dispatchConfirmBtn').addEventListener('click', async () => {
      const email = document.getElementById('dispatchRecipientInput').value.trim();
      if (!email) return;

      const year = currentReport.reporting_year;
      const quarter = currentReport.reporting_quarter;
      try {
        await window.AviaSDCPSApi.post(
          `/state-risk/dispatch-email?year=${year}&quarter=${quarter}&recipient=${encodeURIComponent(email)}`
        );
        overlay.remove();
        alert(`Report dispatch queued for ${email}`);
        loadAuditLogs();
      } catch (err) {
        alert(`Dispatch failed: ${err.message}`);
      }
    });
  }

  return { init };
})();

window.AviaSDCPSCaanOversight = AviaSDCPSCaanOversight;
