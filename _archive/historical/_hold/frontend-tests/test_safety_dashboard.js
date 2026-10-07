/**
 * Frontend unit tests for the Phase 4 Wave 2 Safety Manager dashboard (P4-2).
 *
 * Covers public/dashboard/shared/safety-helpers.js (pure logic, UMD) plus
 * structural wiring assertions on public/dashboard/safety-dashboard.html:
 *  - KPI strip renders 5 counters (helpers + page markup contract)
 *  - Counter click triggers DrillDown (helpers → DrillDown integration)
 *  - EIP shows "None" when zero
 *  - Status bucket mapping (each status → correct bucket, per metric)
 *  - Color thresholds applied correctly (hardcoded defaults, §2.4)
 *  - Create-hazard form posts to the correct endpoint (payload + endpoint)
 *  - Period selector filters counters (period params → overview query)
 *
 * Pattern follows frontend-tests/test_shell.js (plain Node + minimal shims).
 */
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const H = require('../public/dashboard/shared/safety-helpers.js');
const DrillDown = require('../public/dashboard/shared/drilldown.js');

const PAGE = fs.readFileSync(
    path.join(__dirname, '..', 'public', 'dashboard', 'safety-dashboard.html'), 'utf8'
);

// ---------------------------------------------------------------------------
// Page structure (§2.8 layout contract)
// ---------------------------------------------------------------------------

function test_page_structure() {
    assert.ok(PAGE.includes('id="dash-kpi-strip"'), 'KPI strip mount');
    assert.ok(PAGE.includes('id="drill-card"') && PAGE.includes('id="drill-panel"'), 'drill-down panel');
    assert.ok(PAGE.includes('id="hazard-list"'), 'hazard list rail');
    assert.ok(PAGE.includes('id="srm-queue"'), 'SRM queue rail');
    assert.ok(PAGE.includes('id="master-register"'), 'CAN-CAP register rail');
    assert.ok(PAGE.includes('id="eip-monitor"'), 'EIP monitor rail');
    assert.ok(PAGE.includes('id="sag-srb"'), 'SAG/SRB rail');
    assert.ok(PAGE.includes('id="risk-dist"'), 'risk distribution panel');
    assert.ok(PAGE.includes('id="trends"'), 'trends panel');
    assert.ok(PAGE.includes('id="recent-reports"'), 'recent reports panel');
    assert.ok(PAGE.includes('id="sms-maturity"'), 'SMS maturity widget');
    assert.ok(PAGE.includes('id="form-create-hazard"'), 'create-hazard form');
    assert.ok(PAGE.includes('id="form-triage"'), 'triage form');
    // Five KPI defs, left to right: reports | hazards | cans | caps | eip.
    ['reports', 'hazards', 'cans', 'caps', 'eip'].forEach((m) => {
        assert.ok(PAGE.includes("metric: '" + m + "'"), 'KPI def: ' + m);
    });
}

function test_page_wiring() {
    assert.ok(PAGE.includes('Shell.init'), 'shared Shell used');
    assert.ok(PAGE.includes("ModuleFlag.requires('module_b_srm'"), 'module-B guard at load');
    assert.ok(PAGE.includes('DrillDown.mount'), 'DrillDown used for KPI drill');
    assert.ok(PAGE.includes('EmptyState.'), 'EmptyState treatments used');
    assert.ok(PAGE.includes('onPeriodChange'), 'period selector re-filters counters');
    assert.ok(PAGE.includes('withQs(H.ENDPOINTS.overview'), 'period params feed overview');
    assert.ok(PAGE.includes('ApiClient.post(H.ENDPOINTS.hazardCreate'), 'create posts via ApiClient');
    assert.ok(PAGE.includes('H.ENDPOINTS.hazardTriage(currentDetailId)'), 'triage posts to per-hazard endpoint');
}

// ---------------------------------------------------------------------------
// Endpoints (must match live Phase 3 routes — no backend changes)
// ---------------------------------------------------------------------------

function test_endpoints() {
    assert.strictEqual(H.ENDPOINTS.overview, '/api/v1/dashboard/overview');
    assert.strictEqual(H.ENDPOINTS.hazardStats, '/api/v1/hazards/stats');
    assert.strictEqual(H.ENDPOINTS.canCapStats, '/api/v1/cans/stats');
    assert.strictEqual(H.ENDPOINTS.caps, '/api/v1/cans/caps');
    assert.strictEqual(H.ENDPOINTS.hazardCreate, '/api/v1/hazards/');
    assert.strictEqual(H.ENDPOINTS.hazardTriage('abc'), '/api/v1/hazards/abc/triage');
    assert.strictEqual(H.ENDPOINTS.masterRegister, '/api/v1/dashboard/master-register');
}

// ---------------------------------------------------------------------------
// Status bucket mapping (P4-2.5 — every status → correct bucket)
// ---------------------------------------------------------------------------

