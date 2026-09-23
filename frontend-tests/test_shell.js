/**
 * Frontend unit tests for the Phase 4 Wave 1 shared shell + drill-down
 * (public/dashboard/shared/shell.js, drilldown.js).
 *
 * P4-1 verification:
 *  - Shell.init renders header + sidebar + period selector state
 *  - Period change emits event (subscriber + DOM CustomEvent)
 *  - showEmpty / showError render correct copy
 *  - DrillDown: L1 counter → L2 breakdown → L3 records → back
 *
 * Pattern follows frontend-tests/dashboard.test.js (plain Node + minimal
 * document shim; shared modules are UMD-wrapped and dependency-free).
 */
'use strict';

const assert = require('assert');
const Shell = require('../public/dashboard/shared/shell.js');
const DrillDown = require('../public/dashboard/shared/drilldown.js');

// ---------------------------------------------------------------------------
// Minimal DOM shim
// ---------------------------------------------------------------------------

function makeEl(id) {
    const listeners = {};
    const el = {
        id: id || '',
        innerHTML: '',
        textContent: '',
        hidden: true,
        style: {},
        dataset: {},
        value: '',
        __attrs: {},
        __classes: new Set(),
        classList: {
            toggle: (c, force) => {
                if (force === undefined) {
                    if (el.__classes.has(c)) el.__classes.delete(c);
                    else el.__classes.add(c);
                } else if (force) el.__classes.add(c);
                else el.__classes.delete(c);
            },
            contains: (c) => el.__classes.has(c),
            add: (c) => el.__classes.add(c),
            remove: (c) => el.__classes.delete(c),
        },
        setAttribute: (k, v) => { el.__attrs[k] = String(v); },
        getAttribute: (k) => (k in el.__attrs ? el.__attrs[k] : null),
        removeAttribute: (k) => { delete el.__attrs[k]; },
        addEventListener: (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); },
        fire: (t) => { (listeners[t] || []).forEach((fn) => fn()); },
        __listeners: listeners,
    };
    return el;
}

function makeDoc() {
    const els = {};
    const dispatched = [];
    const doc = {
        getElementById: (id) => {
            if (!els[id]) els[id] = makeEl(id);
            return els[id];
        },
        querySelectorAll: () => [],
        querySelector: () => null,
        dispatchEvent: (evt) => { dispatched.push(evt); return true; },
        createEvent: () => ({
            initCustomEvent: function (type, b, c, detail) {
                this.type = type; this.detail = detail;
            },
        }),
        __els: els,
        __dispatched: dispatched,
    };
    return doc;
}

function withDoc(doc, fn) {
    const prevDoc = global.document;
    const prevWin = global.window;
    global.document = doc;
    // Shell reads window.NAV_CONFIG only when window exists; leave undefined
    // here to exercise the no-nav-config fallback path.
    if ('window' in global) delete global.window;
    try {
        return fn();
    } finally {
        if (prevDoc === undefined) delete global.document;
        else global.document = prevDoc;
        if (prevWin === undefined) { if ('window' in global) delete global.window; }
        else global.window = prevWin;
    }
}

// ---------------------------------------------------------------------------
// Shell.init
// ---------------------------------------------------------------------------

function test_init_renders_header_sidebar_period() {
    const doc = makeDoc();
    withDoc(doc, () => {
        Shell._resetForTests();
        const out = Shell.init({
            role: 'TENANT_ADMIN',
            roleLabel: 'Safety Manager',
            tenantName: 'Buddha Air',
            userEmail: 'safety@buddha-air.com',
            title: 'Safety Manager Dashboard',
            activeNav: 'key-indicators',
            period: '90d',
            modules: { module_a_survey: true, module_b_srm: true },
        });
        assert.strictEqual(out.period, '90d');
        assert.strictEqual(out.activeNav, 'key-indicators');
        assert.strictEqual(doc.__els['dash-role-badge'].textContent, 'Safety Manager');
        assert.strictEqual(doc.__els['dash-tenant-name'].textContent, 'Buddha Air');
        assert.strictEqual(doc.__els['dash-user-email'].textContent, 'safety@buddha-air.com');
        assert.strictEqual(doc.__els['dash-title'].textContent, 'Safety Manager Dashboard');
        // Sidebar nav rendered (fallback group when NAV_CONFIG absent).
        assert.ok(doc.__els['dash-nav'].innerHTML.includes('Dashboard'), 'sidebar nav rendered');
        // Module badges: A + B present, C absent.
        const badges = doc.__els['dash-module-badges'].innerHTML;
        assert.ok(badges.includes('mod-a') && badges.includes('mod-b'), 'A+B badges rendered');
        assert.ok(!badges.includes('mod-c'), 'C badge absent');
        assert.strictEqual(Shell.getPeriod(), '90d');
        assert.deepStrictEqual(Shell.getPeriodParams(), { period: '90d', days: 90 });
    });
}

