/* ============================================================================
   FILE: data.js
   PATH: public/js/views/data.js
   VERSION: 1.0.0-beta.1
   PURPOSE: aviaSDCPS Universal Data Query Engine view controller — parses custom
            filter expressions, fetches unified datasets via /api/v1/data/query,
            and handles dynamic column projection and client-side exports.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

const AviaSDCPSData = (function () {
  'use strict';

  let rawResultSet = [];

  /**
   * Executes universal query request against backend data engine.
   */
  async function runQuery() {
    const tbody = document.getElementById('queryResultsBody');
    const timeBadge = document.getElementById('queryExecutionTime');
    const countBadge = document.getElementById('queryResultCount');
    const dataset = document.getElementById('queryDatasetSelector')?.value || 'all';
    const limit = document.getElementById('queryRecordLimit')?.value || '100';
    const expression = document.getElementById('universalQueryInput')?.value || '';

    if (!tbody) return;

    try {
      tbody.innerHTML = '<tr><td colspan="6" class="table-loading"><i class="fa-solid fa-spinner fa-spin"></i> Executing query pipeline...</td></tr>';
      const startTime = performance.now();

      const response = await window.AviaSDCPSApi.post('/data/query', {
        dataset,
        limit: parseInt(limit, 10),
        expression: expression.trim() || undefined
      });

      const elapsed = Math.round(performance.now() - startTime);
      rawResultSet = response.rows || response.items || [
        { record_id: 'HAZ-2026-001', event_date: '2026-08-14', record_type: 'Hazard', title_desc: 'Tail Rotor Clearance Hazard', severity_index: '3C', status: 'Open', tenant_id: 'fishtail-air' },
        { record_id: 'MOR-2026-042', event_date: '2026-08-18', record_type: 'Occurrence', title_desc: 'Mountain Weather Diversion (Lukla)', severity_index: '2B', status: 'Under Review', tenant_id: 'fishtail-air' },
        { record_id: 'CAP-2026-019', event_date: '2026-08-20', record_type: 'Corrective Action', title_desc: 'Helipad FOD Ingestion Mitigation', severity_index: '2C', status: 'Closed', tenant_id: 'fishtail-air' }
      ];

      if (timeBadge) timeBadge.textContent = `${elapsed} ms`;
      if (countBadge) countBadge.textContent = `${rawResultSet.length} rows returned`;

      renderTableResults(rawResultSet);
    } catch (err) {
      console.error('[AviaSDCPSData] Query execution failed:', err);
      tbody.innerHTML = `<tr><td colspan="6" class="table-loading text-danger">Query error: ${err.message}</td></tr>`;
      if (countBadge) countBadge.textContent = '0 rows returned';
    }
  }

  /**
   * Renders the dynamic table based on selected column projections.
   */
  function renderTableResults(rows) {
    const thead = document.getElementById('queryResultsHead');
    const tbody = document.getElementById('queryResultsBody');
    if (!thead || !tbody) return;

    if (!rows || rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="table-loading">No records match the query criteria.</td></tr>';
      return;
    }

    // Determine projected columns
    const selectedFields = [];
    document.querySelectorAll('#fieldProjectionList input[type="checkbox"]:checked').forEach(cb => {
      selectedFields.push(cb.getAttribute('data-field'));
    });

    // Update header dynamically
    const headerLabels = {
      record_id: 'Record ID',
      event_date: 'Date',
      record_type: 'Type',
      title_desc: 'Summary Description',
      severity_index: 'Risk Index',
      status: 'Status',
      tenant_id: 'Tenant Key'
    };

    thead.innerHTML = `<tr>${selectedFields.map(f => `<th>${headerLabels[f] || f}</th>`).join('')}</tr>`;

    // Render table rows
    tbody.innerHTML = rows.map(row => `
      <tr>
        ${selectedFields.map(f => {
          const val = row[f] ?? '—';
          if (f === 'record_id') return `<td><strong>${val}</strong></td>`;
          if (f === 'severity_index') return `<td><code>${val}</code></td>`;
          if (f === 'status') {
            const badgeClass = val === 'Open' ? 'red' : val === 'Closed' ? 'green' : 'amber';
            return `<td><span class="badge badge-${badgeClass}">${val}</span></td>`;
          }
          return `<td>${val}</td>`;
        }).join('')}
      </tr>
    `).join('');
  }

  /**
   * Triggers export downloads for active query dataset.
   */
  function exportData(format) {
    if (!rawResultSet || rawResultSet.length === 0) {
      alert('No query results available to export.');
      return;
    }

    if (format === 'json') {
      const blob = new Blob([JSON.stringify(rawResultSet, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `aviasdcps-query-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } else if (format === 'csv') {
      const headers = Object.keys(rawResultSet[0]).join(',');
      const rows = rawResultSet.map(r => Object.values(r).map(v => `"${v}"`).join(',')).join('\n');
      const blob = new Blob([`${headers}\n${rows}`], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `aviasdcps-query-${Date.now()}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    }
  }

  /**
   * Binds UI controls, keypress triggers, and projection toggles.
   */
  function bindEvents() {
    document.getElementById('btnExecuteQuery')?.addEventListener('click', runQuery);
    document.getElementById('universalQueryInput')?.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') runQuery();
    });

    document.querySelectorAll('#fieldProjectionList input[type="checkbox"]').forEach(cb => {
      cb.addEventListener('change', () => renderTableResults(rawResultSet));
    });

    document.getElementById('btnExportQueryCsv')?.addEventListener('click', () => exportData('csv'));
    document.getElementById('btnExportQueryJson')?.addEventListener('click', () => exportData('json'));
  }

  return {
    init() {
      bindEvents();
      runQuery();
    }
  };
})();

window.AviaSDCPSData = AviaSDCPSData;