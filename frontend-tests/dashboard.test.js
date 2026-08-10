/**
 * Frontend unit tests for the Airline SMS Dashboard render helpers.
 *
 * The render logic in public/js/dashboard-render.js is dependency-free (no
 * firebase/DOM framework) so it can be exercised in plain Node with a minimal
 * document shim. The fixtures mirror the payload of
 * GET /api/v1/dashboard/airline/sms-maturity (the backend `_sms_maturity_model`).
 */
'use strict';

const assert = require('assert');
const DashboardRender = require('../public/js/dashboard-render.js');

// ---------------------------------------------------------------------------
// Minimal document shim
// ---------------------------------------------------------------------------

function makeElement() {
    return { innerHTML: '', style: {}, dataset: {} };
}

function makeDoc() {
    const els = {};
    const get = (id) => {
        if (!els[id]) els[id] = makeElement();
        return els[id];
    };
    return { getElementById: get, __els: els };
}

const SAMPLE = {
    tenant: 'Airline One',
    tenant_id: 'air1',
    overall_score: 72.0,
    tier: 'watch',
    tier_label: 'Watch',
    pillars: {
        safety_policy: 85,
        safety_risk_management: 60,
        safety_assurance: 75,
        safety_promotion: 68,
    },
    assessment: {
        strengths: ['Safety Policy'],
        improvement_opportunities: ['Safety Risk Management', 'Safety Promotion'],
        priority_actions: [{
            pillar_name: 'Safety Risk Management',
            score_pct: 60,
            tier: 'action',
            summary: 'Improve hazard identification and risk assessment processes.',
            root_causes: ['Reporting culture', 'Limited training'],
            actions: [{
                action: 'Run refresher hazard-identification training',
                priority: 'high',
                owner: 'Safety Manager',
                timeframe: '30 days',
                icao_reference: 'Annex 19 §4.2',
                success_metric: 'Training uptake >= 90%',
            }],
            kpi_target: 70,
        }],
    },
    latest_assessment_date: '2026-08-01',
    response_count: 12,
    period_days: 365,
    history: [{
        period: '2026-06',
        assessment_date: '2026-06-15',
        overall_score: 80,
        tier: 'watch',
        tier_label: 'Watch',
        pillars: { safety_policy: 90, safety_risk_management: 70, safety_assurance: 80, safety_promotion: 80 },
        response_count: 5,
    }, {
        period: '2026-07',
        assessment_date: '2026-07-20',
        overall_score: 72,
        tier: 'watch',
        tier_label: 'Watch',
        pillars: { safety_policy: 85, safety_risk_management: 60, safety_assurance: 75, safety_promotion: 68 },
        response_count: 7,
    }],
};

const EMPTY = {
    tenant_id: 'air1',
    overall_score: null,
    tier: null,
    tier_label: null,
    pillars: {},
    assessment: { strengths: [], improvement_opportunities: [], priority_actions: [] },
    latest_assessment_date: null,
    response_count: null,
    history: [],
};

// ---------------------------------------------------------------------------
// tierBadge
// ---------------------------------------------------------------------------

function test_tier_badge_mapping() {
    assert.strictEqual(DashboardRender.tierBadge('strong', 'Good'), '<span class="badge b-acceptable">Good</span>');
    assert.strictEqual(DashboardRender.tierBadge('watch', 'Watch'), '<span class="badge b-tolerable">Watch</span>');
    assert.strictEqual(DashboardRender.tierBadge('action', 'Action Needed'), '<span class="badge b-action">Action Needed</span>');
    assert.strictEqual(DashboardRender.tierBadge('critical', 'Critical'), '<span class="badge b-intolerable">Critical</span>');
    assert.strictEqual(DashboardRender.tierBadge(null, 'x'), '<span class="badge b-tolerable">—</span>');
    assert.strictEqual(DashboardRender.tierBadge('watch', null), '<span class="badge b-tolerable">watch</span>');
}

// ---------------------------------------------------------------------------
// renderAll - populated data
// ---------------------------------------------------------------------------

function test_render_full_data() {
    const doc = makeDoc();
    DashboardRender.renderAll(SAMPLE, doc);

    const overview = doc.__els.overviewStats.innerHTML;
    assert.ok(overview.includes('72%'), 'overall score rendered');
    assert.ok(overview.includes('Watch'), 'tier label rendered');
    assert.ok(overview.includes('12'), 'response count rendered');
    assert.ok(overview.includes('2026-08-01'), 'latest assessment date rendered');

    const bannerEl = doc.__els.maturityBanner;
    assert.ok(bannerEl.innerHTML.includes('Action needed'), 'low-pillar banner shown');
    assert.strictEqual(bannerEl.style.display, 'block', 'banner visible');

    const components = doc.__els.componentsGrid.innerHTML;
    assert.ok(components.includes('Safety Policy'), 'pillar label rendered');
    assert.ok(components.includes('85%'), 'pillar pct rendered');
    assert.ok(components.includes('No data') === false, 'no missing-data badge when pillars present');

    const assessment = doc.__els.assessmentContent.innerHTML;
    assert.ok(assessment.includes('Strengths'), 'strengths section rendered');
    assert.ok(assessment.includes('Improvement Opportunities'), 'opportunities section rendered');
    assert.ok(assessment.includes('Priority Improvement Actions'), 'priority actions header rendered');
    assert.ok(assessment.includes('Run refresher hazard-identification training'), 'action text rendered');
    assert.ok(assessment.includes('Training uptake >= 90%'), 'success metric rendered');

    const history = doc.__els.historyBody.innerHTML;
    assert.ok(history.includes('2026-06'), 'history period rendered');
    assert.ok(history.includes('2026-07'), 'second history period rendered');
    assert.ok(history.includes('80%'), 'history overall score rendered');
    assert.ok(history.includes('<td>5</td>'), 'history response count rendered');
}

// ---------------------------------------------------------------------------
// renderAll - empty data (no surveys)
// ---------------------------------------------------------------------------

function test_render_empty_data() {
    const doc = makeDoc();
    DashboardRender.renderAll(EMPTY, doc);

    const statsEl = doc.__els.overviewStats;
    assert.ok(statsEl.innerHTML.includes('—'), 'overall score shows em-dash when null');
    assert.ok(doc.__els.maturityBanner.innerHTML.includes('No survey responses'), 'empty banner shown');

    const components = doc.__els.componentsGrid.innerHTML;
    assert.ok(components.includes('No data'), 'pillars show no-data badge');

    const assessment = doc.__els.assessmentContent.innerHTML;
    assert.ok(assessment.includes('no assessment available'), 'empty assessment state rendered');

    const history = doc.__els.historyBody.innerHTML;
    assert.ok(history.includes('No monthly history'), 'empty history state rendered');
}

// ---------------------------------------------------------------------------
// renderAll - error tolerance (malformed payload must not throw)
// ---------------------------------------------------------------------------

function test_render_malformed_payload_does_not_throw() {
    const doc = makeDoc();

    assert.doesNotThrow(() => DashboardRender.renderAll({}, doc));
    assert.doesNotThrow(() => DashboardRender.renderAll(null, doc));
    assert.doesNotThrow(() => DashboardRender.renderAll({ overall_score: 50, assessment: null }, doc));

    const history = doc.__els.historyBody.innerHTML;
    assert.ok(history.includes('No monthly history'), 'history falls back to empty state');
}

// ---------------------------------------------------------------------------

function main() {
    test_tier_badge_mapping();
    test_render_full_data();
    test_render_empty_data();
    test_render_malformed_payload_does_not_throw();
    console.log('dashboard-render: 4 tests passed');
}

main();
