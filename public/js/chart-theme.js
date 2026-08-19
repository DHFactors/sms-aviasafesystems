/* ============================================================================
   FILE: chart-theme.js
   PATH: public/js/chart-theme.js
   PURPOSE: ICAO Clean Light chart theming. Forces Chart.js grid lines to
            #E2E8F0 and axis/label text to #475569 regardless of inline chart
            options, so every chart matches the locked light design system.
   LOAD AFTER: chart.js (chart.umd.min.js). No-op when Chart is unavailable.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

(function () {
    if (typeof Chart === 'undefined' || !Chart.defaults) return;

    if (Chart.defaults.scale) {
        if (Chart.defaults.scale.grid) {
            Chart.defaults.scale.grid.color = '#E2E8F0';
        }
        if (Chart.defaults.scale.ticks) {
            Chart.defaults.scale.ticks.color = '#475569';
        }
    }
    Chart.defaults.color = '#475569';
    if (Chart.defaults.font && !Chart.defaults.font.family) {
        Chart.defaults.font.family = "'Inter', 'Segoe UI', sans-serif";
    }
})();
