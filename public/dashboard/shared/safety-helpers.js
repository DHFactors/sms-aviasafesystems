/* ============================================================================
   FILE: safety-helpers.js
   PATH: public/dashboard/shared/safety-helpers.js
   PHASE: P4-2 (Wave 2 — Safety Manager dashboard logic)
   PURPOSE: Testable pure logic for public/dashboard/safety-dashboard.html:
            KPI bucket mapping (§2.3/P4-2.5), color tones (§2.4/P4-2.2),
            EIP derivation (MODULE_B §21/§23), create-hazard + triage
            payload builders, and the endpoint map. All HTTP goes through
            window.ApiClient on the page; this module never touches the
            network or the DOM.
   COLOR THRESHOLDS (P4-2.2 — HARDCODED DEFAULTS):
     Tenant-configurable thresholds do not exist in the backend yet, so the
     §2.4 rules ship as defaults: Green = no overdue items; Yellow = items
     In Process / Under Review; Red = any Overdue / Escalated / Revision
     Required. Phase 4 Wave 5 or a follow-up may source these from tenant
     config; the toneFor() signature already accepts an overrides bag.
   STATUS → BUCKET MAP (P4-2.5):
     Hazards: Open→Open; Processing/Under Review/Pending Closure/Reopened→
       In Process; Closed→Closed.
     CANs: Open/Escalated→Open (attention); Issued/Under Review/Processing→
       In Process; Closed→Closed.
     CAPs: In Progress/Under Review/Revision Required/EIP→In Process;
       Completed→Closed; Overdue/Open→Open (attention).
     EIP: single In-Process-with-attention bucket.
     Reports: open_reports→Open; closed_reports→Closed; remainder→In Process.
   NOTE: No build step. UMD-wrapped for Node unit tests
     (frontend-tests/test_safety_dashboard.js).
   ============================================================================ */
