/* ============================================================================
   FILE: psoe.js
   PATH: public/js/psoe.js
   VERSION: 1.0.0
   PURPOSE: PSOE Audit & Surveillance interactive scoring engine (Phase 3
            Step 2B). Loads the CAAN SMS Procedure Manual Appendix 10 template
            from GET /api/v1/psoe/template, renders the four-component
            checklist, and recomputes component + weighted overall scores live
            in the browser. Scoring logic mirrors backend/app/services/
            psoe_service.py: N/A answers are excluded from the denominator and
            the overall percentage is the weight combination of component
            percentages.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

(function (global) {
    'use strict';

    if (global.PSOE) {
        return;
    }

    // CAAN / ICAO implementation scale (Appendix 10).
    var SCORE_OPTIONS = [
        { value: '0', label: 'Not Implemented', short: '0' },
        { value: '1', label: 'Documented Only', short: '1' },
        { value: '2', label: 'Operating', short: '2' },
        { value: '3', label: 'Fully Effective', short: '3' },
        { value: 'NA', label: 'N/A', short: 'N/A' }
    ];

    // ---- Pure scoring engine (mirrors psoe_service.py) ---------------------

    function round2(value) {
        return Math.round((Number(value) + Number.EPSILON) * 100) / 100;
    }

    function overallLevel(scorePct) {
        if (scorePct >= 90) return 'Fully Effective & Continuous Improvement';
        if (scorePct >= 70) return 'Implemented & Operational';
        if (scorePct >= 40) return 'Partially Implemented (Documented only)';
        return 'Not Implemented / Non-Compliant';
    }

    // CAAN maturity stage badge mapping (Level 0-3).
    function maturityLevel(scorePct) {
        if (scorePct >= 90) return { level: 3, label: 'Effective', tag: 'Level 3 · Effective', color: '#1a7f37' };
        if (scorePct >= 70) return { level: 2, label: 'Suitable / Operating', tag: 'Level 2 · Suitable / Operating', color: '#1a6b8a' };
        if (scorePct >= 40) return { level: 1, label: 'Present', tag: 'Level 1 · Present', color: '#d97706' };
        return { level: 0, label: 'Non-Compliant', tag: 'Level 0 · Non-Compliant', color: '#dc3545' };
    }

    // scoreResponses(responses, template) -> { component_scores, overall_score_pct, overall_level }
    //   responses: [{ question_id, score (0-3|null), is_na, comment, evidence }]
    //   template:  { components: [{ id, name, key, weight, questions: [{id, max_score, ...}] }] }
    function scoreResponses(responses, template) {
        var components = (template && template.components) || [];
        var list = responses || [];
        var componentScores = {};
        var weightedSum = 0;
        var totalWeight = 0;

        components.forEach(function (comp) {
            var qById = {};
            (comp.questions || []).forEach(function (q) { qById[q.id] = q; });
            var qIds = Object.keys(qById);

            var applicable = list.filter(function (a) {
                return qIds.indexOf(a.question_id) !== -1 && !a.is_na &&
                    a.score !== null && a.score !== undefined;
            });
            var naCount = list.filter(function (a) {
                return qIds.indexOf(a.question_id) !== -1 && (a.is_na || a.score === null || a.score === undefined);
            }).length;

            var total = 0;
            var maxTotal = 0;
            applicable.forEach(function (a) {
                total += a.score;
                maxTotal += (qById[a.question_id] && qById[a.question_id].max_score) || 3;
            });
            maxTotal = Math.min(maxTotal, 3 * applicable.length);

            var pct = (applicable.length && maxTotal) ? round2(total / maxTotal * 100) : 0;
            var weightedPct = round2(pct * comp.weight / 100);

            componentScores[comp.id] = {
                component: comp.id,
                name: comp.name,
                weight: comp.weight,
                applicable_questions: applicable.length,
                na_questions: naCount,
                score: total,
                max_score: maxTotal,
                score_pct: pct,
                weighted_pct: weightedPct
            };
            weightedSum += weightedPct;
            totalWeight += comp.weight;
        });

        var overall = round2(weightedSum / (totalWeight || 100) * 100);
        return {
            component_scores: componentScores,
            overall_score_pct: overall,
            overall_level: overallLevel(overall)
        };
    }

    // ---- State --------------------------------------------------------------

    var state = {
        template: null,
        assessmentId: null,
        status: 'draft',
        responses: {},          // question_id -> { score, is_na, comment, evidence }
        user: null,
        isAdmin: false,
        tenantId: null,
        targetTenantId: null
    };

    // ---- DOM helpers --------------------------------------------------------

    function $(id) {
        return document.getElementById(id);
    }

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function showMessage(text, type) {
        var msg = $('psoeMessage');
        if (!msg) return;
        msg.textContent = text;
        msg.className = 'psoe-message ' + (type === 'error' ? 'error' : 'success');
        msg.style.display = 'block';
        if (type === 'error') {
            clearTimeout(showMessage._t);
            showMessage._t = setTimeout(function () { msg.style.display = 'none'; }, 7000);
        } else {
            clearTimeout(showMessage._t);
            showMessage._t = setTimeout(function () { msg.style.display = 'none'; }, 5000);
        }
    }

    function setBusy(button, busy, busyHtml, idleHtml) {
        if (!button) return;
        if (busy) {
            button.disabled = true;
            button.innerHTML = busyHtml;
        } else {
            button.disabled = false;
            button.innerHTML = idleHtml;
        }
    }

    function statusLabel(raw) {
        var s = String(raw || 'draft').toLowerCase();
        return (s === 'completed' || s === 'submitted' || s === 'closed') ? 'COMPLETED' : 'DRAFT';
    }

    // ---- Rendering ----------------------------------------------------------

    function renderHeader() {
        var tenantTitle = state.tenantId ? (state.tenantId.charAt(0).toUpperCase() + state.tenantId.slice(1)) : '—';
        if (state.user && state.user.tenantId && typeof TenantResolver !== 'undefined' &&
            TenantResolver.resolveTenantTitle) {
            TenantResolver.resolveTenantTitle(state.user.tenantId).then(function (name) {
                if (name) {
                    var el = $('auditTenantName');
                    if (el) el.textContent = name;
                }
            });
        }
        $('auditTenantName').textContent = tenantTitle;
        $('auditTitle').value = state.assessmentTitle || 'Annual SMS Surveillance Audit';
        $('auditAuditor').value = state.auditorName || ((state.user && state.user.email) || '');
        $('auditAuditorRole').textContent = (state.user && state.user.role) || '—';
        $('auditDate').value = state.assessmentDate || new Date().toISOString().slice(0, 10);

        var badge = $('auditStatusBadge');
        var completed = statusLabel(state.status) === 'COMPLETED';
        badge.textContent = completed ? 'COMPLETED' : 'DRAFT';
        badge.className = 'status-badge ' + (completed ? 'badge-completed' : 'badge-draft');

        // Cross-tenant (CAAN_SMD / SUPER_ADMIN) target-operator selector.
        var targetWrap = $('targetTenantWrap');
        if (targetWrap) {
            targetWrap.style.display = state.isAdmin && !state.user.tenantId ? 'block' : 'none';
        }
        var targetInput = $('targetTenantId');
        if (targetInput && state.targetTenantId) {
            targetInput.value = state.targetTenantId;
        }
    }

    function renderDashboard(scores) {
        var overall = scores.overall_score_pct;
        var level = maturityLevel(overall);

        var overallEl = $('overallScore');
        if (overallEl) {
            overallEl.textContent = (overall == null || isNaN(overall)) ? '—' : overall + '%';
            overallEl.style.color = level.color;
        }
        var band = $('overallBand');
        if (band) band.style.background = level.color;

        var badge = $('maturityBadge');
        if (badge) {
            badge.textContent = level.tag;
            badge.style.background = level.color;
        }
        var levelLabel = $('maturityLevelLabel');
        if (levelLabel) {
            levelLabel.textContent = overallLevel(overall);
            levelLabel.style.color = level.color;
        }

        var detail = $('overallDetail');
        if (detail) {
            var applicable = 0;
            var na = 0;
            scores.component_scores && Object.keys(scores.component_scores).forEach(function (k) {
                applicable += scores.component_scores[k].applicable_questions;
                na += scores.component_scores[k].na_questions;
            });
            detail.textContent = applicable + ' applicable questions scored · ' + na + ' marked N/A (excluded)';
        }

        var bars = $('componentBars');
        if (bars) {
            var html = '';
            Object.keys(scores.component_scores).forEach(function (k) {
                var c = scores.component_scores[k];
                var color = maturityLevel(c.score_pct).color;
                html +=
                    '<div class="comp-bar">' +
                    '  <div class="comp-bar-head">' +
                    '    <span class="comp-bar-name">' + esc(c.name) + '</span>' +
                    '    <span class="comp-bar-weight">Weight ' + c.weight + '%</span>' +
                    '    <span class="comp-bar-pct" style="color:' + color + ';">' + c.score_pct + '%</span>' +
                    '  </div>' +
                    '  <div class="comp-bar-track"><div class="comp-bar-fill" style="width:' + c.score_pct + '%;background:' + color + ';"></div></div>' +
                    '  <div class="comp-bar-sub">Score ' + c.score + '/' + c.max_score +
                    ' · ' + c.applicable_questions + ' applicable · ' + c.na_questions + ' N/A</div>' +
                    '</div>';
            });
            bars.innerHTML = html;
        }
    }

    function questionCard(compIndex, qIndex, q) {
        var key = q.id;
        var saved = state.responses[key] || {};
        var checked = saved.is_na ? 'NA' : (saved.score !== null && saved.score !== undefined ? String(saved.score) : '');
        var isGap = !saved.is_na && (saved.score === 0 || saved.score === 1);

        var pills = SCORE_OPTIONS.map(function (opt) {
            return '<label class="score-pill' + (opt.value === 'NA' ? ' pill-na' : '') + '">' +
                '<input type="radio" name="score-' + esc(key) + '" value="' + opt.value + '"' +
                (checked === opt.value ? ' checked' : '') + '>' +
                '<span>' + opt.short + '</span><em>' + esc(opt.label) + '</em>' +
                '</label>';
        }).join('');

        return '' +
            '<div class="q-card' + (isGap ? ' q-card-gap' : '') + '" data-qid="' + esc(key) + '">' +
            '  <div class="q-head">' +
            '    <span class="q-ref">' + esc(q.id) + '</span>' +
            '    <div class="q-text">' + esc(q.text) + '</div>' +
            '  </div>' +
            (q.guidance ? '  <div class="q-guidance"><i class="fas fa-book-open"></i> ' + esc(q.guidance) + '</div>' : '') +
            '  <div class="q-score">' +
            '    <span class="q-score-label">Score</span>' +
            '    <div class="score-pills">' + pills + '</div>' +
            '  </div>' +
            '  <div class="q-notes">' +
            '    <textarea class="q-note" id="comment-' + esc(key) + '" rows="2" placeholder="Observations / finding notes">' + esc(saved.comment || '') + '</textarea>' +
            '    <textarea class="q-note" id="evidence-' + esc(key) + '" rows="2" placeholder="Evidence references">' + esc(saved.evidence || '') + '</textarea>' +
            '  </div>' +
            '  <div class="q-gap-actions"' + (isGap ? '' : ' hidden') + '>' +
            '    <span class="gap-tag"><i class="fas fa-triangle-exclamation"></i> Gap / Finding (score 0-1)</span>' +
            '    <button type="button" class="btn-promote" data-promote="' + esc(key) + '"><i class="fas fa-clipboard-check"></i> Promote to CAN / CAP</button>' +
            '  </div>' +
            '</div>';
    }

    function renderChecklist() {
        var container = $('psoeChecklist');
        if (!container || !state.template) return;

        var components = state.template.components || [];
        var html = '';
        components.forEach(function (comp, ci) {
            var questions = comp.questions || [];
            var answered = questions.filter(function (q) {
                var s = state.responses[q.id];
                return s && (s.is_na || (s.score !== null && s.score !== undefined));
            }).length;

            html +=
                '<details class="comp-acc" ' + (ci === 0 ? 'open' : '') + ' data-comp="' + esc(comp.id) + '">' +
                '  <summary>' +
                '    <span class="acc-title">' + esc(comp.name) + '</span>' +
                '    <span class="acc-meta">Weight ' + comp.weight + '% · ' + answered + '/' + questions.length + ' answered</span>' +
                '  </summary>' +
                '  <div class="acc-body">' + questions.map(function (q, qi) { return questionCard(ci, qi, q); }).join('') + '</div>' +
                '</details>';
        });
        container.innerHTML = html;

        // Collapse/expand all
        var collapseBtn = $('collapseAllBtn');
        var expandBtn = $('expandAllBtn');
        if (collapseBtn) collapseBtn.disabled = components.length === 0;
        if (expandBtn) expandBtn.disabled = components.length === 0;
    }

    // ---- Response reading ---------------------------------------------------

    function readResponses() {
        var out = {};
        if (!state.template) return out;
        state.template.components.forEach(function (comp) {
            (comp.questions || []).forEach(function (q) {
                var radio = document.querySelector('input[name="score-' + q.id + '"]:checked');
                var value = radio ? radio.value : '';
                var rec = {
                    score: null,
                    is_na: false,
                    comment: '',
                    evidence: ''
                };
                if (value === 'NA') {
                    rec.is_na = true;
                } else if (value !== '') {
                    rec.score = parseInt(value, 10);
                }
                var commentEl = $('comment-' + q.id);
                var evidenceEl = $('evidence-' + q.id);
                if (commentEl) rec.comment = commentEl.value;
                if (evidenceEl) rec.evidence = evidenceEl.value;
                out[q.id] = rec;
            });
        });
        state.responses = out;
        return out;
    }

    function responsesArray() {
        var arr = [];
        Object.keys(state.responses).forEach(function (qid) {
            var r = state.responses[qid];
            arr.push({
                question_id: qid,
                score: r.is_na ? null : r.score,
                is_na: !!r.is_na,
                comment: r.comment || null,
                evidence: r.evidence || null
            });
        });
        return arr;
    }

    function recompute() {
        if (!state.template) return null;
        var scores = scoreResponses(responsesArray(), state.template);
        renderDashboard(scores);
        updateGapHighlights();
        return scores;
    }

    function updateGapHighlights() {
        var cards = document.querySelectorAll('.q-card');
        for (var i = 0; i < cards.length; i++) {
            var card = cards[i];
            var qid = card.getAttribute('data-qid');
            var rec = state.responses[qid];
            var isGap = rec && !rec.is_na && (rec.score === 0 || rec.score === 1);
            card.classList.toggle('q-card-gap', isGap);
            var actions = card.querySelector('.q-gap-actions');
            if (actions) actions.hidden = !isGap;
        }
    }

    // ---- Persistence --------------------------------------------------------

    function buildPayload(status) {
        var title = $('auditTitle').value.trim();
        var auditor = $('auditAuditor').value.trim();
        var date = $('auditDate').value;
        var payload = {
            title: title || 'Annual SMS Surveillance Audit',
            responses: responsesArray(),
            auditor_name: auditor || null,
            assessor_email: (state.user && state.user.email) || null,
            assessment_date: date ? new Date(date + 'T00:00:00').toISOString() : null,
            status: status,
            department: $('auditDepartment') ? $('auditDepartment').value.trim() || null : null,
            scope: $('auditScope') ? $('auditScope').value.trim() || null : null,
            notes: $('auditNotes') ? $('auditNotes').value.trim() || null : null
        };
        if (status === 'completed') {
            payload.overall_score_pct = scoreResponses(responsesArray(), state.template).overall_score_pct;
        }
        // Cross-tenant roles must target an operator explicitly.
        if (state.isAdmin && !state.user.tenantId) {
            var target = $('targetTenantId') ? $('targetTenantId').value.trim() : '';
            if (!target) {
                showMessage('A target operator (tenant_id) is required for CAAN assessments.', 'error');
                return null;
            }
            payload.tenant_id = target;
        }
        return payload;
    }

    async function saveDraft() {
        readResponses();
        var payload = buildPayload('draft');
        if (!payload) return;
        var btn = $('saveDraftBtn');
        setBusy(btn, true, '<i class="fas fa-spinner fa-spin"></i> Saving…', '');
        try {
            var result;
            if (state.assessmentId) {
                result = await ApiClient.patch('/api/v1/psoe/assessments/' + encodeURIComponent(state.assessmentId), payload);
            } else {
                result = await ApiClient.post('/api/v1/psoe/assessments', payload);
            }
            state.assessmentId = result.id;
            state.status = result.status || 'draft';
            $('auditStatusBadge').textContent = 'DRAFT';
            $('auditStatusBadge').className = 'status-badge badge-draft';
            showMessage('Draft saved successfully.', 'success');
        } catch (err) {
            showMessage('Failed to save draft: ' + err.message, 'error');
        } finally {
            setBusy(btn, false, '<i class="fas fa-save"></i> Save Draft', '<i class="fas fa-save"></i> Save Draft');
        }
    }

    async function completeAssessment() {
        readResponses();
        if (!state.assessmentId) {
            // Persist first, then lock.
            var draft = buildPayload('draft');
            if (!draft) return;
            var btn = $('completeBtn');
            setBusy(btn, true, '<i class="fas fa-spinner fa-spin"></i> Saving…', '');
            try {
                var created = await ApiClient.post('/api/v1/psoe/assessments', draft);
                state.assessmentId = created.id;
            } catch (err) {
                setBusy(btn, false, '<i class="fas fa-lock"></i> Complete & Lock', '<i class="fas fa-lock"></i> Complete & Lock');
                showMessage('Failed to create assessment: ' + err.message, 'error');
                return;
            }
        }
        var payload = buildPayload('completed');
        if (!payload) return;
        var btn2 = $('completeBtn');
        setBusy(btn2, true, '<i class="fas fa-spinner fa-spin"></i> Completing…', '');
        try {
            await ApiClient.patch('/api/v1/psoe/assessments/' + encodeURIComponent(state.assessmentId), payload);
            state.status = 'completed';
            lockAssessment();
            showMessage('Assessment completed and locked.', 'success');
        } catch (err) {
            showMessage('Failed to complete assessment: ' + err.message, 'error');
        } finally {
            setBusy(btn2, false, '<i class="fas fa-lock"></i> Complete & Lock', '<i class="fas fa-lock"></i> Complete & Lock');
        }
    }

    async function reopenAssessment() {
        if (!state.assessmentId) return;
        var btn = $('reopenBtn');
        setBusy(btn, true, '<i class="fas fa-spinner fa-spin"></i> Reopening…', '');
        try {
            await ApiClient.patch('/api/v1/psoe/assessments/' + encodeURIComponent(state.assessmentId), { status: 'draft' });
            state.status = 'draft';
            unlockAssessment();
            showMessage('Assessment reopened for editing.', 'success');
        } catch (err) {
            showMessage('Failed to reopen assessment: ' + err.message, 'error');
        } finally {
            setBusy(btn, false, '<i class="fas fa-rotate-left"></i> Reopen', '<i class="fas fa-rotate-left"></i> Reopen');
        }
    }

    function lockAssessment() {
        $('auditStatusBadge').textContent = 'COMPLETED';
        $('auditStatusBadge').className = 'status-badge badge-completed';
        document.querySelectorAll('.q-card input, .q-card textarea, #auditTitle, #auditAuditor, #auditDate, #auditDepartment, #auditScope, #auditNotes').forEach(function (el) {
            el.disabled = true;
        });
        $('saveDraftBtn').style.display = 'none';
        $('completeBtn').style.display = 'none';
        $('reopenBtn').style.display = 'inline-flex';
    }

    function unlockAssessment() {
        $('auditStatusBadge').textContent = 'DRAFT';
        $('auditStatusBadge').className = 'status-badge badge-draft';
        document.querySelectorAll('.q-card input, .q-card textarea, #auditTitle, #auditAuditor, #auditDate, #auditDepartment, #auditScope, #auditNotes').forEach(function (el) {
            el.disabled = false;
        });
        $('saveDraftBtn').style.display = 'inline-flex';
        $('completeBtn').style.display = 'inline-flex';
        $('reopenBtn').style.display = 'none';
    }

    async function exportReport() {
        if (!state.assessmentId) {
            showMessage('No assessment to export; save or complete first.', 'error');
            return;
        }
        var btn = $('printBtn');
        if (!btn) return;
        setBusy(btn, true, '<i class="fas fa-spinner fa-spin"></i> Generating…', '<i class="fas fa-print"></i> Export / Print');
        try {
            var result = await ApiClient.get('/api/v1/psoe/assessments/' + encodeURIComponent(state.assessmentId) + '/export', {
                headers: { Accept: 'application/pdf' }
            });
            if (result && typeof result.then === 'function') {
                // If promise, wait for it
                result = await result;
            }
            // blob response from FastAPI
            if (result && result.body) {
                var blob = new Blob([result.body], { type: 'application/pdf' });
                var url = URL.createObjectURL(blob);
                var a = document.createElement('a');
                a.href = url;
                a.download = 'psoe_audit_report_' + state.assessmentId + '.pdf';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            } else if (result && result.text) {
                // HTML preview
                var win = window.open('', '_blank');
                win.document.write(result.text);
                win.document.close();
            } else {
                showMessage('Export generated but no content returned.', 'error');
            }
        } catch (err) {
            showMessage('Failed to export report: ' + err.message, 'error');
        } finally {
            setBusy(btn, false, '<i class="fas fa-print"></i> Export / Print', '<i class="fas fa-print"></i> Export / Print');
        }
    }

    function promoteToCan(qid) {
        if (!state.template) return;
        var q = null;
        state.template.components.forEach(function (comp) {
            (comp.questions || []).forEach(function (item) {
                if (item.id === qid) q = item;
            });
        });
        if (!q) return;
        var rec = state.responses[qid] || {};
        var scoreLabel = rec.is_na ? 'N/A' : ('Score ' + rec.score);
        var params = new URLSearchParams();
        params.set('source', 'psoe');
        if (state.assessmentId) params.set('psoe_assessment', state.assessmentId);
        if (state.assessmentId) params.set('psoe_assessment_id', state.assessmentId);
        params.set('title', 'PSOE finding — ' + q.id + ': ' + q.text.slice(0, 80) + (q.text.length > 80 ? '…' : ''));
        var desc = 'Appendix 10 surveillance finding ' + q.id + ' (' + scoreLabel + ').';
        if (rec.comment) desc += '\n\nObservations: ' + rec.comment;
        if (rec.evidence) desc += '\n\nEvidence: ' + rec.evidence;
        params.set('description', desc);
        params.set('required_action', 'Address ' + q.id + ' (' + scoreLabel + ') recorded in PSOE assessment' +
            (state.assessmentId ? ' ' + state.assessmentId : '') + '.');
        window.location.href = '/can_cap/issue.html?' + params.toString();
    }

    // ---- Events -------------------------------------------------------------

    function bindEvents() {
        var checklist = $('psoeChecklist');
        if (checklist) {
            checklist.addEventListener('change', function (e) {
                if (e.target && e.target.matches('input[type="radio"], textarea')) {
                    readResponses();
                    recompute();
                }
            });
            checklist.addEventListener('input', function (e) {
                if (e.target && e.target.matches('textarea')) {
                    readResponses();
                    recompute();
                }
            });
            checklist.addEventListener('click', function (e) {
                var promote = e.target.closest ? e.target.closest('[data-promote]') : null;
                if (promote) {
                    promoteToCan(promote.getAttribute('data-promote'));
                }
            });
        }
        var saveBtn = $('saveDraftBtn');
        if (saveBtn) saveBtn.addEventListener('click', saveDraft);
        var completeBtn = $('completeBtn');
        if (completeBtn) completeBtn.addEventListener('click', completeAssessment);
        var reopenBtn = $('reopenBtn');
        if (reopenBtn) reopenBtn.addEventListener('click', reopenAssessment);
        var printBtn = $('printBtn');
        if (printBtn) printBtn.addEventListener('click', exportReport);
        var collapseBtn = $('collapseAllBtn');
        if (collapseBtn) collapseBtn.addEventListener('click', function () {
            document.querySelectorAll('.comp-acc').forEach(function (d) { d.removeAttribute('open'); });
        });
        var expandBtn = $('expandAllBtn');
        if (expandBtn) expandBtn.addEventListener('click', function () {
            document.querySelectorAll('.comp-acc').forEach(function (d) { d.setAttribute('open', ''); });
        });
    }

    // ---- Load ---------------------------------------------------------------

    function mergeAssessment(data) {
        state.assessmentId = data.id || null;
        state.status = data.status || 'draft';
        state.assessmentTitle = data.title || '';
        state.auditorName = data.auditor_name || '';
        state.assessmentDate = data.assessment_date ? String(data.assessment_date).slice(0, 10) : '';
        (data.responses || []).forEach(function (a) {
            state.responses[a.question_id] = {
                score: a.is_na ? null : a.score,
                is_na: !!a.is_na,
                comment: a.comment || '',
                evidence: a.evidence || ''
            };
        });
    }

    async function init() {
        try {
            await waitForFirebase();
        } catch (e) { /* firebase helper always resolves */ }
        state.user = await getCurrentUser();
        if (!state.user) {
            window.location.href = '/login.html';
            return;
        }

        var role = String(state.user.role || '').toLowerCase();
        var email = String(state.user.email || '').toLowerCase();
        state.isAdmin = ['airline_admin', 'tenant_admin', 'caan_smd', 'super_admin', 'safety'].indexOf(role) !== -1 ||
            email.indexOf('safety') === 0;

        if (!state.isAdmin) {
            var page = $('pageContent');
            if (page) {
                page.style.display = 'block';
                page.innerHTML =
                    '<div style="text-align:center;padding:3rem;">' +
                    '  <i class="fas fa-lock" style="font-size:2.5rem;color:#dc3545;"></i>' +
                    '  <h2 style="color:#dc3545;margin-top:1rem;">Access Denied</h2>' +
                    '  <p style="color:#64748b;">PSOE surveillance audits are available to Safety Managers and CAAN SMD only.</p>' +
                    '  <a href="/safety.html" class="btn btn-outline btn-sm" style="margin-top:1rem;"><i class="fas fa-arrow-left"></i> Back to Dashboard</a>' +
                    '</div>';
            }
            return;
        }

        try {
            state.tenantId = (typeof TenantResolver !== 'undefined' && TenantResolver.getCurrentTenant) ?
                TenantResolver.getCurrentTenant() : (state.user.tenantId || null);
        } catch (e) {
            state.tenantId = state.user.tenantId || null;
        }

        // Target operator for CAAN / cross-tenant roles.
        var params = new URLSearchParams(window.location.search);
        if (params.get('tenant_id')) state.targetTenantId = params.get('tenant_id');

        var page = $('pageContent');
        if (page) page.style.display = 'block';
        if (typeof window.updateShellTenant === 'function') {
            window.updateShellTenant(state.isAdmin && !state.user.tenantId ? 'State Oversight — PSOE' : (state.tenantId ? state.tenantId.toUpperCase() : 'Safety'), 'PSOE Audit & Surveillance');
        }

        var template = await ApiClient.get('/api/v1/psoe/template');
        state.template = template;

        var id = params.get('id');
        if (id) {
            var data = await ApiClient.get('/api/v1/psoe/assessments/' + encodeURIComponent(id));
            mergeAssessment(data);
        }

        renderHeader();
        renderChecklist();
        bindEvents();
        readResponses();
        recompute();

        if (statusLabel(state.status) === 'COMPLETED') {
            lockAssessment();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    global.PSOE = {
        init: init,
        scoreResponses: scoreResponses,
        overallLevel: overallLevel,
        maturityLevel: maturityLevel
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { scoreResponses: scoreResponses, overallLevel: overallLevel, maturityLevel: maturityLevel };
    }
})(typeof window !== 'undefined' ? window : globalThis);