function test_hazard_buckets() {
    assert.strictEqual(H.bucketizeStatus('hazards', 'Open'), 'Open');
    assert.strictEqual(H.bucketizeStatus('hazards', 'Processing'), 'In Process');
    assert.strictEqual(H.bucketizeStatus('hazards', 'Under Review'), 'In Process');
    assert.strictEqual(H.bucketizeStatus('hazards', 'Pending Closure'), 'In Process');
    assert.strictEqual(H.bucketizeStatus('hazards', 'Reopened'), 'In Process');
    assert.strictEqual(H.bucketizeStatus('hazards', 'Closed'), 'Closed');
    assert.strictEqual(H.bucketizeStatus('hazards', 'weird-legacy'), 'In Process', 'unknown falls through');
}

function test_can_buckets() {
    assert.strictEqual(H.bucketizeStatus('cans', 'Open'), 'Open');
    assert.strictEqual(H.bucketizeStatus('cans', 'Escalated'), 'Open', 'attention');
    assert.strictEqual(H.bucketizeStatus('cans', 'Issued'), 'In Process');
    assert.strictEqual(H.bucketizeStatus('cans', 'Under Review'), 'In Process');
    assert.strictEqual(H.bucketizeStatus('cans', 'Closed'), 'Closed');
}

function test_cap_buckets() {
    assert.strictEqual(H.bucketizeStatus('caps', 'In Progress'), 'In Process');
    assert.strictEqual(H.bucketizeStatus('caps', 'Under Review'), 'In Process');
    assert.strictEqual(H.bucketizeStatus('caps', 'Revision Required'), 'In Process');
    assert.strictEqual(H.bucketizeStatus('caps', 'EIP'), 'In Process', 'attention styling via tone');
    assert.strictEqual(H.bucketizeStatus('caps', 'Completed'), 'Closed');
    assert.strictEqual(H.bucketizeStatus('caps', 'Overdue'), 'Open', 'attention');
}

function test_bucketize_counts_and_reports() {
    assert.deepStrictEqual(
        H.bucketizeCounts('hazards', { Open: 61, Processing: 30, 'Under Review': 14, Closed: 23 }),
        { Open: 61, 'In Process': 44, Closed: 23 }
    );
    assert.deepStrictEqual(
        H.bucketizeCounts('caps', { 'In Progress': 5, 'Under Review': 3, 'Revision Required': 2, Completed: 7, Overdue: 1 }),
        { Open: 1, 'In Process': 10, Closed: 7 }
    );
    assert.deepStrictEqual(
        H.reportsBuckets({ total_reports: 50, open_reports: 20, closed_reports: 25 }),
        { Open: 20, 'In Process': 5, Closed: 25, total: 50 }
    );
    assert.deepStrictEqual(
        H.reportsBuckets({}),
        { Open: 0, 'In Process': 0, Closed: 0, total: 0 }
    );
}

// ---------------------------------------------------------------------------
// EIP derivation + "None" display
// ---------------------------------------------------------------------------

function test_eip_none_when_zero() {
    assert.deepStrictEqual(H.eipDisplay(0), { text: 'None', tone: 'neutral' });
    assert.deepStrictEqual(H.eipDisplay(3), { text: '3', tone: 'red' });
}

function test_eip_derivation() {
    const caps = [
        { id: 'a', escalated_to_ae: true, ae_signature: null },   // EIP
        { id: 'b', escalated_to_ae: true, ae_signature: true },   // acked (bool serializer)
        { id: 'c', escalated_to_ae: false, ae_signature: null },  // not escalated
        { id: 'd', status: 'EIP' },                               // persisted status (P2-16)
        { id: 'e', status: 'In Progress' },                      // ordinary
    ];
    assert.deepStrictEqual(H.deriveEIP(caps).map((c) => c.id), ['a', 'd']);
    assert.strictEqual(H.isEIP({ escalated_to_ae: true, ae_signature: {} }), true, 'empty-sig object');
}

// ---------------------------------------------------------------------------
// Color thresholds (§2.4 hardcoded defaults)
// ---------------------------------------------------------------------------

function test_tones() {
    assert.strictEqual(H.toneFor({ Open: 5, 'In Process': 0, Closed: 10 }, {}), 'green', 'no overdue, nothing in process');
    assert.strictEqual(H.toneFor({ Open: 0, 'In Process': 4, Closed: 10 }, {}), 'yellow', 'in-process items');
    assert.strictEqual(H.toneFor({ Open: 0, 'In Process': 0, Closed: 10 }, { overdue: 1 }), 'red', 'overdue');
    assert.strictEqual(H.toneFor({ Open: 9, 'In Process': 0, Closed: 0 }, { escalated: 2 }), 'red', 'escalated');
    assert.strictEqual(H.toneFor({ Open: 0, 'In Process': 9, Closed: 0 }, { revisionRequired: 1 }), 'red', 'revision required');
    const red = H.redSignalsFrom(
        { Open: 1, Reopened: 2 },
        { Open: 1, Escalated: 1, Closed: 1 },
        { 'In Progress': 1, Overdue: 3, 'Revision Required': 2, Completed: 1 }
    );
    assert.deepStrictEqual(red, { overdue: 3, escalated: 1, revisionRequired: 2 });
}