function test_init_with_nav_config_renders_role_nav() {
    const doc = makeDoc();
    const Nav = require('../public/js/nav-config.js');
    const prevWin = global.window;
    global.window = { NAV_CONFIG: Nav.NAV_CONFIG, getVisibleNav: Nav.getVisibleNav };
    const prevDoc = global.document;
    global.document = doc;
    try {
        Shell._resetForTests();
        Shell.init({
            role: 'ACCOUNTABLE_EXECUTIVE',
            roleLabel: 'Accountable Executive',
            tenantName: 'Demo',
            navUser: { role: 'ACCOUNTABLE_EXECUTIVE', email: 'ae@demo.com' },
            activeNav: 'ae-dashboard',
        });
        const html = doc.__els['dash-nav'].innerHTML;
        assert.ok(html.includes('Executive'), 'AE dashboard item rendered');
        assert.ok(html.includes('My Tasks'), 'AE action-queue item rendered');
        assert.ok(html.includes('Trends'), 'AE trends item rendered');
        // Active nav highlight is applied via setActiveNav (querySelectorAll
        // shim returns [] here — assert state instead).
        assert.strictEqual(Shell._state.activeNav, 'ae-dashboard');
    } finally {
        if (prevDoc === undefined) delete global.document;
        else global.document = prevDoc;
        if (prevWin === undefined) delete global.window;
        else global.window = prevWin;
    }
}

// ---------------------------------------------------------------------------
// Period selector
// ---------------------------------------------------------------------------

function test_period_change_emits_event() {
    const doc = makeDoc();
    withDoc(doc, () => {
        Shell._resetForTests();
        Shell.init({ period: '30d' });
        const seen = [];
        const unsub = Shell.onPeriodChange((snap) => seen.push(snap));
        Shell.setPeriod('1y');
        assert.strictEqual(Shell.getPeriod(), '1y');
        assert.strictEqual(seen.length, 1, 'subscriber called once');
        assert.strictEqual(seen[0].period, '1y');
        assert.deepStrictEqual(seen[0].params, { period: '1y', days: 365 });
        assert.strictEqual(doc.__dispatched.length, 1, 'DOM event dispatched');
        assert.strictEqual(doc.__dispatched[0].type, 'dash:period');
        // Unsubscribe works.
        unsub();
        Shell.setPeriod('30d');
        assert.strictEqual(seen.length, 1, 'no further calls after unsub');
        // Unknown period normalizes to 30d.
        assert.strictEqual(Shell.setPeriod('bogus'), '30d');
        // Custom period carries explicit start/end (P3-14).
        Shell.setPeriod('custom', { start: '2026-01-01', end: '2026-03-31' });
        assert.deepStrictEqual(Shell.getPeriodParams(), {
            period: 'custom', start: '2026-01-01', end: '2026-03-31',
        });
    });
}

// ---------------------------------------------------------------------------
// showEmpty / showError
// ---------------------------------------------------------------------------

function test_show_empty_renders_copy() {
    const doc = makeDoc();
    withDoc(doc, () => {
        Shell._resetForTests();
        Shell.init({});
        // Prime overlays visible, then showEmpty must hide the others.
        doc.getElementById('dash-loading').hidden = false;
        Shell.showEmpty('No hazards in this period.', { label: 'Open register', url: '/risk-register/index.html' });
        const node = doc.__els['dash-empty'];
        assert.strictEqual(node.hidden, false, 'empty overlay visible');
        assert.ok(node.innerHTML.includes('No hazards in this period.'), 'message copy');
        assert.ok(node.innerHTML.includes('Open register'), 'CTA label');
        assert.ok(node.innerHTML.includes('/risk-register/index.html'), 'CTA url');
        assert.strictEqual(doc.__els['dash-loading'].hidden, true, 'loading hidden');
    });
}

