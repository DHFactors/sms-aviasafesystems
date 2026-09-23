/* ============================================================================
   FILE: drilldown.js
   PATH: public/dashboard/shared/drilldown.js
   PHASE: P4-1 (Wave 1 — shared drill-down pattern)
   PURPOSE: Three-level drill-down shared by all four dashboards
            (DASHBOARD_CONTRACT.md §6):
              Level 1: KPI counter (e.g. Hazards: 128)
              Level 2: Status breakdown (Open / In Process / Closed)
              Level 3: Record list (the underlying records)
            Preserves the active period + filters across levels.
   API:
     window.DrillDown = {
       mount(container, { metric, breakdownEndpoint, recordsEndpoint }),
       render(level1Data),   // KPI counter → status breakdown
       drill(statusKey),     // status → records
       back(),               // one level up
     }
   DATA CONTRACT: all fetches go through window.ApiClient
     (public/js/api/client.js) and expect the standard envelope
     { status, timestamp, data } (routes/dashboard.py:26-31). Raw arrays
     are tolerated (unwrapped defensively) so missing endpoints degrade
     to empty states instead of throwing (P4-7).
   STATUS BUCKETS (§2.4): Open / In Process / Closed. Raw statuses map:
     Open → Open; Processing / Under Review / Pending Closure / Reopened /
     Revision Required / In Progress → In Process; Closed / Completed →
     Closed; Overdue → Open (attention). Unknown strings fall to In Process.
   NOTE: No build step. UMD-wrapped for Node unit tests.
   ============================================================================ */