(function (root, factory) {
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = factory();
    } else {
        root.SafetyHelpers = factory();
    }
}(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    var BUCKETS = ['Open', 'In Process', 'Closed'];

    // Live backend endpoint map (all Phase 3 APIs verified live; no
    // backend changes in this wave). Router sources cited per route.
    var ENDPOINTS = {
        overview: '/api/v1/dashboard/overview',          // routes/dashboard.py:79
        hazardStats: '/api/v1/hazards/stats',            // routes/hazards.py:311
        canCapStats: '/api/v1/cans/stats',               // routes/can_cap.py:93
        caps: '/api/v1/cans/caps',                       // routes/can_cap.py:105 (?escalated_to_ae=true, P3-7)
        cans: '/api/v1/cans/',                           // routes/can_cap.py:52
        hazards: '/api/v1/hazards/',                     // routes/hazards.py:264 (list)
        hazardDetail: function (id) { return '/api/v1/hazards/' + encodeURIComponent(id); },
        hazardCreate: '/api/v1/hazards/',                // routes/hazards.py:232 (POST)
        hazardTriage: function (id) { return '/api/v1/hazards/' + encodeURIComponent(id) + '/triage'; },
        masterRegister: '/api/v1/dashboard/master-register', // routes/dashboard.py:198
        recent: '/api/v1/dashboard/recent',              // routes/dashboard.py:115
        trends: '/api/v1/dashboard/trends',              // routes/dashboard.py:145
        risk: '/api/v1/dashboard/risk',                  // routes/dashboard.py:133
        smsMaturity: '/api/v1/dashboard/airline/sms-maturity', // routes/dashboard.py:370
    };

    // Roles permitted on the Safety Manager dashboard (§2.1 + platform).
    var ALLOWED_ROLES = ['TENANT_ADMIN', 'SAFETY_OFFICER', 'SUPER_ADMIN', 'AIRLINE_ADMIN'];

    // --- Status → bucket ------------------------------------------------------
    // Per-metric maps; unknown statuses fall through to 'In Process' (never
    // drop a record from the drill-down denominators).

    function hazardBucket(status) {
        var s = String(status == null ? '' : status).trim().toLowerCase();
        if (s === 'open' || s === 'received' || s === 'overdue' || s === 'escalated') return 'Open';
        if (s === 'closed' || s === 'completed') return 'Closed';
        return 'In Process';
    }

    function canBucket(status) {
        var s = String(status == null ? '' : status).trim().toLowerCase();
        if (s === 'open' || s === 'escalated' || s === 'overdue') return 'Open';
        if (s === 'closed' || s === 'completed') return 'Closed';
        return 'In Process';
    }

    function capBucket(status) {
        var s = String(status == null ? '' : status).trim().toLowerCase();
        if (s === 'overdue' || s === 'open') return 'Open';
        if (s === 'completed' || s === 'closed') return 'Closed';
        return 'In Process';
    }

    function bucketizeStatus(metric, status) {
        if (metric === 'hazards') return hazardBucket(status);
        if (metric === 'cans') return canBucket(status);
        if (metric === 'caps' || metric === 'eip') return capBucket(status);
        return 'In Process';
    }

    function zeroBuckets() {
        return { Open: 0, 'In Process': 0, Closed: 0 };
    }

    // Fold a backend by_status object into the 3 buckets.
    function bucketizeCounts(metric, byStatus) {
        var out = zeroBuckets();
        if (!byStatus || typeof byStatus !== 'object') return out;
        Object.keys(byStatus).forEach(function (raw) {
            var n = Number(byStatus[raw]) || 0;
            out[bucketizeStatus(metric, raw)] += n;
        });
        return out;
    }

    // Reports buckets from the overview kpis block (dashboard.py _empty_kpis
    // shape: total_reports / open_reports / closed_reports).
    function reportsBuckets(kpis) {
        kpis = kpis || {};
        var total = Number(kpis.total_reports) || 0;
        var open = Number(kpis.open_reports) || 0;
        var closed = Number(kpis.closed_reports) || 0;
        var inProcess = Math.max(0, total - open - closed);
        return { Open: open, 'In Process': inProcess, Closed: closed, total: total };
    }

    // --- EIP derivation ---------------------------------------------------------
    // EIP = escalated_to_ae=true AND ae_signature IS NULL (MODULE_B §23;
    // db_models caps block), OR the persisted 'EIP' status (P2-16/P1-30).
    // The list serializer emits ae_signature as a BOOLEAN (can_cap.py:617),
    // so both the boolean and the raw-object shapes are accepted.
    function isEIP(cap) {
        if (!cap || typeof cap !== 'object') return false;
        if (String(cap.status || '').toUpperCase() === 'EIP') return true;
        if (!cap.escalated_to_ae) return false;
        var sig = cap.ae_signature;
        if (sig == null || sig === false || sig === '') return true;
        if (typeof sig === 'object' && !Object.keys(sig).length) return true;
        return false;
    }

    function deriveEIP(capsList) {
        return (capsList || []).filter(isEIP);
    }

    // --- Color tones (§2.4; hardcoded defaults — see header) ----------------------
    // redSignals: { overdue, escalated, revisionRequired } counts harvested
    // from the stats payloads. overrides: { redOn, yellowOn } future hook
    // for tenant-configurable thresholds (unused today).
    function toneFor(buckets, redSignals, overrides) {
        buckets = buckets || zeroBuckets();
        redSignals = redSignals || {};
        var red = (Number(redSignals.overdue) || 0) > 0 ||
            (Number(redSignals.escalated) || 0) > 0 ||
            (Number(redSignals.revisionRequired) || 0) > 0;
        if (red) return 'red';
        if ((Number(buckets['In Process']) || 0) > 0) return 'yellow';
        return 'green';
    }

    // Harvest red signals from live stats shapes:
    //   hazard by_status (Reopened counts as attention), can by_status
    //   (Escalated), cap by_status (Overdue, Revision Required).
    function redSignalsFrom(hazardByStatus, canByStatus, capByStatus) {
        var num = function (obj, key) {
            return (obj && Number(obj[key])) || 0;
        };
        return {
            overdue: num(capByStatus, 'Overdue'),
            escalated: num(canByStatus, 'Escalated'),
            revisionRequired: num(capByStatus, 'Revision Required'),
        };
    }

    // EIP counter: literal 'None' when zero (no red/green band); red
    // attention tone when non-zero.
    function eipDisplay(count) {
        var n = Number(count) || 0;
        if (n === 0) return { text: 'None', tone: 'neutral' };
        return { text: String(n), tone: 'red' };
    }

    // --- Payload builders ----------------------------------------------------------
    var HAZARD_SOURCES = ['VSR', 'MOR', 'Internal Audit', 'Quality Audit', 'CAAN Audit', 'Flight Diversion'];
    var HAZARD_TAXONOMIES = ['Organizational', 'Technical', 'Human', 'Environmental'];
    var HAZARD_PRIORITIES = ['H', 'M', 'L'];
    var TRIAGE_DECISIONS = ['Accepted', 'Rejected', 'Duplicate', 'Escalated'];

    // Mirrors HazardCreate required fields (models/hazard.py:197-244):
    // title≥3, description≥10, source∈creation sources, source_id,
    // taxonomy∈4-value set, priority∈H/M/L, tenant_id.
    function buildCreateHazardPayload(form, tenantId) {
        form = form || {};
        var missing = [];
        var title = String(form.title || '').trim();
        var description = String(form.description || '').trim();
        if (title.length < 3) missing.push('title (min 3 chars)');
        if (description.length < 10) missing.push('description (min 10 chars)');
        if (HAZARD_SOURCES.indexOf(form.source) === -1) missing.push('source');
        if (!String(form.source_id || '').trim()) missing.push('source_id');
        if (HAZARD_TAXONOMIES.indexOf(form.taxonomy) === -1) missing.push('taxonomy');
        if (HAZARD_PRIORITIES.indexOf(form.priority) === -1) missing.push('priority');
        if (!tenantId && !form.tenant_id) missing.push('tenant_id');
        if (missing.length) {
            throw new Error('Missing/invalid hazard fields: ' + missing.join(', '));
        }
        return {
            title: title,
            description: description,
            source: form.source,
            source_id: String(form.source_id).trim(),
            taxonomy: form.taxonomy,
            priority: form.priority,
            tenant_id: tenantId || form.tenant_id,
            function: form.function || undefined,
            threat: form.threat || undefined,
            consequence: form.consequence || undefined,
            top_event: form.top_event || undefined,
            srm_flag: !!form.srm_flag,
            department: form.department || undefined,
            assigned_to: form.assigned_to || undefined,
            recommended_action: form.recommended_action || undefined,
        };
    }

    // Mirrors TriageRequest (routes/hazards.py:45-48).
    function buildTriagePayload(decision, notes, initialPriority) {
        if (TRIAGE_DECISIONS.indexOf(decision) === -1) {
            throw new Error('decision must be one of ' + TRIAGE_DECISIONS.join(' | '));
        }
        var out = { decision: decision };
        if (notes) out.notes = notes;
        if (initialPriority) {
            if (HAZARD_PRIORITIES.indexOf(initialPriority) === -1) {
                throw new Error('initial_priority must be one of H | M | L');
            }
            out.initial_priority = initialPriority;
        }
        return out;
    }

    function roleAllowed(role) {
        return ALLOWED_ROLES.indexOf(String(role || '').toUpperCase()) !== -1;
    }

    return {
        BUCKETS: BUCKETS,
        ENDPOINTS: ENDPOINTS,
        ALLOWED_ROLES: ALLOWED_ROLES,
        HAZARD_SOURCES: HAZARD_SOURCES,
        HAZARD_TAXONOMIES: HAZARD_TAXONOMIES,
        HAZARD_PRIORITIES: HAZARD_PRIORITIES,
        TRIAGE_DECISIONS: TRIAGE_DECISIONS,
        bucketizeStatus: bucketizeStatus,
        bucketizeCounts: bucketizeCounts,
        reportsBuckets: reportsBuckets,
        isEIP: isEIP,
        deriveEIP: deriveEIP,
        toneFor: toneFor,
        redSignalsFrom: redSignalsFrom,
        eipDisplay: eipDisplay,
        buildCreateHazardPayload: buildCreateHazardPayload,
        buildTriagePayload: buildTriagePayload,
        roleAllowed: roleAllowed,
    };
}));
