let chartInstances = {};
let currentPage = 1;
let currentDays = 60;
let recentDays = 30;
const PAGE_SIZE = 10;

function safeArray(data) {
    return Array.isArray(data) ? data : [];
}

// Maps a signed-in user (role + department) to the department label shown in
// the header banner subtitle, below the tenant header title. The user's email
// stays visible only in the top-right user menu.
function getDepartmentDisplayName(user) {
    if (user.role === 'CAAN_SMD') return 'State Aviation Safety Oversight';
    if (user.department === 'CAMO' || user.role === 'CAMO') return 'CAMO Department';
    if (user.department === 'Part-145' || user.role === '145') return 'Part-145 Maintenance Department';
    if (user.department === 'Flight Operations' || user.role === 'ops') return 'Flight Operations Department';
    return 'Corporate Safety Department'; // Default for safety / AIRLINE_ADMIN
}

function waitForFirebase() {
    return new Promise(resolve => {
        if (typeof firebase !== 'undefined' && firebase.auth) {
            resolve();
            return;
        }
        const check = setInterval(() => {
            if (typeof firebase !== 'undefined' && firebase.auth) {
                clearInterval(check);
                resolve();
            }
        }, 30);
        setTimeout(() => {
            clearInterval(check);
            resolve();
        }, 8000);
    });
}

var dashboardRedirecting = false;

document.addEventListener('DOMContentLoaded', async () => {
    await waitForFirebase();
    const session = await getCurrentUser();
    if (!session) {
        if (!dashboardRedirecting) {
            dashboardRedirecting = true;
            window.location.href = '/login.html';
        }
        return;
    }

    const { role, tenantId } = session;

    // Sync demo persona storage so header/context never shows a stale demo
    // tenant (e.g. air-dynasty-demo) when the user is actually fishtail-air.
    // This also keeps TenantResolver.getCurrentTenant() consistent for any
    // synchronous title resolution via applyTenantContext.
    try {
        if (typeof TenantResolver !== 'undefined' && TenantResolver.syncDemoTenantWithAuth) {
            TenantResolver.syncDemoTenantWithAuth(session);
        }
        // Expose for synchronous getCurrentTenant() fallback
        window.__AUTH_TENANT_ID = tenantId || null;
    } catch (_) { /* ignore */ }

    if (role !== 'AIRLINE_ADMIN' && role !== 'CAAN_SMD' && role !== 'SUPER_ADMIN') {
        showError('Unauthorized role. Contact your administrator.');
        return;
    }

    document.getElementById('dashboardSection').style.display = 'block';

    // Dynamic tenant context: derive display directly from auth claims
    const tenantName = tenantId ? tenantId.toUpperCase() : 'Cross-Tenant Safety Overview';
    const subtitle = getDepartmentDisplayName({
        role: session.role,
        department: (session.claims && session.claims.department) || ''
    });

    // Tenant + department context placeholders (subdomain / demo resolution +
    // email-prefix department mapping) when the resolver modules are loaded.
    if (typeof applyDepartmentContext === 'function') {
        applyDepartmentContext(session.email || '');
    }
    if (typeof window.updateShellTenant === 'function') {
        window.updateShellTenant(tenantName, subtitle);
    }

    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', async () => {
            try {
                if (typeof TenantResolver !== 'undefined' && TenantResolver.clearTenantSession) {
                    TenantResolver.clearTenantSession();
                } else if (typeof TenantResolver !== 'undefined' && TenantResolver.clearDemoTenant) {
                    TenantResolver.clearDemoTenant();
                }
                // Clear copilot session counters (env-prefixed)
                try {
                    var ck = (typeof storageKey === 'function' ? storageKey('copilot_message_count') : 'aviasafe_copilot_message_count');
                    sessionStorage.removeItem(ck);
                    sessionStorage.removeItem('aviasafe_copilot_message_count');
                    sessionStorage.removeItem('aviasafe:beta:copilot_message_count');
                    sessionStorage.removeItem('aviasafe:prod:copilot_message_count');
                } catch (_) {}
                window.__AUTH_TENANT_ID = null;
            } catch (_) {}
            await firebase.auth().signOut();
            window.location.href = '/login.html';
        });
    }

    const daysEl = document.getElementById('daysFilter');
    if (daysEl) {
        currentDays = parseInt(daysEl.value, 10);
        daysEl.addEventListener('change', () => {
            reloadDashboardData(daysEl.value);
        });
    }

    const timePeriodEl = document.getElementById('time-period-select');
    if (timePeriodEl) {
        timePeriodEl.addEventListener('change', () => {
            reloadDashboardData(timePeriodEl.value);
        });
    }

    const dateRangeEl = document.getElementById('date-range');
    if (dateRangeEl) {
        dateRangeEl.addEventListener('change', () => {
            reloadDashboardData(dateRangeEl.value);
        });
    }

    const recentRangeEl = document.getElementById('recentRange');
    if (recentRangeEl) {
        recentDays = parseInt(recentRangeEl.value, 10);
        recentRangeEl.addEventListener('change', () => {
            recentDays = parseInt(recentRangeEl.value, 10);
            currentPage = 1;
            loadRecentReports();
        });
    }

    document.getElementById('refreshBtn').addEventListener('click', () => {
        currentPage = 1;
        loadAll();
    });

    loadAll();
});

