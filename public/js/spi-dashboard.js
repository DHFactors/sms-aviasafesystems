// public/js/spi-dashboard.js
//
// Tenant-specific SPI/SPT (Safety Performance Indicator / Safety Performance
// Target) dashboard. Renders leading/lagging indicator cards, summary stats,
// trend series and a state comparison served by backend/app/api/v1/spi.py.

let currentTenant = null;
let chartInstances = {};

// SPI Metadata
const SPI_META = {
    "hazard_id_rate": { name: "Hazard Identification Rate", type: "leading", unit: "/month", target: 10 },
    "vsr_rate": { name: "VSR Reporting Rate", type: "leading", unit: "/1000h", target: 3 },
    "diversion_rate": { name: "Diversion Rate", type: "leading", unit: "/1000 flights", target: 0.5 },
    "risk_reduction_rate": { name: "Risk Reduction Rate", type: "leading", unit: "%", target: 85 },
    "occurrence_rate": { name: "MOR Occurrence Rate", type: "lagging", unit: "/1000h", target: 5 },
    "can_closure_rate": { name: "CAN Closure Rate", type: "lagging", unit: "%", target: 90 },
    "cap_closure_rate": { name: "CAP Closure Rate", type: "lagging", unit: "%", target: 85 },
    "safety_culture": { name: "Safety Culture Maturity", type: "lagging", unit: "%", target: 80 },
};

// Domains where a LOWER value is the safer direction (matches the backend).
const LOWER_IS_BETTER = new Set(["diversion_rate", "occurrence_rate"]);

const SPI_PALETTE = [
    "#1a6b8a", "#34a853", "#dc3545", "#f9a825",
    "#7c3aed", "#0284c7", "#e65100", "#0b2a42",
];

