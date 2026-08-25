/* ============================================================================
   FILE: sdps.js
   PATH: public/sdps/sdps.js
   VERSION: 1.0.0
   PURPOSE: Main SDPS application logic — data loading, chart rendering,
            table rendering, drawer, and all view initialization.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

(function () {
    'use strict';

    var _charts = {};
    var _currentDays = 60;
    var _hazardPage = 1;
    var _occurrencePage = 1;
    var PAGE_SIZE = 20;

    // ── Helpers ──
    function safeArray(d) { return Array.isArray(d) ? d : []; }

    function destroyChart(key) {
        if (_charts[key]) { try { _charts[key].destroy(); } catch (_) {} delete _charts[key]; }
        var canvas = document.getElementById(key);
        if (canvas && window.Chart && typeof Chart.getChart === 'function') {
            var orphan = Chart.getChart(canvas);
            if (orphan) { try { orphan.destroy(); } catch (_) {} }
        }
    }

    function setLoading(el) {
        if (!el) return;
        el.classList.add('sdps-loading');
        el.innerHTML = '<div style="text-align:center;padding:2rem;color:#94a3b8;"><i class="fas fa-spinner fa-spin"></i> Loading...</div>';
    }

    function setEmpty(el, msg) {
        if (!el) return;
        el.innerHTML = '<div style="text-align:center;padding:2rem;color:#94a3b8;">' + (msg || 'No data available') + '</div>';
    }

    // ── Auth Gate ──
    function waitForFirebase() {
        return new Promise(function (resolve) {
            if (typeof firebase !== 'undefined' && firebase.auth) { resolve(); return; }
            var check = setInterval(function () {
                if (typeof firebase !== 'undefined' && firebase.auth) { clearInterval(check); resolve(); }
            }, 30);
            setTimeout(function () { clearInterval(check); resolve(); }, 8000);
        });
    }

    var _authRedirecting = false;

    async function requireAuth() {
        await waitForFirebase();
        var user = await new Promise(function (resolve) {
            var settled = false;
            var unsub = null;
            function done(v) { if (settled) return; settled = true; if (unsub) try { unsub(); } catch (_) {} resolve(v); }
            try {
                unsub = firebase.auth().onAuthStateChanged(function (u) {
                    if (u) {
                        u.getIdTokenResult(true).then(function (tr) {
                            done({ uid: u.uid, email: u.email, role: (tr.claims || {}).role || 'USER', tenantId: (tr.claims || {}).tenant_id || null, claims: tr.claims || {} });
                        }).catch(function () { done(null); });
                    }
                });
            } catch (e) { done(null); }
            setTimeout(function () { done(null); }, 8000);
        });
        if (!user) {
            if (!_authRedirecting) { _authRedirecting = true; window.location.href = '/login.html'; }
            return null;
        }
        return user;
    }

    // ── Period Filter ──
    function initPeriodFilter() {
        var sel = document.getElementById('sdpsPeriodSelect');
        if (!sel) return;
        sel.addEventListener('change', function () {
            _currentDays = parseInt(sel.value, 10) || 0;
            loadCurrentView();
        });
        _currentDays = parseInt(sel.value, 10) || 60;
    }

    // ── Drawer ──
    function openDrawer(title, html) {
        var overlay = document.getElementById('sdpsDrawerOverlay');
        var drawer = document.getElementById('sdpsDrawer');
        var titleEl = document.getElementById('sdpsDrawerTitle');
        var body = document.getElementById('sdpsDrawerBody');
        if (titleEl) titleEl.textContent = title;
        if (body) body.innerHTML = html;
        if (overlay) overlay.classList.add('open');
        if (drawer) drawer.classList.add('open');
    }

    function closeDrawer() {
        var overlay = document.getElementById('sdpsDrawerOverlay');
        var drawer = document.getElementById('sdpsDrawer');
        if (overlay) overlay.classList.remove('open');
        if (drawer) drawer.classList.remove('open');
    }

    function initDrawer() {
        var overlay = document.getElementById('sdpsDrawerOverlay');
        var closeBtn = document.getElementById('sdpsDrawerClose');
        if (overlay) overlay.addEventListener('click', closeDrawer);
        if (closeBtn) closeBtn.addEventListener('click', closeDrawer);
    }

    // ════════════════════════════════════════════════════════════════════════
    // HOME VIEW
    // ════════════════════════════════════════════════════════════════════════

    async function loadHome() {
        await Promise.all([loadKpis(), loadInsights(), loadHomeCharts()]);
    }

    async function loadKpis() {
        var grid = document.getElementById('sdpsKpiGrid');
        if (!grid) return;
        setLoading(grid);
        try {
            var data = await DashboardAPI.getOverview(_currentDays);
            var k = data.kpis || {};
            var hazards = data.hazard_summary || {};
            grid.innerHTML = [
                kpiCard('Total Hazards', hazards.total ?? k.total_reports ?? 0, ''),
                kpiCard('High Priority', hazards.high ?? 0, 'kpi-high'),
                kpiCard('Medium Priority', hazards.medium ?? 0, 'kpi-warning'),
                kpiCard('Low Priority', hazards.low ?? 0, 'kpi-success'),
                kpiCard('Open', k.open_reports ?? 0, ''),
                kpiCard('Processing', k.processing_reports ?? k.open_reports ?? 0, 'kpi-warning'),
                kpiCard('Closed', k.closed_reports ?? 0, 'kpi-success'),
                kpiCard('Anonymous Rate', (k.anonymous_percentage ?? 0) + '%', ''),
            ].join('');
        } catch (e) {
            setEmpty(grid, 'Error loading KPIs: ' + e.message);
        }
    }

    function kpiCard(label, value, cls) {
        return '<div class="sdps-kpi-card ' + cls + '"><h3>' + label + '</h3><div class="sdps-kpi-value">' + value + '</div></div>';
    }

    async function loadInsights() {
        var grid = document.getElementById('sdpsInsightGrid');
        if (!grid) return;
        setLoading(grid);
        try {
            var data = await DashboardAPI.getOverview(_currentDays);
            var topTaxonomy = (data.top_taxonomies || [])[0] || '—';
            var topType = (data.top_hazard_types || [])[0] || '—';
            var topSource = (data.top_sources || [])[0] || '—';
            var maxMonth = data.max_hazards_month || '—';
            grid.innerHTML = [
                insightChip('Top 3 Hazard Taxonomy', topTaxonomy),
                insightChip('Top 3 Hazard Types', topType),
                insightChip('Top 3 Source of Reporting', topSource),
                insightChip('Max Hazards Month', maxMonth),
            ].join('');
        } catch (e) {
            setEmpty(grid, 'Error loading insights');
        }
    }

    function insightChip(title, value) {
        return '<div class="sdps-insight-chip"><h4>' + title + '</h4><div class="sdps-insight-value">' + value + '</div></div>';
    }

    async function loadHomeCharts() {
        await Promise.all([loadTaxonomyChart(), loadOccurrenceChart()]);
    }

    async function loadTaxonomyChart() {
        var ctx = document.getElementById('sdpsTaxonomyChart');
        if (!ctx) return;
        destroyChart('sdpsTaxonomyChart');
        try {
            var data = await DashboardAPI.getRiskDistribution(_currentDays);
            var arr = safeArray(data);
            var counts = { Low: 0, High: 0, 'Very High': 0 };
            arr.forEach(function (d) {
                var level = typeof normalizeRiskLevel === 'function' ? normalizeRiskLevel(d.risk_level) : d.risk_level;
                if (counts.hasOwnProperty(level)) counts[level] = d.count;
            });
            var labels = (typeof ICAO_RISK_LABELS !== 'undefined') ? ICAO_RISK_LABELS : ['Low', 'High', 'Very High'];
            var colors = (typeof ICAO_COLORS !== 'undefined') ? ICAO_COLORS : { Low: '#34a853', High: '#f9ab00', 'Very High': '#ea4335' };
            _charts['sdpsTaxonomyChart'] = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{ label: 'Hazards', data: labels.map(function (l) { return counts[l] || 0; }), backgroundColor: labels.map(function (l) { return colors[l] || '#94a3b8'; }), borderRadius: 4 }],
                },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
            });
        } catch (e) { console.warn('[SDPS] Taxonomy chart error:', e); }
    }

    async function loadOccurrenceChart() {
        var ctx = document.getElementById('sdpsOccurrenceChart');
        if (!ctx) return;
        destroyChart('sdpsOccurrenceChart');
        try {
            var trends = safeArray(await DashboardAPI.getMonthlyTrends(_currentDays * 2 > 730 ? 730 : _currentDays * 2));
            if (trends.length === 0) return;
            _charts['sdpsOccurrenceChart'] = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: trends.map(function (d) { return d.month + '/' + d.year; }),
                    datasets: [
                        { label: 'Total', data: trends.map(function (d) { return d.total; }), borderColor: '#1a6b8a', fill: false, tension: 0.3 },
                        { label: 'High Risk', data: trends.map(function (d) { return d.high_risk; }), borderColor: '#dc3545', fill: false, tension: 0.3, borderDash: [5, 5] },
                    ],
                },
                options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
            });
        } catch (e) { console.warn('[SDPS] Occurrence chart error:', e); }
    }

    // ════════════════════════════════════════════════════════════════════════
    // HAZARD VIEW
    // ════════════════════════════════════════════════════════════════════════

    async function loadHazard() {
        var tbody = document.getElementById('sdpsHazardTableBody');
        if (!tbody) return;
        setLoading(tbody.parentElement);
        try {
            var status = document.getElementById('hazardStatusFilter') ? document.getElementById('hazardStatusFilter').value : '';
            var priority = document.getElementById('hazardPriorityFilter') ? document.getElementById('hazardPriorityFilter').value : '';
            var search = document.getElementById('hazardSearchInput') ? document.getElementById('hazardSearchInput').value : '';
            var params = {};
            if (status) params.status = status;
            if (priority) params.priority = priority;
            if (search) params.search = search;
            var data = await HazardsAPI.list(params);
            var items = Array.isArray(data) ? data : (data.items || []);
            tbody.innerHTML = '';
            if (items.length === 0) {
                tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:2rem;color:#94a3b8;">No hazards found</td></tr>';
                return;
            }
            items.slice(0, PAGE_SIZE).forEach(function (h) {
                var riskLevel = classifyHazardRisk(h.risk_index);
                var tr = document.createElement('tr');
                tr.innerHTML = '<td>' + (h.reference || h.id || '—') + '</td>' +
                    '<td>' + (h.title || '—') + '</td>' +
                    '<td>' + (h.taxonomy || '—') + '</td>' +
                    '<td><span class="sdps-badge ' + hazardPriorityBadgeClass(h.priority) + '">' + (h.priority || '—') + '</span></td>' +
                    '<td><span class="sdps-badge ' + getRiskBadgeClass(riskLevel) + '">' + riskLevel + '</span></td>' +
                    '<td><span class="sdps-badge ' + hazardStatusBadgeClass(h.status) + '">' + (h.status || '—') + '</span></td>' +
                    '<td>' + (h.source || '—') + '</td>' +
                    '<td>' + (h.created_at ? new Date(h.created_at).toLocaleDateString() : '—') + '</td>';
                tr.addEventListener('click', function () { openHazardDrawer(h); });
                tbody.appendChild(tr);
            });
        } catch (e) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:1rem;color:#dc3545;">Error: ' + e.message + '</td></tr>';
        }
    }

    function openHazardDrawer(h) {
        var riskLevel = classifyHazardRisk(h.risk_index);
        var html = '<div style="font-size:0.88rem;">' +
            '<p><strong>Reference:</strong> ' + (h.reference || h.id || '—') + '</p>' +
            '<p><strong>Title:</strong> ' + (h.title || '—') + '</p>' +
            '<p><strong>Taxonomy:</strong> ' + (h.taxonomy || '—') + '</p>' +
            '<p><strong>Priority:</strong> <span class="sdps-badge ' + hazardPriorityBadgeClass(h.priority) + '">' + (h.priority || '—') + '</span></p>' +
            '<p><strong>Risk Index:</strong> ' + (h.risk_index ?? '—') + ' (' + riskLevel + ')</p>' +
            '<p><strong>Status:</strong> <span class="sdps-badge ' + hazardStatusBadgeClass(h.status) + '">' + (h.status || '—') + '</span></p>' +
            '<p><strong>Source:</strong> ' + (h.source || '—') + '</p>' +
            '<p><strong>Description:</strong></p><p style="color:#475569;">' + (h.description || 'No description.') + '</p>' +
            '</div>';
        openDrawer('Hazard Detail', html);
    }

    // ════════════════════════════════════════════════════════════════════════
    // HAZARD ANALYSIS VIEW
    // ════════════════════════════════════════════════════════════════════════

    async function loadHazardAnalysis() {
        await Promise.all([loadHazardTrendChart(), loadHazardSourceChart(), loadHazardTaxChart()]);
    }

    async function loadHazardTrendChart() {
        var ctx = document.getElementById('sdpsHazardTrendChart');
        if (!ctx) return;
        destroyChart('sdpsHazardTrendChart');
        try {
            var trends = safeArray(await DashboardAPI.getMonthlyTrends(_currentDays * 2 > 730 ? 730 : _currentDays * 2));
            if (trends.length === 0) return;
            _charts['sdpsHazardTrendChart'] = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: trends.map(function (d) { return d.month + '/' + d.year; }),
                    datasets: [
                        { label: 'Total', data: trends.map(function (d) { return d.total; }), backgroundColor: '#1a6b8a', borderRadius: 3 },
                        { label: 'High Risk', data: trends.map(function (d) { return d.high_risk; }), backgroundColor: '#dc3545', borderRadius: 3 },
                    ],
                },
                options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
            });
        } catch (e) { console.warn('[SDPS] Hazard trend error:', e); }
    }

    async function loadHazardSourceChart() {
        var ctx = document.getElementById('sdpsHazardSourceChart');
        if (!ctx) return;
        destroyChart('sdpsHazardSourceChart');
        try {
            var data = await DashboardAPI.getOverview(_currentDays);
            var sources = data.top_sources || [];
            if (sources.length === 0) return;
            _charts['sdpsHazardSourceChart'] = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: sources.map(function (s) { return s.source || s; }),
                    datasets: [{ data: sources.map(function (s) { return s.count || 1; }), backgroundColor: ['#1a6b8a', '#34a853', '#f9ab00', '#ea4335', '#9334e6', '#188038'] }],
                },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } },
            });
        } catch (e) { console.warn('[SDPS] Source chart error:', e); }
    }

    async function loadHazardTaxChart() {
        var ctx = document.getElementById('sdpsHazardTaxChart');
        if (!ctx) return;
        destroyChart('sdpsHazardTaxChart');
        try {
            var data = await DashboardAPI.getOverview(_currentDays);
            var taxonomies = data.top_taxonomies || [];
            if (taxonomies.length === 0) return;
            _charts['sdpsHazardTaxChart'] = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: taxonomies.map(function (t) { return t.taxonomy || t; }),
                    datasets: [{ label: 'Count', data: taxonomies.map(function (t) { return t.count || 1; }), backgroundColor: '#0ea5e9', borderRadius: 3 }],
                },
                options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true, ticks: { precision: 0 } } } },
            });
        } catch (e) { console.warn('[SDPS] Taxonomy chart error:', e); }
    }

    // ════════════════════════════════════════════════════════════════════════
    // OCCURRENCE VIEW
    // ════════════════════════════════════════════════════════════════════════

    async function loadOccurrence() {
        var tbody = document.getElementById('sdpsOccurrenceTableBody');
        if (!tbody) return;
        setLoading(tbody.parentElement);
        try {
            var data = await DashboardAPI.getRecentReports(_currentDays, _occurrencePage, PAGE_SIZE);
            tbody.innerHTML = '';
            if (!data || !data.items || data.items.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:2rem;color:#94a3b8;">No occurrences found</td></tr>';
                return;
            }
            data.items.forEach(function (r) {
                var date = r.occurrence_date ? new Date(r.occurrence_date).toLocaleDateString() : '—';
                var riskLevel = typeof normalizeRiskLevel === 'function' ? normalizeRiskLevel(r.risk_level) : (r.risk_level || '—');
                var tr = document.createElement('tr');
                tr.innerHTML = '<td>' + date + '</td>' +
                    '<td>' + (r.report_type === 'mandatory' ? 'MOR' : 'VSR') + '</td>' +
                    '<td>' + (r.occurrence_type || '—') + '</td>' +
                    '<td>' + (r.location || '—') + '</td>' +
                    '<td style="text-align:center;font-weight:700;">' + (r.risk_index ?? '—') + '</td>' +
                    '<td><span class="sdps-badge ' + getRiskBadgeClass(riskLevel) + '">' + riskLevel + '</span></td>' +
                    '<td><span class="sdps-badge badge-' + (r.status || 'new').toLowerCase() + '">' + (r.status || '—') + '</span></td>';
                tbody.appendChild(tr);
            });
            renderOccurrencePagination(data);
        } catch (e) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:1rem;color:#dc3545;">Error: ' + e.message + '</td></tr>';
        }
    }

    function renderOccurrencePagination(data) {
        var el = document.getElementById('sdpsOccurrencePagination');
        if (!el) return;
        el.innerHTML = '';
        var prev = document.createElement('button');
        prev.textContent = '‹ Prev';
        prev.className = 'sdps-page-btn';
        prev.disabled = !data.has_prev;
        prev.addEventListener('click', function () { _occurrencePage--; loadOccurrence(); });
        var next = document.createElement('button');
        next.textContent = 'Next ›';
        next.className = 'sdps-page-btn';
        next.disabled = !data.has_next;
        next.addEventListener('click', function () { _occurrencePage++; loadOccurrence(); });
        var info = document.createElement('span');
        info.className = 'sdps-page-info';
        info.textContent = 'Page ' + data.page + ' of ' + data.total_pages + ' (' + data.total + ' total)';
        el.appendChild(prev);
        el.appendChild(info);
        el.appendChild(next);
    }

    // ════════════════════════════════════════════════════════════════════════
    // OCCURRENCE ANALYSIS VIEW
    // ════════════════════════════════════════════════════════════════════════

    async function loadOccurrenceAnalysis() {
        await Promise.all([loadOccTrendChart(), loadOccRiskChart(), loadOccTypeChart()]);
    }

    async function loadOccTrendChart() {
        var ctx = document.getElementById('sdpsOccurrenceTrendChart');
        if (!ctx) return;
        destroyChart('sdpsOccurrenceTrendChart');
        try {
            var trends = safeArray(await DashboardAPI.getMonthlyTrends(_currentDays * 2 > 730 ? 730 : _currentDays * 2));
            if (trends.length === 0) return;
            _charts['sdpsOccurrenceTrendChart'] = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: trends.map(function (d) { return d.month + '/' + d.year; }),
                    datasets: [
                        { label: 'Total', data: trends.map(function (d) { return d.total; }), borderColor: '#1a6b8a', fill: false, tension: 0.3 },
                        { label: 'Voluntary', data: trends.map(function (d) { return d.voluntary; }), borderColor: '#28a745', fill: false, tension: 0.3 },
                        { label: 'Mandatory', data: trends.map(function (d) { return d.mandatory; }), borderColor: '#dc3545', fill: false, tension: 0.3 },
                    ],
                },
                options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
            });
        } catch (e) { console.warn('[SDPS] Occ trend error:', e); }
    }

    async function loadOccRiskChart() {
        var ctx = document.getElementById('sdpsOccurrenceRiskChart');
        if (!ctx) return;
        destroyChart('sdpsOccurrenceRiskChart');
        try {
            var data = await DashboardAPI.getRiskDistribution(_currentDays);
            var arr = safeArray(data);
            var counts = { Low: 0, High: 0, 'Very High': 0 };
            arr.forEach(function (d) {
                var level = typeof normalizeRiskLevel === 'function' ? normalizeRiskLevel(d.risk_level) : d.risk_level;
                if (counts.hasOwnProperty(level)) counts[level] = d.count;
            });
            var labels = (typeof ICAO_RISK_LABELS !== 'undefined') ? ICAO_RISK_LABELS : ['Low', 'High', 'Very High'];
            var colors = (typeof ICAO_COLORS !== 'undefined') ? ICAO_COLORS : { Low: '#34a853', High: '#f9ab00', 'Very High': '#ea4335' };
            _charts['sdpsOccurrenceRiskChart'] = new Chart(ctx, {
                type: 'pie',
                data: {
                    labels: labels,
                    datasets: [{ data: labels.map(function (l) { return counts[l] || 0; }), backgroundColor: labels.map(function (l) { return colors[l] || '#94a3b8'; }) }],
                },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } },
            });
        } catch (e) { console.warn('[SDPS] Occ risk chart error:', e); }
    }

    async function loadOccTypeChart() {
        var ctx = document.getElementById('sdpsOccurrenceTypeChart');
        if (!ctx) return;
        destroyChart('sdpsOccurrenceTypeChart');
        try {
            var data = await DashboardAPI.getOverview(_currentDays);
            var types = data.top_hazard_types || [];
            if (types.length === 0) return;
            _charts['sdpsOccurrenceTypeChart'] = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: types.map(function (t) { return t.type || t; }),
                    datasets: [{ label: 'Count', data: types.map(function (t) { return t.count || 1; }), backgroundColor: '#f9ab00', borderRadius: 3 }],
                },
                options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true, ticks: { precision: 0 } } } },
            });
        } catch (e) { console.warn('[SDPS] Occ type chart error:', e); }
    }

    // ════════════════════════════════════════════════════════════════════════
    // HRC VIEW
    // ════════════════════════════════════════════════════════════════════════

    async function loadHRC() {
        var tbody = document.getElementById('sdpsHrcTableBody');
        var kpiGrid = document.getElementById('sdpsHrcKpiGrid');
        if (!tbody) return;
        setLoading(tbody.parentElement);
        try {
            var data = await DashboardAPI.getOverview(_currentDays);
            var k = data.kpis || {};
            if (kpiGrid) {
                kpiGrid.innerHTML = [
                    kpiCard('Total Hazards', k.total_reports ?? 0, ''),
                    kpiCard('Very High Risk', k.critical_reports ?? 0, 'kpi-high'),
                    kpiCard('High Risk', k.high_risk_reports ?? 0, 'kpi-warning'),
                    kpiCard('Closed', k.closed_reports ?? 0, 'kpi-success'),
                ].join('');
            }
            var riskData = safeArray(await DashboardAPI.getRiskDistribution(_currentDays));
            tbody.innerHTML = '';
            if (riskData.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:2rem;color:#94a3b8;">No risk data available</td></tr>';
                return;
            }
            riskData.forEach(function (d) {
                var level = typeof normalizeRiskLevel === 'function' ? normalizeRiskLevel(d.risk_level) : d.risk_level;
                var tr = document.createElement('tr');
                tr.innerHTML = '<td>' + level + '</td>' +
                    '<td style="text-align:center;">' + (d.count || 0) + '</td>' +
                    '<td style="text-align:center;">' + (d.avg_risk_index ?? '—') + '</td>' +
                    '<td><span class="sdps-badge ' + getRiskBadgeClass(level) + '">' + level + '</span></td>' +
                    '<td>' + (d.trend || '—') + '</td>';
                tbody.appendChild(tr);
            });
        } catch (e) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:1rem;color:#dc3545;">Error: ' + e.message + '</td></tr>';
        }
    }

    // ════════════════════════════════════════════════════════════════════════
    // SPIs VIEW
    // ════════════════════════════════════════════════════════════════════════

    async function loadSPIs() {
        var kpiGrid = document.getElementById('sdpsSpisKpiGrid');
        if (!kpiGrid) return;
        setLoading(kpiGrid);
        try {
            var data = await DashboardAPI.getOverview(_currentDays);
            var k = data.kpis || {};
            kpiGrid.innerHTML = [
                kpiCard('Hazard Reports', k.total_reports ?? 0, ''),
                kpiCard('CANs Open', k.open_cans ?? 0, 'kpi-warning'),
                kpiCard('CAPs Open', k.open_caps ?? 0, 'kpi-high'),
                kpiCard('Anonymous Reports', k.anonymous_reports ?? 0, ''),
            ].join('');
        } catch (e) { setEmpty(kpiGrid, 'Error loading SPIs'); }
        await loadSpiTrendChart();
    }

    async function loadSpiTrendChart() {
        var ctx = document.getElementById('sdpsSpiTrendChart');
        if (!ctx) return;
        destroyChart('sdpsSpiTrendChart');
        try {
            var trends = safeArray(await DashboardAPI.getMonthlyTrends(_currentDays * 2 > 730 ? 730 : _currentDays * 2));
            if (trends.length === 0) return;
            _charts['sdpsSpiTrendChart'] = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: trends.map(function (d) { return d.month + '/' + d.year; }),
                    datasets: [
                        { label: 'Total Reports', data: trends.map(function (d) { return d.total; }), borderColor: '#1a6b8a', fill: false, tension: 0.3 },
                    ],
                },
                options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
            });
        } catch (e) { console.warn('[SDPS] SPI trend error:', e); }
    }

    // ════════════════════════════════════════════════════════════════════════
    // ROUTE LOADING DISPATCHER
    // ════════════════════════════════════════════════════════════════════════

    var _viewLoaded = {};

    function loadCurrentView() {
        var route = SDPSRouter.getCurrentRoute();
        loadView(route);
    }

    function loadView(route) {
        if (_viewLoaded[route]) return;
        _viewLoaded[route] = true;
        switch (route) {
            case 'home': loadHome(); break;
            case 'hazard': loadHazard(); break;
            case 'hazard-analysis': loadHazardAnalysis(); break;
            case 'occurrence': loadOccurrence(); break;
            case 'occurrence-analysis': loadOccurrenceAnalysis(); break;
            case 'hrc': loadHRC(); break;
            case 'spis': loadSPIs(); break;
        }
    }

    // ════════════════════════════════════════════════════════════════════════
    // INIT
    // ════════════════════════════════════════════════════════════════════════

    async function init() {
        var user = await requireAuth();
        if (!user) return;

        // Set user pill
        var emailEl = document.getElementById('sdpsUserEmail');
        if (emailEl) emailEl.textContent = user.email || '—';

        initPeriodFilter();
        initDrawer();

        // Register route callbacks
        SDPSRouter.onRoute('home', function () { _viewLoaded['home'] = false; loadHome(); });
        SDPSRouter.onRoute('hazard', function () { _viewLoaded['hazard'] = false; loadHazard(); });
        SDPSRouter.onRoute('hazard-analysis', function () { _viewLoaded['hazard-analysis'] = false; loadHazardAnalysis(); });
        SDPSRouter.onRoute('occurrence', function () { _viewLoaded['occurrence'] = false; loadOccurrence(); });
        SDPSRouter.onRoute('occurrence-analysis', function () { _viewLoaded['occurrence-analysis'] = false; loadOccurrenceAnalysis(); });
        SDPSRouter.onRoute('hrc', function () { _viewLoaded['hrc'] = false; loadHRC(); });
        SDPSRouter.onRoute('spis', function () { _viewLoaded['spis'] = false; loadSPIs(); });

        // Load initial view
        loadCurrentView();

        // Home sub-nav tabs
        var subnavBtns = document.querySelectorAll('.sdps-subnav-btn');
        for (var i = 0; i < subnavBtns.length; i++) {
            subnavBtns[i].addEventListener('click', function () {
                for (var j = 0; j < subnavBtns.length; j++) subnavBtns[j].classList.remove('active');
                this.classList.add('active');
            });
        }

        // Hazard filters
        var hazardRefresh = document.getElementById('hazardRefreshBtn');
        if (hazardRefresh) hazardRefresh.addEventListener('click', function () { _viewLoaded['hazard'] = false; loadHazard(); });
        var hazardStatus = document.getElementById('hazardStatusFilter');
        if (hazardStatus) hazardStatus.addEventListener('change', function () { _viewLoaded['hazard'] = false; loadHazard(); });
        var hazardPriority = document.getElementById('hazardPriorityFilter');
        if (hazardPriority) hazardPriority.addEventListener('change', function () { _viewLoaded['hazard'] = false; loadHazard(); });
        var hazardSearch = document.getElementById('hazardSearchInput');
        if (hazardSearch) hazardSearch.addEventListener('keyup', function (e) { if (e.key === 'Enter') { _viewLoaded['hazard'] = false; loadHazard(); } });

        // Occurrence filters
        var occRefresh = document.getElementById('occurrenceRefreshBtn');
        if (occRefresh) occRefresh.addEventListener('click', function () { _viewLoaded['occurrence'] = false; loadOccurrence(); });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
