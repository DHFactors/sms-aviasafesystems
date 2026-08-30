/**
 * @module AviaSAFE aviaSDCPS
 * @file public/js/views/home.js
 * @version 1.0.0-beta.1 (2026-08-25)
 * @target sms-db / consolidated platform
 */

const AviaSDCPSHome = (function () {
  'use strict';

  let chartTaxonomy = null;
  let chartOccurrence = null;

  /**
   * Fetches KPI summary data and binds to DOM elements.
   */
  async function loadKpiMetrics(days = 'all') {
    try {
      const stats = await window.AviaSDCPSApi.get('/hazards/stats', { days });
      
      document.getElementById('kpiTotalHazards').textContent = stats.total ?? 0;
      document.getElementById('kpiPriorityHigh').textContent = stats.by_priority?.H ?? 0;
      document.getElementById('kpiPriorityMed').textContent = stats.by_priority?.M ?? 0;
      document.getElementById('kpiPriorityLow').textContent = stats.by_priority?.L ?? 0;

      document.getElementById('kpiStatusPending').textContent = stats.by_status?.Pending ?? 0;
      document.getElementById('kpiStatusOpen').textContent = stats.by_status?.Open ?? 0;
      document.getElementById('kpiStatusClosed').textContent = stats.by_status?.Closed ?? 0;
    } catch (err) {
      console.error('[AviaSDCPSHome] Failed to load KPI stats:', err);
    }
  }

  /**
   * Fetches categorical insight data and binds top-3 chips.
   */
  async function loadTopInsights(days = 'all') {
    try {
      const data = await window.AviaSDCPSApi.get('/dashboard/overview', { days });
      
      renderInsightList('insightTopTaxonomy', data.top_taxonomies);
      renderInsightList('insightTopTypes', data.top_types);
      renderInsightList('insightTopSources', data.top_sources);
      
      const maxMonthEl = document.getElementById('insightMaxMonth');
      if (maxMonthEl) {
        maxMonthEl.textContent = data.peak_month ? `${data.peak_month.name} (${data.peak_month.count})` : 'No data';
      }
    } catch (err) {
      console.error('[AviaSDCPSHome] Failed to load top insights:', err);
    }
  }

  function renderInsightList(containerId, items) {
    const el = document.getElementById(containerId);
    if (!el) return;
    if (!items || items.length === 0) {
      el.innerHTML = '<span class="no-data">No data</span>';
      return;
    }
    el.innerHTML = items
      .map(item => `<div class="insight-row"><span>${item.name}</span><strong>${item.count}</strong></div>`)
      .join('');
  }

  /**
   * Initializes and populates Chart.js analytics instances.
   */
  async function loadCharts(days = 'all') {
    try {
      const riskData = await window.AviaSDCPSApi.get('/dashboard/risk', { days });
      
      const ctxTaxonomy = document.getElementById('chartTaxonomyVsPriority')?.getContext('2d');
      const ctxOccurrence = document.getElementById('chartOccurrenceVsPriority')?.getContext('2d');

      if (chartTaxonomy) chartTaxonomy.destroy();
      if (chartOccurrence) chartOccurrence.destroy();

      if (ctxTaxonomy) {
        chartTaxonomy = new Chart(ctxTaxonomy, {
          type: 'bar',
          data: {
            labels: riskData.taxonomy_labels || ['Flight Ops', 'Maintenance', 'Airside'],
            datasets: [
              { label: 'High', data: riskData.tax_high || [0, 0, 0], backgroundColor: '#de350b' },
              { label: 'Med', data: riskData.tax_med || [0, 0, 0], backgroundColor: '#ff8b00' },
              { label: 'Low', data: riskData.tax_low || [0, 0, 0], backgroundColor: '#00875a' }
            ]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } }
          }
        });
      }

      if (ctxOccurrence) {
        chartOccurrence = new Chart(ctxOccurrence, {
          type: 'bar',
          data: {
            labels: riskData.occ_labels || ['Mandatory (MOR)', 'Voluntary (VSR)'],
            datasets: [
              { label: 'High', data: riskData.occ_high || [0, 0], backgroundColor: '#de350b' },
              { label: 'Med', data: riskData.occ_med || [0, 0], backgroundColor: '#ff8b00' },
              { label: 'Low', data: riskData.occ_low || [0, 0], backgroundColor: '#00875a' }
            ]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } }
          }
        });
      }
    } catch (err) {
      console.error('[AviaSDCPSHome] Failed to load charts:', err);
    }
  }

  function bindEvents() {
    const subTabs = document.querySelectorAll('#homeSubTabs .tab-btn');
    subTabs.forEach(btn => {
      btn.addEventListener('click', (e) => {
        subTabs.forEach(b => b.classList.remove('active'));
        e.currentTarget.classList.add('active');
        const tab = e.currentTarget.getAttribute('data-tab');
        if (tab === 'hazard') loadKpiMetrics();
        // Additional sub-tab switches can trigger corresponding views or aggregations
      });
    });
  }

  return {
    init() {
      bindEvents();
      loadKpiMetrics();
      loadTopInsights();
      loadCharts();
    }
  };
})();

window.AviaSDCPSHome = AviaSDCPSHome;
