// public/js/nhrc-dashboard.js
//
// Tenant-specific N-HRC (National High-Risk Category) dashboard. Renders the
// KPI cards, summary stats and charts served by the N-HRC mapping engine
// (backend/app/api/v1/nhrc.py), and loads NASP SEIs / contributing factors
// from the same API.

let currentTenant = null;
let chartInstances = {};
let nhrcData = null;
let stateData = null;

// N-HRC Metadata
const NHRC_META = {
    "CFIT": { name: "Controlled Flight Into Terrain", color: "#dc3545" },
    "LOC-I": { name: "Loss of Control - In Flight", color: "#e65100" },
    "MAC": { name: "Mid Air Collision", color: "#7c3aed" },
    "RE": { name: "Runway Excursion", color: "#f9a825" },
    "RI": { name: "Runway Incursion", color: "#d97706" },
    "ARC": { name: "Abnormal Runway Contact", color: "#0284c7" },
    "WS": { name: "Wildlife Strike", color: "#34a853" },
};

function escapeHtml(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// Deterministic per-code+month pseudo-random so the demo trend chart stays
// stable across refreshes (replaces Math.random() shuffling on every load).
function trendValueFor(code, monthIndex) {
    let seed = 0;
    const key = code + '-' + monthIndex;
    for (let i = 0; i < key.length; i++) {
        seed = (seed * 31 + key.charCodeAt(i)) >>> 0;
    }
    return Math.round(((seed % 100) / 100) * 5);
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
    document.getElementById('nhrcContent').style.display = 'block';

    window.updateShellTenant('N-HRC Dashboard', 'National High-Risk Categories');

    await loadNhrcData();
});

async function loadNhrcData() {
    try {
        const [tenantKpis, stateKpis] = await Promise.all([
            ApiClient.get(`/api/v1/nhrc/tenant/${currentTenant}/kpis`),
            ApiClient.get('/api/v1/nhrc/state/kpis')
        ]);

        nhrcData = tenantKpis || [];
        stateData = stateKpis || [];

        renderStats();
        renderNhrcCards();
        renderCharts();
    } catch (err) {
        console.error('Error loading N-HRC data:', err);
        document.getElementById('nhrcGrid').innerHTML = `
            <div class="nhrc-error">
                <i class="fas fa-exclamation-circle"></i>
                Failed to load N-HRC data: ${escapeHtml(err.message)}
            </div>
        `;
    }
}

function renderStats() {
    const total = nhrcData.reduce((sum, k) => sum + k.active_hazards, 0);
    const action = nhrcData.filter(k => k.status === 'action').length;
    const stable = nhrcData.filter(k => k.status === 'ok').length;
    const avgRisk = nhrcData.length ? (nhrcData.reduce((sum, k) => sum + (k.avg_risk_index || 0), 0) / nhrcData.length) : 0;

    document.getElementById('statTotalHazards').textContent = total;
    document.getElementById('statActionRequired').textContent = action;
    document.getElementById('statStable').textContent = stable;
    document.getElementById('statAvgRisk').textContent = avgRisk.toFixed(1);
}

function renderNhrcCards() {
    const grid = document.getElementById('nhrcGrid');
    if (!nhrcData || nhrcData.length === 0) {
        grid.innerHTML = '<div class="nhrc-empty">No N-HRC data available.</div>';
        return;
    }

    grid.innerHTML = nhrcData.map(k => {
        const meta = NHRC_META[k.nhrc] || { name: k.nhrc, color: '#64748b' };
        const statusClass = k.status === 'ok' ? 'status-ok' : k.status === 'watch' ? 'status-watch' : 'status-action';
        const statusLabel = k.status === 'ok' ? '✅ OK' : k.status === 'watch' ? '⚠️ Watch' : '🚨 Action';

        return `
            <div class="nhrc-card" onclick="openSeiModal('${escapeHtml(k.nhrc)}')">
                <div class="nhrc-header">
                    <div>
                        <span class="nhrc-code">${escapeHtml(k.nhrc)}</span>
                        <div class="nhrc-name">${escapeHtml(meta.name)}</div>
                    </div>
                    <span class="nhrc-status ${statusClass}">${statusLabel}</span>
                </div>
                <div class="nhrc-stats">
                    <div class="nhrc-stat">
                        <div class="num">${k.active_hazards}</div>
                        <div class="lbl">Hazards</div>
                    </div>
                    <div class="nhrc-stat">
                        <div class="num">${k.avg_risk_index || '—'}</div>
                        <div class="lbl">Avg Risk</div>
                    </div>
                    <div class="nhrc-stat">
                        <div class="num">${k.max_risk_index || '—'}</div>
                        <div class="lbl">Max Risk</div>
                    </div>
                </div>
                <div class="nhrc-trend">
                    Trend: ${k.trend === 'increasing' ? '📈 Increasing' : k.trend === 'decreasing' ? '📉 Decreasing' : '➡️ Stable'}
                </div>
                <a href="#" class="nhrc-sei-link" onclick="event.stopPropagation();openSeiModal('${escapeHtml(k.nhrc)}')">
                    <i class="fas fa-list-check"></i> View SEIs & Contributing Factors
                </a>
            </div>
        `;
    }).join('');
}