(function (root, factory) {
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = factory();
    } else {
        root.DrillDown = factory();
    }
}(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    var BUCKETS = ['Open', 'In Process', 'Closed'];

    // Raw status → bucket mapping (§2.4).
    function toBucket(status) {
        var s = String(status == null ? '' : status).trim().toLowerCase();
        if (!s) return 'In Process';
        if (s === 'open' || s === 'received' || s === 'overdue' || s === 'escalated' || s === 'eip') return 'Open';
        if (s === 'closed' || s === 'completed') return 'Closed';
        return 'In Process';
    }

    function escHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // Unwrap the API envelope { status, timestamp, data }; tolerate raw
    // arrays/objects so panels degrade gracefully (P4-7: never throw on a
    // missing endpoint).
    function unwrap(body) {
        if (body == null) return null;
        if (Array.isArray(body)) return body;
        if (typeof body === 'object' && body.data !== undefined) return body.data;
        return body;
    }

    function bucketize(records, statusField) {
        var counts = { 'Open': 0, 'In Process': 0, 'Closed': 0 };
        var field = statusField || 'status';
        (records || []).forEach(function (r) {
            var b = toBucket(r ? r[field] : null);
            if (counts[b] === undefined) counts[b] = 0;
            counts[b] += 1;
        });
        return counts;
    }

    // ---- Instance ------------------------------------------------------------
    function create(container, opts) {
        opts = opts || {};
        var st = {
            container: container || null,
            metric: opts.metric || 'Records',
            breakdownEndpoint: opts.breakdownEndpoint || null,
            recordsEndpoint: opts.recordsEndpoint || null,
            statusField: opts.statusField || 'status',
            level: 1,
            level1: null,
            breakdown: null,
            records: [],
            activeBucket: null,
            period: opts.period || '30d',
        };

        function html(str) {
            if (!st.container) return;
            st.container.innerHTML = str;
        }

        function crumbHtml(trail) {
            return '<div class="dash-drill-crumb">' +
                trail.map(function (t, i) {
                    if (i < trail.length - 1) {
                        return '<button type="button" data-drill-back="' + i + '">' +
                            escHtml(t) + '</button><span aria-hidden="true">›</span>';
                    }
                    return '<span>' + escHtml(t) + '</span>';
                }).join('') +
                '</div>';
        }

        function bind() {
            if (!st.container || !st.container.querySelectorAll) return;
            Array.prototype.forEach.call(
                st.container.querySelectorAll('[data-drill-bucket]'), function (b) {
                    var go = function () { drill(b.getAttribute('data-drill-bucket')); };
                    if (b.addEventListener) b.addEventListener('click', go);
                    else b.onclick = go;
                });
            Array.prototype.forEach.call(
                st.container.querySelectorAll('[data-drill-back]'), function (b) {
                    var go = function () { backTo(parseInt(b.getAttribute('data-drill-back'), 10)); };
                    if (b.addEventListener) b.addEventListener('click', go);
                    else b.onclick = go;
                });
        }

        // Level 1: KPI counter. level1Data: { total } | number | records array.
        function render(level1Data) {
            st.level = 1;
            st.level1 = level1Data;
            var total = 0;
            if (typeof level1Data === 'number') total = level1Data;
            else if (Array.isArray(level1Data)) total = level1Data.length;
            else if (level1Data && typeof level1Data.total === 'number') total = level1Data.total;
            html('<div class="dash-drill" data-level="1">' +
                '<div class="dash-kpi clickable" data-drill-total="1" role="button" tabindex="0"' +
                ' aria-label="' + escHtml(st.metric) + ' total: ' + total + '. Activate for breakdown.">' +
                '<div class="dash-kpi-value">' + total + '</div>' +
                '<div class="dash-kpi-label">' + escHtml(st.metric) + '</div>' +
                '<div class="dash-kpi-sub">Select for status breakdown</div>' +
                '</div></div>');
            // Clicking the counter advances to the breakdown.
            if (st.container && st.container.querySelector) {
                var card = st.container.querySelector('[data-drill-total]');
                if (card) {
                    var go = function () { drill(null); };
                    if (card.addEventListener) card.addEventListener('click', go);
                    else card.onclick = go;
                }
            }
            return total;
        }

        function paintBreakdown(counts) {
            st.level = 2;
            st.breakdown = counts;
            var total = BUCKETS.reduce(function (a, b) { return a + (counts[b] || 0); }, 0);
            html('<div class="dash-drill" data-level="2">' +
                crumbHtml([st.metric + ' (' + total + ')', 'Status breakdown']) +
                '<div class="dash-breakdown">' +
                BUCKETS.map(function (b) {
                    return '<div class="dash-breakdown-bucket" data-drill-bucket="' + escHtml(b) + '"' +
                        ' role="button" tabindex="0">' +
                        '<div class="num">' + (counts[b] || 0) + '</div>' +
                        '<div class="lbl">' + escHtml(b) + '</div></div>';
                }).join('') +
                '</div></div>');
            bind();
            return counts;
        }

        function paintRecords(bucket, records) {
            st.level = 3;
            st.activeBucket = bucket;
            st.records = records || [];
            var rows = st.records.map(function (r) {
                var title = (r && (r.title || r.reference || r.ref || r.name || r.id)) || '—';
                var status = (r && r[st.statusField]) || bucket || '—';
                return '<tr><td>' + escHtml(title) + '</td><td>' + escHtml(status) + '</td></tr>';
            }).join('') || '<tr><td colspan="2" class="empty">No records in this bucket.</td></tr>';
            html('<div class="dash-drill" data-level="3">' +
                crumbHtml([st.metric, 'Status breakdown', bucket || 'Records']) +
                '<table class="dash-table"><thead><tr><th>Record</th><th>Status</th></tr></thead>' +
                '<tbody>' + rows + '</tbody></table></div>');
            bind();
            return st.records;
        }

        function paintEmpty(message) {
            html('<div class="dash-drill" data-level="' + st.level + '">' +
                '<div class="empty">' + escHtml(message || 'No data for this period.') + '</div></div>');
        }

        function apiGet(endpoint, params) {
            try {
                if (typeof window !== 'undefined' && window.ApiClient && typeof window.ApiClient.get === 'function') {
                    var path = endpoint;
                    if (params && typeof params === 'object') {
                        var qs = Object.keys(params)
                            .filter(function (k) { return params[k] != null && params[k] !== ''; })
                            .map(function (k) { return encodeURIComponent(k) + '=' + encodeURIComponent(params[k]); })
                            .join('&');
                        if (qs) path += (path.indexOf('?') === -1 ? '?' : '&') + qs;
                    }
                    return window.ApiClient.get(path).then(function (body) { return unwrap(body); });
                }
            } catch (e) { /* fall through to empty */ }
            return Promise.resolve(null);
        }

        // Level 1 → 2. When statusKey is null, derives the breakdown from the
        // breakdown endpoint (or client-side bucketing of level-1 records).
        function drill(statusKey) {
            if (statusKey) {
                var wanted = toBucket(statusKey) === statusKey ? statusKey : toBucket(statusKey);
                // Normalize: callers may pass a raw status; bucket it.
                var bucket = BUCKETS.indexOf(statusKey) !== -1 ? statusKey : toBucket(statusKey);
                var params = { status: bucket };
                if (st.period) params.period = st.period;
                return apiGet(st.recordsEndpoint, params).then(function (data) {
                    var records = Array.isArray(data) ? data
                        : (data && Array.isArray(data.records)) ? data.records
                        : (data && Array.isArray(data.items)) ? data.items : [];
                    // Client-side fallback: filter level-1 records by bucket.
                    if (!records.length && Array.isArray(st.level1)) {
                        records = st.level1.filter(function (r) { return toBucket(r && r[st.statusField]) === bucket; });
                    }
                    paintRecords(bucket, records);
                    return records;
                }).catch(function () {
                    paintRecords(bucket, []);
                    return [];
                });
            }
            var bparams = {};
            if (st.period) bparams.period = st.period;
            return apiGet(st.breakdownEndpoint, bparams).then(function (data) {
                if (data && (data.by_status || data.byStatus || data.breakdown)) {
                    var raw = data.by_status || data.byStatus || data.breakdown;
                    var counts = { 'Open': 0, 'In Process': 0, 'Closed': 0 };
                    Object.keys(raw).forEach(function (k) {
                        counts[toBucket(k)] += (Number(raw[k]) || 0);
                    });
                    paintBreakdown(counts);
                    return counts;
                }
                if (Array.isArray(data)) {
                    var c = bucketize(data, st.statusField);
                    paintBreakdown(c);
                    return c;
                }
                if (Array.isArray(st.level1)) {
                    var c2 = bucketize(st.level1, st.statusField);
                    paintBreakdown(c2);
                    return c2;
                }
                var zero = { 'Open': 0, 'In Process': 0, 'Closed': 0 };
                paintBreakdown(zero);
                return zero;
            }).catch(function () {
                paintEmpty('Breakdown unavailable.');
                return { 'Open': 0, 'In Process': 0, 'Closed': 0 };
            });
        }

        function backTo(index) {
            if (index <= 0) {
                render(st.level1);
                return 1;
            }
            if (st.breakdown) {
                paintBreakdown(st.breakdown);
                return 2;
            }
            render(st.level1);
            return 1;
        }

        function back() {
            if (st.level >= 3) {
                if (st.breakdown) { paintBreakdown(st.breakdown); return 2; }
                render(st.level1);
                return 1;
            }
            if (st.level === 2) { render(st.level1); return 1; }
            return 1;
        }

        function setPeriod(period) {
            st.period = period || st.period;
        }

        return {
            render: render,
            drill: drill,
            back: back,
            backTo: backTo,
            setPeriod: setPeriod,
            _state: st,
        };
    }

    // Default singleton mount (spec shape): DrillDown.mount(container, opts).
    var current = null;

    function mount(container, opts) {
        current = create(container, opts);
        return current;
    }

    function render(level1Data) {
        if (!current) current = create(null, {});
        return current.render(level1Data);
    }

    function drill(statusKey) {
        if (!current) current = create(null, {});
        return current.drill(statusKey);
    }

    function back() {
        if (!current) return 1;
        return current.back();
    }

    return {
        mount: mount,
        render: render,
        drill: drill,
        back: back,
        create: create,
        toBucket: toBucket,
        bucketize: bucketize,
        unwrap: unwrap,
        BUCKETS: BUCKETS,
    };
}));
