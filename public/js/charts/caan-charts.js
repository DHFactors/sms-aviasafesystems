/* ============================================================================
   FILE: caan-charts.js
   PATH: public/js/charts/caan-charts.js
   VERSION: 1.0.0
   PURPOSE: CaanChartFactory — Chart.js factory for CAAN SSP oversight visualizations:
            HRC doughnut, SPI control chart with sigma bands, operator risk scatter,
            and domain compliance bar chart.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

const CaanChartFactory = (function () {
  'use strict';

  const COLORS = {
    primary: '#002f6c',
    accent: '#34a853',
    danger: '#dc2626',
    warning: '#f59e0b',
    info: '#3b82f6',
    muted: '#94a3b8',
    bg: ['#002f6c', '#34a853', '#dc2626', '#f59e0b', '#8b5cf6', '#06b6d4', '#ec4899', '#64748b'],
  };

  function _destroyIfCanvas(canvasId) {
    const existing = Chart.getChart(canvasId);
    if (existing) existing.destroy();
  }

  /**
   * HRC doughnut — proportional breakdown of High Risk Category counts.
   */
  function createHrcDoughnut(canvasId, hrcData) {
    _destroyIfCanvas(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const labels = hrcData.map(d => d.category || d.icoc_category || 'Unknown');
    const counts = hrcData.map(d => d.count || 0);

    return new Chart(canvas, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data: counts,
          backgroundColor: COLORS.bg.slice(0, labels.length),
          borderWidth: 2,
          borderColor: '#ffffff',
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'right', labels: { font: { size: 11 } } },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                const pct = total ? ((ctx.parsed / total) * 100).toFixed(1) : 0;
                return `${ctx.label}: ${ctx.parsed} (${pct}%)`;
              },
            },
          },
        },
      },
    });
  }

  /**
   * SPI control chart — line chart with 1-Sigma and 2-Sigma shaded bands.
   */
  function createSpiControlChart(canvasId, spiData) {
    _destroyIfCanvas(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const labels = spiData.map(d => d.name || d.domain);
    const values = spiData.map(d => d.current_value ?? 0);
    const targets = spiData.map(d => d.target_value ?? 0);

    const mean = values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0;
    const stdDev = values.length > 1
      ? Math.sqrt(values.reduce((s, v) => s + (v - mean) ** 2, 0) / (values.length - 1))
      : 0;

    return new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: '2-Sigma Upper',
            data: values.map(() => mean + 2 * stdDev),
            borderColor: 'rgba(220,38,38,0.3)',
            backgroundColor: 'rgba(220,38,38,0.06)',
            fill: '+1',
            borderDash: [4, 4],
            pointRadius: 0,
          },
          {
            label: '1-Sigma Upper',
            data: values.map(() => mean + stdDev),
            borderColor: 'rgba(245,158,11,0.3)',
            backgroundColor: 'rgba(245,158,11,0.06)',
            fill: '+1',
            borderDash: [4, 4],
            pointRadius: 0,
          },
          {
            label: 'Current Value',
            data: values,
            borderColor: COLORS.primary,
            backgroundColor: COLORS.primary,
            pointRadius: 4,
            pointHoverRadius: 6,
            borderWidth: 2,
            tension: 0.3,
            fill: false,
          },
          {
            label: 'Target',
            data: targets,
            borderColor: COLORS.accent,
            borderDash: [6, 3],
            pointRadius: 3,
            borderWidth: 1.5,
            fill: false,
          },
        ],
      },
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

  /**
   * Operator risk scatter — bubble chart mapping operators by risk index vs compliance.
   */
  function createOperatorRiskScatter(canvasId, operatorData) {
    _destroyIfCanvas(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const points = operatorData.map(op => ({
      x: op.risk_index ?? 0,
      y: op.compliance_score ?? 0,
      r: Math.max(4, Math.min(20, (op.total_hazards || 1) * 1.5)),
    }));

    const labels = operatorData.map(op => op.operator_name || op.tenant_id);

    return new Chart(canvas, {
      type: 'bubble',
      data: {
        datasets: [{
          label: 'Operators',
          data: points,
          backgroundColor: COLORS.bg[0] + '99',
          borderColor: COLORS.primary,
          borderWidth: 1,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                const op = operatorData[ctx.dataIndex] || {};
                return [
                  op.operator_name || op.tenant_id || 'Unknown',
                  `Risk: ${op.risk_index ?? 'N/A'}`,
                  `Compliance: ${op.compliance_score ?? 0}%`,
                  `Hazards: ${op.total_hazards ?? 0}`,
                ];
              },
            },
          },
        },
        scales: {
          x: {
            title: { display: true, text: 'Risk Index', font: { size: 11 } },
            grid: { color: '#f1f5f9' },
          },
          y: {
            title: { display: true, text: 'Compliance Score %', font: { size: 11 } },
            grid: { color: '#f1f5f9' },
            min: 0,
            max: 100,
          },
        },
      },
    });
  }

  /**
   * Domain compliance bar — grouped bar chart per SPI domain.
   */
  function createDomainComplianceBar(canvasId, spiData) {
    _destroyIfCanvas(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const labels = spiData.map(d => d.domain || d.name);
    const current = spiData.map(d => d.current_value ?? 0);
    const targets = spiData.map(d => d.target_value ?? 0);

    return new Chart(canvas, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: 'Current',
            data: current,
            backgroundColor: COLORS.primary,
            borderRadius: 3,
          },
          {
            label: 'Target',
            data: targets,
            backgroundColor: COLORS.accent + '66',
            borderRadius: 3,
          },
        ],
      },
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
    createHrcDoughnut,
    createSpiControlChart,
    createOperatorRiskScatter,
    createDomainComplianceBar,
  };
})();

window.CaanChartFactory = CaanChartFactory;
