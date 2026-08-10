/**
 * Airline SMS Dashboard render helpers.
 *
 * Pure-ish DOM rendering for the four SMS maturity sections of the Airline SMS
 * Dashboard. Kept dependency-free so the same logic is unit-testable in Node
 * (via a minimal document shim) and runs in the browser. The data contract
 * mirrors the backend `_sms_maturity_model` payload served by
 * GET /api/v1/dashboard/airline/sms-maturity.
 */
(function (root, factory) {
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = factory();
    } else {
        root.DashboardRender = factory();
    }
}(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    var PILLAR_META = [
        { key: 'safety_policy', label: 'Safety Policy', desc: 'Policy, objectives, commitment and SMS documentation' },
        { key: 'safety_risk_management', label: 'Safety Risk Management', desc: 'Hazard identification and safety risk assessment & mitigation' },
        { key: 'safety_assurance', label: 'Safety Assurance', desc: 'Performance monitoring, audit and continuous improvement' },
        { key: 'safety_promotion', label: 'Safety Promotion', desc: 'Training, communication and positive safety culture' },
    ];

    function tierBadge(tier, label) {
        if (!tier) return '<span class="badge b-tolerable">—</span>';
        var cls = tier === 'strong' ? 'b-acceptable'
            : tier === 'watch' ? 'b-tolerable'
            : tier === 'action' ? 'b-action'
            : 'b-intolerable';
        return '<span class="badge ' + cls + '">' + (label || tier) + '</span>';
    }

    function tierClass(tier) {
        return tier === 'strong' ? 'b-acceptable'
            : tier === 'watch' ? 'b-tolerable'
            : tier === 'action' ? 'b-action'
            : 'b-intolerable';
    }

    function fmtPct(v) {
        return v != null ? v + '%' : '—';
    }

    function getEl(id, doc) {
        var d = doc || (typeof document !== 'undefined' ? document : null);
        return d ? d.getElementById(id) : null;
    }

    // ------------------------------------------------------------------ 1: Overview
    function renderOverview(data, statsEl, bannerEl) {
        var tier = data.tier;
        var tierLabel = data.tier_label || (tier ? tier.charAt(0).toUpperCase() + tier.slice(1) : null);

        statsEl.innerHTML =
            '<div class="stat-card gold"><div class="num">' + fmtPct(data.overall_score) + '</div><div class="lbl">Overall SMS Maturity</div></div>' +
            '<div class="stat-card"><div class="num">' + tierBadge(tier, tierLabel) + '</div><div class="lbl">Tier</div></div>' +
            '<div class="stat-card green"><div class="num">' + (data.latest_assessment_date || '—') + '</div><div class="lbl">Latest Assessment</div></div>' +
            '<div class="stat-card"><div class="num">' + (data.response_count != null ? data.response_count : '—') + '</div><div class="lbl">Survey Responses</div></div>';

        if (!bannerEl) return;
        var lowCount = (data.assessment && data.assessment.improvement_opportunities || []).length;
        var banner;
        if (data.overall_score == null) {
            banner = '<div class="loading" style="padding:1rem;">No survey responses in the selected period. Run the safety survey to generate an SMS maturity score.</div>';
        } else if (lowCount > 0) {
            banner = '<div style="background:#fde8d0;border:1px solid #f5b380;border-radius:8px;padding:10px 14px;font-size:13px;color:#8a4b00;line-height:1.5;">' +
                '<strong>Action needed:</strong> ' + lowCount + ' pillar(s) score below 70% — see the SMS Maturity Assessment below for improvement actions.</div>';
        } else {
            banner = '<div style="background:#e6f4ea;border:1px solid #9ed6ad;border-radius:8px;padding:10px 14px;font-size:13px;color:#1e7e34;line-height:1.5;">' +
                '<strong>Good standing:</strong> all pillars scored at or above 70% in the selected period.</div>';
        }
        bannerEl.innerHTML = banner;
        bannerEl.style.display = data.overall_score != null || data.response_count != null ? 'block' : 'none';
    }

    // ------------------------------------------------------------------ 2: Components
    function renderComponents(data, doc) {
        var grid = getEl('componentsGrid', doc);
        if (!grid) return;
        var pillars = data.pillars || {};
        grid.innerHTML = PILLAR_META.map(function (meta) {
            var pct = pillars[meta.key];
            var sub = pct != null
                ? tierBadge(pct >= 85 ? 'strong' : pct >= 70 ? 'watch' : pct >= 50 ? 'action' : 'critical', null)
                : '<span class="badge b-tolerable">No data</span>';
            return '<div class="stat-card"><div class="num">' + fmtPct(pct) + '</div><div class="lbl">' + meta.label + '</div>' +
                '<div style="margin-top:0.5rem;">' + sub + '</div>' +
                '<div style="color:#64748b;font-size:12px;margin-top:0.4rem;">' + meta.desc + '</div></div>';
        }).join('');
    }

    // ------------------------------------------------------------------ 3: Assessment
    function renderAssessment(data, doc) {
        var el = getEl('assessmentContent', doc);
        if (!el) return;
        var assessment = data.assessment || {};
        var strengths = assessment.strengths || [];
        var opportunities = assessment.improvement_opportunities || [];
        var recs = assessment.priority_actions || [];

        if (data.overall_score == null && !recs.length) {
            el.innerHTML = '<p class="empty">No survey data in the selected period — no assessment available.</p>';
            return;
        }

        var html = '';

        if (strengths.length) {
            html += '<div style="margin-bottom:1rem;">' +
                '<h4 style="color:#1e7e34;margin:0 0 8px;"><i class="fas fa-thumbs-up"></i> Strengths</h4>' +
                '<ul style="margin:0;padding-left:18px;font-size:13px;color:#0b2a42;">' + strengths.map(function (s) { return '<li>' + s + '</li>'; }).join('') + '</ul></div>';
        }

        if (opportunities.length) {
            html += '<div style="margin-bottom:1rem;">' +
                '<h4 style="color:#c25400;margin:0 0 8px;"><i class="fas fa-bullseye"></i> Improvement Opportunities</h4>' +
                '<ul style="margin:0;padding-left:18px;font-size:13px;color:#0b2a42;">' + opportunities.map(function (o) { return '<li>' + o + '</li>'; }).join('') + '</ul></div>';
        }

        if (!recs.length) {
            html += '<div class="success-banner" style="background:#e6f4ea;color:#1e7e34;padding:12px 16px;border-radius:8px;font-weight:600;">All pillars scored ≥70% in the selected period — no improvement actions required.</div>';
        } else {
            html += '<h4 style="color:#0b2a42;margin:0 0 8px;"><i class="fas fa-wand-magic-sparkles"></i> Priority Improvement Actions</h4>';
            html += '<div class="section-sub" style="margin-bottom:12px;">ICAO-aligned actions targeting pillars scoring below 70% (Gemini).</div>';
            html += recs.map(function (r) {
                var tierBadgeHtml = r.tier === 'critical'
                    ? '<span class="badge b-intolerable">CRITICAL</span>'
                    : '<span class="badge b-tolerable">ACTION</span>';
                var actions = (r.actions || []).map(function (a) {
                    return '<li style="margin-bottom:8px;">' +
                        '<strong>' + a.action + '</strong>' +
                        '<div style="color:#475569;font-size:12px;margin-top:2px;">' +
                        '<span class="badge ' + (a.priority === 'high' ? 'b-intolerable' : a.priority === 'medium' ? 'b-tolerable' : 'b-acceptable') + '" style="text-transform:uppercase;">' + (a.priority || '—') + '</span> ' +
                        (a.icao_reference || '') + ' · Owner: ' + (a.owner || '—') + ' · ' + (a.timeframe || '') +
                        '</div>' +
                        '<div style="color:#64748b;font-size:12px;margin-top:2px;">Success metric: ' + (a.success_metric || '—') + '</div>' +
                        '</li>';
                }).join('');
                return '<div style="border:1px solid #e2e8f0;border-left:4px solid ' + (r.tier === 'critical' ? '#dc3545' : '#f57c00') + ';border-radius:8px;padding:14px 16px;margin-bottom:12px;background:#fff;">' +
                    '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">' +
                    '<strong style="font-size:15px;color:#0b2a42;">' + r.pillar_name + ' — ' + r.score_pct + '%</strong>' +
                    tierBadgeHtml +
                    '</div>' +
                    '<p style="margin:8px 0;color:#475569;font-size:13px;">' + (r.summary || '') + '</p>' +
                    (r.root_causes && r.root_causes.length ? '<div style="font-size:12px;color:#64748b;margin-bottom:8px;"><strong>Root causes:</strong> ' + r.root_causes.join('; ') + '</div>' : '') +
                    '<ul style="margin:0;padding-left:18px;list-style:disc;font-size:13px;">' + actions + '</ul>' +
                    (r.kpi_target ? '<div style="margin-top:8px;font-size:12px;color:#1a6b8a;"><strong>Target:</strong> raise to ≥' + r.kpi_target + '%</div>' : '') +
                    '</div>';
            }).join('');
        }

        el.innerHTML = html;
    }

    // ------------------------------------------------------------------ 4: History
    function renderHistory(data, doc) {
        var body = getEl('historyBody', doc);
        if (!body) return;
        var history = data.history || [];
        if (!history.length) {
            body.innerHTML = '<tr><td colspan="9" class="empty">No monthly history available.</td></tr>';
            return;
        }
        body.innerHTML = history.map(function (h) {
            var p = h.pillars || {};
            return '<tr>' +
                '<td><strong>' + h.period + '</strong></td>' +
                '<td>' + (h.assessment_date || '—') + '</td>' +
                '<td><span class="badge ' + tierClass(h.tier) + '">' + fmtPct(h.overall_score) + '</span></td>' +
                '<td>' + tierBadge(h.tier, h.tier_label) + '</td>' +
                '<td>' + fmtPct(p.safety_policy) + '</td>' +
                '<td>' + fmtPct(p.safety_risk_management) + '</td>' +
                '<td>' + fmtPct(p.safety_assurance) + '</td>' +
                '<td>' + fmtPct(p.safety_promotion) + '</td>' +
                '<td>' + h.response_count + '</td>' +
                '</tr>';
        }).join('');
    }

    function renderAll(data, doc) {
        data = data || {};
        renderOverview(data, getEl('overviewStats', doc), getEl('maturityBanner', doc));
        renderComponents(data, doc);
        renderAssessment(data, doc);
        renderHistory(data, doc);
    }

    return {
        PILLAR_META: PILLAR_META,
        tierBadge: tierBadge,
        tierClass: tierClass,
        renderOverview: renderOverview,
        renderComponents: renderComponents,
        renderAssessment: renderAssessment,
        renderHistory: renderHistory,
        renderAll: renderAll,
    };
}));