// ============================================================================
// Global dashboard reload entry point (wired to the date-range dropdowns on
// safety.html and caan.html). Re-queries KPIs, Risk Matrix, Hazards, the
// CAN/CAP table and the supporting charts for the selected period.
// days = 0 / null / "0" / "" means "All Time" (no date cutoff).
// ============================================================================
window.reloadDashboardData = function reloadDashboardData(days) {
    const n = parseInt(days, 10);
    currentDays = n > 0 ? n : null;
    currentPage = 1;
    return loadAll();
};

async function loadAll() {
    const jobs = [loadKpis()];

    if (document.getElementById('riskChart')) jobs.push(loadRiskDistribution());
    if (document.getElementById('trendChart')) jobs.push(loadMonthlyTrends());
    if (document.getElementById('ssmRiskChart')) jobs.push(loadSSMRiskTrends());
    if (document.getElementById('hazardChart')) jobs.push(loadHazardFrequency());
    if (document.getElementById('reportsTable')) jobs.push(loadRecentReports());
    if (typeof fetchCans === 'function') jobs.push(fetchCans(currentDays));

    await Promise.all(jobs);
}

async function loadKpis() {
    const el = document.getElementById('kpiGrid');
    setLoading(el);

    try {
        const data = await DashboardAPI.getOverview(currentDays);
        let k = data.kpis || {};
        // Demo fallback: if seeded data is in Postgres but dashboard read 0 from Firestore, show static demo values
        if (!k.total_reports && k.total_reports !== undefined && k.total_reports === 0) {
            // Check if this is a demo tenant (fixedwing/rotarywing/demoairport) - show seeded demo values
            const isDemoTenant = ['fixedwing', 'rotarywing', 'demoairport'].includes(currentTenant);
            if (isDemoTenant) {
                k = {
                    total_reports: 4,
                    open_reports: 2,
                    closed_reports: 2,
                    high_risk_reports: 1,
                    critical_reports: 0,
                    anonymous_percentage: 25.0,
                    avg_closure_days: 7.5,
                    reporting_rate_trend: 'up',
                    repeat_occurrence_rate: 0.1
                };
            }
        }

        el.innerHTML = `
            <div class="kpi-card"><h3>Total Reports</h3><div class="kpi-value">${k.total_reports ?? 0}</div></div>
            <div class="kpi-card"><h3>Open</h3><div class="kpi-value">${k.open_reports ?? 0}</div></div>
            <div class="kpi-card"><h3>Closed</h3><div class="kpi-value">${k.closed_reports ?? 0}</div></div>
            <div class="kpi-card high"><h3>High Risk</h3><div class="kpi-value">${k.high_risk_reports ?? 0}</div></div>
            <div class="kpi-card"><h3>Critical</h3><div class="kpi-value">${k.critical_reports ?? 0}</div></div>
            <div class="kpi-card"><h3>Anon Rate</h3><div class="kpi-value">${k.anonymous_percentage ?? 0}%</div></div>
        `;
        setReady(el);
    } catch (err) {
        setError(el, err.message);
    }
}

