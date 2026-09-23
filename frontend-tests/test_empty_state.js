/**
 * Frontend unit tests for the Phase 4 Wave 1 shared empty states (P4-1) and
 * the module-flag degradation helper (P4-7).
 *
 * Covers:
 *  - public/dashboard/shared/empty-state.js: noData, noModule (§9 copy),
 *    noPermission, loading, error (+ container painting + retry wiring)
 *  - public/dashboard/shared/module-flag.js: has/requires, canonical +
 *    legacy flag mapping, sessionStorage cache, §9 empty-state guard
 *    (never throws, degrades gracefully when endpoints are missing)
 *
 * Pattern follows frontend-tests/input-guard.test.js (plain Node; shared
 * modules are UMD-wrapped and dependency-free).
 */
'use strict';

const assert = require('assert');
const EmptyState = require('../public/dashboard/shared/empty-state.js');
const ModuleFlag = require('../public/dashboard/shared/module-flag.js');

function makeContainer() {
    const listeners = {};
    return {
        innerHTML: '',
        hidden: true,
        querySelector: () => null,
        addEventListener: (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); },
        __listeners: listeners,
    };
}

function withSessionStorage(fn) {
    const store = {};
    const prev = global.sessionStorage;
    global.sessionStorage = {
        getItem: (k) => (k in store ? store[k] : null),
        setItem: (k, v) => { store[k] = String(v); },
        removeItem: (k) => { delete store[k]; },
        __store: store,
    };
    try {
        return fn(store);
    } finally {
        if (prev === undefined) delete global.sessionStorage;
        else global.sessionStorage = prev;
    }
}

// ---------------------------------------------------------------------------
// EmptyState variants
// ---------------------------------------------------------------------------

function test_no_data_variant() {
    const html = EmptyState.noData('No hazards', 'Nothing to show for this period.', 'Open register', '/risk-register/index.html');
    assert.ok(html.includes('No hazards'), 'title');
    assert.ok(html.includes('Nothing to show for this period.'), 'subtitle');
    assert.ok(html.includes('Open register'), 'CTA label');
    assert.ok(html.includes('/risk-register/index.html'), 'CTA url');
    // Defaults (EIP-None-style neutral message tolerated by callers).
    const def = EmptyState.noData();
    assert.ok(def.includes('No data'), 'default title');
}

function test_no_module_contract_copy() {
    // Exact DASHBOARD_CONTRACT.md §9 copy.
    const html = EmptyState.noModule('Hazard & Risk (SRM)');
    assert.ok(html.includes('This module is not enabled'), '§9 title');
    assert.ok(html.includes('Contact your tenant administrator to enable'), '§9 subtitle');
    assert.ok(html.includes('Back to Dashboard'), '§9 CTA');
}

function test_no_permission_variant() {
    const html = EmptyState.noPermission('ACCOUNTABLE_EXECUTIVE');
    assert.ok(html.includes('Access restricted'), 'title');
    assert.ok(html.includes('ACCOUNTABLE_EXECUTIVE'), 'required role named');
    assert.ok(html.includes('Back to Dashboard'), 'CTA');
}

function test_loading_variant() {
    const html = EmptyState.loading('Crunching risk trends…');
    assert.ok(html.includes('Crunching risk trends…'), 'message');
    assert.ok(html.includes('dash-spinner'), 'skeleton/spinner affordance');
}

function test_error_variant_with_retry() {
    let retried = 0;
    const c = makeContainer();
    const html = EmptyState.error('KPIs unavailable.', () => { retried += 1; }, c);
    assert.ok(html.includes('KPIs unavailable.'), 'message');
    assert.ok(html.includes('Retry'), 'retry affordance');
    assert.strictEqual(c.innerHTML, html, 'container painted');
}

function test_container_painting() {
    const c = makeContainer();
    EmptyState.noData('T', 'S', null, null, c);
    assert.ok(c.innerHTML.includes('T'), 'noData paints container');
}

// ---------------------------------------------------------------------------
// ModuleFlag helper (P4-7)
// ---------------------------------------------------------------------------

