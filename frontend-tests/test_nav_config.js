/**
 * Frontend unit tests for the Phase 4 Wave 1 nav-config update (P4-6).
 *
 * Covers public/js/nav-config.js:
 *  - ACCOUNTABLE_EXECUTIVE → AE with the NARROW menu only
 *    (Dashboard/Executive, Action Queues/My Tasks, Trends)
 *  - SAG_MEMBER → hidden from nav (no dashboard in scope)
 *  - Canonical role literals + legacy aliases resolve correctly
 *  - Module flag gating (canonical + legacy keys) hides tagged items
 *  - All canonical module flags recognized
 *
 * Pattern follows frontend-tests/tenant-context.test.js (plain Node).
 */
'use strict';

const assert = require('assert');
const Nav = require('../public/js/nav-config.js');

const { NAV_CONFIG, NAV_MODULE_FLAGS, getUserRoleType, getVisibleNav, normalizeModuleAccess } = Nav;

// ---------------------------------------------------------------------------
// Role resolution
// ---------------------------------------------------------------------------

function test_role_type_mapping() {
    assert.strictEqual(getUserRoleType({ role: 'SUPER_ADMIN' }), 'SUPER');
    assert.strictEqual(getUserRoleType({ role: 'CAAN_SMD' }), 'CAAN');
    assert.strictEqual(getUserRoleType({ role: 'CAAN_ADMIN' }), 'CAAN');
    assert.strictEqual(getUserRoleType({ role: 'CAAN_AUDITOR' }), 'CAAN');
    assert.strictEqual(getUserRoleType({ role: 'TENANT_ADMIN' }), 'SAFETY');
    assert.strictEqual(getUserRoleType({ role: 'AIRLINE_ADMIN' }), 'SAFETY');
    assert.strictEqual(getUserRoleType({ role: 'SAFETY_OFFICER' }), 'SAFETY');
    assert.strictEqual(getUserRoleType({ role: 'DEPT_ADMIN' }), 'DEPT_ADMIN');
    assert.strictEqual(getUserRoleType({ role: 'ACCOUNTABLE_EXECUTIVE' }), 'AE');
    assert.strictEqual(getUserRoleType({ role: 'SAG_MEMBER' }), 'SAG');
    assert.strictEqual(getUserRoleType({ role: 'STAFF' }), 'ALL');
    assert.strictEqual(getUserRoleType({ role: 'USER' }), 'ALL');
    // ae@ email heuristic retained as fallback for legacy AE accounts.
    assert.strictEqual(getUserRoleType({ role: 'TENANT_ADMIN', email: 'ae@buddha-air.com' }), 'AE');
    assert.strictEqual(getUserRoleType(null), 'ALL');
}

function groupsOf(visible) {
    const out = {};
    visible.forEach((g) => { out[g.group] = g.items.map((i) => i.id); });
    return out;
}

// ---------------------------------------------------------------------------
// ACCOUNTABLE_EXECUTIVE narrow menu (P4-6.1)
// ---------------------------------------------------------------------------

function test_ae_narrow_menu() {
    const visible = getVisibleNav({ role: 'ACCOUNTABLE_EXECUTIVE', email: 'boss@airline.com' });
    const groups = groupsOf(visible);
    assert.deepStrictEqual(Object.keys(groups), ['Dashboard'], 'AE sees ONLY the Dashboard group');
    assert.deepStrictEqual(
        groups.Dashboard.sort(),
        ['ae-dashboard', 'ae-trends', 'my-tasks'].sort(),
        'AE menu = Executive dashboard + My Tasks (action queues) + Trends'
    );
    const exec = visible[0].items.find((i) => i.id === 'ae-dashboard');
    assert.strictEqual(exec.href, '/dashboard/ae-dashboard.html', 'AE dashboard target');
    // No CAN/CAP authoring, no admin anywhere in the AE menu.
    const ids = groups.Dashboard.join(' ');
    assert.ok(!ids.includes('issue-can'), 'no CAN authoring for AE');
    assert.ok(!ids.includes('production') && !ids.includes('settings'), 'no admin for AE');
}

function test_ae_email_fallback_same_menu() {
    const viaLiteral = groupsOf(getVisibleNav({ role: 'ACCOUNTABLE_EXECUTIVE', email: 'x@y.com' }));
    const viaEmail = groupsOf(getVisibleNav({ role: 'TENANT_ADMIN', email: 'ae@buddha-air.com' }));
    assert.deepStrictEqual(viaEmail, viaLiteral, 'ae@ fallback matches the literal AE menu');
}

// ---------------------------------------------------------------------------
// SAG_MEMBER hidden (P4-6.2 — no SAG dashboard in scope)
// ---------------------------------------------------------------------------

function test_sag_member_hidden() {
    assert.deepStrictEqual(getVisibleNav({ role: 'SAG_MEMBER', email: 'sag@airline.com' }), [],
        'SAG_MEMBER sees no nav groups');
}