// ---------------------------------------------------------------------------
// Create-hazard + triage payloads (mirror backend models)
// ---------------------------------------------------------------------------

function test_create_payload_valid() {
    const p = H.buildCreateHazardPayload({
        title: 'Fuel leak on stand',
        description: 'Ground crew observed fuel pooling under the wing root.',
        source: 'VSR',
        source_id: 'VSR-2026-014',
        taxonomy: 'Technical',
        priority: 'H',
        srm_flag: true,
    }, 'tenant-1');
    assert.strictEqual(p.title, 'Fuel leak on stand');
    assert.strictEqual(p.tenant_id, 'tenant-1');
    assert.strictEqual(p.srm_flag, true);
    assert.strictEqual(p.source, 'VSR');
}

function test_create_payload_rejects_bad_input() {
    assert.throws(() => H.buildCreateHazardPayload({}, 't'), /Missing\/invalid hazard fields/);
    assert.throws(() => H.buildCreateHazardPayload({
        title: 'x', description: 'short',
        source: 'Tweet', source_id: '', taxonomy: 'Alien', priority: 'Z',
    }, 't'), /title.*description.*source.*source_id.*taxonomy.*priority/);
}

function test_triage_payload() {
    assert.deepStrictEqual(
        H.buildTriagePayload('Accepted', 'Valid report', 'H'),
        { decision: 'Accepted', notes: 'Valid report', initial_priority: 'H' }
    );
    assert.deepStrictEqual(H.buildTriagePayload('Escalated'), { decision: 'Escalated' });
    assert.throws(() => H.buildTriagePayload('Maybe'), /decision must be one of/);
    assert.throws(() => H.buildTriagePayload('Accepted', null, 'X'), /initial_priority/);
}

// ---------------------------------------------------------------------------
// Role gate (§2.1)
// ---------------------------------------------------------------------------

function test_role_gate() {
    assert.strictEqual(H.roleAllowed('TENANT_ADMIN'), true);
    assert.strictEqual(H.roleAllowed('SAFETY_OFFICER'), true);
    assert.strictEqual(H.roleAllowed('SUPER_ADMIN'), true);
    assert.strictEqual(H.roleAllowed('DEPT_ADMIN'), false);
    assert.strictEqual(H.roleAllowed('CAAN_SMD'), false);
    assert.strictEqual(H.roleAllowed('ACCOUNTABLE_EXECUTIVE'), false);
}

// ---------------------------------------------------------------------------
// DrillDown integration: counter click → breakdown → records
// ---------------------------------------------------------------------------

function test_drill_integration() {
    const container = { innerHTML: '', querySelectorAll: () => [], querySelector: () => null };
    const hazards = [
        { id: '1', title: 'A', status: 'Open' },
        { id: '2', title: 'B', status: 'Processing' },
        { id: '3', title: 'C', status: 'Closed' },
    ];
    const dd = DrillDown.mount(container, { metric: 'HAZARDS' });
    assert.strictEqual(dd.render(hazards), 3, 'L1 counter from records');
    return dd.drill(null).then((counts) => {
        assert.deepStrictEqual(counts, { Open: 1, 'In Process': 1, Closed: 1 });
        assert.ok(container.innerHTML.includes('Status breakdown'), 'L2 painted on counter click');
        return dd.drill('Open');
    }).then((records) => {
        // No records endpoint in Node (no ApiClient) → client-side fallback
        // filters the L1 records by bucket.
        assert.strictEqual(records.length, 1, 'L3 filtered to bucket');
        assert.strictEqual(records[0].id, '1');
        assert.ok(container.innerHTML.includes('A'), 'L3 lists the record');
    });
}

// ---------------------------------------------------------------------------

function main() {
    test_page_structure();
    test_page_wiring();
    test_endpoints();
    test_hazard_buckets();
    test_can_buckets();
    test_cap_buckets();
    test_bucketize_counts_and_reports();
    test_eip_none_when_zero();
    test_eip_derivation();
    test_tones();
    test_create_payload_valid();
    test_create_payload_rejects_bad_input();
    test_triage_payload();
    test_role_gate();
    test_drill_integration().then(() => {
        console.log('test_safety_dashboard: 15 tests passed (structure, wiring, endpoints, buckets, EIP, tones, payloads, roles, drill)');
    }).catch((e) => { console.error(e); process.exit(1); });
}

main();
