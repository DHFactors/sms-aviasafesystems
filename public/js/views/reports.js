/* ============================================================================
   FILE: reports.js
   PATH: public/js/views/reports.js
   VERSION: 1.0.0-beta.1
   PURPOSE: aviaSDCPS Generate Report view controller — communicates with
            /api/v1/reporting/quarterly and /api/v1/reporting/annual to generate,
            preview, and export ICAO/CAR-19 safety performance reports.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

const AviaSDCPSReports = (function () {
  'use strict';

  let currentReportType = 'quarterly';
  let compiledReportData = null;
  let currentReportId = null;
  let currentPeriod = '';

  /**
   * Mirror of AviaSDCPSApi's base URL / auth headers, used for the PDF export
   * which must read the response as a blob (the standard API wrapper is JSON-only).
   */
  function apiBaseUrl() {
    return 'https://aviasafe-unified-platform.onrender.com/api/v1';
  }
  function authHeaders(extra) {
    const token = sessionStorage.getItem('aviasafe_token') || localStorage.getItem('aviasafe_token') || null;
    const headers = { 'Accept': 'application/json', ...(extra || {}) };
    if (token) headers['Authorization'] = 'Bearer ' + token;
    return headers;
  }
  function esc(val) {
    return String(val == null ? '' : val)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  /**
   * Compiles report payload and queries generation endpoint.
   * The backend reads year/quarter as QUERY parameters (int), not the JSON body.
   */
  async function compileReport() {
    const previewContainer = document.getElementById('reportDocumentPreview');
    const btnDownload = document.getElementById('btnDownloadPdf');
    const btnPrint = document.getElementById('btnPrintReport');

    const year = document.getElementById('reportYearSelect')?.value || '2026';
    const quarterRaw = document.getElementById('reportQuarterSelect')?.value || 'Q1';
    const quarterNum = parseInt(String(quarterRaw).replace(/^Q/i, ''), 10) || 1;

    const payload = {
      year: parseInt(year, 10),
      quarter: currentReportType === 'quarterly' ? quarterNum : undefined,
      prepared_by: document.getElementById('reportAuthor')?.value || 'Safety Manager',
      submitted_to: document.getElementById('reportRecipient')?.value || 'CAAN'
    };

    try {
      previewContainer.innerHTML = `
        <div class="document-placeholder">
          <i class="fa-solid fa-spinner fa-spin doc-icon"></i>
          <h4>Compiling Safety Data...</h4>
          <p class="text-muted">Aggregating occurrences, hazards, and Bow-Tie risk metrics.</p>
        </div>
      `;

      const baseEndpoint = currentReportType === 'quarterly'
        ? '/reporting/quarterly'
        : '/reporting/annual';

      const params = new URLSearchParams({ year: String(year) });
      if (currentReportType === 'quarterly') params.set('quarter', String(quarterNum));
      const endpoint = `${baseEndpoint}?${params.toString()}`;

      compiledReportData = await window.AviaSDCPSApi.post(endpoint, payload);
      currentReportId = compiledReportData?.id || null;
      currentPeriod = compiledReportData?.period ||
        (currentReportType === 'quarterly' ? `Q${quarterNum} ${year}` : String(year));

      renderDocumentPreview(compiledReportData, payload);

      btnDownload.removeAttribute('disabled');
      btnPrint.removeAttribute('disabled');
    } catch (err) {
      console.error('[AviaSDCPSReports] Generation failed:', err);
      currentReportId = null;
      btnDownload.setAttribute('disabled', 'disabled');
      btnPrint.setAttribute('disabled', 'disabled');
      previewContainer.innerHTML = `
        <div class="document-placeholder text-danger">
          <i class="fa-solid fa-circle-exclamation doc-icon"></i>
          <h4>Compilation Error</h4>
          <p>${esc(err.message)}</p>
        </div>
      `;
    }
  }

  /**
   * Renders compiled executive report into the preview canvas.
   * The backend returns nested `summary` and `data` objects, so read those
   * instead of flat fields.
   */
  function renderDocumentPreview(response, params) {
    const container = document.getElementById('reportDocumentPreview');
    if (!container) return;

    const summary = (response && response.summary) || {};
    const data = (response && response.data) || {};

    const reportTitle = currentReportType === 'quarterly'
      ? `Quarterly SMS Performance Review (${params.quarter ? 'Q' + params.quarter : ''} ${params.year})`
      : `Annual State Safety Programme Performance Report (${params.year})`;

    const totalHazards = summary.total_hazards ?? 0;
    const newHazards = summary.new_hazards ?? summary.hazards_opened ?? 0;
    const closedHazards = summary.closed_hazards ?? summary.hazards_closed ?? 0;
    const openHazards = summary.open_hazards ?? 0;
    const closureRate = summary.closure_rate ?? 0;

    const riskLevels = (data.risk_levels || []).map(function (rl, i) {
      return `<li><span class="risk-dot" style="background:${esc(rl.color || '#ccc')}"></span> ` +
             `${esc(rl.label)} (${rl.value})</li>`;
    }).join('');

    const topRisks = (data.top_risks || []).slice(0, 6).map(function (r) {
      return `<li><strong>${esc(r.category)}:</strong> ${r.count}</li>`;
    }).join('') || '<li class="text-muted">No risk categories recorded.</li>';

    const canCap = data.can_cap_status || data.can_cap_summary || {};
    const canCapRows = Object.keys(canCap).filter(function (k) {
      return typeof canCap[k] === 'number';
    }).map(function (k) {
      return `<li><strong>${esc(k.replace(/_/g, ' '))}:</strong> ${canCap[k]}</li>`;
    }).join('');

    const insights = (data.insights || []).map(function (i) {
      return `<li>${esc(i)}</li>`;
    }).join('');

    const ssp = data.ssp_indicators || {};
    const sspKeys = Object.keys(ssp).filter(function (k) {
      return ssp[k] !== null && ssp[k] !== undefined;
    }).map(function (k) {
      return `<li><strong>${esc(k.replace(/_/g, ' '))}:</strong> ${esc(ssp[k])}</li>`;
    }).join('');

    const recs = [];
    if (Array.isArray(data.strategic_recommendations)) {
      data.strategic_recommendations.forEach(function (r) { recs.push(r); });
    }
    if (Array.isArray(data.operational_recommendations)) {
      data.operational_recommendations.forEach(function (r) { recs.push(r); });
    }
    const recommendations = recs.slice(0, 8).map(function (r) {
      return `<li>${esc(r)}</li>`;
    }).join('');

    container.innerHTML = `
      <div class="doc-sheet">
        <div class="doc-header-block">
          <div class="doc-badge">CIVIL AVIATION SAFETY OVERSIGHT</div>
          <h2>${esc(reportTitle)}</h2>
          <div class="doc-meta-row">
            <span><strong>Organization:</strong> ${esc(params.organization || 'Fishtail Air (AOC)')}</span>
            <span><strong>Regulator:</strong> ${esc(params.submitted_to || 'CAAN')}</span>
            <span><strong>Date Generated:</strong> ${new Date().toLocaleDateString()}</span>
          </div>
        </div>

        <hr class="doc-divider" />

        <div class="doc-body-section">
          <h3>1. Executive Risk Summary</h3>
          <p>${esc(insights.length ? insights : 'The safety performance for this operating period meets baseline acceptability criteria under CAAN CAR-19 guidelines.')}</p>

          <div class="doc-stats-grid">
            <div class="doc-stat-box">
              <span>Total Reportable Hazards</span>
              <strong>${totalHazards}</strong>
            </div>
            <div class="doc-stat-box">
              <span>Open Hazards</span>
              <strong>${openHazards}</strong>
            </div>
            <div class="doc-stat-box">
              <span>Hazard Closure Rate</span>
              <strong>${closureRate}%</strong>
            </div>
            <div class="doc-stat-box">
              <span>New (This Period)</span>
              <strong>${newHazards}</strong>
            </div>
          </div>
        </div>

        <div class="doc-body-section">
          <h3>2. Risk Distribution</h3>
          <ul class="doc-list">${riskLevels || '<li class="text-muted">No risk data available.</li>'}</ul>
        </div>

        <div class="doc-body-section">
          <h3>3. Top Risk Categories</h3>
          <ul class="doc-list">${topRisks}</ul>
        </div>

        <div class="doc-body-section">
          <h3>4. Corrective Action (CAN/CAP) Status</h3>
          <ul class="doc-list">${canCapRows || '<li class="text-muted">No corrective action data available.</li>'}</ul>
        </div>

        ${sspKeys ? `
        <div class="doc-body-section">
          <h3>5. State Safety Programme Indicators</h3>
          <ul class="doc-list">${sspKeys}</ul>
        </div>` : ''}

        ${recommendations ? `
        <div class="doc-body-section">
          <h3>6. Recommendations</h3>
          <ul class="doc-list">${recommendations}</ul>
        </div>` : ''}

        <div class="doc-signoff">
          <div>
            <div class="sig-line"></div>
            <small>Prepared By: ${esc(params.prepared_by || 'Safety Manager')}</small>
          </div>
          <div>
            <div class="sig-line"></div>
            <small>Accepted By: CAAN SMD Inspectorate</small>
          </div>
        </div>
      </div>
    `;
  }

  /**
   * Downloads the compiled report's PDF from the export endpoint (returns a blob).
   */
  async function downloadPdf() {
    if (!currentReportId) {
      alert('No report to download. Compile a report first.');
      return;
    }
    const path = currentReportType === 'quarterly'
      ? `/reporting/quarterly/${currentReportId}/export`
      : `/reporting/annual/${currentReportId}/export`;

    try {
      const res = await fetch(apiBaseUrl() + path, {
        method: 'GET',
        headers: authHeaders({ 'Accept': 'application/pdf' })
      });
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try { const j = await res.json(); detail = j.detail || detail; } catch (_) { /* not JSON */ }
        throw new Error(detail);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${currentReportType}_report_${currentPeriod.replace(/\s+/g, '_').replace(/[^A-Za-z0-9_-]/g, '') || 'generated'}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('[AviaSDCPSReports] PDF export failed:', err);
      alert('PDF export failed: ' + err.message);
    }
  }

  /**
   * Event bindings for report type toggles and action triggers.
   */
  function bindEvents() {
    const toggleBtns = document.querySelectorAll('#reportsViewContainer .toggle-btn');
    const quarterSelect = document.getElementById('reportQuarterSelect');

    toggleBtns.forEach(btn => {
      btn.addEventListener('click', (e) => {
        toggleBtns.forEach(b => b.classList.remove('active'));
        e.currentTarget.classList.add('active');

        currentReportType = e.currentTarget.getAttribute('data-report-type');
        if (quarterSelect) {
          quarterSelect.style.display = currentReportType === 'quarterly' ? 'inline-block' : 'none';
        }
        // A compiled report corresponds to the previous type; invalidate it.
        currentReportId = null;
        currentPeriod = '';
        const btnDownload = document.getElementById('btnDownloadPdf');
        const btnPrint = document.getElementById('btnPrintReport');
        if (btnDownload) btnDownload.setAttribute('disabled', 'disabled');
        if (btnPrint) btnPrint.setAttribute('disabled', 'disabled');
      });
    });

    document.getElementById('btnCompileReport')?.addEventListener('click', compileReport);

    document.getElementById('btnPrintReport')?.addEventListener('click', () => {
      if (!compiledReportData) { alert('No report to print. Compile a report first.'); return; }
      window.print();
    });

    document.getElementById('btnDownloadPdf')?.addEventListener('click', downloadPdf);
  }

  return {
    init() {
      bindEvents();
    }
  };
})();

window.AviaSDCPSReports = AviaSDCPSReports;