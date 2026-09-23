/* ============================================================================
   FILE: module-flag.js
   PATH: public/dashboard/shared/module-flag.js
   PHASE: P4-7 (Wave 1 — module flag degradation)
   PURPOSE: Graceful degradation when a tenant does not have a module flag
            (DASHBOARD_CONTRACT.md §9; RBAC_MODEL.md §3):
              - hide nav items for that module (via nav-config.js gating)
              - show a graceful empty state on direct page access
              - never throw from missing endpoints
   API:
     window.ModuleFlag = {
       has(flag),        // read from tenant config (cached)
       requires(flag),   // guard: true when enabled; else paints empty state
       set(flags),       // seed/replace the cache (tenant switch, API fetch)
       refresh(),        // re-fetch flags from the tenant config endpoint
       clear(),          // drop the cache (logout / tenant switch)
       onChange(cb),     // subscribe to flag updates (returns unsub)
     }
   CANONICAL FLAGS (RBAC decision Q-R5; DASHBOARD_CONTRACT.md §9):
     module_a_survey, module_b_srm, module_b_can_cap, module_c_regulator
   LEGACY KEYS (tolerated, mapped): module1 → module_a_survey,
     module2 → module_b_srm (+ module_b_can_cap subset — see below),
     module3/module4 → module_c_regulator; module_access / modules bags.
   Q-D7 / Q-R6 NOTE: `module_b_can_cap` has no independent add-on flag in
     the backend, so it is treated as a SUBSET of `module_b_srm`: a tenant
     with module_b_srm has CAN/CAP unless an explicit
     module_b_can_cap:false opt-out is present. This keeps the canonical
     name usable in nav gating today without inventing a backend flag.
   CACHE: sessionStorage `dash:module-flags` (+ per-tenant key). Refreshed
     on tenant switch; non-fatal when storage is unavailable.
   USAGE (each dashboard page):
     if (!window.ModuleFlag.requires('module_b_srm', { container, moduleName })) return;
     // ... load() logic only runs when the flag is on.
   NOTE: No build step. UMD-wrapped for Node unit tests.
   ============================================================================ */
