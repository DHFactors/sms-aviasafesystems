/**
 * @module AviaSAFE aviaSDCPS
 * @file public/js/views/hazard.js
 * @version 1.0.0-beta.1 (2026-08-25)
 * @target sms-db / consolidated platform
 */

const AviaSDCPSHazard = (function () {
  'use strict';

  let currentHazards = [];

  /**
   * Fetches paginated hazard records from Master Register.
   */
  async function loadHazards() {
    const tbody = document.getElementById('hazardTableBody');
    if (!tbody) return;

    try {
      tbody.innerHTML = '<tr><td colspan="9" class="table-loading">Loading hazards...</td></tr>';
      
      const response = await window.AviaSDCPSApi.get('/dashboard/master-register', {
        page_size: 50,
        by_type: 'hazard'
      });

      currentHazards = response.rows || [];
      renderTable(currentHazards);
    } catch (err) {
      console.error('[AviaSDCPSHazard] Error loading hazards:', err);
      tbody.innerHTML = `<tr><td colspan="9" class="table-loading text-danger">Error: ${err.message}</td></tr>`;
    }
  }

  function renderTable(rows) {
    const tbody = document.getElementById('hazardTableBody');
    if (!tbody) return;

    if (!rows || rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" class="table-loading">No hazard records found.</td></tr>';
      return;
    }

    tbody.innerHTML = rows.map(item => `
      <tr data-id="${item.id}">
        <td><strong>${item.id || '—'}</strong></td>
        <td>
          <div class="cell-title">${item.title || 'Untitled Hazard'}</div>
          <small class="text-muted">${item.description ? item.description.substring(0, 60) + '...' : ''}</small>
        </td>
        <td><span class="badge badge-subtle">${item.source || 'Direct'}</span></td>
        <td>${item.taxonomy || 'ADREP General'}</td>
        <td>
          <span class="badge badge-${item.priority === 'H' ? 'red' : item.priority === 'M' ? 'amber' : 'green'}">
            ${item.priority || 'L'}
          </span>
        </td>
        <td><code>${item.risk_index || '3C'}</code></td>
        <td>${item.assigned_to || 'Safety Manager'}</td>
        <td>
          <span class="status-indicator status-${(item.status || 'open').toLowerCase()}">
            ${item.status || 'Open'}
          </span>
        </td>
        <td>
          <button class="btn-sm btn-view-hazard" data-id="${item.id}">View</button>
        </td>
      </tr>
    `).join('');

    tbody.querySelectorAll('.btn-view-hazard').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const id = e.currentTarget.getAttribute('data-id');
        openDrawer(id);
      });
    });
  }

  async function openDrawer(hazardId) {
    const drawer = document.getElementById('hazardDetailDrawer');
    const content = document.getElementById('drawerHazardContent');
    const title = document.getElementById('drawerHazardTitle');
    if (!drawer || !content) return;

    const record = currentHazards.find(h => h.id === hazardId);
    if (!record) return;

    title.textContent = `Hazard: ${record.id}`;
    content.innerHTML = `
      <div class="drawer-section">
        <label>Title</label>
        <p><strong>${record.title || '—'}</strong></p>
      </div>
      <div class="drawer-section">
        <label>Description</label>
        <p>${record.description || 'No description provided.'}</p>
      </div>
      <div class="drawer-section">
        <label>Risk Tolerability & Index</label>
        <p>Initial: <code>${record.initial_risk || record.risk_index || '3C'}</code> | Tolerability: <strong>${record.tolerability || 'Tolerable'}</strong></p>
      </div>
      <div class="drawer-section">
        <label>Linked Actions (CAN/CAP)</label>
        <p>${record.linked_caps ? record.linked_caps.join(', ') : 'No linked CAPs'}</p>
      </div>
    `;

    drawer.classList.add('open');
  }

  function closeDrawer() {
    const drawer = document.getElementById('hazardDetailDrawer');
    if (drawer) drawer.classList.remove('open');
  }

  function bindEvents() {
    document.getElementById('btnCloseHazardDrawer')?.addEventListener('click', closeDrawer);
    
    document.getElementById('hazardSearchInput')?.addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase();
      const filtered = currentHazards.filter(h => 
        (h.title && h.title.toLowerCase().includes(q)) || 
        (h.id && h.id.toLowerCase().includes(q)) ||
        (h.taxonomy && h.taxonomy.toLowerCase().includes(q))
      );
      renderTable(filtered);
    });

    document.getElementById('hazardPriorityFilter')?.addEventListener('change', (e) => {
      const p = e.target.value;
      const filtered = p ? currentHazards.filter(h => h.priority === p) : currentHazards;
      renderTable(filtered);
    });
  }

  return {
    init() {
      bindEvents();
      loadHazards();
    }
  };
})();

window.AviaSDCPSHazard = AviaSDCPSHazard;
