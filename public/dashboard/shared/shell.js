/* ============================================================================
   FILE: shell.js
   PATH: public/dashboard/shared/shell.js
   PHASE: P4-1 (Wave 1 — shared shell behavior)
   PURPOSE: Shared shell for the four role-scoped dashboards
            (DASHBOARD_CONTRACT.md §1 layout blueprint, §6 shared components,
            §7 API contract, §8 visual design system).
   API:
     window.Shell = {
       init(config),        // mount shell with role + tenant
       setActiveNav(key),   // highlight current page
       setPeriod(period),   // dispatch period change event (+ optional dates)
       getPeriod(),         // read current period key
       getPeriodParams(),   // query params honoring P3-14 (period > days)
       onPeriodChange(cb),  // subscribe to period changes (returns unsub)
       showLoading(msg),
       hideLoading(),
       showEmpty(message, cta),
       showError(message, retry),
     }
   init(config) fields:
     { role, roleLabel, tenantName, userEmail, title, modules, activeNav,
       period, customStart, customEnd, navUser, onPeriodChange }
   INTEGRATIONS: Firebase Auth via public/js/firebase.js (getCurrentUser /
     firebase.auth — best-effort, never blocks); data via window.ApiClient
     (public/js/api/client.js — never throws when absent). Nav rendered from
     window.NAV_CONFIG / window.getVisibleNav (public/js/nav-config.js).
   NOTE: No build step. UMD-wrapped so the pure logic is unit-testable in
     Node (frontend-tests/test_shell.js). Does NOT replace the legacy
     public/js/shell.js top-header shell — this is the dashboard-scoped
     sidebar shell used only by the four role dashboards.
   ============================================================================ */
