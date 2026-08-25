/* ============================================================================
   FILE: hrc.js
   PATH: public/js/views/hrc.js
   VERSION: 1.0.0-beta.1
   PURPOSE: aviaSDCPS High Risk Categories view controller — queries state risk
            aggregation endpoints (/api/v1/state-risk/aggregate, /api/v1/state-risk/register),
            populates priority cards, and handles drilldown searches.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

const AviaSDCPSHrc = (function () {
  'use strict';

  let currentCategories = [];

  /**
   * Fetches state risk aggregation and high risk category datasets.
   */
  async function loadHrcData() {
    const tbody = document.getElementById('hrcTableBody');
    if (!tbody) return;

    try {
      tbody.innerHTML = '<tr><td colspan="7" class="table-loading">Loading High Risk Category register...</td></tr>';

      const response = await window.AviaSDCPSApi.get('/state-risk/aggregate');
      currentCategories = response.categories || response.items || [];

      updateCategoryCards(response.summary || {});
      renderHrcTable(currentCategories);
    } catch (err) {
      console.error('[AviaSDCPSHrc] Error loading high risk category data:', err);
      tbody.innerHTML = `<tr><td colspan="7" class="table-loading text-danger">Error loading HRC register: ${err.message}</td></tr>`;
    }
  }

  /**
   * Updates top insight mini-cards with category metrics.
   */
  function updateCategoryCards(summary) {
    const renderCard = (elementId, data) => {
      const el = document.getElementById(elementId);
      if (!el) return;
      if (!data) {
        el.innerHTML = '<span class="no-data">0 Active Precursors</span>';
        return;
      }
      el.innerHTML = `
        <div class="insight-row">
          <span>Precursors: <strong>${data.precursors ?? 0}</strong></span>
          <span>Risk: <strong class="badge badge-${data.level === 'High' ? 'red' : 'amber'}">${data.index ?? 'Low'}</strong></span>
        </div>
      `;
    };

    renderCard('hrcCardCfit', summary.cfit);
    renderCard('hrcCardLoci', summary.loci);
    renderCard('hrcCardRs', summary.rs);
    renderCard('hrcCardMac', summary.mac);
  }

  /**
   * Renders the High Risk Category master table.
   */
  function renderHrcTable(rows) {
    const tbody = document.getElementById('hrcTableBody');
    if (!tbody) return;

    if (!rows || rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="table-loading">No High Risk Category records found.</td></tr>';
      return;
    }

    tbody.innerHTML = rows.map(item => `
      <tr data-id="${item.code}">
        <td><strong>${item.code || '—'}</strong></td>
        <td>${item.name || 'Unclassified Risk'}</td>
        <td>${item.precursor_count ?? 0}</td>
        <td>${item.hazard_count ?? 0}</td>
        <td>${item.open_cap_count ?? 0}</td>
        <td><code>${item.risk_index || '1B'}</code></td>
        <td>
          <span class="badge badge-${item.status === 'Alert' ? 'red' : item.status === 'Watch' ? 'amber' : 'green'}">
            ${item.status || 'Nominal'}
          </span>
        </td>
      </tr>
    `).join('');
  }

  /**
   * Attaches interactive toolbar filters and search handlers.
   */
  function bindEvents() {
    document.getElementById('hrcSearchInput')?.addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase();
      const filtered = currentCategories.filter(c =>
        (c.name && c.name.toLowerCase().includes(q)) ||
        (c.code && c.code.toLowerCase().includes(q))
      );
      renderHrcTable(filtered);
    });

    document.getElementById('hrcTaxonomyStandard')?.addEventListener('change', () => {
      loadHrcData();
    });

    document.getElementById('btnExportHrcReport')?.addEventListener('click', () => {
      alert('Generating State High Risk Category (HRC) Executive Brief PDF...');
    });
  }

  return {
    init() {
      bindEvents();
      loadHrcData();
    }
  };
})();

window.AviaSDCPSHrc = AviaSDCPSHrc;