(function (root, factory) {
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = factory();
    } else {
        root.ModuleFlag = factory();
    }
}(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    // Canonical flags (Q-R5).
    var CANONICAL = [
        'module_a_survey',
        'module_b_srm',
        'module_b_can_cap',
        'module_c_regulator',
    ];

    var MODULE_NAMES = {
        module_a_survey: 'Survey / SMS Health',
        module_b_srm: 'Hazard & Risk (SRM)',
        module_b_can_cap: 'CAN / CAP',
        module_c_regulator: 'Regulator / PSOE',
    };

    // Legacy numeric → canonical (DISCOVERY_REPORT.md:61; RBAC §3).
    var LEGACY_MAP = {
        module1: 'module_a_survey',
        module_1: 'module_a_survey',
        module2: 'module_b_srm',
        module_2: 'module_b_srm',
        module3: 'module_c_regulator',
        module_3: 'module_c_regulator',
        module4: 'module_c_regulator',
        module_4: 'module_c_regulator',
    };

    var CACHE_KEY = 'dash:module-flags';

    var cache = null; // { flag: bool }
    var listeners = [];

    function store() {
        try {
            if (typeof sessionStorage !== 'undefined') return sessionStorage;
        } catch (e) {}
        return null;
    }

    function truthy(v) {
        return v === true || v === 'true' || v === 1 || v === '1';
    }

    function normalizeBag(bag) {
        var out = {};
        if (!bag || typeof bag !== 'object') return out;
        // Unwrap common envelopes: { module_access: {...} }, { modules: {...} }.
        var src = bag;
        if (src.module_access && typeof src.module_access === 'object') src = src.module_access;
        else if (src.modules && typeof src.modules === 'object') {
            // Merge both levels: explicit canonical keys win.
            var merged = {};
            Object.keys(src.modules).forEach(function (k) { merged[k] = src.modules[k]; });
            Object.keys(src).forEach(function (k) {
                if (k !== 'modules' && k !== 'module_access') merged[k] = src[k];
            });
            src = merged;
        }
        Object.keys(src).forEach(function (k) {
            if (k === 'modules' || k === 'module_access') return;
            var canon = LEGACY_MAP[k] || k;
            if (CANONICAL.indexOf(canon) !== -1) out[canon] = truthy(src[k]);
        });
        // module_b_can_cap subset rule (Q-R6): inherits module_b_srm unless
        // an explicit opt-out (false) is present.
        if (out.module_b_can_cap === undefined && out.module_b_srm !== undefined) {
            out.module_b_can_cap = !!out.module_b_srm;
        }
        return out;
    }

    function emit() {
        var snap = cache ? JSON.parse(JSON.stringify(cache)) : null;
        listeners.slice().forEach(function (cb) {
            try { cb(snap); } catch (e) {}
        });
    }

    function persist() {
        var s = store();
        if (!s || !cache) return;
        try { s.setItem(CACHE_KEY, JSON.stringify(cache)); } catch (e) {}
    }

    function restore() {
        if (cache) return cache;
        var s = store();
        if (s) {
            try {
                var raw = s.getItem(CACHE_KEY);
                if (raw) {
                    var parsed = JSON.parse(raw);
                    if (parsed && typeof parsed === 'object') {
                        cache = normalizeBag(parsed);
                        return cache;
                    }
                }
            } catch (e) {}
        }
        return null;
    }

    // Seed or replace the cache (tenant switch, API fetch, claims).
    function set(flags) {
        cache = normalizeBag(flags || {});
        persist();
        emit();
        return cache;
    }

    function clear() {
        cache = null;
        var s = store();
        if (s) {
            try { s.removeItem(CACHE_KEY); } catch (e) {}
        }
        emit();
    }

    // Read a flag from the cache. Unknown / uncached → false (fail-closed
    // for gating; pages show the §9 empty state rather than erroring).
    // SUPER_ADMIN / cross-tenant preview bypass: set(flags, { bypass: true })
    // is NOT implicit — callers pass opts.bypass explicitly.
    function has(flag, opts) {
        if (opts && opts.bypass) return true;
        var c = cache || restore();
        if (!c) return false;
        var canon = LEGACY_MAP[flag] || flag;
        if (canon === 'module_b_can_cap' && c.module_b_can_cap === undefined) {
            return !!c.module_b_srm;
        }
        return !!c[canon];
    }

    function moduleDisplayName(flag) {
        var canon = LEGACY_MAP[flag] || flag;
        return MODULE_NAMES[canon] || String(flag);
    }

    // Guard for dashboard load() logic. Returns true when the flag is on.
    // When off: paints the §9 empty state into opts.container (or the
    // shell #dash-empty overlay) and returns false. Never throws.
    function requires(flag, opts) {
        opts = opts || {};
        if (has(flag, opts)) return true;
        var message = 'Contact your tenant administrator to enable ' +
            moduleDisplayName(flag) + '.';
        try {
            if (typeof window !== 'undefined' && window.EmptyState &&
                typeof window.EmptyState.noModule === 'function') {
                window.EmptyState.noModule(moduleDisplayName(flag), message, opts.container || null);
                // EmptyState.noModule without a container returns HTML only —
                // fall through to the shell overlay so something is visible.
                var overlay = (typeof document !== 'undefined')
                    ? document.getElementById('dash-empty') : null;
                if (!opts.container && overlay) {
                    window.EmptyState.noModule(moduleDisplayName(flag), message, overlay);
                    overlay.hidden = false;
                } else if (!opts.container && overlay === null && typeof document !== 'undefined') {
                    // Shell overlay markup not on this page — no-op, caller
                    // receives false and renders its own state.
                }
            } else if (opts.container) {
                opts.container.innerHTML =
                    '<div class="dash-empty" role="status">' +
                    '<div class="dash-empty-illus" aria-hidden="true">🧩</div>' +
                    '<p class="dash-empty-title">This module is not enabled</p>' +
                    '<p class="dash-empty-sub">' + message.replace(/</g, '&lt;') + '</p>' +
                    '<a class="dash-btn dash-btn-primary" href="/safety.html">Back to Dashboard</a></div>';
            }
        } catch (e) { /* never throw from a guard */ }
        return false;
    }

    // Re-fetch flags from the tenant config endpoint (authoritative Postgres
    // tenant doc; same channel as shell.js refreshModulesFromApi). Non-fatal.
    function refresh(tenantId) {
        var tid = tenantId || null;
        try {
            if (typeof window !== 'undefined' && window.TenantResolver &&
                typeof window.TenantResolver.getCurrentTenant === 'function' && !tid) {
                tid = window.TenantResolver.getCurrentTenant();
            }
        } catch (e) {}
        if (!tid) return Promise.resolve(cache);
        var fetchFn = (typeof window !== 'undefined' && window.fetch) ? window.fetch
            : (typeof fetch !== 'undefined' ? fetch : null);
        if (!fetchFn) return Promise.resolve(cache);
        var getToken = function () {
            try {
                if (typeof firebase !== 'undefined' && firebase.auth && firebase.auth().currentUser) {
                    return firebase.auth().currentUser.getIdToken(false);
                }
            } catch (e) {}
            return Promise.resolve(null);
        };
        return getToken().then(function (token) {
            var headers = {};
            if (token) headers.Authorization = 'Bearer ' + token;
            return fetchFn('/api/v1/tenants/' + encodeURIComponent(tid), { headers: headers });
        }).then(function (resp) {
            if (!resp || !resp.ok) return cache;
            return resp.json();
        }).then(function (body) {
            if (!body) return cache;
            var data = (body.data !== undefined) ? body.data : body;
            var bag = (data && (data.module_access || data.modules)) || data || {};
            set(bag);
            return cache;
        }).catch(function () {
            return cache; // non-fatal: keep previous gating
        });
    }

    function onChange(cb) {
        if (typeof cb !== 'function') return function () {};
        listeners.push(cb);
        return function unsubscribe() {
            var i = listeners.indexOf(cb);
            if (i !== -1) listeners.splice(i, 1);
        };
    }

    function _resetForTests() {
        cache = null;
        listeners = [];
    }

    return {
        has: has,
        requires: requires,
        set: set,
        refresh: refresh,
        clear: clear,
        onChange: onChange,
        moduleDisplayName: moduleDisplayName,
        CANONICAL: CANONICAL,
        MODULE_NAMES: MODULE_NAMES,
        _resetForTests: _resetForTests,
        _normalizeBag: normalizeBag,
    };
}));