// ---------------------------------------------------------------------------
// Module flag gating (P4-6.3/4, §9)
// ---------------------------------------------------------------------------

function test_canonical_flags_exact() {
    assert.deepStrictEqual(NAV_MODULE_FLAGS.slice().sort(), [
        'module_a_survey',
        'module_b_can_cap',
        'module_b_srm',
        'module_c_regulator',
    ].sort(), 'canonical Q-R5 flags');
}

function test_module_gating_hides_groups() {
    const user = { role: 'TENANT_ADMIN', email: 'safety@airline.com' };
    const allOn = {
        module_a_survey: true, module_b_srm: true,
        module_b_can_cap: true, module_c_regulator: false,
    };
    const groupsOn = groupsOf(getVisibleNav(user, allOn));
    assert.ok(groupsOn['Hazard Management'], 'hazards visible with module_b_srm');
    assert.ok(groupsOn['Corrective Actions'], 'corrective visible with module_b_can_cap');

    const bOff = { module_a_survey: true, module_b_srm: false };
    const groupsOff = groupsOf(getVisibleNav(user, bOff));
    assert.ok(!groupsOff['Hazard Management'], 'hazards hidden without module_b_srm');
    assert.ok(!groupsOff['Corrective Actions'], 'corrective hidden without module_b_can_cap (subset of SRM)');
    // §9: every Dashboard item for SAFETY is Module-B-tagged, so with SRM off
    // the group drops entirely (the page then shows "module not enabled").
    assert.ok(!groupsOff.Dashboard, 'dashboard group drops when all its items are gated off');
    // Partial gating: CAN/CAP off but SRM on — Dashboard survives on Key Indicators.
    const partial = groupsOf(getVisibleNav(user, {
        module_a_survey: true, module_b_srm: true, module_b_can_cap: false,
    }));
    assert.deepStrictEqual(partial.Dashboard, ['key-indicators'], 'item-level gating keeps Key Indicators');
}

function test_module_gating_item_level() {
    const user = { role: 'TENANT_ADMIN', email: 'safety@airline.com' };
    // Survey off: SMS Maturity item drops, SPI/N-HRC stay (Module B).
    const visible = getVisibleNav(user, { module_a_survey: false, module_b_srm: true });
    const perf = visible.find((g) => g.group === 'Performance');
    assert.ok(perf, 'Performance group survives');
    const ids = perf.items.map((i) => i.id);
    assert.ok(!ids.includes('sms-maturity'), 'SMS Maturity hidden without module_a_survey');
    assert.ok(ids.includes('spi-dashboard'), 'SPI stays with module_b_srm');
}

function test_legacy_module_keys_mapped() {
    // Live tenants.module_access scheme (module1..module4).
    const norm = normalizeModuleAccess({ module1: true, module2: true, module3: false });
    assert.strictEqual(norm.module_a_survey, true);
    assert.strictEqual(norm.module_b_srm, true);
    assert.strictEqual(norm.module_b_can_cap, true, 'can_cap inherits module2 (Q-R6 subset rule)');
    assert.strictEqual(norm.module_c_regulator, false);
    const user = { role: 'TENANT_ADMIN', email: 'safety@airline.com' };
    const groups = groupsOf(getVisibleNav(user, { module1: true, module2: false, module3: false }));
    assert.ok(!groups['Hazard Management'], 'legacy module2:false hides hazards');
}

function test_no_module_access_arg_backward_compatible() {
    // Existing callers (shell.js buildNavFromConfig) pass one arg — no
    // module filtering, full role menu as before.
    const user = { role: 'TENANT_ADMIN', email: 'safety@airline.com' };
    const groups = groupsOf(getVisibleNav(user));
    assert.ok(groups['Hazard Management'], 'no filtering without moduleAccess');
    assert.ok(groups['Corrective Actions'], 'no filtering without moduleAccess');
    assert.ok(groups.Performance, 'no filtering without moduleAccess');
}

function test_regulator_untouched() {
    const visible = groupsOf(getVisibleNav({ role: 'CAAN_SMD', email: 'smd@caanepal.gov.np' }));
    assert.ok(visible.Dashboard && visible.Dashboard.includes('caan-dashboard'), 'CAAN oversight kept');
    assert.ok(visible.Regulator, 'Regulator group kept');
    assert.ok(!visible['Hazard Management'], 'CAAN never had hazard groups');
}

// ---------------------------------------------------------------------------

function main() {
    test_role_type_mapping();
    test_ae_narrow_menu();
    test_ae_email_fallback_same_menu();
    test_sag_member_hidden();
    test_canonical_flags_exact();
    test_module_gating_hides_groups();
    test_module_gating_item_level();
    test_legacy_module_keys_mapped();
    test_no_module_access_arg_backward_compatible();
    test_regulator_untouched();
    console.log('test_nav_config: 10 tests passed (AE narrow menu, SAG hidden, canonical flags, module gating, back-compat)');
}

main();
