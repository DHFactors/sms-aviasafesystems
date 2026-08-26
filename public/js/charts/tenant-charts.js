/* ============================================================================
   FILE: tenant-charts.js
   PATH: public/js/charts/tenant-charts.js
   VERSION: 1.0.0
   PURPOSE: TenantChartFactory — Chart.js factory for tenant-level visualizations:
            5x5 risk matrix heatmap, SPI trend line with warning triggers.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

const TenantChartFactory = (function () {
  'use strict';

  const TOLERABILITY_COLORS = {
    ACCEPTABLE: '#22c55e',
    TOLERABLE_WITH_MITIGATION: '#f59e0b',
    INTOLERABLE: '#dc2626',
  };

  function _destroyIfCanvas(canvasId) {
    const existing = Chart.getChart(canvasId);
    if (existing) existing.destroy();
  }

  /**
   * 5x5 Risk Matrix scatter — plots active hazards by Severity (x) vs Likelihood (y).
   * Each point's radius reflects hazard count at that cell.
   */
  function createTenantRiskMatrixChart(canvasId, heatmapData) {
    _destroyIfCanvas(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const SEV_MAP = {
      '1_NEGLIGIBLE': 1, '2_MINOR': 2, '3_MAJOR': 3,
      '4_HAZARDOUS': 4, '5_CATASTROPHIC': 5,
    };
    const LIKE_MAP = {
      'E_EXTREMELY_IMPROBABLE': 1, 'D_IMPROBABLE': 2, 'C_REMOTE': 3,
      'B_OCCASIONAL': 4, 'A_FREQUENT': 5,
    };

    const points = heatmapData.map(cell => ({
      x: SEV_MAP[cell.severity] || 0,
      y: LIKE_MAP[cell.likelihood] || 0,
      r: Math.max(5, Math.min(25, (cell.hazard_count || 0) * 3)),
      tolerability: cell.tolerability || 'ACCEPTABLE',
      count: cell.hazard_count || 0,
    }));

    return new Chart(canvas, {
      type: 'bubble',
      data: {
        datasets: [
          {
            label: 'Intolerable',
            data: points.filter(p => p.tolerability === 'INTOLERABLE'),
            backgroundColor: TOLERABILITY_COLORS.INTOLERABLE + 'cc',
            borderColor: TOLERABILITY_COLORS.INTOLERABLE,
            borderWidth: 1,
          },
          {
            label: 'Tolerable',
            data: points.filter(p => p.tolerability === 'TOLERABLE_WITH_MITIGATION'),
            backgroundColor: TOLERABILITY_COLORS.TOLERABLE_WITH_MITIGATION + 'cc',
            borderColor: TOLERABILITY_COLORS.TOLERABLE_WITH_MITIGATION,
            borderWidth: 1,
          },
          {
            label: 'Acceptable',
            data: points.filter(p => p.tolerability === 'ACCEPTABLE'),
            backgroundColor: TOLERABILITY_COLORS.ACCEPTABLE + 'cc',
            borderColor: TOLERABILITY_COLORS.ACCEPTABLE,
            borderWidth: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'top', labels: { font: { size: 10 }, boxWidth: 12 } },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                const p = ctx.raw;
                return `Severity ${p.x}, Likelihood ${p.y}: ${p.count} hazard(s) [${p.tolerability}]`;
              },
            },
          },
        },
        scales: {
          x: {
            title: { display: true, text: 'Severity', font: { size: 11 } },
            min: 0.5, max: 5.5,
            ticks: {
              stepSize: 1,
              callback: function (val) {
                return ['', 'Negligible', 'Minor', 'Major', 'Hazardous', 'Catastrophic'][val] || '';
              },
              font: { size: 9 },
            },
            grid: { color: '#f1f5f9' },
          },
          y: {
            title: { display: true, text: 'Likelihood', font: { size: 11 } },
            min: 0.5, max: 5.5,
            ticks: {
              stepSize: 1,
              callback: function (val) {
                return ['', 'Ext. Improbable', 'Improbable', 'Remote', 'Occasional', 'Frequent'][val] || '';
              },
              font: { size: 9 },
            },
            grid: { color: '#f1f5f9' },
          },
        },
      },
    });
  }

  /**
   * SPI Trend Line — tracks operational SPIs over time with warning threshold bands.
   */
  function createTenantSpiTrendChart(canvasId, spiData, historyData) {
    _destroyIfCanvas(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const labels = (historyData || []).map(h => h.period || h.label || '');
    const values = (historyData || []).map(h => h.value ?? 0);
    const targets = (historyData || []).map(h => h.target ?? 0);
    const warnings = (historyData || []).map(h => h.warning_threshold ?? null);

    const datasets = [
      {
        label: spiData.name || 'SPI Value',
        data: values,
        borderColor: '#002f6c',
        backgroundColor: '#002f6c',
        pointRadius: 4,
        pointHoverRadius: 6,
        borderWidth: 2,
        tension: 0.3,
        fill: false,
      },
      {
        label: 'Target',
        data: targets,
        borderColor: '#22c55e',
        borderDash: [6, 3],
        pointRadius: 2,
        borderWidth: 1.5,
        fill: false,
      },
    ];

    if (warnings.some(w => w !== null)) {
      datasets.push({
        label: 'Warning Threshold',
        data: warnings,
        borderColor: '#dc2626',
        borderDash: [4, 4],
        pointRadius: 0,
        borderWidth: 1.5,
        fill: false,
      });
    }

    return new Chart(canvas, {
      type: 'line',
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'top', labels: { font: { size: 10 }, boxWidth: 12 } },
        },
        scales: {
          y: {
            beginAtZero: true,
            grid: { color: '#f1f5f9' },
            ticks: { font: { size: 10 } },
          },
          x: {
            grid: { display: false },
            ticks: { font: { size: 10 }, maxRotation: 45 },
          },
        },
      },
    });
  }

  return {
    createTenantRiskMatrixChart,
    createTenantSpiTrendChart,
  };
})();

window.TenantChartFactory = TenantChartFactory;