(function (root, factory) {
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = factory();
    } else {
        root.Shell = factory();
    }
}(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    // ---- Period grammar (§7; P3-14) ---------------------------------------
    // Canonical keys: 30d | 90d | 1y | custom. Legacy numeric `days` is
    // preserved for back-compat; `period` takes precedence when both are
    // supplied (P3-14 decision).
    var PERIODS = ['30d', '90d', '1y', 'custom'];

    var PERIOD_DAYS = { '30d': 30, '90d': 90, '1y': 365 };

    function normalizePeriod(key) {
        if (PERIODS.indexOf(key) !== -1) return key;
        return '30d';
    }

    function periodToDays(key) {
        return PERIOD_DAYS[key] || null;
    }

    // ---- State --------------------------------------------------------------
    var state = {
        initialized: false,
        config: {},
        period: '30d',
        customStart: null,
        customEnd: null,
        listeners: [],
        activeNav: null,
    };

    function getDoc() {
        if (typeof document !== 'undefined') return document;
        return null;
    }

    function el(id) {
        var d = getDoc();
        return d ? d.getElementById(id) : null;
    }

    // ---- Period ---------------------------------------------------------------
    function getPeriod() {
        return state.period;
    }

    // Query params for dashboard endpoints: { period, days?, start?, end? }.
    // `period` is always present (canonical); `days` is included for legacy
    // endpoints; custom maps to explicit start/end.
    function getPeriodParams() {
        var params = { period: state.period };
        var days = periodToDays(state.period);
        if (days) {
            params.days = days;
        } else if (state.period === 'custom') {
            if (state.customStart) params.start = state.customStart;
            if (state.customEnd) params.end = state.customEnd;
        }
        return params;
    }

    function emitPeriodChange() {
        var snapshot = {
            period: state.period,
            params: getPeriodParams(),
        };
        state.listeners.slice().forEach(function (cb) {
            try { cb(snapshot); } catch (e) { /* subscriber errors are non-fatal */ }
        });
        var d = getDoc();
        if (d && typeof d.dispatchEvent === 'function' && typeof CustomEvent === 'function') {
            try { d.dispatchEvent(new CustomEvent('dash:period', { detail: snapshot })); } catch (e) {}
        } else if (d && typeof d.dispatchEvent === 'function') {
            try {
                var evt = d.createEvent('CustomEvent');
                evt.initCustomEvent('dash:period', false, false, snapshot);
                d.dispatchEvent(evt);
            } catch (e) {}
        }
        paintPeriodButtons();
    }

    // setPeriod('90d') or setPeriod('custom', { start, end }).
    function setPeriod(period, opts) {
        state.period = normalizePeriod(period);
        if (opts && (opts.start || opts.end)) {
            state.customStart = opts.start || null;
            state.customEnd = opts.end || null;
        }
        emitPeriodChange();
        return state.period;
    }

    function onPeriodChange(cb) {
        if (typeof cb !== 'function') return function () {};
        state.listeners.push(cb);
        return function unsubscribe() {
            var i = state.listeners.indexOf(cb);
            if (i !== -1) state.listeners.splice(i, 1);
        };
    }

    function paintPeriodButtons() {
        var d = getDoc();
        if (!d || !d.querySelectorAll) return;
        var btns = d.querySelectorAll('.dash-period-btn[data-period]');
        Array.prototype.forEach.call(btns, function (b) {
            var active = b.getAttribute('data-period') === state.period;
            b.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        var custom = el('dash-period-custom');
        if (custom) {
            if (custom.hidden !== undefined) custom.hidden = (state.period !== 'custom');
            else custom.style.display = state.period === 'custom' ? '' : 'none';
        }
    }

    // ---- Nav --------------------------------------------------------------------
    function setActiveNav(key) {
        state.activeNav = key || null;
        var d = getDoc();
        if (!d || !d.querySelectorAll) return state.activeNav;
        var links = d.querySelectorAll('.dash-nav-link[data-nav-id]');
        Array.prototype.forEach.call(links, function (a) {
            var on = a.getAttribute('data-nav-id') === state.activeNav;
            if (a.classList) a.classList.toggle('active', on);
            if (on) a.setAttribute('aria-current', 'page');
            else a.removeAttribute('aria-current');
        });
        return state.activeNav;
    }

    function escHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // Render role-based nav from NAV_CONFIG (progressive: falls back to a
    // minimal Dashboard link when nav-config.js is absent, e.g. in tests).
    function renderNav(navUser, moduleAccess) {
        var container = el('dash-nav');
        if (!container) return [];
        var groups = [];
        try {
            if (typeof window !== 'undefined' && window.NAV_CONFIG && typeof window.getVisibleNav === 'function') {
                groups = window.getVisibleNav(navUser || {}, moduleAccess || null) || [];
            }
        } catch (e) { groups = []; }
        if (!groups.length) {
            groups = [{ group: 'Dashboard', icon: 'fa-gauge-high', items: [{ id: 'dashboard', label: 'Dashboard', href: '#' }] }];
        }
        container.innerHTML = groups.map(function (g) {
            var items = (g.items || []).map(function (it) {
                var active = state.activeNav && (it.id === state.activeNav) ? ' active' : '';
                return '<a class="dash-nav-link' + active + '" data-nav-id="' + escHtml(it.id) + '"' +
                    ' href="' + escHtml(it.href || '#') + '">' +
                    '<i class="fa-solid ' + escHtml(it.icon || g.icon || 'fa-circle') + '" aria-hidden="true"></i>' +
                    escHtml(it.label) +
                    (it.badge ? '<span class="dash-nav-dot" aria-label="New"></span>' : '') +
                    '</a>';
            }).join('');
            return '<div class="dash-nav-group" data-nav-group="' + escHtml(g.group) + '">' +
                '<p class="dash-nav-group-title"><i class="fa-solid ' + escHtml(g.icon || 'fa-circle') +
                '" aria-hidden="true"></i>' + escHtml(g.group) + '</p>' + items + '</div>';
        }).join('');
        return groups;
    }

    // ---- Overlays ---------------------------------------------------------------
    function showOverlay(id, others) {
        [el('dash-loading'), el('dash-empty'), el('dash-error')].forEach(function (node, i) {
            if (!node) return;
            var show = (['dash-loading', 'dash-empty', 'dash-error'][i] === id);
            if (node.hidden !== undefined) node.hidden = !show;
            else node.style.display = show ? '' : 'none';
        });
    }

    function showLoading(message) {
        var text = el('dash-loading-text');
        if (text) text.textContent = message || 'Loading…';
        showOverlay('dash-loading');
    }

    function hideLoading() {
        var node = el('dash-loading');
        if (!node) return;
        if (node.hidden !== undefined) node.hidden = true;
        else node.style.display = 'none';
    }

    // showEmpty(message, cta) — cta: { label, url } | null.
    // Copy convention per §6: neutral message, e.g. EIP `None`-style states.
    function showEmpty(message, cta) {
        var node = el('dash-empty');
        if (node) {
            var html = '<div class="dash-empty-illus" aria-hidden="true">📭</div>' +
                '<p class="dash-empty-title">No data</p>' +
                '<p class="dash-empty-sub">' + escHtml(message || 'Nothing to show for this period.') + '</p>';
            if (cta && cta.label) {
                html += '<a class="dash-btn dash-btn-primary" href="' + escHtml(cta.url || '#') + '">' +
                    escHtml(cta.label) + '</a>';
            }
            node.innerHTML = html;
        }
        showOverlay('dash-empty');
    }

    // showError(message, retry) — retry: function | null. Non-blocking per
    // panel (§6): shows a per-shell error box, never a blank page.
    function showError(message, retry) {
        var node = el('dash-error');
        if (node) {
            var rid = 'dash-retry-' + Date.now();
            node.innerHTML = '<div class="dash-error-box" role="alert">' +
                '<strong>Something went wrong.</strong> ' + escHtml(message || 'Please try again.') +
                (typeof retry === 'function'
                    ? ' <button type="button" class="dash-btn dash-btn-small" id="' + rid + '">Retry</button>'
                    : '') +
                '</div>';
            if (typeof retry === 'function') {
                var btn = el(rid);
                if (btn && btn.addEventListener) btn.addEventListener('click', retry);
                else if (btn) btn.onclick = retry;
            }
        }
        showOverlay('dash-error');
        // Auto-register the retry handler for shim DOMs without addEventListener.
        if (typeof retry === 'function') state._lastRetry = retry;
        else state._lastRetry = null;
    }

    function clearOverlays() {
        [el('dash-loading'), el('dash-empty'), el('dash-error')].forEach(function (node) {
            if (!node) return;
            if (node.hidden !== undefined) node.hidden = true;
            else node.style.display = 'none';
        });
    }

    // ---- Header -------------------------------------------------------------------
    function moduleBadgesHtml(modules) {
        if (!modules || typeof modules !== 'object') return '';
        var out = [];
        if (modules.module_a_survey) out.push('<span class="dash-module-badge mod-a" title="Module A — Survey">A</span>');
        if (modules.module_b_srm || modules.module_b_can_cap) out.push('<span class="dash-module-badge mod-b" title="Module B — Hazard & Risk">B</span>');
        if (modules.module_c_regulator) out.push('<span class="dash-module-badge mod-c" title="Module C — Regulator">C</span>');
        return out.join('');
    }

    function paintHeader(cfg) {
        var set = function (id, text) {
            var n = el(id);
            if (n) n.textContent = text;
        };
        set('dash-role-badge', cfg.roleLabel || cfg.role || 'Dashboard');
        set('dash-tenant-name', cfg.tenantName || '—');
        set('dash-user-email', cfg.userEmail || '—');
        if (cfg.title) set('dash-title', cfg.title);
        var badges = el('dash-module-badges');
        if (badges) badges.innerHTML = moduleBadgesHtml(cfg.modules);
    }

    function bindChrome() {
        var d = getDoc();
        if (!d) return;
        // Period buttons.
        if (d.querySelectorAll) {
            Array.prototype.forEach.call(d.querySelectorAll('.dash-period-btn[data-period]'), function (b) {
                var handler = function () { setPeriod(b.getAttribute('data-period')); };
                if (b.addEventListener) b.addEventListener('click', handler);
                else b.onclick = handler;
            });
        }
        var apply = el('dash-period-apply');
        if (apply) {
            var onApply = function () {
                var s = el('dash-period-start'), e = el('dash-period-end');
                setPeriod('custom', {
                    start: s && s.value ? s.value : null,
                    end: e && e.value ? e.value : null,
                });
            };
            if (apply.addEventListener) apply.addEventListener('click', onApply);
            else apply.onclick = onApply;
        }
        // Mobile nav toggle.
        var toggle = el('dash-nav-toggle');
        if (toggle) {
            var onToggle = function () {
                var body = d.querySelector('.dash-body');
                if (!body || !body.classList) return;
                body.classList.toggle('nav-open');
                toggle.setAttribute('aria-expanded', body.classList.contains('nav-open') ? 'true' : 'false');
            };
            if (toggle.addEventListener) toggle.addEventListener('click', onToggle);
            else toggle.onclick = onToggle;
        }
        var scrim = el('dash-sidebar-scrim');
        if (scrim) {
            var close = function () {
                var body = d.querySelector('.dash-body');
                if (body && body.classList) body.classList.remove('nav-open');
            };
            if (scrim.addEventListener) scrim.addEventListener('click', close);
            else scrim.onclick = close;
        }
        // Logout (Firebase best-effort; falls back to /login.html).
        var logout = el('dash-logout-btn');
        if (logout && !logout.__shellBound) {
            logout.__shellBound = true;
            var onLogout = function () {
                try {
                    if (typeof window !== 'undefined' && typeof window.handleLogout === 'function') {
                        window.handleLogout();
                        return;
                    }
                    if (typeof firebase !== 'undefined' && firebase.auth) {
                        firebase.auth().signOut().then(function () {
                            window.location.href = '/login.html';
                        }).catch(function () {
                            window.location.href = '/login.html';
                        });
                        return;
                    }
                } catch (e) {}
                if (typeof window !== 'undefined' && window.location) window.location.href = '/login.html';
            };
            if (logout.addEventListener) logout.addEventListener('click', onLogout);
            else logout.onclick = onLogout;
        }
    }

    // Best-effort identity fill from Firebase Auth (existing
    // public/js/firebase.js). Never blocks shell paint.
    function fillIdentityAsync(cfg) {
        try {
            var done = function (email) {
                if (email && !cfg.userEmail) {
                    var n = el('dash-user-email');
                    if (n) n.textContent = email;
                }
            };
            if (typeof window !== 'undefined' && typeof window.getCurrentUser === 'function') {
                window.getCurrentUser().then(function (u) {
                    if (u && u.email) done(u.email);
                }).catch(function () {});
                return;
            }
            if (typeof firebase !== 'undefined' && firebase.auth) {
                firebase.auth().onAuthStateChanged(function (user) {
                    if (user && user.email) done(user.email);
                });
            }
        } catch (e) { /* non-fatal */ }
    }

    // ---- init -----------------------------------------------------------------------
    // Mounts header/sidebar/period state. Idempotent per page load.
    function init(config) {
        config = config || {};
        state.config = config;
        state.period = normalizePeriod(config.period || state.period || '30d');
        state.customStart = config.customStart || null;
        state.customEnd = config.customEnd || null;
        if (config.activeNav) state.activeNav = config.activeNav;
        if (typeof config.onPeriodChange === 'function') onPeriodChange(config.onPeriodChange);

        paintHeader(config);
        renderNav(config.navUser || { role: config.role }, config.modules || null);
        if (state.activeNav) setActiveNav(state.activeNav);
        paintPeriodButtons();
        bindChrome();
        fillIdentityAsync(config);
        state.initialized = true;
        return {
            period: state.period,
            activeNav: state.activeNav,
        };
    }

    function resetForTests() {
        state.initialized = false;
        state.config = {};
        state.period = '30d';
        state.customStart = null;
        state.customEnd = null;
        state.listeners = [];
        state.activeNav = null;
        state._lastRetry = null;
    }

    return {
        init: init,
        setActiveNav: setActiveNav,
        setPeriod: setPeriod,
        getPeriod: getPeriod,
        getPeriodParams: getPeriodParams,
        onPeriodChange: onPeriodChange,
        showLoading: showLoading,
        hideLoading: hideLoading,
        showEmpty: showEmpty,
        showError: showError,
        clearOverlays: clearOverlays,
        renderNav: renderNav,
        normalizePeriod: normalizePeriod,
        periodToDays: periodToDays,
        _resetForTests: resetForTests,
        _state: state,
    };
}));