async function loadRiskDistribution() {
    const el = document.getElementById('riskChart');
    setLoading(el);

    try {
        const data = safeArray(await DashboardAPI.getRiskDistribution(currentDays));
        if (data.length === 0) {
            setEmpty(el, 'No risk data available');
            return;
        }
        setReady(el);
        renderRiskChart(data);
    } catch (err) {
        setError(el, err.message);
    }
}

async function loadSSMRiskTrends() {
    const el = document.getElementById('ssmRiskChart');
    setLoading(el);

    try {
        const data = (await DashboardAPI.getSSPRiskTrends(730)) || {};
        let labels = Array.isArray(data.labels) ? data.labels : [];
        let series = Array.isArray(data.series) ? data.series : [];
        // Demo fallback: if no data but demo tenant, show static trend
        if (labels.length === 0) {
            const isDemoTenant = ['fixedwing', 'rotarywing', 'demoairport'].includes(currentTenant);
            if (isDemoTenant) {
                labels = ['2026-Q1', '2026-Q2', '2026-Q3'];
                series = [
                    { category: 'Operational', points: [{avg_risk_index: 45}, {avg_risk_index: 42}, {avg_risk_index: 38}] },
                    { category: 'Technical', points: [{avg_risk_index: 55}, {avg_risk_index: 52}, {avg_risk_index: 48}] }
                ];
                data.labels = labels;
                data.series = series;
            } else {
                setEmpty(el, 'No SSM risk trend data available yet');
                return;
            }
        }
        setReady(el);
        renderSSMRiskChart(data);
    } catch (err) {
        setError(el, err.message);
    }
}

async function loadMonthlyTrends() {
    const el = document.getElementById('trendChart');
    setLoading(el);

    try {
        const data = safeArray(await DashboardAPI.getMonthlyTrends(currentDays * 2 > 730 ? 730 : currentDays * 2));
        if (data.length === 0) {
            setEmpty(el, 'No trend data available');
            return;
        }
        setReady(el);
        renderTrendChart(data);
    } catch (err) {
        setError(el, err.message);
    }
}

async function loadHazardFrequency() {
    const el = document.getElementById('hazardChart');
    setLoading(el);

    try {
        let data = safeArray(await DashboardAPI.getHazardFrequency(currentDays));
        if (data.length === 0) {
            const isDemoTenant = ['fixedwing', 'rotarywing', 'demoairport'].includes(currentTenant);
            if (isDemoTenant) {
                // Static demo hazards matching seeded data
                data = [
                    { occurrence_type: 'Runway Excursion', count: 3, percentage: 30 },
                    { occurrence_type: 'Bird Strike', count: 2, percentage: 20 },
                    { occurrence_type: 'Engine Failure', count: 2, percentage: 20 },
                    { occurrence_type: 'Cabin Pressurization', count: 1, percentage: 10 },
                    { occurrence_type: 'Tail Rotor', count: 1, percentage: 10 }
                ];
            } else {
                setEmpty(el, 'No hazard data available');
                return;
            }
        }
        setReady(el);
        renderHazardChart(data);
    } catch (err) {
        setError(el, err.message);
    }
}

async function loadRecentReports() {
    const el = document.getElementById('reportsTable');
    const pagEl = document.getElementById('pagination');
    setLoading(el);

    try {
        const data = await DashboardAPI.getRecentReports(recentDays, currentPage, PAGE_SIZE);
        if (!data || !data.items || data.items.length === 0) {
            setEmpty(el, 'No reports found');
            pagEl.innerHTML = '';
            return;
        }
        setReady(el);
        renderReportsTable(data.items);
        renderPagination(data, pagEl);
    } catch (err) {
        setError(el, err.message);
    }
}

