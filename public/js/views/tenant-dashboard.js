/* ============================================================================
   FILE: tenant-dashboard.js
   PATH: public/js/views/tenant-dashboard.js
   VERSION: 1.0.0
   PURPOSE: AviaSDCPSTenantDashboard controller — fetches tenant-scoped data,
            initializes risk matrix, SPI charts, CAPA table, and audit register.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

const AviaSDCPSTenantDashboard = (function () {
  'use strict';

  let currentReport = null;

  async function init() {
    loadDashboardData();
    bindActions();
  }

  async function loadDashboardData() {
    const loadingEl = document.getElementById('tenantDashboardLoading');
    const contentEl = document.getElementById('tenantDashboardContent');

    try {
      const now = new Date();
      const year = now.getFullYear();
      const month = now.getMonth() + 1;

      const response = await window.AviaSDCPSApi.get(
        `/tenants/sms/monthly-summary?year=${year}&month=${month}`
      );

      currentReport = response.report || response;

      if (loadingEl) loadingEl.style.display = 'none';
      if (contentEl) contentEl.style.display = 'block';

      renderKpiStrip(currentReport);
      renderRiskMatrix(currentReport.risk_heatmap || []);
      mountCharts(currentReport);
      renderCapaTable(currentReport.open_capas || []);
      loadAuditLogs();
    } catch (err) {
      console.error('[TenantDashboard] Failed to load data:', err);
      if (loadingEl) {
        loadingEl.innerHTML = `
          <div class="tenant-loading">
            <i class="fa-solid fa-triangle-exclamation"></i>&nbsp;
            Failed to load dashboard: ${err.message}
          </div>`;
      }
    }
  }

  function renderKpiStrip(report) {
    const strip = document.getElementById('tenantKpiStrip');
    if (!strip) return;

    const kpis = [
      { label: 'Flight Hours', value: (report.flight_hours_logged || 0).toFixed(1), trend: '' },
      { label: 'Safety Reports', value: report.safety_reports_submitted || 0, trend: '' },
      { label: 'Open Hazards', value: report.open_hazards || 0, trend: '' },
      { label: 'Intolerable Risks', value: report.intolerable_risks || 0, trend: report.intolerable_risks > 0 ? 'alert' : 'ok' },
      { label: 'Open CAPAs', value: (report.open_capas || []).length, trend: '' },
      { label: 'Overdue CAPAs', value: report.overdue_capas || 0, trend: report.overdue_capas > 0 ? 'alert' : 'ok' },
    ];

    strip.innerHTML = kpis.map(k => `
      <div class="kpi-card">
        <span class="kpi-label">${k.label}</span>
        <span class="kpi-value">${k.value}</span>
        ${k.trend ? `<span class="kpi-trend ${k.trend}">${k.trend === 'alert' ? '&#9650; Attention' : '&#9660; OK'}</span>` : ''}
      </div>
    `).join('');
  }

  function renderRiskMatrix(heatmap) {
    const container = document.getElementById('tenantRiskMatrix');
    if (!container || !heatmap || heatmap.length === 0) {
      if (container) container.innerHTML = '<div class="tenant-loading">No heatmap data available</div>';
      return;
    }

    const SEV_ORDER = ['5_CATASTROPHIC', '4_HAZARDOUS', '3_MAJOR', '2_MINOR', '1_NEGLIGIBLE'];
    const LIKE_ORDER = ['A_FREQUENT', 'B_OCCASIONAL', 'C_REMOTE', 'D_IMPROBABLE', 'E_EXTREMELY_IMPROBABLE'];
    const SEV_LABELS = { '5_CATASTROPHIC': 'Cat.', '4_HAZARDOUS': 'Haz.', '3_MAJOR': 'Maj.', '2_MINOR': 'Min.', '1_NEGLIGIBLE': 'Neg.' };
    const LIKE_LABELS = { 'A_FREQUENT': 'Frequent', 'B_OCCASIONAL': 'Occasional', 'C_REMOTE': 'Remote', 'D_IMPROBABLE': 'Improbable', 'E_EXTREMELY_IMPROBABLE': 'Ext. Improb.' };
    const TOL_CLASS = { 'ACCEPTABLE': 'tolerability-ACCEPTABLE', 'TOLERABLE_WITH_MITIGATION': 'tolerability-TOLERABLE', 'INTOLERABLE': 'tolerability-INTOLERABLE' };

    const lookup = {};
    heatmap.forEach(c => { lookup[`${c.severity}|${c.likelihood}`] = c; });

    let html = '<div class="matrix-corner"></div>';
    LIKE_ORDER.forEach(l => { html += `<div class="matrix-header">${LIKE_LABELS[l]}</div>`; });

    SEV_ORDER.forEach(sev => {
      html += `<div class="matrix-row-label">${SEV_LABELS[sev]}</div>`;
      LIKE_ORDER.forEach(like => {
        const cell = lookup[`${sev}|${like}`] || {};
        const count = cell.hazard_count || 0;
        const tol = cell.tolerability || 'ACCEPTABLE';
        const tolClass = TOL_CLASS[tol] || TOL_CLASS['ACCEPTABLE'];
        html += `<div class="matrix-cell ${tolClass}" title="${sev} x ${like}: ${count} hazard(s) — ${tol}">
          <span class="cell-count ${count === 0 ? 'zero' : ''}">${count || '-'}</span>
        </div>`;
      });
    });

    container.innerHTML = html;
  }

  function mountCharts(report) {
    if (typeof window.TenantChartFactory === 'undefined') return;

    const heatmap = report.risk_heatmap || [];
    if (heatmap.length > 0) {
      window.TenantChartFactory.createTenantRiskMatrixChart('tenantRiskMatrixChart', heatmap);
    }

    const spi = (report.spi_metrics || [])[0] || { name: 'SPI Trend' };
    window.TenantChartFactory.createTenantSpiTrendChart(
      'tenantSpiTrendChart',
      spi,
      spi.history || []
    );
  }

  function renderCapaTable(capas) {
    const tbody = document.getElementById('tenantCapaBody');
    if (!tbody) return;

    if (!capas || capas.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="table-loading">No open CAPA items.</td></tr>';
      return;
    }

    tbody.innerHTML = capas.map(c => `
      <tr>
        <td><code>${c.source_reference || '—'}</code></td>
        <td>${(c.description || '').substring(0, 60)}${(c.description || '').length > 60 ? '...' : ''}</td>
        <td>${c.responsible_post_holder || '—'}</td>
        <td>${c.target_close_out_date || '—'}</td>
        <td><span class="status-badge ${c.implementation_status || 'OPEN'}">${c.implementation_status || 'OPEN'}</span></td>
        <td>${c.priority || 'MEDIUM'}</td>
      </tr>
    `).join('');
  }

  async function loadAuditLogs() {
    const tbody = document.getElementById('tenantAuditBody');
    if (!tbody) return;

    try {
      const response = await window.AviaSDCPSApi.get('/tenants/sms/audit-logs?limit=20');
      const logs = response.logs || [];

      if (logs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="table-loading">No dispatch audit records.</td></tr>';
        return;
      }

      tbody.innerHTML = logs.map(log => `
        <tr>
          <td><code>${log.audit_id || log.id || '—'}</code></td>
          <td>${log.reporting_year || '—'}-${(log.reporting_month || 0).toString().padStart(2, '0')}</td>
          <td>${(log.recipients || []).length} recipient(s)</td>
          <td><span class="status-badge ${log.status || 'pending'}">${log.status || 'pending'}</span></td>
          <td>${log.pdf_sha256_checksum ? log.pdf_sha256_checksum.substring(0, 12) + '...' : '—'}</td>
        </tr>
      `).join('');
    } catch (err) {
      console.error('[TenantDashboard] Failed to load audit logs:', err);
      tbody.innerHTML = `<tr><td colspan="5" class="table-loading text-danger">Error: ${err.message}</td></tr>`;
    }
  }

  function bindActions() {
    const exportBtn = document.getElementById('btnTenantExportPdf');
    if (exportBtn) exportBtn.addEventListener('click', handlePdfExport);

    const dispatchBtn = document.getElementById('btnTenantDispatchSrb');
    if (dispatchBtn) dispatchBtn.addEventListener('click', handleDispatchSrb);
  }

  function handlePdfExport() {
    if (!currentReport) { alert('No report data loaded.'); return; }
    const now = new Date();
    const url = window.AviaSDCPSApi.getBaseUrl
      ? `${window.AviaSDCPSApi.getBaseUrl()}/tenants/sms/export-pdf?year=${now.getFullYear()}&month=${now.getMonth() + 1}`
      : `/api/v1/tenants/sms/export-pdf?year=${now.getFullYear()}&month=${now.getMonth() + 1}`;
    window.open(url, '_blank');
  }

  function handleDispatchSrb() {
    if (!currentReport) { alert('No report data loaded.'); return; }
    const email = prompt('Enter Safety Action Group recipient email:');
    if (!email) return;
    const now = new Date();
    window.AviaSDCPSApi.post(
      `/tenants/sms/dispatch-srb?year=${now.getFullYear()}&month=${now.getMonth() + 1}&recipient=${encodeURIComponent(email)}`
    ).then(() => {
      alert(`SRB dispatch queued for ${email}`);
      loadAuditLogs();
    }).catch(err => {
      alert(`Dispatch failed: ${err.message}`);
    });
  }

  return { init };
})();

window.AviaSDCPSTenantDashboard = AviaSDCPSTenantDashboard;