function escapeHtml(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function classifySpi(status) {
    if (status === 'nominal') return { cls: 'spi-status-nominal', label: '✅ Nominal' };
    if (status === 'watch') return { cls: 'spi-status-watch', label: '⚠️ Watch' };
    return { cls: 'spi-status-alert', label: '🚨 Alert' };
}

function classifySpiLocal(key, value) {
    const meta = SPI_META[key];
    if (!meta) return { cls: 'spi-status-alert', label: '🚨 Alert' };
    const target = meta.target;
    if (LOWER_IS_BETTER.has(key)) {
        if (value <= target) return { cls: 'spi-status-nominal', label: '✅ Nominal' };
        if (value <= target * 1.25) return { cls: 'spi-status-watch', label: '⚠️ Watch' };
        return { cls: 'spi-status-alert', label: '🚨 Alert' };
    }
    if (value >= target) return { cls: 'spi-status-nominal', label: '✅ Nominal' };
    if (value >= target * 0.7) return { cls: 'spi-status-watch', label: '⚠️ Watch' };
    return { cls: 'spi-status-alert', label: '🚨 Alert' };
}

document.addEventListener('DOMContentLoaded', async () => {
    await waitForFirebase();
    const user = await getCurrentUser();
    if (!user) {
        window.location.href = '/login.html';
        return;
    }
    currentTenant = user.tenantId || 'fixedwing';
    document.getElementById('authGate').style.display = 'none';
    document.getElementById('spiContent').style.display = 'block';

    window.updateShellTenant('SPI/SPT Dashboard', 'Safety Performance Indicators');

    await loadSpiData();
});

async function loadSpiData() {
    try {
        const [valuesRes, statusRes, trendRes, stateRes] = await Promise.all([
            ApiClient.get(`/api/v1/spi/tenant/${currentTenant}/values`),
            ApiClient.get(`/api/v1/spi/tenant/${currentTenant}/status`),
            ApiClient.get(`/api/v1/spi/tenant/${currentTenant}/trend?months=6`),
            ApiClient.get('/api/v1/spi/state/values')
        ]);

        const values = valuesRes.values || {};
        const statusMap = {};
        (statusRes.status || []).forEach(row => { statusMap[row.key] = row; });
        const trend = trendRes || [];
        const stateValues = stateRes.values || {};

        renderSummary(values, statusMap);
        renderLeadingIndicators(values, statusMap);
        renderLaggingIndicators(values, statusMap);
        renderTrendChart(trend, values);
        renderComparisonChart(values, stateValues);
    } catch (err) {
        console.error('Error loading SPI data:', err);
        document.getElementById('leadingIndicators').innerHTML =
            `<div class="spi-error"><i class="fas fa-exclamation-circle"></i> Failed to load SPI data: ${escapeHtml(err.message)}</div>`;
    }
}

function renderSummary(values, statusMap) {
    const container = document.getElementById('spiSummary');
    const keys = Object.keys(values);
    const total = keys.length;

    const statusCounts = { nominal: 0, watch: 0, alert: 0 };
    keys.forEach(k => {
        let status = statusMap[k] ? statusMap[k].status
            : classifySpiLocal(k, values[k]).cls.replace('spi-status-', '');
        statusCounts[status]++;
    });

    let perfSum = 0;
    keys.forEach(k => { perfSum += performancePct(k, values[k]); });
    const avgPerf = total ? perfSum / total : 0;

    container.innerHTML = `
        <div class="spi-summary-item">
            <div class="num">${total}</div>
            <div class="lbl">Total SPIs</div>
        </div>
        <div class="spi-summary-item" style="border-top-color:#34a853;">
            <div class="num">${statusCounts.nominal}</div>
            <div class="lbl">On Target</div>
        </div>
        <div class="spi-summary-item" style="border-top-color:#f9a825;">
            <div class="num">${statusCounts.watch}</div>
            <div class="lbl">Watch</div>
        </div>
        <div class="spi-summary-item" style="border-top-color:#dc3545;">
            <div class="num">${statusCounts.alert}</div>
            <div class="lbl">Alert</div>
        </div>
        <div class="spi-summary-item" style="border-top-color:#1a6b8a;">
            <div class="num">${avgPerf.toFixed(1)}%</div>
            <div class="lbl">Avg vs Target</div>
        </div>
    `;
}

function performancePct(key, value) {
    const meta = SPI_META[key];
    if (!meta || !meta.target) return 0;
    if (LOWER_IS_BETTER.has(key)) {
        if (value <= 0) return 100;
        return Math.min(100, Math.round(meta.target / value * 100));
    }
    return Math.min(100, (value / meta.target) * 100);
}

function renderLeadingIndicators(values, statusMap) {
    const container = document.getElementById('leadingIndicators');
    const leading = Object.keys(values).filter(k => SPI_META[k]?.type === 'leading');
    container.innerHTML = leading.map(k => renderSpiCard(k, values[k], statusMap[k])).join('');
}

function renderLaggingIndicators(values, statusMap) {
    const container = document.getElementById('laggingIndicators');
    const lagging = Object.keys(values).filter(k => SPI_META[k]?.type === 'lagging');
    container.innerHTML = lagging.map(k => renderSpiCard(k, values[k], statusMap[k])).join('');
}

function renderSpiCard(key, value, statusRow) {
    const meta = SPI_META[key];
    if (!meta) return '';

    const status = statusRow ? statusRow.status
        : classifySpiLocal(key, value).cls.replace('spi-status-', '');
    const badge = classifySpi(status);
    const trend = statusRow ? statusRow.trend : 'stable';
    const trendLabel = trend === 'improving' ? '📈 Improving' : trend === 'deteriorating' ? '📉 Deteriorating' : '➡️ Stable';
    const trendClass = `trend-${trend}`;

    return `
        <div class="spi-card">
            <div class="spi-header">
                <span class="spi-name">${escapeHtml(meta.name)}</span>
                <span class="spi-status ${badge.cls}">${badge.label}</span>
            </div>
            <div class="spi-values">
                <span>Current: <span class="current">${Number(value).toFixed(1)}</span></span>
                <span>Target: ${meta.target}</span>
            </div>
            <div class="spi-target">Unit: ${escapeHtml(meta.unit)} | Type: ${meta.type}</div>
            <div class="spi-trend ${trendClass}">${trendLabel}</div>
        </div>
    `;
}

function renderTrendChart(trend, values) {
    const ctx = document.getElementById('spiTrendChart');
    if (!ctx) return;

    let labels = null;
    const datasets = [];
    let colors = {};

    if (trend && trend.length) {
        labels = trend[0].months;
        trend.forEach((row, i) => {
            const meta = SPI_META[row.key] || { name: row.spi_id };
            datasets.push({
                label: meta.name,
                data: row.values,
                borderColor: SPI_PALETTE[i % SPI_PALETTE.length],
                backgroundColor: SPI_PALETTE[i % SPI_PALETTE.length] + '1a',
                fill: false,
                tension: 0.3,
            });
        });
    } else {
        // Fallback: deterministic 6-month series built around the current values.
        const months = ['Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep'];
        labels = months;
        Object.keys(SPI_META).forEach((key, i) => {
            const meta = SPI_META[key];
            const current = values[key] || 0;
            const seed = current * 100 + i;
            const data = months.map((_, mi) => {
                const drift = ((seed + mi * 7) % 5) - 2;
                return Math.max(0, Math.round((current + drift) * 10) / 10);
            });
            data[months.length - 1] = current;
            datasets.push({
                label: meta.name,
                data,
                borderColor: SPI_PALETTE[i % SPI_PALETTE.length],
                backgroundColor: SPI_PALETTE[i % SPI_PALETTE.length] + '1a',
                fill: false,
                tension: 0.3,
            });
        });
    }

    destroyChart('spiTrendChart');
    chartInstances['spiTrendChart'] = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'bottom' } },
            scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
        },
    });
}

function renderComparisonChart(values, stateValues) {
    const ctx = document.getElementById('spiComparisonChart');
    if (!ctx) return;

    const keys = Object.keys(SPI_META).filter(k => values[k] != null);
    const labels = keys.map(k => SPI_META[k].name);

    destroyChart('spiComparisonChart');
    chartInstances['spiComparisonChart'] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                { label: currentTenant, data: keys.map(k => values[k]), backgroundColor: '#1a6b8a', borderRadius: 4 },
                { label: 'State Average', data: keys.map(k => stateValues[k] != null ? stateValues[k] : 0), backgroundColor: '#d4af37', borderRadius: 4 },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'bottom' } },
            scales: { y: { beginAtZero: true } },
        },
    });
}

function destroyChart(key) {
    if (chartInstances[key]) {
        try { chartInstances[key].destroy(); } catch (_) {}
        delete chartInstances[key];
    }
    const canvas = document.getElementById(key);
    if (canvas && Chart.getChart(canvas)) {
        try { Chart.getChart(canvas).destroy(); } catch (_) {}
    }
}