function renderRiskChart(data) {
    destroyChart('riskChartCanvas');
    const ctx = document.getElementById('riskChartCanvas');
    if (!ctx) return;
    // Extra guard: Chart.js binds instance to canvas; destroy orphan if destroyChart missed it
    if (window.Chart && typeof Chart.getChart === 'function') {
        const orphan = Chart.getChart(ctx);
        if (orphan) { try { orphan.destroy(); } catch (_) {} }
    }

    const counts = { Low: 0, High: 0, 'Very High': 0 };
    for (const d of data) {
        const level = typeof normalizeRiskLevel === 'function' ? normalizeRiskLevel(d.risk_level) : d.risk_level;
        if (counts.hasOwnProperty(level)) counts[level] = d.count;
    }
    const labels = ICAO_RISK_LABELS;
    const vals = labels.map(l => counts[l] || 0);
    const colors = labels.map(l => ICAO_COLORS[l]);

    chartInstances['riskChartCanvas'] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: 'Reports',
                data: vals,
                backgroundColor: colors,
                borderRadius: 4,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                tooltip: {
                    callbacks: {
                        label: (ctx) => `${ctx.parsed.y} (${data[ctx.dataIndex]?.percentage || 0}%)`,
                    },
                },
                legend: { display: false },
            },
            scales: {
                y: { beginAtZero: true, ticks: { precision: 0 } },
            },
        },
    });
}

function renderSSMRiskChart(data) {
    destroyChart('ssmRiskChartCanvas');
    const ctx = document.getElementById('ssmRiskChartCanvas');
    if (!ctx) return;
    if (window.Chart && typeof Chart.getChart === 'function') {
        const orphan = Chart.getChart(ctx);
        if (orphan) { try { orphan.destroy(); } catch (_) {} }
    }

    const colors = {
        Organizational: '#188038',
        Technical: '#e8710a',
        Human: '#9334e6',
        Environmental: '#c5221f',
        // Legacy aliases kept so already-stored series still colour correctly.
        Operational: '#1a73e8',
        'Human Factors': '#9334e6',
        Wildlife: '#c5221f',
        External: '#c5221f',
    };

    const labels = Array.isArray(data.labels) ? data.labels : [];
    const series = Array.isArray(data.series) ? data.series : [];

    chartInstances['ssmRiskChartCanvas'] = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: series.map(s => ({
                label: s.category,
                data: (s.points || []).map(p => p.avg_risk_index),
                borderColor: colors[s.category] || '#5f6368',
                backgroundColor: (colors[s.category] || '#5f6368') + '1a',
                borderWidth: 2,
                pointRadius: 3,
                pointHoverRadius: 5,
                tension: 0.3,
                spanGaps: true,
            })),
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    title: { display: true, text: 'Avg Risk Index (0–100)' },
                    ticks: { precision: 0 },
                },
            },
            plugins: {
                legend: { position: 'bottom' },
                tooltip: {
                    callbacks: {
                        label: (item) => {
                            const v = item.raw;
                            return v == null
                                ? `${item.dataset.label}: no data`
                                : `${item.dataset.label}: ${v}`;
                        },
                    },
                },
            },
        },
    });
}

function renderTrendChart(data) {
    destroyChart('trendChartCanvas');
    const ctx = document.getElementById('trendChartCanvas');
    if (!ctx) return;
    if (window.Chart && typeof Chart.getChart === 'function') {
        const orphan = Chart.getChart(ctx);
        if (orphan) { try { orphan.destroy(); } catch (_) {} }
    }

    chartInstances['trendChartCanvas'] = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.map(d => `${d.month}/${d.year}`),
            datasets: [
                { label: 'Total', data: data.map(d => d.total), borderColor: '#1a6b8a', fill: false, tension: 0.3 },
                { label: 'Voluntary', data: data.map(d => d.voluntary), borderColor: '#28a745', fill: false, tension: 0.3 },
                { label: 'Mandatory', data: data.map(d => d.mandatory), borderColor: '#dc3545', fill: false, tension: 0.3 },
                { label: 'High Risk', data: data.map(d => d.high_risk), borderColor: '#fd7e14', fill: false, tension: 0.3, borderDash: [5, 5] },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, ticks: { precision: 0 } },
            },
        },
    });
}

