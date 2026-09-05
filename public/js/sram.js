/**
 * ============================================================================
 * FILE: public/js/sram.js
 * PURPOSE: SRAM - Safety Risk Assessment & Mitigation (Bow-Tie, Risk Matrix,
 *          Barrier Strength, ALARP acceptance). ICAO Annex 19 / Doc 9859 /
 *          CAAN Chapter 2.3.
 *
 * Exposes window.SRAM (and CommonJS module.exports for Node testability):
 *   window.SRAM {
 *     // pure helpers (Node-testable, no window deps)
 *     SEVERITY_LETTERS, ELEMENT_LABELS, getTolerability, getColor,
 *     riskIndex, buildRiskMatrix, bsvFromScores, bsvLabel, formatDate,
 *     // API operations (require ApiClient at call time)
 *     loadHazards, loadBowtie, getBowtie, createBowtie, addThreat,
 *     addConsequence, addControl, calculateRisk, acceptRisk,
 *     loadRiskRegister, loadBarriers, updateBarrier, saveSRAM
 *   }
 * ============================================================================
 */
(function (root, factory) {
    if (typeof module === 'object' && module.exports) { module.exports = factory(); }
    else { root.SRAM = factory(); }
}(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    // ------------------------------------------------------------------
    // Pure constants
    // ------------------------------------------------------------------

    var SEVERITY_LETTERS = ['A', 'B', 'C', 'D', 'E'];

    var ELEMENT_KEYS = [
        'effectiveness', 'cost_benefit', 'practicality', 'acceptability',
        'enforceability', 'durability', 'disinclination',
    ];

    var ELEMENT_LABELS = {
        effectiveness: 'Effectiveness',
        cost_benefit: 'Cost / Benefit',
        practicality: 'Practicality',
        acceptability: 'Acceptability',
        enforceability: 'Enforceability',
        durability: 'Durability',
        disinclination: 'Disinclination',
    };

    var ELEMENT_WEIGHTS = {
        effectiveness: 3, cost_benefit: 1, practicality: 1, acceptability: 1,
        enforceability: 1, durability: 1, disinclination: 2,
    };

    var TOLERANCE_CLASSES = {
        '5A': 'Intolerable', '5B': 'Intolerable', '5C': 'Intolerable',
        '4A': 'Intolerable', '4B': 'Intolerable', '3A': 'Intolerable',
        '5D': 'Tolerable', '5E': 'Tolerable', '4C': 'Tolerable',
        '4D': 'Tolerable', '4E': 'Tolerable', '3B': 'Tolerable',
        '3C': 'Tolerable', '3D': 'Tolerable', '2A': 'Tolerable',
        '2B': 'Tolerable', '2C': 'Tolerable', '1A': 'Tolerable',
        '3E': 'Acceptable', '2D': 'Acceptable', '2E': 'Acceptable',
        '1B': 'Acceptable', '1C': 'Acceptable', '1D': 'Acceptable',
        '1E': 'Acceptable',
    };

    // ------------------------------------------------------------------
    // API plumbing (ApiClient with optional AviaSDCPSApi fallback).
    // ApiClient paths are fully qualified: /api/v1/...
    // ------------------------------------------------------------------

    function _client() {
        if (window.ApiClient) return window.ApiClient;
        if (window.AviaSDCPSApi) return window.AviaSDCPSApi;
        throw new Error('No API client found. Load /js/api/client.js first.');
    }

    function _fullPath(path) {
        if (window.ApiClient) return '/api/v1' + path;
        return path;
    }

    function _get(path, params) {
        var qs = '';
        if (params && Object.keys(params).length) {
            var parts = [];
            Object.keys(params).forEach(function (k) {
                if (params[k] !== undefined && params[k] !== null && params[k] !== '') {
                    parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(params[k]));
                }
            });
            if (parts.length) qs = '?' + parts.join('&');
        }
        try {
            return _client().get(_fullPath(path) + qs);
        } catch (err) {
            return Promise.reject(err);
        }
    }

    function _post(path, body) {
        try {
            return _client().post(_fullPath(path), body);
        } catch (err) {
            return Promise.reject(err);
        }
    }

    function _patch(path, body) {
        try {
            if (typeof _client().patch === 'function') return _client().patch(_fullPath(path), body);
            return _client().put(_fullPath(path), body);
        } catch (err) {
            return Promise.reject(err);
        }
    }

    // ------------------------------------------------------------------
    // Pure helpers
    // ------------------------------------------------------------------

    function clamp(v, lo, hi) {
        v = Number(v);
        if (isNaN(v)) v = lo;
        return Math.min(hi, Math.max(lo, v));
    }

    function severityToValue(letter) {
        var idx = SEVERITY_LETTERS.indexOf(String(letter || '').toUpperCase());
        return idx === -1 ? 1 : idx + 1;
    }

    function riskIndex(probability, severity) {
        var p = clamp(probability, 1, 5);
        var s = String(severity || 'E').toUpperCase();
        if (SEVERITY_LETTERS.indexOf(s) === -1) s = 'E';
        return String(p) + s;
    }

    function getTolerability(probability, severity) {
        var idx = riskIndex(probability, severity);
        return TOLERANCE_CLASSES[idx] || 'Acceptable';
    }

    function getColor(probability, severity) {
        var t = getTolerability(probability, severity);
        if (t === 'Intolerable') return 'red';
        if (t === 'Tolerable') return 'yellow';
        return 'green';
    }

    function buildRiskMatrix() {
        var table = [];
        for (var p = 5; p >= 1; p--) {
            var row = { probability: p, cells: [] };
            SEVERITY_LETTERS.forEach(function (sev) {
                var tolerability = getTolerability(p, sev);
                var color = getColor(p, sev);
                var value = severityToValue(sev);
                row.cells.push({
                    probability: p, severity: sev,
                    risk_index: riskIndex(p, sev),
                    severity_value: value,
                    tolerability: tolerability,
                    color: color,
                });
            });
            table.push(row);
        }
        return table;
    }

    function bsvFromScores(scores) {
        var total = 0, weight = 0, filled = 0;
        ELEMENT_KEYS.forEach(function (key) {
            var raw = scores && scores[key];
            if (raw === undefined || raw === null || raw === '') return;
            var w = ELEMENT_WEIGHTS[key] || 1;
            total += clamp(raw, 1, 5) * w;
            weight += w;
            filled += 1;
        });
        if (!weight) return { bsv: null, weight: 0, score: 3.0, filled: 0, correlation: 'Unassessed' };
        var score = Math.round((total / weight) * 10) / 10;
        return { bsv: score, weight: weight, score: score, filled: filled, correlation: bsvLabel(score) };
    }

    function bsvLabel(bsv) {
        if (bsv === null || bsv === undefined || bsv === '') return 'Unassessed';
        var v = Number(bsv);
        if (isNaN(v)) return 'Unassessed';
        if (v >= 4.8) return 'Strong';
        if (v >= 4.0) return 'Satisfactory';
        if (v >= 3.0) return 'Moderate';
        if (v >= 2.0) return 'Weak';
        return 'Very Weak';
    }

    function formatDate(iso) {
        if (!iso) return '-';
        try { return new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' }); }
        catch (e) { return iso; }
    }

    function statusLabel(status) {
        var map = { open: 'Open', in_progress: 'In Progress', closed: 'Closed', not_started: 'Not Started', implemented: 'Implemented', verified: 'Verified' };
        return map[String(status || '').toLowerCase()] || status || '-';
    }

    function statusBadgeClass(status) {
        var s = String(status || '').toLowerCase();
        if (s === 'closed' || s === 'implemented' || s === 'verified') return 'badge-completed';
        if (s === 'in_progress' || s === 'processing') return 'badge-processing';
        if (s === 'open' || s === 'not_started') return 'badge-new';
        if (s === 'in_test' || s === 'internal') return 'badge-warning';
        return 'badge-default';
    }

    // ------------------------------------------------------------------
    // Master register integration (hazards)
    // ------------------------------------------------------------------

    function normalizeHazards(data) {
        var rows = (data && data.rows) || [];
        return rows.filter(function (r) {
            return String(r.type || '').toUpperCase() === 'HAZARD';
        }).map(function (r) {
            return {
                id: r.id || r.hazard_id || r.reference,
                reference: r.reference,
                title: r.title,
                status: r.status,
                risk_level: r.risk_level,
            };
        });
    }

    function loadHazards() {
        return _get('/dashboard/master-register', { page_size: 200 }).then(normalizeHazards);
    }

    // ------------------------------------------------------------------
    // Bow-Tie
    // ------------------------------------------------------------------

    function createBowtie(hazardId, opts) {
        opts = opts || {};
        return _post('/sram/bowtie', {
            hazard_id: hazardId,
            top_event: opts.top_event || undefined,
            description: opts.description || undefined,
        });
    }

    function getBowtie(hazardId) {
        return _get('/sram/bowtie/' + encodeURIComponent(hazardId));
    }

    function addThreat(bowtieId, threat, opts) {
        opts = opts || {};
        return _post('/sram/bowtie/' + encodeURIComponent(bowtieId) + '/threat', {
            threat: threat,
            order: opts.order || undefined,
            probability: opts.probability || undefined,
        });
    }

    function addConsequence(bowtieId, consequence, severity, opts) {
        opts = opts || {};
        return _post('/sram/bowtie/' + encodeURIComponent(bowtieId) + '/consequence', {
            consequence: consequence,
            severity: severity || 'C',
            order: opts.order || undefined,
        });
    }

    function addControl(bowtieId, control, controlType, opts) {
        opts = opts || {};
        return _post('/sram/bowtie/' + encodeURIComponent(bowtieId) + '/control', {
            control: control,
            control_type: controlType,
            order: opts.order || undefined,
            owner: opts.owner || undefined,
            implementation_status: opts.implementation_status || undefined,
            action_by: opts.action_by || undefined,
            follow_up_date: opts.follow_up_date || undefined,
            barrier_scores: opts.barrier_scores || undefined,
        });
    }

    function updateBarrier(barrierId, patch) {
        return _patch('/sram/barriers/' + encodeURIComponent(barrierId), patch);
    }

    // ------------------------------------------------------------------
    // Risk + acceptance
    // ------------------------------------------------------------------

    function calculateRisk(hazardId, assessment) {
        return _post('/sram/risk/calculate', {
            hazard_id: hazardId,
            probability_current: assessment.probability_current,
            severity_current: assessment.severity_current,
            probability_resultant: assessment.probability_resultant || undefined,
            severity_resultant: assessment.severity_resultant || undefined,
            barrier_scores: assessment.barrier_scores || undefined,
        });
    }

    function acceptRisk(payload) {
        return _post('/sram/risk/accept', {
            hazard_id: payload.hazard_id || undefined,
            alarp_justification: payload.alarp_justification,
            status: payload.status || undefined,
            review_date: payload.review_date || undefined,
        });
    }

    // ------------------------------------------------------------------
    // Registers
    // ------------------------------------------------------------------

    function loadBarriers(hazardId) {
        var path = hazardId
            ? '/sram/barriers/' + encodeURIComponent(hazardId)
            : '/sram/barriers';
        return _get(path);
    }

    function loadRiskRegister(tenantId) {
        return _get('/sram/risk-register/' + encodeURIComponent(tenantId));
    }

    // ------------------------------------------------------------------
    // Composed flow used by the SRAM page "Save & Accept" action
    // ------------------------------------------------------------------
    // state: {
    //   hazard_id, bowtie_id (nullable), top_event, description,
    //   pending: { threats: [], consequences: [], controls: [] },
    //   assessment: {}, acceptance: {}
    // }
    // Returns the risk-register entry produced by acceptRisk.

    function saveSRAM(state) {
        var chain = Promise.resolve();
        var created = null;

        if (!state.hazard_id) return Promise.reject(new Error('No hazard selected'));
        if (!state.bowtie_id) {
            chain = chain.then(function () {
                return createBowtie(state.hazard_id, {
                    top_event: state.top_event,
                    description: state.description,
                }).then(function (data) {
                    state.bowtie_id = data && (data.id || data.bowtie_id);
                    created = data;
                    return data;
                });
            });
        }

        function drain(list, fn) {
            list.forEach(function (item) {
                chain = chain.then(function () { return fn(item); });
            });
        }

        drain(state.pending.threats || [], function (item) {
            return addThreat(state.bowtie_id, item.threat, item);
        });
        drain(state.pending.consequences || [], function (item) {
            return addConsequence(state.bowtie_id, item.consequence, item.severity, item);
        });
        drain(state.pending.controls || [], function (item) {
            return addControl(state.bowtie_id, item.control, item.control_type, item);
        });

        chain = chain.then(function () {
            if (!state.assessment || !state.assessment.probability_current) {
                return { success: true, data: created };
            }
            return calculateRisk(state.hazard_id, state.assessment);
        });

        if (state.acceptance && state.acceptance.alarp_justification) {
            chain = chain.then(function () {
                return acceptRisk({
                    hazard_id: state.hazard_id,
                    alarp_justification: state.acceptance.alarp_justification,
                    status: state.acceptance.status,
                    review_date: state.acceptance.review_date,
                });
            });
        }

        return chain;
    }

    // ------------------------------------------------------------------

    return {
        SEVERITY_LETTERS: SEVERITY_LETTERS,
        ELEMENT_KEYS: ELEMENT_KEYS,
        ELEMENT_LABELS: ELEMENT_LABELS,
        ELEMENT_WEIGHTS: ELEMENT_WEIGHTS,
        getTolerability: getTolerability,
        getColor: getColor,
        riskIndex: riskIndex,
        buildRiskMatrix: buildRiskMatrix,
        bsvFromScores: bsvFromScores,
        bsvLabel: bsvLabel,
        formatDate: formatDate,
        statusLabel: statusLabel,
        statusBadgeClass: statusBadgeClass,
        loadHazards: loadHazards,
        createBowtie: createBowtie,
        getBowtie: getBowtie,
        addThreat: addThreat,
        addConsequence: addConsequence,
        addControl: addControl,
        updateBarrier: updateBarrier,
        calculateRisk: calculateRisk,
        acceptRisk: acceptRisk,
        loadBarriers: loadBarriers,
        loadRiskRegister: loadRiskRegister,
        saveSRAM: saveSRAM,
    };
}));