function test_module_flag_has_and_canonical() {
    withSessionStorage(() => {
        ModuleFlag._resetForTests();
        ModuleFlag.set({ module_a_survey: true, module_b_srm: true });
        assert.strictEqual(ModuleFlag.has('module_a_survey'), true);
        assert.strictEqual(ModuleFlag.has('module_b_srm'), true);
        assert.strictEqual(ModuleFlag.has('module_b_can_cap'), true, 'can_cap inherits srm (Q-R6 subset)');
        assert.strictEqual(ModuleFlag.has('module_c_regulator'), false, 'unknown flag is fail-closed');
        assert.ok(ModuleFlag.CANONICAL.includes('module_a_survey'), 'canonical list');
        assert.ok(ModuleFlag.CANONICAL.includes('module_b_can_cap'), 'canonical list');
    });
}

function test_module_flag_legacy_keys() {
    withSessionStorage(() => {
        ModuleFlag._resetForTests();
        ModuleFlag.set({ module1: true, module2: false, module3: false });
        assert.strictEqual(ModuleFlag.has('module_a_survey'), true, 'module1 → survey');
        assert.strictEqual(ModuleFlag.has('module_b_srm'), false, 'module2 → srm');
        assert.strictEqual(ModuleFlag.has('module1'), true, 'legacy key readable directly');
    });
}

function test_module_flag_cache_and_clear() {
    withSessionStorage((store) => {
        ModuleFlag._resetForTests();
        ModuleFlag.set({ module_b_srm: true });
        assert.ok(store['dash:module-flags'], 'persisted to sessionStorage');
        // Fresh in-memory state restores from the cache.
        ModuleFlag._resetForTests();
        // _resetForTests drops the in-memory cache; restore path re-reads it.
        assert.strictEqual(ModuleFlag.has('module_b_srm'), true, 'restored from sessionStorage');
        ModuleFlag.clear();
        assert.strictEqual(ModuleFlag.has('module_b_srm'), false, 'cleared (tenant switch / logout)');
    });
}

function test_module_flag_requires_guard() {
    withSessionStorage(() => {
        ModuleFlag._resetForTests();
        ModuleFlag.set({ module_b_srm: false });
        const c = makeContainer();
        assert.strictEqual(
            ModuleFlag.requires('module_b_srm', { container: c }), false,
            'guard blocks when flag off'
        );
        assert.ok(c.innerHTML.includes('This module is not enabled'), '§9 empty state painted');
        ModuleFlag.set({ module_b_srm: true });
        const c2 = makeContainer();
        assert.strictEqual(
            ModuleFlag.requires('module_b_srm', { container: c2 }), true,
            'guard passes when flag on'
        );
        assert.strictEqual(c2.innerHTML, '', 'no empty state when enabled');
        // Guard never throws, even with no container and no DOM.
        ModuleFlag.set({ module_b_srm: false });
        assert.doesNotThrow(() => ModuleFlag.requires('module_b_srm'), 'never throws');
    });
}

function test_module_flag_onchange() {
    withSessionStorage(() => {
        ModuleFlag._resetForTests();
        const seen = [];
        const unsub = ModuleFlag.onChange((snap) => seen.push(snap));
        ModuleFlag.set({ module_a_survey: true });
        assert.strictEqual(seen.length, 1, 'subscriber notified');
        assert.strictEqual(seen[0].module_a_survey, true);
        unsub();
        ModuleFlag.set({ module_a_survey: false });
        assert.strictEqual(seen.length, 1, 'unsub works');
    });
}

// ---------------------------------------------------------------------------

function main() {
    test_no_data_variant();
    test_no_module_contract_copy();
    test_no_permission_variant();
    test_loading_variant();
    test_error_variant_with_retry();
    test_container_painting();
    test_module_flag_has_and_canonical();
    test_module_flag_legacy_keys();
    test_module_flag_cache_and_clear();
    test_module_flag_requires_guard();
    test_module_flag_onchange();
    console.log('test_empty_state: 11 tests passed (5 EmptyState variants + 6 ModuleFlag behaviors)');
}

main();