function renderHazardChart(data) {
    destroyChart('hazardChartCanvas');
    const ctx = document.getElementById('hazardChartCanvas');
    if (!ctx) return;
    if (window.Chart && typeof Chart.getChart === 'function') {
        const orphan = Chart.getChart(ctx);
        if (orphan) { try { orphan.destroy(); } catch (_) {} }
    }

    const top = data.slice(0, 10);
    chartInstances['hazardChartCanvas'] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: top.map(d => d.occurrence_type),
            datasets: [{
                label: 'Occurrences',
                data: top.map(d => d.count),
                backgroundColor: '#1a6b8a',
                borderRadius: 4,
            }],
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { beginAtZero: true, ticks: { precision: 0 } },
            },
            plugins: { legend: { display: false } },
        },
    });
}

function renderReportsTable(items) {
    const tbody = document.getElementById('reportsBody');
    tbody.innerHTML = '';

    for (const r of items) {
        const date = r.occurrence_date ? new Date(r.occurrence_date).toLocaleDateString() : '-';
        const riskLevel = r.risk_level || getRiskLevelLabel(r.risk_index).text;
        const riskClass = getRiskBadgeClass(riskLevel);
        const statClass = statusBadgeClass(r.status);
        const ri = r.risk_index !== null && r.risk_index !== undefined ? r.risk_index : '-';
        const reportId = r.id;

        const row = document.createElement('tr');
        row.style.cursor = 'pointer';
        row.addEventListener('click', () => {
            window.location.href = `/report/detail.html?id=${reportId}`;
        });
        row.innerHTML = `
            <td>${date}</td>
            <td>${r.report_type === 'mandatory' ? 'MOR' : 'VSR'}</td>
            <td>${r.occurrence_type || '-'}</td>
            <td>${r.location || '-'}</td>
            <td style="text-align:center;font-weight:700;">${ri}</td>
            <td><span class="badge ${riskClass}">${riskLevel}</span></td>
            <td><span class="badge ${statClass}">${r.status || 'NEW'}</span></td>
        `;
        tbody.appendChild(row);
    }
}

function renderPagination(data, container) {
    container.innerHTML = '';

    const prev = document.createElement('button');
    prev.textContent = '‹ Prev';
    prev.className = 'page-btn';
    prev.disabled = !data.has_prev;
    prev.addEventListener('click', () => { currentPage--; loadRecentReports(); });

    const next = document.createElement('button');
    next.textContent = 'Next ›';
    next.className = 'page-btn';
    next.disabled = !data.has_next;
    next.addEventListener('click', () => { currentPage++; loadRecentReports(); });

    const info = document.createElement('span');
    info.className = 'page-info';
    info.textContent = `Page ${data.page} of ${data.total_pages} (${data.total} total)`;

    container.appendChild(prev);
    container.appendChild(info);
    container.appendChild(next);
}

function getRiskLevelLabel(index) {
    const level = classifyRisk(index);
    return { text: level, class: getRiskBadgeClass(level) };
}

function severityBadgeClass(sev) {
    switch (sev) {
        case 'Critical': return 'badge-critical';
        case 'High': return 'badge-high';
        case 'Medium': return 'badge-medium';
        case 'Low': return 'badge-low';
        default: return 'badge-default';
    }
}

function statusBadgeClass(status) {
    switch (status) {
        case 'NEW': return 'badge-new';
        case 'PROCESSING': return 'badge-processing';
        case 'COMPLETED': case 'SUBMITTED': return 'badge-completed';
        case 'FAILED': return 'badge-failed';
        case 'ARCHIVED': return 'badge-archived';
        default: return 'badge-default';
    }
}

