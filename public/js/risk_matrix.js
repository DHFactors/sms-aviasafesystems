// ============================================================================
// FILE: risk_matrix.js
// PURPOSE: Reusable ICAO 5x5 Safety Risk Assessment (SRA) matrix component.
//          Severity A-E (1-5) x Probability 1-5. Driven by the tenant's risk
//          matrix configuration (backend/app/services/risk_matrix.py) so labels
//          and thresholds stay in sync with the API.
// MODES:
//   - 'interactive': click a cell to select (Severity, Probability) -> risk state
//   - 'readonly'   : highlight a given (severity, probability) risk state
// COLOR CODING: outcome-based (Red=Unacceptable, Yellow=Tolerable, Green=
//   Acceptable) by default, or 4-level config colors via { colorMode: 'level' }.
// ============================================================================

const RiskMatrix = (() => {
    // Severity letter mapping: A=1 ... E=5 (CAAN/ICAO SRA matrix convention).
    const SEVERITY_LETTERS = ['A', 'B', 'C', 'D', 'E'];
    const SEVERITY_NUMS = [1, 2, 3, 4, 5];
    const PROBABILITY_NUMS = [1, 2, 3, 4, 5];

    const DEFAULTS = {
        thresholds: { low_max: 5, medium_max: 9, high_max: 15 },
        severity_labels: {
            1: 'Negligible', 2: 'Minor', 3: 'Major', 4: 'Hazardous', 5: 'Catastrophic',
        },
        probability_labels: {
            1: 'Extremely Improbable', 2: 'Improbable', 3: 'Remote', 4: 'Occasional', 5: 'Frequent',
        },
        risk_level_labels: {
            Low: 'Low (Acceptable)', Medium: 'Medium (Tolerable)',
            High: 'High (Intolerable)', 'Very High': 'Very High (Intolerable – Immediate Action)',
        },
        risk_level_colors: {
            Low: '#4CAF50', Medium: '#FFC107', High: '#FF9800', 'Very High': '#F44336',
        },
    };

    const OUTCOME_COLORS = {
        Acceptable: '#2e7d32',   // green
        Tolerable: '#b8860b',    // yellow/amber
        Intolerable: '#b91c1c',  // red
    };

    // ------------------------------------------------------------------
    // Config loading
    // ------------------------------------------------------------------

    async function fetchConfig() {
        if (window.ApiClient && typeof ApiClient.get === 'function') {
            try {
                const cfg = await ApiClient.get('/api/v1/admin/risk-matrix');
                if (cfg && cfg.thresholds) return cfg;
            } catch (e) {
                console.warn('[RiskMatrix] config fetch failed, using defaults:', e.message);
            }
        }
        return JSON.parse(JSON.stringify(DEFAULTS));
    }

    function resolveConfig(cfg) {
        const merged = JSON.parse(JSON.stringify(DEFAULTS));
        if (!cfg) return merged;
        if (cfg.thresholds) Object.assign(merged.thresholds, cfg.thresholds);
        if (cfg.severity_labels) Object.assign(merged.severity_labels, cfg.severity_labels);
        if (cfg.probability_labels) Object.assign(merged.probability_labels, cfg.probability_labels);
        if (cfg.risk_level_labels) Object.assign(merged.risk_level_labels, cfg.risk_level_labels);
        if (cfg.risk_level_colors) Object.assign(merged.risk_level_colors, cfg.risk_level_colors);
        return merged;
    }

    // ------------------------------------------------------------------
    // Classification
    // ------------------------------------------------------------------

    function classify(severity, probability, cfg) {
        const config = resolveConfig(cfg);
        const s = parseInt(severity, 10);
        const p = parseInt(probability, 10);
        if (!s || !p || s < 1 || s > 5 || p < 1 || p > 5) {
            return { severity: null, probability: null, index: null, level: null, outcome: null, color: null };
        }
        const index = s * p;
        const t = config.thresholds || DEFAULTS.thresholds;
        let level, outcome;
        if (index <= t.low_max) { level = 'Low'; outcome = 'Acceptable'; }
        else if (index <= t.medium_max) { level = 'Medium'; outcome = 'Tolerable'; }
        else if (index <= t.high_max) { level = 'High'; outcome = 'Intolerable'; }
        else { level = 'Very High'; outcome = 'Intolerable'; }
        const color = (config.risk_level_colors || {})[level] || null;
        return {
            severity: s,
            probability: p,
            severity_letter: SEVERITY_LETTERS[s - 1],
            index,
            level,
            outcome,
            color,
        };
    }

    // ------------------------------------------------------------------
    // Rendering
    // ------------------------------------------------------------------

    function cssColor(cfg, level) {
        return (cfg.risk_level_colors || {})[level] || null;
    }

    function badgeClassFor(level) {
        const map = { Low: 'badge-low', Medium: 'badge-medium', High: 'badge-high', 'Very High': 'badge-critical' };
        return map[level] || 'badge-default';
    }

    /**
     * Render a 5x5 SRA matrix.
     *
     * @param {string|Element} containerId  Target element or selector.
     * @param {Object} opts
     *   mode         'interactive' | 'readonly' (default 'readonly')
     *   config       Tenant risk-matrix config; omit to auto-fetch.
     *   severity     1..5 initial/current selection
     *   probability  1..5 initial/current selection
     *   colorMode    'outcome' (Red/Yellow/Green) | 'level' (4-level config colors)
     *   onSelect     callback(selection) on cell click (interactive only)
     *   showHeader   show matrix title/labels (default true)
     *   showSummary  show risk-index summary bar (default true)
     * @returns {Object} controller { getValue, setValue, getConfig, element }
     */
    async function render(containerId, opts) {
        opts = opts || {};
        const mode = opts.mode === 'interactive' ? 'interactive' : 'readonly';
        const colorMode = opts.colorMode === 'level' ? 'level' : 'outcome';
        const cfg = resolveConfig(opts.config || await fetchConfig());

        const el = typeof containerId === 'string' ? document.getElementById(containerId) : containerId;
        if (!el) throw new Error('[RiskMatrix] container not found: ' + containerId);

        const state = { severity: null, probability: null };
        if (opts.severity && opts.probability) {
            state.severity = parseInt(opts.severity, 10);
            state.probability = parseInt(opts.probability, 10);
        }

        el.innerHTML = '';

        const wrapper = document.createElement('div');
        wrapper.className = 'sra-matrix';

        if (opts.showHeader !== false) {
            const head = document.createElement('div');
            head.className = 'sra-matrix-head';
            head.innerHTML = `
                <div class="sra-matrix-title"><i class="fas fa-th"></i> Safety Risk Assessment (Severity A–E × Probability 1–5)</div>
                <div class="sra-matrix-legend">
                    <span class="sra-legend-item sra-legend-acceptable"><i class="fas fa-square"></i> Acceptable</span>
                    <span class="sra-legend-item sra-legend-tolerable"><i class="fas fa-square"></i> Tolerable</span>
                    <span class="sra-legend-item sra-legend-intolerable"><i class="fas fa-square"></i> Unacceptable</span>
                </div>
            `;
            wrapper.appendChild(head);
        }

        const table = document.createElement('table');
        table.className = 'sra-matrix-table';
        table.setAttribute('role', 'grid');
        table.setAttribute('aria-label', '5x5 Safety Risk Assessment Matrix');

        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        const corner = document.createElement('th');
        corner.textContent = 'Severity →';
        corner.className = 'sra-corner';
        headerRow.appendChild(corner);

        for (const s of SEVERITY_NUMS) {
            const th = document.createElement('th');
            th.className = 'sra-sev-header';
            th.innerHTML = `<span class="sra-letter">${SEVERITY_LETTERS[s - 1]}</span> <span class="sra-label">${cfg.severity_labels[s] || ''}</span>`;
            headerRow.appendChild(th);
        }
        thead.appendChild(headerRow);
        table.appendChild(thead);

        const tbody = document.createElement('tbody');
        for (const p of PROBABILITY_NUMS) {
            const tr = document.createElement('tr');
            const th = document.createElement('th');
            th.className = 'sra-prob-header';
            th.innerHTML = `<span class="sra-num">${p}</span> <span class="sra-label">${cfg.probability_labels[p] || ''}</span>`;
            tr.appendChild(th);

            for (const s of SEVERITY_NUMS) {
                const idx = s * p;
                const level = classify(s, p, cfg).level;
                const outcome = classify(s, p, cfg).outcome;

                const cell = document.createElement('td');
                cell.className = 'sra-cell';
                cell.dataset.severity = s;
                cell.dataset.probability = p;
                cell.dataset.index = idx;
                cell.dataset.level = level;
                cell.dataset.outcome = outcome;
                cell.textContent = idx;

                if (colorMode === 'outcome') {
                    cell.style.backgroundColor = OUTCOME_COLORS[outcome] || '#eee';
                    cell.style.color = '#fff';
                } else {
                    const col = cssColor(cfg, level);
                    if (col) { cell.style.backgroundColor = col; cell.style.color = '#fff'; }
                }

                cell.title = `Severity ${SEVERITY_LETTERS[s - 1]} (${s}) × Probability ${p} = ${idx} · ${level}`;

                if (mode === 'interactive') {
                    cell.setAttribute('role', 'gridcell');
                    cell.tabIndex = 0;
                    const select = () => {
                        state.severity = s;
                        state.probability = p;
                        highlight();
                        if (typeof opts.onSelect === 'function') {
                            opts.onSelect({ severity: s, probability: p, ...classify(s, p, cfg) });
                        }
                    };
                    cell.addEventListener('click', select);
                    cell.addEventListener('keydown', (ev) => {
                        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); select(); }
                    });
                }

                tr.appendChild(cell);
            }
            tbody.appendChild(tr);
        }
        table.appendChild(tbody);
        wrapper.appendChild(table);

        let summaryBar = null;
        if (opts.showSummary !== false) {
            summaryBar = document.createElement('div');
            summaryBar.className = 'sra-matrix-summary';
            wrapper.appendChild(summaryBar);
        }

        function highlight() {
            const cells = table.querySelectorAll('.sra-cell');
            cells.forEach(c => c.classList.remove('sra-selected'));
            if (state.severity && state.probability) {
                const target = table.querySelector(
                    `.sra-cell[data-severity="${state.severity}"][data-probability="${state.probability}"]`
                );
                if (target) target.classList.add('sra-selected');
            }
            if (summaryBar) {
                const r = classify(state.severity, state.probability, cfg);
                if (r.index == null) {
                    summaryBar.innerHTML = '<span class="sra-summary-empty">Risk Index: —</span>';
                } else {
                    const badge = r.level ? `badge ${badgeClassFor(r.level)}` : 'badge-default';
                    summaryBar.innerHTML = `
                        Risk Index: <strong>${r.index}</strong>
                        &nbsp;·&nbsp; Severity: <strong>${r.severity_letter} (${r.severity})</strong>
                        &nbsp;·&nbsp; Probability: <strong>${r.probability}</strong>
                        &nbsp;·&nbsp; Level: <span class="${badge}">${r.level || '—'}</span>
                        &nbsp;·&nbsp; Outcome: <strong style="color:${OUTCOME_COLORS[r.outcome] || '#334155'}">${r.outcome || '—'}</strong>
                    `;
                }
            }
        }

        highlight();

        el.appendChild(wrapper);

        return {
            element: wrapper,
            getValue: () => ({
                severity: state.severity,
                probability: state.probability,
                ...classify(state.severity, state.probability, cfg),
            }),
            setValue: (sev, prob) => {
                state.severity = parseInt(sev, 10) || null;
                state.probability = parseInt(prob, 10) || null;
                highlight();
            },
            getConfig: () => cfg,
        };
    }

    return { render, classify, fetchConfig, resolveConfig, SEVERITY_LETTERS, DEFAULTS, OUTCOME_COLORS };
})();

if (typeof window !== 'undefined') {
    window.RiskMatrix = RiskMatrix;
}