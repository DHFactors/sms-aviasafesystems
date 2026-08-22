// ============================================================================
// FILE: fishbone.js
// PURPOSE: Reusable 6-category Fishbone (Ishikawa / aviation human factors 6M)
//          Root Cause Analysis editor and viewer for the CAN/CAP workflow.
// CATEGORIES: Man, Machine, Medium (Environment), Mission, Management,
//             Measurement — mirrors backend/seed/config.py FISHBONE_CATEGORIES.
// FEATURES:
//   - dynamic add/remove of cause items per category
//   - radio selection of exactly ONE 'Primary Root Cause'
//   - structured CAP action items linked 1:1 to root cause IDs
// DATA MODEL (stored on the CAP record):
//   {
//     root_causes:  [{ id, category, description, is_primary }],
//     action_items: [{ id, description, root_cause_id, owner, target_date }]
//   }
// ============================================================================

const Fishbone = (() => {
    const CATEGORIES = ['Man', 'Machine', 'Medium', 'Mission', 'Management', 'Measurement'];
    const DEFAULT_ACTION = {
        Man: 'People, staffing, training, fatigue, human performance',
        Machine: 'Equipment, tools, aircraft/component condition, technology',
        Medium: 'Environment (weather, facilities, noise, workspace)',
        Mission: 'Mission objective / profile risk, crew-resource alignment',
        Management: 'Policies, oversight, supervision, accountability, culture',
        Measurement: 'Safety performance monitoring, KPIs, data analysis',
    };

    function uid(prefix) {
        return (prefix || 'rc') + '_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
    }

    function normalize(data) {
        data = data || {};
        return {
            root_causes: Array.isArray(data.root_causes) ? data.root_causes : [],
            action_items: Array.isArray(data.action_items) ? data.action_items : [],
        };
    }

    function primaryCauseId(data) {
        for (const c of (data.root_causes || [])) {
            if (c.is_primary) return c.id;
        }
        return null;
    }

    // ------------------------------------------------------------------
    // Validation
    // ------------------------------------------------------------------

    function validate(data) {
        const errors = [];
        const norm = normalize(data);
        if (!norm.root_causes.length) errors.push('At least one root cause is required.');
        if (norm.root_causes.length && !primaryCauseId(norm)) errors.push('Exactly one Primary Root Cause must be designated.');
        for (const c of norm.root_causes) {
            if (!c.description || !c.description.trim()) errors.push(`Root cause in "${c.category}" is missing a description.`);
        }
        for (const a of norm.action_items) {
            if (!a.description || !a.description.trim()) errors.push('Action item is missing a description.');
            if (!a.root_cause_id) errors.push(`Action item "${a.description}" must be linked to a root cause.`);
            else if (!norm.root_causes.some(rc => rc.id === a.root_cause_id)) {
                errors.push(`Action item "${a.description}" links to an unknown root cause.`);
            }
        }
        return errors;
    }

    // ------------------------------------------------------------------
    // Editor
    // ------------------------------------------------------------------

    function renderEditor(container, opts) {
        opts = opts || {};
        const el = typeof container === 'string' ? document.getElementById(container) : container;
        if (!el) throw new Error('[Fishbone] container not found: ' + container);

        const data = normalize(opts.data);
        const onChange = opts.onChange || function () {};

        el.innerHTML = '';
        const wrap = document.createElement('div');
        wrap.className = 'fishbone';

        const head = document.createElement('div');
        head.className = 'fishbone-head';
        head.innerHTML = `
            <div class="fishbone-title"><i class="fas fa-diagnoses"></i> Root Cause Analysis — Fishbone / Ishikawa (6M)</div>
            <div class="fishbone-hint">Add causes under each category. Designate exactly one <strong>Primary Root Cause</strong>.</div>
        `;
        wrap.appendChild(head);

        const grid = document.createElement('div');
        grid.className = 'fishbone-grid';

        function renderCategory(cat) {
            const panel = document.createElement('div');
            panel.className = 'fishbone-category';
            panel.dataset.category = cat;
            panel.innerHTML = `
                <div class="fishbone-category-head">
                    <span class="fishbone-category-name">${cat}</span>
                    <span class="fishbone-category-desc">${DEFAULT_ACTION[cat] || ''}</span>
                </div>
                <div class="fishbone-causes"></div>
                <button type="button" class="fishbone-add-cause btn btn-outline btn-sm"><i class="fas fa-plus"></i> Add cause</button>
            `;

            const list = panel.querySelector('.fishbone-causes');

            function renderCauses() {
                const causes = data.root_causes.filter(c => c.category === cat);
                list.innerHTML = '';
                if (!causes.length) {
                    const empty = document.createElement('div');
                    empty.className = 'fishbone-empty';
                    empty.textContent = 'No causes identified yet.';
                    list.appendChild(empty);
                }
                causes.forEach(cause => {
                    const row = document.createElement('div');
                    row.className = 'fishbone-cause-row';
                    row.innerHTML = `
                        <label class="fishbone-primary-radio" title="Mark as Primary Root Cause">
                            <input type="radio" name="fishbone_primary" value="${cause.id}" ${cause.is_primary ? 'checked' : ''}>
                            <span>Primary</span>
                        </label>
                        <input type="text" class="form-control fishbone-cause-input" value="${escapeAttr(cause.description || '')}" placeholder="Describe the cause…">
                        <button type="button" class="fishbone-remove-cause" title="Remove cause"><i class="fas fa-times"></i></button>
                    `;
                    const input = row.querySelector('.fishbone-cause-input');
                    input.addEventListener('input', () => {
                        cause.description = input.value;
                        onChange(getData());
                    });
                    row.querySelector('.fishbone-primary-radio input').addEventListener('change', () => {
                        data.root_causes.forEach(c => { c.is_primary = (c.id === cause.id); });
                        onChange(getData());
                    });
                    row.querySelector('.fishbone-remove-cause').addEventListener('click', () => {
                        data.root_causes = data.root_causes.filter(c => c.id !== cause.id);
                        // Unlink any action items pointing at the removed cause.
                        data.action_items.forEach(a => {
                            if (a.root_cause_id === cause.id) a.root_cause_id = null;
                        });
                        renderAll();
                        onChange(getData());
                    });
                    list.appendChild(row);
                });
            }

            panel.querySelector('.fishbone-add-cause').addEventListener('click', () => {
                data.root_causes.push({
                    id: uid('rc'),
                    category: cat,
                    description: '',
                    is_primary: data.root_causes.length === 0,
                });
                renderAll();
                onChange(getData());
            });

            return { panel, renderCauses };
        }

        const categoryPanels = {};
        CATEGORIES.forEach(cat => {
            const { panel, renderCauses } = renderCategory(cat);
            categoryPanels[cat] = renderCauses;
            grid.appendChild(panel);
        });
        wrap.appendChild(grid);

        // ------------------------------------------------------------------
        // Action Items (1:1 linkage to root causes)
        // ------------------------------------------------------------------

        const actionsSection = document.createElement('div');
        actionsSection.className = 'fishbone-actions';
        actionsSection.innerHTML = `
            <div class="fishbone-actions-head">
                <span class="fishbone-actions-title"><i class="fas fa-tasks"></i> Corrective Action Items</span>
                <span class="fishbone-actions-hint">Each action item links 1:1 to an identified root cause.</span>
            </div>
            <div class="fishbone-actions-table-wrap">
                <table class="fishbone-actions-table">
                    <thead>
                        <tr>
                            <th style="width:38%;">Action Item</th>
                            <th style="width:30%;">Linked Root Cause</th>
                            <th style="width:16%;">Owner</th>
                            <th style="width:12%;">Target Date</th>
                            <th style="width:4%;"></th>
                        </tr>
                    </thead>
                    <tbody class="fishbone-actions-body"></tbody>
                </table>
            </div>
            <button type="button" class="fishbone-add-action btn btn-outline btn-sm"><i class="fas fa-plus"></i> Add action item</button>
            <div class="fishbone-actions-errors" style="display:none;"></div>
        `;
        wrap.appendChild(actionsSection);

        const actionsBody = actionsSection.querySelector('.fishbone-actions-body');

        function causeOptions(selectedId) {
            const options = ['<option value="">— select root cause —</option>'];
            data.root_causes.forEach(c => {
                const sel = c.id === selectedId ? 'selected' : '';
                options.push(`<option value="${c.id}" ${sel}>${escapeAttr((c.category + ' — ' + (c.description || '')).slice(0, 60))}</option>`);
            });
            return options.join('');
        }

        function renderActions() {
            actionsBody.innerHTML = '';
            if (!data.action_items.length) {
                const tr = document.createElement('tr');
                tr.innerHTML = '<td colspan="5" class="fishbone-empty">No action items yet. Add one to link a corrective action to a root cause.</td>';
                actionsBody.appendChild(tr);
                return;
            }
            data.action_items.forEach(item => {
                const tr = document.createElement('tr');
                tr.dataset.actionId = item.id;
                tr.innerHTML = `
                    <td><input type="text" class="form-control fishbone-action-desc" value="${escapeAttr(item.description || '')}" placeholder="What will be done?"></td>
                    <td><select class="form-control fishbone-action-cause">${causeOptions(item.root_cause_id)}</select></td>
                    <td><input type="text" class="form-control fishbone-action-owner" value="${escapeAttr(item.owner || '')}" placeholder="Owner"></td>
                    <td><input type="date" class="form-control fishbone-action-date" value="${item.target_date || ''}"></td>
                    <td><button type="button" class="fishbone-remove-action" title="Remove"><i class="fas fa-times"></i></button></td>
                `;
                tr.querySelector('.fishbone-action-desc').addEventListener('input', () => {
                    item.description = tr.querySelector('.fishbone-action-desc').value;
                    refreshCauseOptions();
                    onChange(getData());
                });
                tr.querySelector('.fishbone-action-cause').addEventListener('change', (ev) => {
                    item.root_cause_id = ev.target.value || null;
                    onChange(getData());
                });
                tr.querySelector('.fishbone-action-owner').addEventListener('input', () => {
                    item.owner = tr.querySelector('.fishbone-action-owner').value;
                    onChange(getData());
                });
                tr.querySelector('.fishbone-action-date').addEventListener('change', () => {
                    item.target_date = tr.querySelector('.fishbone-action-date').value || null;
                    onChange(getData());
                });
                tr.querySelector('.fishbone-remove-action').addEventListener('click', () => {
                    data.action_items = data.action_items.filter(a => a.id !== item.id);
                    renderActions();
                    onChange(getData());
                });
                actionsBody.appendChild(tr);
            });
        }

        function refreshCauseOptions() {
            const selects = actionsBody.querySelectorAll('.fishbone-action-cause');
            selects.forEach(sel => {
                const current = sel.value;
                sel.innerHTML = causeOptions(current);
            });
        }

        actionsSection.querySelector('.fishbone-add-action').addEventListener('click', () => {
            const primaryId = primaryCauseId(data);
            data.action_items.push({
                id: uid('ai'),
                description: '',
                root_cause_id: primaryId || null,
                owner: '',
                target_date: null,
            });
            renderActions();
            onChange(getData());
        });

        function renderAll() {
            CATEGORIES.forEach(cat => categoryPanels[cat]());
            renderActions();
        }

        function getData() {
            const errs = validate(data);
            const errEl = actionsSection.querySelector('.fishbone-actions-errors');
            if (errs.length) {
                errEl.style.display = 'block';
                errEl.textContent = errs.join(' ');
                errEl.className = 'fishbone-actions-errors fishbone-errors-show';
            } else {
                errEl.style.display = 'none';
            }
            return normalize(data);
        }

        renderAll();

        return {
            element: wrap,
            getData,
            validate: () => validate(data),
        };
    }

    // ------------------------------------------------------------------
    // Viewer (read-only)
    // ------------------------------------------------------------------

    function renderViewer(container, data) {
        const el = typeof container === 'string' ? document.getElementById(container) : container;
        if (!el) throw new Error('[Fishbone] container not found: ' + container);
        const norm = normalize(data);

        el.innerHTML = '';
        const wrap = document.createElement('div');
        wrap.className = 'fishbone fishbone-view';

        const head = document.createElement('div');
        head.className = 'fishbone-head';
        head.innerHTML = `
            <div class="fishbone-title"><i class="fas fa-diagnoses"></i> Root Cause Analysis — Fishbone / Ishikawa (6M)</div>
        `;
        wrap.appendChild(head);

        if (!norm.root_causes.length) {
            const none = document.createElement('div');
            none.className = 'fishbone-empty';
            none.textContent = 'No root causes recorded.';
            wrap.appendChild(none);
            el.appendChild(wrap);
            return { element: wrap };
        }

        const grid = document.createElement('div');
        grid.className = 'fishbone-grid';
        CATEGORIES.forEach(cat => {
            const causes = norm.root_causes.filter(c => c.category === cat);
            const panel = document.createElement('div');
            panel.className = 'fishbone-category';
            panel.innerHTML = `
                <div class="fishbone-category-head">
                    <span class="fishbone-category-name">${cat}</span>
                </div>
                <div class="fishbone-causes">
                    ${causes.length ? causes.map(c => `
                        <div class="fishbone-view-cause ${c.is_primary ? 'fishbone-primary' : ''}">
                            ${c.is_primary ? '<span class="fishbone-primary-badge"><i class="fas fa-star"></i> Primary</span>' : ''}
                            <span class="fishbone-view-text">${escapeHtml(c.description || '')}</span>
                        </div>`).join('')
                        : '<div class="fishbone-empty">None</div>'}
                </div>
            `;
            grid.appendChild(panel);
        });
        wrap.appendChild(grid);

        if (norm.action_items.length) {
            const acts = document.createElement('div');
            acts.className = 'fishbone-actions';
            acts.innerHTML = `<div class="fishbone-actions-head"><span class="fishbone-actions-title"><i class="fas fa-tasks"></i> Corrective Action Items</span></div>`;
            const table = document.createElement('table');
            table.className = 'fishbone-actions-table';
            table.innerHTML = `<thead><tr><th>Action Item</th><th>Linked Root Cause</th><th>Owner</th><th>Target Date</th></tr></thead>`;
            const tbody = document.createElement('tbody');
            norm.action_items.forEach(a => {
                const cause = norm.root_causes.find(c => c.id === a.root_cause_id);
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${escapeHtml(a.description || '')}</td>
                    <td>${cause ? escapeHtml(cause.category + ' — ' + (cause.description || '')) : '<span style="color:#b91c1c;">Unlinked</span>'}</td>
                    <td>${escapeHtml(a.owner || '')}</td>
                    <td>${a.target_date ? escapeHtml(a.target_date) : '—'}</td>
                `;
                tbody.appendChild(tr);
            });
            table.appendChild(tbody);
            acts.appendChild(table);
            wrap.appendChild(acts);
        }

        el.appendChild(wrap);
        return { element: wrap };
    }

    // ------------------------------------------------------------------
    // HTML escaping helpers
    // ------------------------------------------------------------------

    function escapeHtml(v) {
        if (v === null || v === undefined) return '';
        return String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function escapeAttr(v) {
        return escapeHtml(v);
    }

    return {
        CATEGORIES,
        renderEditor,
        renderViewer,
        validate,
        normalize,
        primaryCauseId,
    };
})();

if (typeof window !== 'undefined') {
    window.Fishbone = Fishbone;
}