function destroyChart(key) {
    // 1) Destroy tracked instance for this canvas key
    if (chartInstances[key]) {
        try { chartInstances[key].destroy(); } catch (_) {}
        delete chartInstances[key];
    }
    // 2) Legacy alias support (previous logical keys: risk, ssmTrend, trend, hazard)
    const legacyMap = {
        'riskChartCanvas': 'risk',
        'ssmRiskChartCanvas': 'ssmTrend',
        'trendChartCanvas': 'trend',
        'hazardChartCanvas': 'hazard'
    };
    const legacyKey = legacyMap[key];
    if (legacyKey && chartInstances[legacyKey]) {
        try { chartInstances[legacyKey].destroy(); } catch (_) {}
        delete chartInstances[legacyKey];
    }
    // 3) Fallback: destroy any Chart.js instance still bound to this canvas (covers tenant-switch reloads without hard refresh)
    const canvas = document.getElementById(key);
    if (canvas && window.Chart && typeof Chart.getChart === 'function') {
        const orphan = Chart.getChart(canvas);
        if (orphan) { try { orphan.destroy(); } catch (_) {} }
    }
}

async function loadRiskMatrixConfig() {
    try {
        const config = await getRiskMatrix();
        if (config && config.thresholds) {
            document.getElementById('rmLowMax').value = config.thresholds.low_max || 5;
            document.getElementById('rmMediumMax').value = config.thresholds.medium_max || 9;
            document.getElementById('rmHighMax').value = config.thresholds.high_max || 15;
        }
    } catch {
        // Use defaults
    }
    syncRiskMatrixThresholds();
    renderRiskMatrixPreview();
}

function riskMatrixThresholdsFromInputs() {
    return {
        lowMax: parseInt(document.getElementById('rmLowMax').value, 10) || 5,
        mediumMax: parseInt(document.getElementById('rmMediumMax').value, 10) || 9,
        highMax: parseInt(document.getElementById('rmHighMax').value, 10) || 15,
    };
}

function syncRiskMatrixThresholds() {
    const t = riskMatrixThresholdsFromInputs();
    if (t.lowMax >= t.mediumMax || t.mediumMax >= t.highMax) return;
    if (typeof ICAO_THRESHOLDS !== 'undefined') {
        ICAO_THRESHOLDS.lowMax = t.lowMax;
        ICAO_THRESHOLDS.mediumMax = t.mediumMax;
        ICAO_THRESHOLDS.highMax = t.highMax;
    }
}

function renderRiskMatrixPreview() {
    const container = document.getElementById('riskMatrixPreview');
    if (!container) return;
    const t = riskMatrixThresholdsFromInputs();
    const valid = t.lowMax >= 1 && t.lowMax < t.mediumMax && t.mediumMax < t.highMax && t.highMax <= 25;

    const levelFor = (index) => {
        if (!valid) return 'Very High';
        if (index <= t.lowMax) return 'Low';
        if (index <= t.highMax) return 'High';
        return 'Very High';
    };

    const colorFor = (index) => {
        if (!valid) return '#e2e8f0';
        return ICAO_COLORS[levelFor(index)] || '#e2e8f0';
    };

    let html = '<table style="border-collapse:collapse;margin:0 auto;font-size:0.78rem;">';
    html += '<tr><td style="padding:0.4rem;font-weight:700;color:#475569;text-align:right;">P\\S</td>';
    for (let s = 1; s <= 5; s++) {
        html += `<td style="padding:0.4rem 0.55rem;font-weight:700;color:#1a6b8a;text-align:center;">${s}</td>`;
    }
    html += '</tr>';
    for (let p = 5; p >= 1; p--) {
        html += `<tr><td style="padding:0.4rem;font-weight:700;color:#475569;text-align:right;">${p}</td>`;
        for (let s = 1; s <= 5; s++) {
            const index = s * p;
            const color = colorFor(index);
            const textColor = (index > 15 && valid) ? '#fff' : '#0b2a42';
            html += `<td style="padding:0.4rem;text-align:center;background:${color};border:1px solid #fff;border-radius:4px;min-width:42px;color:${textColor};font-weight:700;">${index}</td>`;
        }
        html += '</tr>';
    }
    html += '</table>';

    let note;
    if (!valid) {
        note = '<p style="text-align:center;font-size:0.72rem;color:#d97706;margin-top:0.5rem;">Thresholds must be strictly increasing: 1 ≤ Low &lt; Medium &lt; High ≤ 25.</p>';
    } else {
        note = `<p style="text-align:center;font-size:0.72rem;color:#94a3b8;margin-top:0.5rem;">Low ≤ ${t.lowMax} · High ≤ ${t.highMax} · Very High &gt; ${t.highMax}</p>`;
    }
    container.innerHTML = html + note;
}

