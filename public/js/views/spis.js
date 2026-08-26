/**
 * @module AviaSAFE aviaSDCPS
 * @file public/js/views/spis.js
 * @version 1.0.0-beta.1 (2026-08-25)
 * @target sms-db-beta / feat/betasms-self-service
 *
 * SPIs / SPTs controller — fetches indicators from /safety-performance/indicators,
 * renders KPI cards, master indicator table with trajectory and status badges,
 * and interactive domain + alert-status filters.
 */

const AviaSDCPSSpis = (function () {
  'use strict';

  let allIndicators = [];
  let activeStatusFilter = 'all';
  let activeDomainFilter = 'all';
  let searchQuery = '';

  function el(id) { return document.getElementById(id); }

  // ── Status Classification ──────────────────────────────────────────────────

  function getStatus(spi) {
    if (spi.status) return spi.status;
    const val = parseFloat(spi.current_value ?? spi.value);
    const threshold = parseFloat(spi.alert_threshold ?? spi.target_threshold);
    if (isNaN(val) || isNaN(threshold)) return 'nominal';
    if (val >= threshold) return 'alert';
    if (val >= threshold * 0.8) return 'watch';
    return 'nominal';
  }

  function statusBadgeClass(status) {
    const map = { nominal: 'badge-green', watch: 'badge-amber', alert: 'badge-red' };
    return map[status] || 'badge-muted';
  }

  function statusLabel(status) {
    const map = { nominal: 'Nominal', watch: 'Watch', alert: 'Alert / Exceeded' };
    return map[status] || status;
  }

  function trajectoryIcon(spi) {
    const trend = (spi.trend || spi.trajectory || '').toLowerCase();
    if (trend === 'up' || trend === 'increasing')
      return '<i class="fa-solid fa-arrow-trend-up" style="color:#dc3545;" title="Increasing"></i>';
    if (trend === 'down' || trend === 'decreasing')
      return '<i class="fa-solid fa-arrow-trend-down" style="color:#28a745;" title="Decreasing"></i>';
    return '<i class="fa-solid fa-minus" style="color:#6c757d;" title="Stable"></i>';
  }

  // ── KPI Cards ──────────────────────────────────────────────────────────────

  function updateKpiCards(indicators) {
    const total   = indicators.length;
    const nominal = indicators.filter(s => getStatus(s) === 'nominal').length;
    const alert   = indicators.filter(s => getStatus(s) === 'alert').length;
    const watch   = indicators.filter(s => getStatus(s) === 'watch').length;

    setText('spisActiveCount', total);
    setText('spisNominalCount', nominal);
    setText('spisAlertCount', alert);
    setText('spisWatchCount', watch);
  }

  function setText(id, val) {
    const el_ = el(id);
    if (el_) el_.textContent = val;
  }

  // ── Master Table ───────────────────────────────────────────────────────────

  function renderTable(indicators) {
    const tbody = el('spisTableBody');
    if (!tbody) return;

    const filtered = applyFilters(indicators);

    if (filtered.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" class="text-muted" style="text-align:center;padding:1.5rem;">No indicators match the current filters.</td></tr>';
      return;
    }

    tbody.innerHTML = filtered.map(spi => {
      const status   = getStatus(spi);
      const code     = spi.code || spi.id || '—';
      const name     = spi.name || spi.title || '—';
      const domain   = spi.domain || spi.category || '—';
      const target   = spi.spt_target ?? spi.target_threshold ?? '—';
      const alert    = spi.alert_threshold ?? '—';
      const current  = spi.current_value ?? spi.value ?? '—';
      const traj     = trajectoryIcon(spi);

      return `
        <tr>
          <td><strong>${code}</strong></td>
          <td>${name}</td>
          <td>${domain}</td>
          <td><code>${target}</code></td>
          <td><code>${alert}</code></td>
          <td><code>${current}</code></td>
          <td style="text-align:center;">${traj}</td>
          <td><span class="badge ${statusBadgeClass(status)}">${statusLabel(status)}</span></td>
        </tr>`;
    }).join('');
  }

  // ── Filters ────────────────────────────────────────────────────────────────

  function applyFilters(indicators) {
    return indicators.filter(spi => {
      // Status filter
      if (activeStatusFilter !== 'all' && getStatus(spi) !== activeStatusFilter) return false;
      // Domain filter
      if (activeDomainFilter !== 'all') {
        const domain = (spi.domain || spi.category || '').toLowerCase();
        if (domain !== activeDomainFilter) return false;
      }
      // Search filter
      if (searchQuery) {
        const name = (spi.name || spi.title || '').toLowerCase();
        const code = (spi.code || spi.id || '').toLowerCase();
        if (!name.includes(searchQuery) && !code.includes(searchQuery)) return false;
      }
      return true;
    });
  }

  // ── Data Fetch → GET /safety-performance/indicators ────────────────────────

  async function loadIndicators() {
    const tbody = el('spisTableBody');
    if (!tbody) return;

    try {
      tbody.innerHTML = '<tr><td colspan="8" class="text-muted" style="text-align:center;padding:1.5rem;"><i class="fa-solid fa-spinner fa-spin"></i> Loading indicators…</td></tr>';

      const data = await AviaSDCPSApi.get('/safety-performance/indicators');
      allIndicators = data.indicators || data.items || data || [];

      updateKpiCards(allIndicators);
      renderTable(allIndicators);
    } catch (err) {
      console.error('[AviaSDCPSSpis] Failed to load indicators:', err);
      tbody.innerHTML = `<tr><td colspan="8" class="text-danger" style="text-align:center;padding:1.5rem;">Error loading indicators: ${err.message}</td></tr>`;
    }
  }

  // ── Event Bindings ─────────────────────────────────────────────────────────

  function bindEvents() {
    // Status filter buttons
    document.querySelectorAll('.spis-filter-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('.spis-filter-btn').forEach(b => b.classList.remove('active'));
        e.currentTarget.classList.add('active');
        activeStatusFilter = e.currentTarget.getAttribute('data-filter');
        renderTable(allIndicators);
      });
    });

    // Domain filter
    el('spisDomainFilter')?.addEventListener('change', (e) => {
      activeDomainFilter = e.target.value;
      renderTable(allIndicators);
    });

    // Search
    el('spisSearchInput')?.addEventListener('input', (e) => {
      searchQuery = e.target.value.toLowerCase();
      renderTable(allIndicators);
    });
  }

  return {
    init() {
      allIndicators = [];
      activeStatusFilter = 'all';
      activeDomainFilter = 'all';
      searchQuery = '';
      bindEvents();
      loadIndicators();
    }
  };
})();

window.AviaSDCPSSpis = AviaSDCPSSpis;