function test_show_error_renders_copy_and_retry() {
    const doc = makeDoc();
    withDoc(doc, () => {
        Shell._resetForTests();
        Shell.init({});
        let retried = 0;
        Shell.showError('KPIs unavailable.', () => { retried += 1; });
        const node = doc.__els['dash-error'];
        assert.strictEqual(node.hidden, false, 'error overlay visible');
        assert.ok(node.innerHTML.includes('KPIs unavailable.'), 'message copy');
        assert.ok(node.innerHTML.includes('Retry'), 'retry affordance');
        assert.strictEqual(typeof Shell._state._lastRetry, 'function', 'retry registered');
        Shell._state._lastRetry();
        assert.strictEqual(retried, 1, 'retry fires');
        // Loading / hideLoading round-trip.
        Shell.showLoading('Crunching…');
        assert.strictEqual(doc.__els['dash-loading'].hidden, false);
        assert.ok(doc.__els['dash-loading-text'].textContent.includes('Crunching'));
        Shell.hideLoading();
        assert.strictEqual(doc.__els['dash-loading'].hidden, true);
    });
}

// ---------------------------------------------------------------------------
// DrillDown: L1 → L2 → L3 → back
// ---------------------------------------------------------------------------

function test_drilldown_levels() {
    const container = makeEl('drill');
    const dd = DrillDown.create(container, { metric: 'Hazards' });
    // L1: counter.
    const total = dd.render({ total: 128 });
    assert.strictEqual(total, 128);
    assert.ok(container.innerHTML.includes('128'), 'L1 counter rendered');
    assert.ok(container.innerHTML.includes('Hazards'), 'metric label rendered');
    // L2: breakdown buckets.
    const inst = dd;
    inst._state.breakdown = null;
    // Feed breakdown directly via client-side bucketing of L1 records.
    const records = [
        { id: 'H-1', status: 'Open' },
        { id: 'H-2', status: 'Processing' },
        { id: 'H-3', status: 'Under Review' },
        { id: 'H-4', status: 'Closed' },
        { id: 'H-5', status: 'Completed' },
        { id: 'H-6', status: 'Overdue' },
    ];
    const dd2 = DrillDown.create(container, { metric: 'Hazards' });
    dd2.render(records);
    // drill(null) with no endpoints falls back to client-side bucketize.
    return dd2.drill(null).then((counts) => {
        assert.deepStrictEqual(counts, { Open: 2, 'In Process': 2, Closed: 2 }, 'bucket mapping');
        assert.ok(container.innerHTML.includes('Status breakdown'), 'L2 rendered');
        assert.strictEqual(dd2._state.level, 2);
        // Back from L2 → L1.
        assert.strictEqual(dd2.back(), 1);
        assert.ok(container.innerHTML.includes('Hazards'), 'L1 restored');
    });
}

function test_drilldown_bucket_mapping() {
    assert.strictEqual(DrillDown.toBucket('Open'), 'Open');
    assert.strictEqual(DrillDown.toBucket('Processing'), 'In Process');
    assert.strictEqual(DrillDown.toBucket('Under Review'), 'In Process');
    assert.strictEqual(DrillDown.toBucket('Pending Closure'), 'In Process');
    assert.strictEqual(DrillDown.toBucket('Reopened'), 'In Process');
    assert.strictEqual(DrillDown.toBucket('Revision Required'), 'In Process');
    assert.strictEqual(DrillDown.toBucket('In Progress'), 'In Process');
    assert.strictEqual(DrillDown.toBucket('Closed'), 'Closed');
    assert.strictEqual(DrillDown.toBucket('Completed'), 'Closed');
    assert.strictEqual(DrillDown.toBucket('Overdue'), 'Open');
    // Envelope unwrap tolerance (P4-7: never throw on missing endpoints).
    assert.deepStrictEqual(DrillDown.unwrap({ status: 'success', timestamp: 'x', data: [1] }), [1]);
    assert.deepStrictEqual(DrillDown.unwrap([1, 2]), [1, 2]);
    assert.strictEqual(DrillDown.unwrap(null), null);
}

// ---------------------------------------------------------------------------

function main() {
    test_init_renders_header_sidebar_period();
    test_init_with_nav_config_renders_role_nav();
    test_period_change_emits_event();
    test_show_empty_renders_copy();
    test_show_error_renders_copy_and_retry();
    test_drilldown_bucket_mapping();
    test_drilldown_levels().then(() => {
        console.log('test_shell: 7 tests passed (Shell.init, period events, empty/error, DrillDown L1→L2→back, buckets)');
    }).catch((e) => { console.error(e); process.exit(1); });
}

main();