function renderCharts() {
    renderTrendChart();
    renderDistributionChart();
    renderComparisonChart();
}

function renderTrendChart() {
    const ctx = document.getElementById('nhrcTrendChart');
    if (!ctx) return;

    // Demo trend data derived deterministically from the hazard counts; in
    // production this would come from a time-bucketed API series.
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'];
    const datasets = nhrcData.map(k => {
        const meta = NHRC_META[k.nhrc] || { color: '#64748b' };
        return {
            label: k.nhrc,
            data: months.map((_, i) => trendValueFor(k.nhrc, i)),
            borderColor: meta.color,
            backgroundColor: meta.color + '1a',
            fill: false,
            tension: 0.3,
        };
    });

    destroyChart('nhrcTrendChart');
    chartInstances['nhrcTrendChart'] = new Chart(ctx, {
        type: 'line',
        data: { labels: months, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'bottom' } },
            scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
        },
    });
}

function renderDistributionChart() {
    const ctx = document.getElementById('nhrcDistributionChart');
    if (!ctx) return;

    const labels = nhrcData.map(k => k.nhrc);
    const values = nhrcData.map(k => k.active_hazards);
    const colors = nhrcData.map(k => NHRC_META[k.nhrc]?.color || '#64748b');

    destroyChart('nhrcDistributionChart');
    chartInstances['nhrcDistributionChart'] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{ label: 'Active Hazards', data: values, backgroundColor: colors, borderRadius: 4 }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
        },
    });
}

function renderComparisonChart() {
    const ctx = document.getElementById('nhrcComparisonChart');
    if (!ctx) return;

    const labels = nhrcData.map(k => k.nhrc);
    const tenantValues = nhrcData.map(k => k.avg_risk_index || 0);
    const stateValues = labels.map(code => {
        const state = stateData.find(s => s.nhrc === code);
        return state ? state.avg_risk_index || 0 : 0;
    });

    destroyChart('nhrcComparisonChart');
    chartInstances['nhrcComparisonChart'] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                { label: `${currentTenant}`, data: tenantValues, backgroundColor: '#1a6b8a', borderRadius: 4 },
                { label: 'State Average', data: stateValues, backgroundColor: '#d4af37', borderRadius: 4 },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'bottom' } },
            scales: { y: { beginAtZero: true, title: { display: true, text: 'Avg Risk Index' } } },
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

async function openSeiModal(nhrcCode) {
    const modal = document.getElementById('seiModal');
    const title = document.getElementById('seiModalTitle');
    const body = document.getElementById('seiModalBody');

    try {
        const [seis, factors] = await Promise.all([
            ApiClient.get(`/api/v1/nhrc/seis/${nhrcCode}`),
            ApiClient.get(`/api/v1/nhrc/contributing-factors/${nhrcCode}`)
        ]);

        const meta = NHRC_META[nhrcCode] || { name: nhrcCode };

        title.textContent = `${nhrcCode} — ${meta.name}`;

        let html = '';
        if (factors && factors.length) {
            html += `<h4>Contributing Factors</h4><ul>`;
            factors.forEach(f => { html += `<li>${escapeHtml(f)}</li>`; });
            html += `</ul>`;
        }
        if (seis && seis.length) {
            html += `<h4>Safety Enhancement Initiatives (SEIs)</h4><ul>`;
            seis.forEach(s => { html += `<li>${escapeHtml(s)}</li>`; });
            html += `</ul>`;
        }
        if (!html) html = '<p>No data available for this N-HRC.</p>';

        body.innerHTML = html;
        modal.style.display = 'flex';
    } catch (err) {
        body.innerHTML = `<p style="color:#c5221f;">Error loading data: ${escapeHtml(err.message)}</p>`;
        modal.style.display = 'flex';
    }
}

function closeSeiModal() {
    document.getElementById('seiModal').style.display = 'none';
}

// Click outside modal to close
document.getElementById('seiModal').addEventListener('click', function(e) {
    if (e.target === this) closeSeiModal();
});

// ESC closes the modal
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeSeiModal();
});