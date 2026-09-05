/**
 * Frontend unit tests for SRAM (public/js/sram.js).
 *
 * Covers the pure helpers (risk matrix, tolerability, BSV) and the composed
 * saveSRAM pipeline against a mock ApiClient. The factory is dependency-free
 * at require() time; window is only consulted when an API call runs.
 */
'use strict';

const assert = require('assert');
const SRAM = require('../public/js/sram.js');

// ---------------------------------------------------------------------------
// Risk matrix / tolerability
// ---------------------------------------------------------------------------

function test_matrix_is_exhaustive() {
    const table = SRAM.buildRiskMatrix();
    assert.strictEqual(table.length, 5, '5 probability rows');
    table.forEach((row) => {
        assert.strictEqual(row.cells.length, 5, '5 severity columns per row');
        row.cells.forEach((cell) => {
            assert.ok(['Intolerable', 'Tolerable', 'Acceptable'].includes(cell.tolerability),
                `cell ${cell.risk_index} has a valid tolerability`);
            assert.ok(['red', 'yellow', 'green'].includes(cell.color),
                `cell ${cell.risk_index} has a valid color`);
        });
    });

    // Tolerance set cardinality must be 25 total.
    let counts = { Intolerable: 0, Tolerable: 0, Acceptable: 0 };
    for (const row of table) {
        for (const cell of row.cells) counts[cell.tolerability] += 1;
    }
    assert.strictEqual(counts.Intolerable, 6, 'Intolerable has 6 cells');
    assert.strictEqual(counts.Tolerable, 12, 'Tolerable has 12 cells');
    assert.strictEqual(counts.Acceptable, 7, 'Acceptable has 7 cells');
    assert.strictEqual(counts.Intolerable + counts.Tolerable + counts.Acceptable, 25, 'matrix is 25 cells');

    // Straight-line cells.
    assert.strictEqual(SRAM.getTolerability(5, 'A'), 'Intolerable');
    assert.strictEqual(SRAM.getTolerability(4, 'C'), 'Tolerable');
    assert.strictEqual(SRAM.getTolerability(1, 'E'), 'Acceptable');
    assert.strictEqual(SRAM.getColor(5, 'A'), 'red');
    assert.strictEqual(SRAM.getColor(1, 'E'), 'green');
}

function test_risk_index_normalization() {
    assert.strictEqual(SRAM.riskIndex(4, 'C'), '4C');
    assert.strictEqual(SRAM.riskIndex(9, 'F'), '5E', 'clamps out-of-range inputs');
    assert.strictEqual(SRAM.riskIndex(0, 'a'), '1A', 'lowercase severity normalised');
}

// ---------------------------------------------------------------------------
// Barrier Strength Value
// ---------------------------------------------------------------------------

function test_bsv_calculation() {
    const all5 = {
        effectiveness: 5, cost_benefit: 5, practicality: 5, acceptability: 5,
        enforceability: 5, durability: 5, disinclination: 5,
    };
    const result = SRAM.bsvFromScores(all5);
    assert.strictEqual(result.bsv, 5, 'all-5 scores give BSV 5');
    assert.strictEqual(result.correlation, 'Strong');

    const all1 = {};
    Object.keys(all5).forEach((k) => { all1[k] = 1; });
    const weak = SRAM.bsvFromScores(all1);
    assert.strictEqual(weak.bsv, 1, 'all-1 scores give BSV 1');
    assert.strictEqual(weak.correlation, 'Very Weak');

    const empty = SRAM.bsvFromScores({});
    assert.strictEqual(empty.bsv, null, 'no scores gives null BSV');
    assert.strictEqual(empty.correlation, 'Unassessed');

    // Weighted: effectiveness weight 3 dominates.
    const weighted = SRAM.bsvFromScores({
        effectiveness: 5, cost_benefit: 1, practicality: 1, acceptability: 1,
        enforceability: 1, durability: 1, disinclination: 1,
    });
    // total = 5*3 + 5*1 + 1*2 = 22 over weight 10 -> 2.2
    assert.strictEqual(weighted.bsv, 2.2, 'weighted BSV respects element weights');

    const partial = SRAM.bsvFromScores({ effectiveness: 5 });
    assert.strictEqual(partial.bsv, 5, 'single-element score uses its weight');
    assert.strictEqual(partial.filled, 1, 'filled count reflects provided elements');
}

function test_bsv_labels() {
    assert.strictEqual(SRAM.bsvLabel(5), 'Strong');
    assert.strictEqual(SRAM.bsvLabel(4.2), 'Satisfactory');
    assert.strictEqual(SRAM.bsvLabel(3), 'Moderate');
    assert.strictEqual(SRAM.bsvLabel(2), 'Weak');
    assert.strictEqual(SRAM.bsvLabel(1), 'Very Weak');
    assert.strictEqual(SRAM.bsvLabel(null), 'Unassessed');
}

// ---------------------------------------------------------------------------
// Registers / formatting helpers
// ---------------------------------------------------------------------------

function test_helpers() {
    assert.strictEqual(SRAM.statusLabel('in_progress'), 'In Progress');
    assert.strictEqual(SRAM.statusLabel('IMPLEMENTED'), 'Implemented');
    assert.strictEqual(SRAM.statusLabel(null), '-');
    assert.strictEqual(SRAM.statusBadgeClass('closed'), 'badge-completed');
    assert.strictEqual(SRAM.statusBadgeClass('open'), 'badge-new');
    assert.strictEqual(SRAM.formatDate(null), '-');
}

// ---------------------------------------------------------------------------
// saveSRAM pipeline with a mock ApiClient
// ---------------------------------------------------------------------------

