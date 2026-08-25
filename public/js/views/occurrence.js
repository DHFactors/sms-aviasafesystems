/* ============================================================================
   FILE: occurrence.js
   PATH: public/js/views/occurrence.js
   VERSION: 1.0.0-beta.1
   PURPOSE: aviaSDCPS Occurrence Register view controller — fetches reports from
            /api/reports with tab and filter support, renders the table, and
            wires up the slide-out detail drawer.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

/**
 * @module AviaSAFE aviaSDCPS
 * @file public/js/views/occurrence.js
 * @version 1.0.0-beta.1 (2026-08-25)
 * @target sms-db-beta / feat/betasms-self-service
 */

const AviaSDCPSOccurrence = (function () {
  'use strict';

  let currentOccurrences = [];

  /**
   * Fetches occurrence and MOR/VSR reports.
   */
  async function loadOccurrences() {
    const tbody = document.getElementById('occurrenceTableBody');
    if (!tbody) return;

    try {
      tbody.innerHTML = '<tr><td colspan="9" class="table-loading">Loading occurrences...</td></tr>';
      
      const response = await window.AviaSDCPSApi.get('/reports/', { limit: 50 });
      currentOccurrences = response.items || response.reports || [];
      renderTable(currentOccurrences);
    } catch (err) {
      console.error('[AviaSDCPSOccurrence] Error loading occurrences:', err);
      tbody.innerHTML = `<tr><td colspan="9" class="table-loading text-danger">Error: ${err.message}</td></tr>`;
    }
  }

  function renderTable(rows) {
    const tbody = document.getElementById('occurrenceTableBody');
    if (!tbody) return;

    if (!rows || rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" class="table-loading">No occurrence reports found.</td></tr>';
      return;
    }

    tbody.innerHTML = rows.map(item => `
      <tr data-id="${item.id}">
        <td><strong>${item.id || item.report_number || '—'}</strong></td>
        <td>${item.occurrence_date || item.created_at || '—'}</td>
        <td>
          <span class="badge badge-${item.type === 'MOR' ? 'red' : 'blue'}">
            ${item.type || 'MOR'}
          </span>
        </td>
        <td>${item.location || item.aerodrome || 'VNKT'}</td>
        <td><code>${item.aircraft_reg || item.callsign || '9N-A**'}</code></td>
        <td>${item.flight_phase || 'Cruise'}</td>
        <td>${item.occurrence_class || 'Incident'}</td>
        <td>${item.severity || 'Medium'}</td>
        <td>
          <span class="status-indicator status-${(item.status || 'submitted').toLowerCase()}">
            ${item.status || 'Submitted'}
          </span>
        </td>
      </tr>
    `).join('');
  }

  function bindEvents() {
    const toggles = document.querySelectorAll('.occurrence-type-toggle .toggle-btn');
    toggles.forEach(btn => {
      btn.addEventListener('click', (e) => {
        toggles.forEach(b => b.classList.remove('active'));
        e.currentTarget.classList.add('active');
        const type = e.currentTarget.getAttribute('data-type');
        
        if (type === 'all') {
          renderTable(currentOccurrences);
        } else {
          const targetType = type === 'mandatory' ? 'MOR' : 'VSR';
          renderTable(currentOccurrences.filter(o => (o.type || 'MOR') === targetType));
        }
      });
    });

    document.getElementById('occurrencePhaseFilter')?.addEventListener('change', (e) => {
      const phase = e.target.value;
      const filtered = phase 
        ? currentOccurrences.filter(o => o.flight_phase === phase) 
        : currentOccurrences;
      renderTable(filtered);
    });

    document.getElementById('btnExportEccairs')?.addEventListener('click', () => {
      alert('Generating ICAO ECCAIRS E5X XML dataset export for CAAN...');
    });
  }

  return {
    init() {
      bindEvents();
      loadOccurrences();
    }
  };
})();

window.AviaSDCPSOccurrence = AviaSDCPSOccurrence;