function setupRiskMatrixForm() {
    ['rmLowMax', 'rmMediumMax', 'rmHighMax'].forEach(function (id) {
        const input = document.getElementById(id);
        if (input) {
            input.addEventListener('input', () => {
                syncRiskMatrixThresholds();
                renderRiskMatrixPreview();
            });
        }
    });
    document.getElementById('riskMatrixForm').addEventListener('submit', async function(e) {
        e.preventDefault();
        const btn = document.getElementById('rmSaveBtn');
        const status = document.getElementById('rmStatus');
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
        status.style.display = 'none';

        try {
            const lowMax = parseInt(document.getElementById('rmLowMax').value, 10);
            const mediumMax = parseInt(document.getElementById('rmMediumMax').value, 10);
            const highMax = parseInt(document.getElementById('rmHighMax').value, 10);

            if (lowMax >= mediumMax || mediumMax >= highMax) {
                throw new Error('Thresholds must be strictly increasing: Low < Medium < High');
            }
            if (lowMax < 1 || highMax > 25) {
                throw new Error('Values must be between 1 and 25.');
            }

            await updateRiskMatrix({ lowMax, mediumMax, highMax });

            syncRiskMatrixThresholds();
            renderRiskMatrixPreview();

            status.style.color = '#2e7d32';
            status.innerHTML = '<i class="fas fa-check-circle"></i> Saved successfully';
            status.style.display = 'inline';
            setTimeout(() => { status.style.display = 'none'; }, 3000);
        } catch (err) {
            status.style.color = '#dc3545';
            status.innerHTML = '<i class="fas fa-exclamation-circle"></i> ' + err.message;
            status.style.display = 'inline';
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-save"></i> Save Thresholds';
        }
    });
}

function setLoading(el) {
    el.dataset.state = 'loading';
    el.classList.remove('state-ready', 'state-empty', 'state-error');
    el.classList.add('state-loading');
}

function setReady(el) {
    el.dataset.state = 'ready';
    el.classList.remove('state-loading', 'state-empty', 'state-error');
    el.classList.add('state-ready');
}

function setEmpty(el, msg) {
    el.dataset.state = 'empty';
    el.classList.remove('state-loading', 'state-ready', 'state-error');
    el.classList.add('state-empty');
    if (!el.querySelector('.empty-msg')) {
        const p = document.createElement('p');
        p.className = 'empty-msg';
        p.textContent = msg;
        el.appendChild(p);
    }
}

function setError(el, msg) {
    el.dataset.state = 'error';
    el.classList.remove('state-loading', 'state-ready', 'state-empty');
    el.classList.add('state-error');
    let errEl = el.querySelector('.error-msg');
    if (!errEl) {
        errEl = document.createElement('p');
        errEl.className = 'error-msg';
        el.appendChild(errEl);
    }
    errEl.textContent = `Error: ${msg}`;
}

function showError(msg) {
    document.body.innerHTML = `
        <div style="display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column;font-family:sans-serif;">
            <h2 style="color:#dc3545;">Access Denied</h2>
            <p>${msg}</p>
            <a href="/login.html" style="margin-top:1rem;color:#1a6b8a;">Return to Login</a>
        </div>
    `;
}
