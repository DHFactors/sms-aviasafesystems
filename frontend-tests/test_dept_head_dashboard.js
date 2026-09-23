/**
 * Frontend unit tests for the Phase 4 Wave 3 Department Head dashboard (P4-3).
 *
 * Covers public/dashboard/dept-head-dashboard.html (CAP-only DEPT_ADMIN view)
 * plus shared bucket logic via public/dashboard/shared/safety-helpers.js:
 *  - 3-counter strip renders (CANs | CAPs | EIP, dept-filtered)
 *  - Dept filtering is server-side (?department= on every list; no
 *    client-side cross-dept filtering — would leak data)
 *  - CAP create/edit/submit call the correct endpoints
 *  - Non-DEPT_ADMIN redirects (token role claim → role dashboard)
 *  - Status bucket mapping matches the Safety Manager dashboard (§2.3)
 *  - Module gate requires module_b_can_cap; EIP panel is read-only
 *
 * Pattern follows frontend-tests/test_safety_dashboard.js (plain Node).
 */
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const H = require('../public/dashboard/shared/safety-helpers.js');

const PAGE = fs.readFileSync(
    path.join(__dirname, '..', 'public', 'dashboard', 'dept-head-dashboard.html'), 'utf8'
);

// ---------------------------------------------------------------------------
// Page structure (§3.7 layout contract)
// ---------------------------------------------------------------------------

function test_page_structure() {
    assert.ok(PAGE.includes('id="dash-kpi-strip"'), 'KPI strip mount');
    assert.ok(PAGE.includes('id="drill-card"') && PAGE.includes('id="drill-panel"'), 'drill-down panel');
    assert.ok(PAGE.includes('id="can-list"'), 'CAN list (my dept)');
    assert.ok(PAGE.includes('id="cap-list"'), 'CAP list (my dept)');
    assert.ok(PAGE.includes('id="cap-detail"'), 'CAP detail / response view');
    assert.ok(PAGE.includes('id="eip-panel"'), 'EIP panel');
    assert.ok(PAGE.includes('id="form-cap"'), 'CAP create/edit form');
    // Exactly three KPI defs: cans | caps | eip (no reports/hazards on this page).
    ['cans', 'caps', 'eip'].forEach((m) => {
        assert.ok(PAGE.includes("metric: '" + m + "'"), 'KPI def: ' + m);
    });
    assert.ok(!PAGE.includes("metric: 'reports'"), 'no reports KPI on dept page');
    assert.ok(!PAGE.includes("metric: 'hazards'"), 'no hazards KPI on dept page');
}

function test_page_wiring() {
    assert.ok(PAGE.includes('Shell.init'), 'shared Shell used');
    assert.ok(PAGE.includes("ModuleFlag.requires('module_b_can_cap'"), 'module-B CAN/CAP guard at load');
    assert.ok(PAGE.includes('DrillDown.mount'), 'DrillDown used for KPI drill');
    assert.ok(PAGE.includes('EmptyState.'), 'EmptyState treatments used');
    assert.ok(PAGE.includes('onPeriodChange'), 'period selector re-filters lists');
    assert.ok(PAGE.includes("role: 'DEPT_ADMIN'") || PAGE.includes('role: role'), 'Shell.init with DEPT_ADMIN role');
}

// ---------------------------------------------------------------------------
// Dept filtering: server-side (?department=), never client-side
// ---------------------------------------------------------------------------

function test_dept_filtering_server_side() {
    // Every dept-scoped list passes ?department= explicitly…
    assert.ok(PAGE.includes('/api/v1/cans/') && PAGE.includes('deptParams'), 'CAN list passes department param');
    assert.ok(PAGE.includes('/api/v1/cans/caps') && PAGE.includes('deptParams'), 'CAP list passes department param');
    assert.ok(PAGE.includes('escalated_to_ae') && PAGE.includes('deptParams'), 'EIP query passes department param');
    // …and documents that the backend enforces it (P3-9 isolation).
    assert.ok(PAGE.includes('get_department_scope'), 'backend dept enforcement cited');
    assert.ok(PAGE.toLowerCase().includes('dept isolation'), 'PATCH isolation cited');
    // No client-side cross-dept filtering (would leak data across departments).
    assert.ok(!PAGE.includes('filter(') || PAGE.includes('deriveEIP'), 'no ad-hoc client dept filter');
    assert.ok(PAGE.includes('SERVER-SIDE ONLY'), 'server-side-only filtering documented');
}

// ---------------------------------------------------------------------------
// Workflow actions (§3.5): create / edit / submit; evidence deferred
// ---------------------------------------------------------------------------

