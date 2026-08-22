// ============================================================================
// FILE: public/js/demo-analytics.js
// PURPOSE: Demo session analytics tracker (Chunk 7).
//
// Tracks prospect AE behaviour during Virtual Tenant Mirroring demos and
// flushes events to /api/v1/demo/analytics/batch (persisted under
// demo_analytics/{email}/events by the backend).
//
// Tracked signals:
//   login_time, session_duration (60s heartbeat), pages_viewed,
//   time_per_panel (IntersectionObserver dwell on .panel elements),
//   features_used, decisions_made, simulator_uses, exports_triggered,
//   switch_event (Quick-Switch toolbar archetype changes).
//
// SAFE FALLBACK: tracking activates ONLY for registered demo AE accounts
// (ae@* present in PROSPECT_REGISTRY with a mirroring context). Standard
// tenants are never tracked; network failures queue locally and retry.
// ============================================================================

(function () {
    'use strict';

    var QUEUE_KEY = 'demoAnalyticsQueue';
    var FLUSH_INTERVAL_MS = 20000;
    var HEARTBEAT_MS = 60000;
    var SIM_THROTTLE_MS = 5000;

    var state = {
        active: false,
        email: null,
        loginTime: null,
        queue: [],
        features: {},
        panelDwell: {},
        lastSim: 0,
        timer: null,
        heartbeat: null,
        observer: null,
    };

    function ctx() {
        return (window.DEMO_CONTEXT || window.getStoredDemoContext && window.getStoredDemoContext()) || null;
    }

    function eligible() {
        var dp = window.DEMO_PROSPECTS;
        var c = ctx();
        return !!(dp && c && c.email && dp.getArchetypeId(c.email));
    }

    function nowIso() { return new Date().toISOString(); }

    function track(eventType, payload) {
        if (!state.active) return;
        state.queue.push({
            event_type: eventType,
            payload: payload || {},
            created_at: nowIso(),
        });
        if (eventType === 'feature_used' && payload && payload.name) {
            state.features[payload.name] = (state.features[payload.name] || 0) + 1;
        }
    }

    function flush() {
        if (!state.active || !state.queue.length) return;
        var batch = state.queue.splice(0, state.queue.length);
        fetch('/api/v1/demo/analytics/batch', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + (window.__demoIdToken || ''),
            },
            body: JSON.stringify({
                email: state.email,
                events: batch.map(function (e) {
                    return { event_type: e.event_type, payload: e.payload, created_at: e.created_at };
                }),
            }),
        }).catch(function () {
            // Re-queue on failure (bounded to avoid unbounded growth).
            state.queue = batch.concat(state.queue).slice(-500);
        });
    }

    function heartbeat() {
        if (!state.active) return;
        var durationSec = Math.round((Date.now() - state.loginTime) / 1000);
        track('session_duration', {
            seconds: durationSec,
            pages_viewed: Object.keys(state.panelDwell).length ? undefined : undefined,
            features_used: Object.keys(state.features),
        });
        track('pages_viewed', { page: window.location.pathname });
        flush();
    }

    function initPanelObserver() {
        if (!window.IntersectionObserver) return;
        state.observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                var key = entry.target.getAttribute('data-panel-key') ||
                    (entry.target.querySelector('h2') || {}).textContent ||
                    entry.target.id || ('panel-' + Math.random());
                if (entry.isIntersecting) {
                    state.panelDwell[key] = Date.now();
                    track('pages_viewed', { panel: key });
                } else if (state.panelDwell[key]) {
                    var dwell = Date.now() - state.panelDwell[key];
                    if (dwell > 1500) track('time_per_panel', { panel: key, ms: dwell });
                    delete state.panelDwell[key];
                }
            });
        }, { threshold: 0.35 });
        document.querySelectorAll('.panel').forEach(function (p) {
            p.setAttribute('data-panel-key', p.getAttribute('data-panel-key') ||
                (p.querySelector('h2') || {}).textContent || p.id);
            state.observer.observe(p);
        });
    }

    function initDemoSwitchListener() {
        // Fired by the Quick-Switch toolbar in firebase.js.
        document.addEventListener('demoSwitch', function (ev) {
            var d = (ev.detail || {});
            track('switch_event', {
                from: d.from || null,
                to: d.to || null,
                from_company: d.fromCompany || null,
                to_company: d.toCompany || null,
                timestamp: nowIso(),
            });
            flush();
        });
    }

    function init(opts) {
        opts = opts || {};
        try {
            var c = ctx();
            if (!eligible()) return false;
            state.active = true;
            state.email = c.email;
            state.loginTime = Date.now();

            track('login_time', { email: c.email, archetype_id: c.archetypeId, at: nowIso() });

            state.timer = setInterval(flush, FLUSH_INTERVAL_MS);
            state.heartbeat = setInterval(heartbeat, HEARTBEAT_MS);
            initPanelObserver();
            initDemoSwitchListener();

            window.addEventListener('beforeunload', function () {
                track('session_duration', {
                    seconds: Math.round((Date.now() - state.loginTime) / 1000),
                    final: true,
                });
                flush();
            });

            if (opts.onReady) opts.onReady(state);
            return true;
        } catch (e) {
            console.warn('[demo-analytics] init failed:', e);
            return false;
        }
    }

    // ── Public API ─────────────────────────────────────────────────────────
    window.DemoAnalytics = {
        init: init,
        track: track,
        flush: flush,
        isActive: function () { return state.active; },

        // Convenience wrappers used across AE surfaces.
        decisionMade: function (decision, capRef) {
            track('decisions_made', { decision: decision, cap_reference: capRef || null });
            flush();
        },
        simulatorUse: function (payload) {
            var t = Date.now();
            if (t - state.lastSim < SIM_THROTTLE_MS) return;
            state.lastSim = t;
            track('simulator_uses', payload || {});
        },
        exportTriggered: function (format, what) {
            track('exports_triggered', { format: format, what: what || null });
            flush();
        },
        featureUsed: function (name) { track('feature_used', { name: name }); },
    };
})();