function makeMockClient() {
    const calls = [];
    const client = {
        calls,
        get(path) { calls.push(['get', path]); return Promise.resolve({ success: true, data: {} }); },
        post(path, body) {
            calls.push(['post', path, body]);
            if (path.endsWith('/bowtie')) return Promise.resolve({ id: 'bowtie-1', hazard_id: 'HZ-001' });
            return Promise.resolve({ id: 'item-' + calls.length });
        },
        patch(path, body) { calls.push(['patch', path, body]); return Promise.resolve({ success: true, data: {} }); },
    };
    return client;
}

function test_save_sram_full_flow() {
    const client = makeMockClient();
    global.window = { ApiClient: client };

    const state = {
        hazard_id: 'HZ-001',
        bowtie_id: null,
        top_event: 'Engine failure',
        pending: {
            threats: [{ threat: 'Bird strike' }],
            consequences: [{ consequence: 'Forced landing', severity: 'C' }],
            controls: [{ control: 'Bird patrol', control_type: 'preventive' }],
        },
        assessment: { probability_current: 4, severity_current: 'C', barrier_scores: {} },
        acceptance: { alarp_justification: 'Controls reduce residual risk', status: 'in_progress' },
    };

    return SRAM.saveSRAM(state).then((result) => {
        assert.ok(state.bowtie_id, 'bowtie id captured from create response');
        const methods = client.calls.map((c) => c[0]);
        const paths = client.calls.map((c) => c[1]);
        assert.ok(methods.includes('post'), 'create bowtie posted');
        assert.strictEqual(client.calls[0][1], '/api/v1/sram/bowtie', 'create bowtie is the first call');
        assert.strictEqual(client.calls[0][2].hazard_id, 'HZ-001');
        assert.ok(paths.includes('/api/v1/sram/bowtie/bowtie-1/threat'), 'threat drained');
        assert.ok(paths.includes('/api/v1/sram/bowtie/bowtie-1/consequence'), 'consequence drained');
        assert.ok(paths.includes('/api/v1/sram/bowtie/bowtie-1/control'), 'control drained');
        const riskCall = client.calls.find((c) => c[1] === '/api/v1/sram/risk/calculate');
        assert.ok(riskCall, 'calculateRisk invoked when assessment present');
        assert.strictEqual(riskCall[2].hazard_id, 'HZ-001');
        assert.strictEqual(riskCall[2].probability_current, 4);
        const acceptCall = client.calls.find((c) => c[1] === '/api/v1/sram/risk/accept');
        assert.ok(acceptCall, 'acceptRisk invoked when justification present');
        assert.strictEqual(acceptCall[2].alarp_justification, state.acceptance.alarp_justification);
        assert.ok(result, 'pipeline resolves');
        delete global.window;
    });
}

function test_save_sram_minimal_flow() {
    const client = makeMockClient();
    global.window = { ApiClient: client };

    // No assessment, no acceptance: only the bowtie is created.
    return SRAM.saveSRAM({
        hazard_id: 'HZ-002',
        bowtie_id: 'existing-bowtie',
        pending: { threats: [], consequences: [], controls: [] },
        assessment: null,
        acceptance: null,
    }).then(() => {
        const paths = client.calls.map((c) => c[1]);
        assert.strictEqual(client.calls.length, 0, 'no API calls when nothing to do');
        assert.strictEqual(paths.indexOf('/api/v1/sram/bowtie'), -1, 'no bowtie create when id known');
        assert.strictEqual(paths.indexOf('/api/v1/sram/risk/calculate'), -1, 'no risk calc without assessment');
        assert.strictEqual(paths.indexOf('/api/v1/sram/risk/accept'), -1, 'no accept without justification');
        delete global.window;
    });
}

function test_save_sram_requires_hazard() {
    const client = makeMockClient();
    global.window = { ApiClient: client };
    return SRAM.saveSRAM({ hazard_id: '', pending: {}, assessment: null, acceptance: null })
        .then(() => { throw new Error('should have rejected without hazard'); })
        .catch((err) => {
            assert.ok(/No hazard selected/.test(err.message), 'rejects with a clear message');
            assert.strictEqual(client.calls.length, 0, 'no calls made without hazard');
            delete global.window;
        });
}

function test_load_hazards_normalises() {
    const client = makeMockClient();
    global.window = { ApiClient: client };
    client.get = (path) => Promise.resolve({
        rows: [
            { reference: 'HZ-001', title: 'Bird strike', type: 'Hazard', status: 'Open', risk_level: 'Low' },
            { reference: 'CAN-001', title: 'Narrow runway', type: 'CAN' },
            { reference: 'HZ-002', title: 'Fatigue', type: 'hazard', status: 'Closed' },
        ],
    });
    return SRAM.loadHazards().then((out) => {
        assert.strictEqual(out.length, 2, 'filters to hazards case-insensitively');
        assert.strictEqual(out[0].id, 'HZ-001', 'uses reference when no id present');
        assert.strictEqual(out[1].id, 'HZ-002');
        assert.strictEqual(out[0].title, 'Bird strike');
        delete global.window;
    });
}

// ---------------------------------------------------------------------------

function main() {
    test_matrix_is_exhaustive();
    test_risk_index_normalization();
    test_bsv_calculation();
    test_bsv_labels();
    test_helpers();

    // Async tests share global.window, so they MUST run strictly sequentially.
    return Promise.resolve()
        .then(test_load_hazards_normalises)
        .then(test_save_sram_full_flow)
        .then(test_save_sram_minimal_flow)
        .then(test_save_sram_requires_hazard)
        .then(() => {
            console.log('sram.js: 9 tests passed');
        });
}

main().catch((err) => { console.error(err); process.exit(1); });