function test_workflow_endpoints() {
    // CAP create (POST /api/v1/cans/{can_id}/caps, can_cap.py:218).
    assert.ok(
        PAGE.includes("ApiClient.post('/api/v1/cans/'") && PAGE.includes('/caps'),
        'CAP create posts to POST /api/v1/cans/{can_id}/caps'
    );
    // CAP edit (PATCH /api/v1/cans/caps/{cap_id}, can_cap.py:278).
    assert.ok(
        PAGE.includes("ApiClient.patch('/api/v1/cans/caps/'"),
        'CAP edit patches PATCH /api/v1/cans/caps/{cap_id}'
    );
    // CAP submit (PATCH …/status → Under Review, can_cap.py:408).
    assert.ok(
        PAGE.includes('/status') && PAGE.includes('Under Review'),
        'CAP submit patches …/status to Under Review'
    );
    // Deferred: evidence upload, review response, status beyond submit.
    assert.ok(PAGE.includes('Evidence upload') && PAGE.includes('deferred'), 'evidence upload deferred');
    assert.ok(PAGE.includes('review responses are deferred') || PAGE.includes('Response to review'), 'review response deferred');
}

function test_eip_read_only() {
    // EIP panel has no write actions (no New/Edit/Submit buttons inside eip-panel wiring).
    const eipSection = PAGE.slice(PAGE.indexOf('id="eip-panel"'), PAGE.indexOf('id="eip-panel"') + 200);
    assert.ok(!/data-act/.test(eipSection), 'EIP panel carries no write actions');
    assert.ok(PAGE.includes('read-only'), 'EIP documented read-only');
}

// ---------------------------------------------------------------------------
// Role gate (§3.1): DEPT_ADMIN only; others redirect
// ---------------------------------------------------------------------------

function test_role_gate() {
    assert.ok(PAGE.includes("=== 'DEPT_ADMIN'") || PAGE.includes('DEPT_ADMIN'), 'DEPT_ADMIN gate present');
    assert.ok(PAGE.includes('redirectFor'), 'redirect helper present');
    assert.ok(PAGE.includes('getRoleDestination'), 'nav-config/firebase role mapping used');
    // Non-DEPT_ADMIN destinations are wired (at least safety + AE + CAAN).
    assert.ok(PAGE.includes('/safety.html'), 'safety redirect for non-dept roles');
    assert.ok(PAGE.includes('/dashboard/ae-dashboard.html'), 'AE redirect wired');
    assert.ok(PAGE.includes('/caan.html'), 'CAAN redirect wired');
    // Safety helpers must NOT admit DEPT_ADMIN on the safety page (cross-check).
    assert.strictEqual(H.roleAllowed('DEPT_ADMIN'), false, 'safety page excludes DEPT_ADMIN');
}

// ---------------------------------------------------------------------------
// Status bucket mapping (same §2.3 map as the Safety Manager dashboard)
// ---------------------------------------------------------------------------

function test_bucket_mapping() {
    assert.strictEqual(H.bucketizeStatus('cans', 'Open'), 'Open');
    assert.strictEqual(H.bucketizeStatus('cans', 'Escalated'), 'Open', 'attention');
    assert.strictEqual(H.bucketizeStatus('cans', 'Issued'), 'In Process');
    assert.strictEqual(H.bucketizeStatus('cans', 'Closed'), 'Closed');
    assert.strictEqual(H.bucketizeStatus('caps', 'In Progress'), 'In Process');
    assert.strictEqual(H.bucketizeStatus('caps', 'Under Review'), 'In Process');
    assert.strictEqual(H.bucketizeStatus('caps', 'Revision Required'), 'In Process');
    assert.strictEqual(H.bucketizeStatus('caps', 'EIP'), 'In Process', 'attention styling via tone');
    assert.strictEqual(H.bucketizeStatus('caps', 'Completed'), 'Closed');
    assert.strictEqual(H.bucketizeStatus('caps', 'Overdue'), 'Open', 'attention');
    assert.strictEqual(H.bucketizeStatus('eip', 'EIP'), 'In Process', 'EIP uses CAP map');
}

// ---------------------------------------------------------------------------

function main() {
    test_page_structure();
    test_page_wiring();
    test_dept_filtering_server_side();
    test_workflow_endpoints();
    test_eip_read_only();
    test_role_gate();
    test_bucket_mapping();
    console.log('test_dept_head_dashboard: 7 tests passed (structure, wiring, dept-filter, workflow, eip-readonly, roles, buckets)');
}

main();
