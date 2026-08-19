// ============================================================================
// FILE: srm.js
// PURPOSE: CAAN CAR-19 Safety Risk Management (SRM) Bow-Tie workspace for the
//          hazard detail page and the CAN/CAP Combined RCA + SRAM workflow.
//
// Exposes `window.SRM` with:
//   - Pure computation helpers mirroring backend/app/services/srm_engine.py
//     (severity A-E, BQV/BSV, probability bands, tolerability + sign-off) for
//     live client-side previews.
//   - `createWorkspace(container, opts)` — full Analysis Model Selector +
//     Bow-Tie workspace used on public/hazards/detail.html. Calls
//     HazardsAPI.sramCalculate / sramSave for authoritative results.
//   - `attachCombined(container, opts)` — Combined RCA + SRAM panel used on
//     public/can_cap/cap_submit.html that promotes Fish-Bone root causes into
//     Bow-Tie New Control Measures (NCM) and returns a `getSramData()` payload.
// ============================================================================

const SRM = (() => {

    // ── Constants (mirror backend/app/services/srm_engine.py) ──────────────
    const SEVERITY_KEYS = [
        { key: 'pax', label: 'Passenger (PAX) Safety', icon: 'fa-users' },
        { key: 'worker', label: 'Worker / Staff Safety', icon: 'fa-hard-hat' },
        { key: 'quality', label: 'Quality / Service', icon: 'fa-medal' },
        { key: 'asset', label: 'Asset / Equipment', icon: 'fa-gears' },
        { key: 'rep', label: 'Reputation / Trust', icon: 'fa-bullhorn' },
        { key: 'sec', label: 'Security', icon: 'fa-shield-halved' },
        { key: 'env', label: 'Environment', icon: 'fa-leaf' },
    ];

    const SEVERITY_BANDS = [
        [52, 65, 'A', 'Catastrophic'],
        [39, 51, 'B', 'Major'],
        [26, 38, 'C', 'Moderate'],
        [13, 25, 'D', 'Minor'],
        [0, 12, 'E', 'Insignificant'],
    ];

    const BQV_KEYS = [
        { key: 'effectiveness', label: 'Effectiveness', weight: 3 },
        { key: 'cost_benefit', label: 'Cost-Benefit', weight: 1 },
        { key: 'practicality', label: 'Practicality', weight: 1 },
        { key: 'acceptability', label: 'Acceptability', weight: 1 },
        { key: 'enforceability', label: 'Enforceability', weight: 1 },
        { key: 'durability', label: 'Durability', weight: 1 },
        { key: 'disinclination', label: 'Disinclination to Override', weight: 2 },
    ];

    const BQV_BANDS = [
        [42, 50, 5, 'Excellent'],
        [34, 41, 4, 'Very Good'],
        [26, 33, 3, 'Good'],
        [18, 25, 2, 'Fair'],
        [10, 17, 1, 'Poor'],
        [0, 9, 0, 'Ineffective'],
    ];

    const PROBABILITY_CONFIG = {
        A: [8, 40, [[0, 7, 5], [8, 15, 4], [16, 23, 3], [24, 31, 2], [32, 40, 1]]],
        B: [6, 30, [[0, 5, 5], [6, 11, 4], [12, 17, 3], [18, 23, 2], [24, 30, 1]]],
        C: [4, 20, [[0, 3, 5], [4, 7, 4], [8, 11, 3], [12, 15, 2], [16, 20, 1]]],
        D: [3, 15, [[0, 2, 5], [3, 5, 4], [6, 8, 3], [9, 11, 2], [12, 15, 1]]],
        E: [2, 10, [[0, 1, 5], [2, 3, 4], [4, 5, 3], [6, 7, 2], [8, 10, 1]]],
    };

    const TOLERABILITY = {
        '5A': 'Intolerable', '5B': 'Intolerable', '5C': 'Intolerable',
        '5D': 'Tolerable', '5E': 'Tolerable',
        '4A': 'Intolerable', '4B': 'Intolerable',
        '4C': 'Tolerable', '4D': 'Tolerable', '4E': 'Tolerable',
        '3A': 'Intolerable',
        '3B': 'Tolerable', '3C': 'Tolerable', '3D': 'Tolerable', '3E': 'Acceptable',
        '2A': 'Tolerable', '2B': 'Tolerable', '2C': 'Tolerable',
        '2D': 'Acceptable', '2E': 'Acceptable',
        '1A': 'Tolerable',
        '1B': 'Acceptable', '1C': 'Acceptable', '1D': 'Acceptable', '1E': 'Acceptable',
    };

    const SIGNOFF_AUTHORITY = {
        Intolerable: 'Accountable Manager',
        Tolerable: 'Risk Owner / Functional Chief',
        Acceptable: 'Safety Manager / SAG Member',
    };

    const LETTER_TO_NUMERIC = { A: 5, B: 4, C: 3, D: 2, E: 1 };

    const FISHBONE_CATEGORIES = ['Man', 'Machine', 'Method', 'Medium', 'Management', 'Material'];

    // ── Helpers ─────────────────────────────────────────────────────────────
    function esc(v) {
        if (v === null || v === undefined) return '';
        return String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function uid(prefix) {
        return (prefix || 'b') + '_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
    }

    function defaultQuality() {
        return {
            effectiveness: 3, cost_benefit: 3, practicality: 3,
            acceptability: 3, enforceability: 3, durability: 3, disinclination: 3,
        };
    }

    function emptySeverityInputs() {
        return { pax: 0, worker: 0, quality: 0, asset: 0, rep: 0, sec: 0, env: 0 };
    }

    // ── Computation (mirrors the backend engine) ────────────────────────────
    function computeSeverity(inputs) {
        inputs = inputs || emptySeverityInputs();
        const score = 4 * (inputs.pax || 0) + 3 * (inputs.worker || 0)
            + 2 * (inputs.quality || 0) + (inputs.asset || 0)
            + (inputs.rep || 0) + (inputs.sec || 0) + (inputs.env || 0);
        for (const [lo, hi, letter, desc] of SEVERITY_BANDS) {
            if (score >= lo && score <= hi) return { total_score: score, severity_letter: letter, descriptor: desc };
        }
        return { total_score: score, severity_letter: 'E', descriptor: 'Insignificant' };
    }

    function computeBqv(q) {
        q = q || defaultQuality();
        const bqv = 3 * (q.effectiveness || 1) + (q.cost_benefit || 1)
            + (q.practicality || 1) + (q.acceptability || 1)
            + (q.enforceability || 1) + (q.durability || 1)
            + 2 * (q.disinclination || 1);
        for (const [lo, hi, bsv, robustness] of BQV_BANDS) {
            if (bqv >= lo && bqv <= hi) return { bqv, bsv, robustness };
        }
        return { bqv, bsv: 0, robustness: 'Ineffective' };
    }

    function computeProbability(severityLetter, cbsv) {
        const cfg = PROBABILITY_CONFIG[(severityLetter || 'E').toUpperCase()] || PROBABILITY_CONFIG.E;
        const maxv = cfg[1];
        const bands = cfg[2];
        const value = Math.max(0, Math.min(cbsv || 0, maxv));
        for (const [lo, hi, pv] of bands) {
            if (value >= lo && value <= hi) return pv;
        }
        return 1;
    }

    function tolerability(probabilityValue, severityLetter) {
        return TOLERABILITY[probabilityValue + severityLetter] || 'Acceptable';
    }

    function evaluateRiskProfile(severity, barriers) {
        const lists = {
            ecb: (barriers && barriers.ecb) || [],
            erb: (barriers && barriers.erb) || [],
            ncb: (barriers && barriers.ncb) || [],
            nrb: (barriers && barriers.nrb) || [],
        };
        const sum = (arr) => arr.reduce((acc, b) => acc + (b.bsv || 0), 0);
        const existingBsv = sum(lists.ecb) + sum(lists.erb);
        const consolidatedBsv = existingBsv + sum(lists.ncb) + sum(lists.nrb);
        const letter = (severity && severity.severity_letter) || 'E';
        const initialP = computeProbability(letter, existingBsv);
        const resultantP = computeProbability(letter, consolidatedBsv);
        const initialTol = tolerability(initialP, letter);
        const resultantTol = tolerability(resultantP, letter);
        return {
            existing_bsv: existingBsv,
            consolidated_bsv: consolidatedBsv,
            severity_letter: letter,
            initial_risk: {
                index: initialP + letter, probability_value: initialP,
                descriptor: '', tolerability: initialTol,
            },
            resultant_risk: {
                index: resultantP + letter, probability_value: resultantP,
                descriptor: '', tolerability: resultantTol,
            },
            signoff: {
                authority: SIGNOFF_AUTHORITY[resultantTol],
                initial_authority: SIGNOFF_AUTHORITY[initialTol],
                resultant_authority: SIGNOFF_AUTHORITY[resultantTol],
            },
        };
    }

    // ── Barrier Quality modal ───────────────────────────────────────────────
    function openBarrierQualityModal(barrier, { onSave, title }) {
        const overlay = document.createElement('div');
        overlay.className = 'srm-modal-overlay';
        const q = Object.assign(defaultQuality(), barrier.quality || {});

        const sliderRows = BQV_KEYS.map(k => `
            <div class="srm-slider-row">
                <span class="srm-slider-icon"><i class="fas fa-sliders-h"></i></span>
                <span class="srm-slider-label">${esc(k.label)} ${k.weight > 1 ? '×' + k.weight : ''}</span>
                <input type="range" min="1" max="5" step="1" value="${q[k.key]}" data-bqv-key="${k.key}">
                <span class="srm-slider-value" data-bqv-val="${k.key}">${q[k.key]}</span>
            </div>`).join('');

        overlay.innerHTML = `
            <div class="srm-modal" role="dialog" aria-modal="true">
                <h3><i class="fas fa-shield-halved"></i> ${esc(title || 'Barrier Quality Rating')}</h3>
                <div class="srm-modal-sub">${esc(barrier.name || '')}</div>
                <div class="srm-bqv-badge">
                    <span>BQV</span>
                    <span class="srm-bqv-value" data-bqv-total>${computeBqv(q).bqv}</span>
                    <span class="srm-bsv-chip" data-bsv>${computeBqv(q).bsv}</span>
                    <span class="srm-bsv-robustness" data-robustness>${computeBqv(q).robustness}</span>
                </div>
                ${sliderRows}
                <div class="srm-modal-actions">
                    <button type="button" class="srm-btn srm-btn-outline" data-bqv-cancel>Cancel</button>
                    <button type="button" class="srm-btn srm-btn-save" data-bqv-ok>Apply Rating</button>
                </div>
            </div>`;

        function refresh() {
            const total = document.querySelector('[data-bqv-total]');
            const chip = document.querySelector('[data-bsv]');
            const rob = document.querySelector('[data-robustness]');
            const res = computeBqv(q);
            total.textContent = res.bqv;
            chip.textContent = res.bsv;
            rob.textContent = res.robustness;
        }

        overlay.querySelectorAll('[data-bqv-key]').forEach(slider => {
            slider.addEventListener('input', () => {
                const key = slider.dataset.bqvKey;
                q[key] = parseInt(slider.value, 10);
                overlay.querySelector(`[data-bqv-val="${key}"]`).textContent = q[key];
                refresh();
            });
        });
        overlay.querySelector('[data-bqv-cancel]').addEventListener('click', () => overlay.remove());
        overlay.querySelector('[data-bqv-ok]').addEventListener('click', () => {
            const res = computeBqv(q);
            barrier.quality = q;
            barrier.bqv = res.bqv;
            barrier.bsv = res.bsv;
            barrier.robustness = res.robustness;
            overlay.remove();
            if (typeof onSave === 'function') onSave();
        });
        overlay.addEventListener('click', (ev) => {
            if (ev.target === overlay) overlay.remove();
        });
        document.body.appendChild(overlay);
    }

    // ── Barrier pill rendering ──────────────────────────────────────────────
    function barrierPillHtml(barrier, cls) {
        const bsv = barrier.bsv != null ? barrier.bsv : 0;
        const name = barrier.name || '(unnamed)';
        const robNote = barrier.robustness ? ` · ${esc(barrier.robustness)}` : '';
        return `
            <div class="srm-barrier-pill ${cls}" data-barrier-id="${esc(barrier.id || '')}">
                <span class="srm-pill-name" title="${esc(name)}${robNote}">${esc(name)}</span>
                <span class="srm-bsv-badge" title="Barrier Score Value (BSV)">BSV ${bsv}</span>
                <button type="button" class="srm-pill-remove" title="Remove barrier" data-pill-remove><i class="fas fa-times"></i></button>
            </div>`;
    }

    function bindBarrierPills(listEl, barriers, cls, ctx) {
        listEl.querySelectorAll('[data-barrier-id]').forEach(pill => {
            const id = pill.dataset.barrierId;
            const barrier = barriers.find(b => b.id === id);
            pill.addEventListener('click', (ev) => {
                if (ev.target.closest('[data-pill-remove]')) return;
                if (!barrier) return;
                openBarrierQualityModal(barrier, {
                    title: (cls === 'srm-erb' ? 'Existing Recovery Barrier' : cls === 'srm-ncb' ? 'New Control Measure' : cls === 'srm-nrb' ? 'New Recovery Barrier' : 'Existing Control Measure') + ' Quality',
                    onSave: () => { ctx.renderBarriers(); ctx.updateLive(); },
                });
            });
            const rm = pill.querySelector('[data-pill-remove]');
            if (rm) rm.addEventListener('click', (ev) => {
                ev.stopPropagation();
                const idx = barriers.findIndex(b => b.id === id);
                if (idx >= 0) barriers.splice(idx, 1);
                ctx.renderBarriers();
                ctx.updateLive();
            });
        });
    }

    // ── SrmWorkspace (hazard detail page) ───────────────────────────────────
    class SrmWorkspace {
        constructor(container, opts) {
            opts = opts || {};
            this.el = typeof container === 'string' ? document.getElementById(container) : container;
            if (!this.el) throw new Error('[SRM] container not found');
            this.hazardId = opts.hazardId;
            this.saved = opts.saved || null;
            this.mode = (opts.mode || 'FISHBONE_ONLY');
            this.onSaved = opts.onSaved || null;

            this.severityInputs = emptySeverityInputs();
            this.barriers = { ecb: [], erb: [], ncb: [], nrb: [] };
            this.bowtie = { threats: [], top_event: '', consequences: [] };
            this.fishbone = { root_causes: [], action_items: [] };
            this.signoffs = { name: '', role: '', date: '' };
            this.riskProfile = null;
            this.fishboneController = null;
            this.savedSeverityLetter = null;

            this._loadSaved();
            this.render();
        }

        _loadSaved() {
            if (!this.saved) return;
            const s = this.saved;
            if (s.severity && typeof s.severity === 'object') {
                SEVERITY_KEYS.forEach(k => {
                    if (s.severity[k.key] != null) this.severityInputs[k.key] = s.severity[k.key];
                });
                if (s.severity.severity_letter) this.savedSeverityLetter = s.severity.severity_letter;
            }
            if (s.barriers) {
                this.barriers = {
                    ecb: (s.barriers.ecb || []).map(b => Object.assign({}, b)),
                    erb: (s.barriers.erb || []).map(b => Object.assign({}, b)),
                    ncb: (s.barriers.ncb || []).map(b => Object.assign({}, b)),
                    nrb: (s.barriers.nrb || []).map(b => Object.assign({}, b)),
                };
            }
            if (s.bowtie) this.bowtie = Object.assign(this.bowtie, s.bowtie);
            if (s.fishbone) this.fishbone = s.fishbone;
            if (s.signoffs) this.signoffs = Object.assign(this.signoffs, s.signoffs);
            if (s.risk_profile) this.riskProfile = s.risk_profile;
        }

        render() {
            this.el.innerHTML = `
                <div class="srm-workspace">
                    <div class="srm-mode-selector">
                        <span class="srm-mode-title"><i class="fas fa-arrows-left-right"></i> Analysis Model Selector</span>
                        <label data-mode="FISHBONE_ONLY"><input type="radio" name="srm_mode" value="FISHBONE_ONLY"> Fish-Bone RCA</label>
                        <label data-mode="BOWTIE_SRAM"><input type="radio" name="srm_mode" value="BOWTIE_SRAM"> Bow-Tie SRAM</label>
                        <label data-mode="COMBINED"><input type="radio" name="srm_mode" value="COMBINED"> Combined RCA + SRAM</label>
                    </div>

                    <div class="srm-section" data-srm-part="fishbone">
                        <h3><i class="fas fa-diagnoses"></i> 6M Root-Cause Diagram — Interactive Fish-Bone (Ishikawa)</h3>
                        <div id="srmFishboneEditor_${uid('fb')}" data-srm-fishbone></div>
                        <div class="srm-promotion" data-srm-promotion style="display:none;margin-top:0.7rem;">
                            <div class="srm-promotion-head"><i class="fas fa-arrow-up"></i> Promote Root Causes to Bow-Tie New Control Measures (NCM)</div>
                            <div data-srm-promotion-list></div>
                            <div class="srm-promoted-note">In Combined mode, root causes you promote become New Control Measures in the Bow-Tie, lowering the resultant risk.</div>
                        </div>
                    </div>

                    <div class="srm-section" data-srm-part="severity">
                        <h3><i class="fas fa-balance-scale"></i> 7-Impact Severity Assessment (0-5 per impact)</h3>
                        <div class="srm-severity-grid">${this._severityRows()}</div>
                        <div class="srm-score-badge">
                            <span>Weighted Score</span>
                            <span class="srm-score-value" data-srm-score>0</span>
                            <span class="srm-severity-letter" data-srm-letter>E</span>
                            <span class="srm-severity-desc" data-srm-desc>Insignificant</span>
                        </div>
                    </div>

                    <div class="srm-section" data-srm-part="bowtie" style="display:none;">
                        <h3><i class="fas fa-bow-arrow"></i> Interactive Bow-Tie</h3>
                        <div class="srm-bowtie">
                            <div class="srm-col">
                                <div class="srm-col-head">Threats</div>
                                <div data-srm-threats></div>
                                <button type="button" class="srm-add-btn" data-srm-add-threat><i class="fas fa-plus"></i> Add Threat</button>
                            </div>
                            <div class="srm-col">
                                <div class="srm-col-head">Existing Control Measures (ECM)</div>
                                <div data-srm-ecm></div>
                                <button type="button" class="srm-add-btn" data-srm-add-ecm><i class="fas fa-plus"></i> Add ECM</button>
                            </div>
                            <div class="srm-top-event">
                                <span>TOP EVENT</span>
                                <input type="text" placeholder="e.g. Wheel jack sinks into apron" data-srm-top-event>
                            </div>
                            <div class="srm-col">
                                <div class="srm-col-head">Existing Recovery Barriers (ERB)</div>
                                <div data-srm-erb></div>
                                <button type="button" class="srm-add-btn" data-srm-add-erb><i class="fas fa-plus"></i> Add ERB</button>
                            </div>
                            <div class="srm-col">
                                <div class="srm-col-head">Consequences</div>
                                <div data-srm-consequences></div>
                                <button type="button" class="srm-add-btn" data-srm-add-consequence><i class="fas fa-plus"></i> Add Consequence</button>
                            </div>
                        </div>
                        <div class="srm-new-barriers" style="margin-top:0.7rem;">
                            <div class="srm-col">
                                <div class="srm-col-head">New Control Measures (NCM)</div>
                                <div data-srm-ncb></div>
                                <button type="button" class="srm-add-btn" data-srm-add-ncb><i class="fas fa-plus"></i> Add NCM</button>
                            </div>
                            <div class="srm-col">
                                <div class="srm-col-head">New Recovery Barriers (NRB)</div>
                                <div data-srm-nrb></div>
                                <button type="button" class="srm-add-btn" data-srm-add-nrb2><i class="fas fa-plus"></i> Add NRB</button>
                            </div>
                        </div>
                    </div>

                    <div class="srm-section">
                        <h3><i class="fas fa-th-large"></i> Before &amp; After Risk Matrix Comparison</h3>
                        <div class="srm-risk-comparison">
                            <div class="srm-risk-box">
                                <div class="srm-risk-label">Current Risk Index</div>
                                <div class="srm-risk-index" data-srm-initial-index>—</div>
                                <div class="srm-risk-tol" data-srm-initial-tol>—</div>
                                <div class="srm-bsv-summary" data-srm-initial-bsv></div>
                            </div>
                            <div class="srm-risk-arrow"><i class="fas fa-arrow-right"></i></div>
                            <div class="srm-risk-box">
                                <div class="srm-risk-label">Resultant Risk Index</div>
                                <div class="srm-risk-index" data-srm-resultant-index>—</div>
                                <div class="srm-risk-tol" data-srm-resultant-tol>—</div>
                                <div class="srm-bsv-summary" data-srm-resultant-bsv></div>
                            </div>
                        </div>
                    </div>

                    <div class="srm-section">
                        <h3><i class="fas fa-file-signature"></i> Digital Postholder Sign-Off</h3>
                        <div class="srm-signoff">
                            <span class="srm-authority-badge" data-srm-authority><i class="fas fa-user-shield"></i> Required: —</span>
                            <div class="srm-signoff-grid">
                                <div><label>Postholder Name</label><input type="text" data-srm-sign-name placeholder="Full name"></div>
                                <div><label>Postholder Role</label><input type="text" data-srm-sign-role placeholder="e.g. Safety Manager"></div>
                                <div><label>Date</label><input type="date" data-srm-sign-date></div>
                            </div>
                        </div>
                    </div>

                    <div class="srm-actions">
                        <button type="button" class="srm-btn srm-btn-calc" data-srm-calc><i class="fas fa-calculator"></i> Calculate (Preview)</button>
                        <button type="button" class="srm-btn srm-btn-save" data-srm-save><i class="fas fa-save"></i> Save Configuration</button>
                        <span class="srm-status" data-srm-status></span>
                    </div>
                </div>`;

            this._initFishbone();
            this._bindEvents();
            this._applyMode(this.mode);
            this.renderBarriers();
            this.renderBowtie();
            this.updateLive();
        }

        _severityRows() {
            return SEVERITY_KEYS.map(k => `
                <div class="srm-slider-row">
                    <span class="srm-slider-icon"><i class="fas ${k.icon}"></i></span>
                    <span class="srm-slider-label">${esc(k.label)}</span>
                    <input type="range" min="0" max="5" step="1" value="${this.severityInputs[k.key] || 0}" data-sev="${k.key}">
                    <span class="srm-slider-value" data-sev-val="${k.key}">${this.severityInputs[k.key] || 0}</span>
                </div>`).join('');
        }

        _initFishbone() {
            const holder = this.el.querySelector('[data-srm-fishbone]');
            if (holder && typeof Fishbone !== 'undefined' && Fishbone.renderEditor) {
                try {
                    this.fishboneController = Fishbone.renderEditor(holder, {
                        data: this.fishbone,
                        onChange: () => {
                            this.fishbone = this.fishboneController.getData();
                            this.renderPromotion();
                        },
                    });
                } catch (err) {
                    holder.innerHTML = '<div class="fishbone-empty">Fishbone editor unavailable.</div>';
                }
            } else if (holder) {
                holder.innerHTML = '<div class="fishbone-empty">Fishbone editor script not loaded.</div>';
            }
        }

        _bindEvents() {
            // Mode selector.
            this.el.querySelectorAll('[data-mode] input').forEach(radio => {
                radio.addEventListener('change', () => {
                    if (radio.checked) this._applyMode(radio.value);
                });
            });

            // Severity sliders.
            this.el.querySelectorAll('[data-sev]').forEach(slider => {
                slider.addEventListener('input', () => {
                    const key = slider.dataset.sev;
                    const val = parseInt(slider.value, 10);
                    this.severityInputs[key] = val;
                    this.el.querySelector(`[data-sev-val="${key}"]`).textContent = val;
                    this.updateLive();
                });
            });

            // Bow-tie add buttons.
            this.el.querySelector('[data-srm-add-threat]').addEventListener('click', () => this._addBowtieItem('threats'));
            this.el.querySelector('[data-srm-add-consequence]').addEventListener('click', () => this._addBowtieItem('consequences'));
            this.el.querySelector('[data-srm-add-ecm]').addEventListener('click', () => this._addBarrier('ecb', 'srm-ecm'));
            this.el.querySelector('[data-srm-add-erb]').addEventListener('click', () => this._addBarrier('erb', 'srm-erb'));
            this.el.querySelector('[data-srm-add-ncb]').addEventListener('click', () => this._addBarrier('ncb', 'srm-ncb'));
            this.el.querySelector('[data-srm-add-nrb2]').addEventListener('click', () => this._addBarrier('nrb', 'srm-nrb'));

            const topEventInput = this.el.querySelector('[data-srm-top-event]');
            topEventInput.value = this.bowtie.top_event || '';
            topEventInput.addEventListener('input', () => { this.bowtie.top_event = topEventInput.value; });

            // Sign-off.
            const nameIn = this.el.querySelector('[data-srm-sign-name]');
            const roleIn = this.el.querySelector('[data-srm-sign-role]');
            const dateIn = this.el.querySelector('[data-srm-sign-date]');
            nameIn.value = this.signoffs.name || '';
            roleIn.value = this.signoffs.role || '';
            dateIn.value = this.signoffs.date || '';
            nameIn.addEventListener('input', () => { this.signoffs.name = nameIn.value; });
            roleIn.addEventListener('input', () => { this.signoffs.role = roleIn.value; });
            dateIn.addEventListener('change', () => { this.signoffs.date = dateIn.value; });

            // Actions.
            this.el.querySelector('[data-srm-calc]').addEventListener('click', () => this.calculate());
            this.el.querySelector('[data-srm-save]').addEventListener('click', () => this.save());
        }

        _applyMode(mode) {
            this.mode = mode;
            this.el.querySelectorAll('[data-mode]').forEach(label => {
                const active = label.dataset.mode === mode;
                label.classList.toggle('srm-mode-active', active);
                const radio = label.querySelector('input');
                if (active) radio.checked = true;
            });

            const fishbonePart = this.el.querySelector('[data-srm-part="fishbone"]');
            const bowtiePart = this.el.querySelector('[data-srm-part="bowtie"]');
            const promotion = this.el.querySelector('[data-srm-promotion]');

            fishbonePart.style.display = (mode === 'FISHBONE_ONLY' || mode === 'COMBINED') ? 'block' : 'none';
            bowtiePart.style.display = (mode === 'BOWTIE_SRAM' || mode === 'COMBINED') ? 'block' : 'none';
            promotion.style.display = mode === 'COMBINED' ? 'block' : 'none';
            if (mode === 'COMBINED') this.renderPromotion();
        }

        renderPromotion() {
            const list = this.el.querySelector('[data-srm-promotion-list]');
            if (!list) return;
            const causes = (this.fishbone && this.fishbone.root_causes) || [];
            const promotedIds = (this.barriers.ncb || [])
                .map(b => b.source_root_cause_id).filter(Boolean);

            if (!causes.length) {
                list.innerHTML = '<div class="srm-promoted-note">Add root causes above, then promote them here as New Control Measures.</div>';
                return;
            }

            list.innerHTML = causes.map(c => {
                const promoted = promotedIds.indexOf(c.id) >= 0;
                return `
                    <div class="srm-promote-row">
                        <span class="srm-promote-text"><strong>${esc(c.category)}</strong> — ${esc(c.description || '')}</span>
                        ${promoted
                            ? '<span class="srm-promoted-note"><i class="fas fa-check-circle"></i> Promoted to NCM</span>'
                            : `<button type="button" class="srm-promote-btn" data-promote="${esc(c.id)}"><i class="fas fa-arrow-up"></i> Promote to NCM</button>`}
                    </div>`;
            }).join('');

            list.querySelectorAll('[data-promote]').forEach(btn => {
                btn.addEventListener('click', () => {
                    const cause = causes.find(c => c.id === btn.dataset.promote);
                    if (!cause) return;
                    const barrier = {
                        id: uid('ncm'),
                        name: (cause.description || '').trim() || `${cause.category} root cause`,
                        description: cause.description,
                        category: cause.category,
                        source_root_cause_id: cause.id,
                        quality: defaultQuality(),
                    };
                    const res = computeBqv(barrier.quality);
                    barrier.bqv = res.bqv;
                    barrier.bsv = res.bsv;
                    barrier.robustness = res.robustness;
                    this.barriers.ncb.push(barrier);
                    this.renderBarriers();
                    this.renderPromotion();
                    this.updateLive();
                });
            });
        }

        _addBowtieItem(kind) {
            this.bowtie[kind].push({ id: uid('bt'), label: '', barrier_ids: [] });
            this.renderBowtie();
        }

        renderBowtie() {
            const threatsEl = this.el.querySelector('[data-srm-threats]');
            const consEl = this.el.querySelector('[data-srm-consequences]');
            if (!threatsEl || !consEl) return;

            const ecm = this.barriers.ecb;
            const erb = this.barriers.erb;

            const renderItem = (item, placeholder, ecmOpts) => `
                <div class="srm-card srm-threat">
                    <input type="text" value="${esc(item.label || '')}" placeholder="${placeholder}" data-bt-label="${esc(item.id)}">
                    <select data-bt-ecm="${esc(item.id)}">
                        <option value="">— link ECM barrier —</option>
                        ${(ecmOpts || []).map(b => `<option value="${esc(b.id)}" ${(item.barrier_ids || []).indexOf(b.id) >= 0 ? 'selected' : ''}>${esc(b.name || 'ECM')}</option>`).join('')}
                    </select>
                    <button type="button" class="srm-pill-remove" title="Remove" data-bt-remove="${esc(item.id)}"><i class="fas fa-times"></i></button>
                </div>`;

            threatsEl.innerHTML = (this.bowtie.threats || []).map(t => renderItem(t, 'e.g. Unsafe apron surface', ecm)).join('')
                || '<div class="srm-hint">Add a threat to build the left side of the Bow-Tie.</div>';
            consEl.innerHTML = (this.bowtie.consequences || []).map(c => `
                <div class="srm-card srm-consequence">
                    <input type="text" value="${esc(c.label || '')}" placeholder="e.g. Aircraft/crew injury" data-bt-label="${esc(c.id)}">
                    <select data-bt-erb="${esc(c.id)}">
                        <option value="">— link ERB barrier —</option>
                        ${(erb || []).map(b => `<option value="${esc(b.id)}" ${(c.barrier_ids || []).indexOf(b.id) >= 0 ? 'selected' : ''}>${esc(b.name || 'ERB')}</option>`).join('')}
                    </select>
                    <button type="button" class="srm-pill-remove" title="Remove" data-bt-remove="${esc(c.id)}"><i class="fas fa-times"></i></button>
                </div>`).join('')
                || '<div class="srm-hint">Add a consequence to build the right side of the Bow-Tie.</div>';

            threatsEl.querySelectorAll('[data-bt-label]').forEach(inp => {
                inp.addEventListener('input', () => {
                    const item = this.bowtie.threats.find(t => t.id === inp.dataset.btLabel);
                    if (item) item.label = inp.value;
                });
            });
            threatsEl.querySelectorAll('[data-bt-ecm]').forEach(sel => {
                sel.addEventListener('change', () => {
                    const item = this.bowtie.threats.find(t => t.id === sel.dataset.btEcm);
                    if (item) item.barrier_ids = sel.value ? [sel.value] : [];
                });
            });
            consEl.querySelectorAll('[data-bt-label]').forEach(inp => {
                inp.addEventListener('input', () => {
                    const item = this.bowtie.consequences.find(c => c.id === inp.dataset.btLabel);
                    if (item) item.label = inp.value;
                });
            });
            consEl.querySelectorAll('[data-bt-erb]').forEach(sel => {
                sel.addEventListener('change', () => {
                    const item = this.bowtie.consequences.find(c => c.id === sel.dataset.btErb);
                    if (item) item.barrier_ids = sel.value ? [sel.value] : [];
                });
            });
            threatsEl.querySelectorAll('[data-bt-remove]').forEach(btn => {
                btn.addEventListener('click', () => {
                    this.bowtie.threats = this.bowtie.threats.filter(t => t.id !== btn.dataset.btRemove);
                    this.renderBowtie();
                });
            });
            consEl.querySelectorAll('[data-bt-remove]').forEach(btn => {
                btn.addEventListener('click', () => {
                    this.bowtie.consequences = this.bowtie.consequences.filter(c => c.id !== btn.dataset.btRemove);
                    this.renderBowtie();
                });
            });
        }

        _addBarrier(listKey, cls) {
            const barrier = { id: uid('b'), name: '', quality: defaultQuality() };
            const res = computeBqv(barrier.quality);
            barrier.bqv = res.bqv;
            barrier.bsv = res.bsv;
            barrier.robustness = res.robustness;
            this.barriers[listKey].push(barrier);
            this.renderBarriers();
            this.updateLive();
        }

        renderBarriers() {
            const map = {
                ecb: ['[data-srm-ecm]', 'srm-ecm'],
                erb: ['[data-srm-erb]', 'srm-erb'],
                ncb: ['[data-srm-ncb]', 'srm-ncb'],
                nrb: ['[data-srm-nrb]', 'srm-nrb'],
            };
            Object.keys(map).forEach(key => {
                const [sel, cls] = map[key];
                const listEl = this.el.querySelector(sel);
                if (!listEl) return;
                const barriers = this.barriers[key];
                listEl.innerHTML = barriers.length
                    ? barriers.map(b => barrierPillHtml(b, cls)).join('')
                    : '<div class="srm-hint">No barriers added.</div>';
                bindBarrierPills(listEl, barriers, cls, this);
            });
        }

        updateLive() {
            const severity = computeSeverity(this.severityInputs);
            this.el.querySelector('[data-srm-score]').textContent = severity.total_score;
            this.el.querySelector('[data-srm-letter]').textContent = severity.severity_letter;
            this.el.querySelector('[data-srm-desc]').textContent = severity.descriptor;

            const profile = evaluateRiskProfile(severity, this.barriers);
            this.riskProfile = profile;
            this._renderComparison(profile);

            const authority = profile.signoff.authority;
            const badge = this.el.querySelector('[data-srm-authority]');
            badge.innerHTML = `<i class="fas fa-user-shield"></i> Required: ${esc(authority)}`;

            const tol = profile.resultant_risk.tolerability;
            badge.style.background = tol === 'Intolerable' ? '#7f1d1d' : tol === 'Tolerable' ? '#b45309' : '#14532d';
        }

        _renderComparison(profile) {
            const setIndex = (sel, risk) => {
                const idx = this.el.querySelector(sel + '-index');
                const tol = this.el.querySelector(sel + '-tol');
                const bsv = this.el.querySelector(sel + '-bsv');
                idx.textContent = risk.index;
                tol.textContent = risk.tolerability;
                tol.className = 'srm-risk-tol ' + (risk.tolerability === 'Intolerable' ? 'srm-tol-intolerable' : risk.tolerability === 'Tolerable' ? 'srm-tol-tolerable' : 'srm-tol-acceptable');
                bsv.textContent = '';
            };
            setIndex('[data-srm-initial]', profile.initial_risk);
            setIndex('[data-srm-resultant]', profile.resultant_risk);
            this.el.querySelector('[data-srm-initial-bsv]').textContent =
                `Existing BSV ${profile.existing_bsv}`;
            this.el.querySelector('[data-srm-resultant-bsv]').textContent =
                `Consolidated BSV ${profile.consolidated_bsv}`;
        }

        _buildCalculatePayload() {
            const barriers = {};
            Object.keys(this.barriers).forEach(key => {
                barriers[key] = this.barriers[key].map(b => ({
                    id: b.id,
                    name: b.name,
                    description: b.description,
                    category: b.category,
                    source_root_cause_id: b.source_root_cause_id,
                    quality: b.quality,
                    bqv: b.bqv,
                    bsv: b.bsv,
                }));
            });
            return {
                severity: Object.assign({}, this.severityInputs),
                barriers,
                bowtie: this.bowtie,
            };
        }

        async calculate() {
            if (!this.hazardId) { this._status('Hazard not loaded.', 'srm-err'); return; }
            const btn = this.el.querySelector('[data-srm-calc]');
            btn.disabled = true;
            try {
                const result = await HazardsAPI.sramCalculate(this.hazardId, this._buildCalculatePayload());
                this.riskProfile = result.risk_profile;
                this._renderComparison(result.risk_profile);
                const authority = result.risk_profile.signoff.authority;
                this.el.querySelector('[data-srm-authority]').innerHTML =
                    `<i class="fas fa-user-shield"></i> Required: ${esc(authority)}`;
                // Adopt authoritative barrier scores.
                if (result.barriers) {
                    ['ecb', 'erb', 'ncb', 'nrb'].forEach(key => {
                        if (Array.isArray(result.barriers[key])) {
                            result.barriers[key].forEach(rb => {
                                const local = this.barriers[key].find(b => b.id === rb.id);
                                if (local) { local.bsv = rb.bsv; local.bqv = rb.bqv; local.robustness = rb.robustness; }
                            });
                        }
                    });
                    this.renderBarriers();
                }
                this._status(`Calculated: ${result.risk_profile.initial_risk.index} → ${result.risk_profile.resultant_risk.index} (${result.risk_profile.resultant_risk.tolerability})`, 'srm-ok');
            } catch (err) {
                this._status('Calculate failed: ' + err.message, 'srm-err');
            } finally {
                btn.disabled = false;
            }
        }

        _buildSavePayload() {
            const severity = Object.assign({}, this.severityInputs, computeSeverity(this.severityInputs));
            const barriers = {};
            Object.keys(this.barriers).forEach(key => {
                barriers[key] = this.barriers[key].map(b => ({
                    id: b.id,
                    name: b.name,
                    description: b.description,
                    category: b.category,
                    source_root_cause_id: b.source_root_cause_id,
                    quality: b.quality,
                    bqv: b.bqv,
                    bsv: b.bsv,
                    robustness: b.robustness,
                }));
            });
            const profile = this.riskProfile || evaluateRiskProfile(severity, this.barriers);
            const authority = profile.signoff.authority;
            const signoffs = {
                name: this.signoffs.name || null,
                role: this.signoffs.role || null,
                date: this.signoffs.date || null,
                authority,
            };
            return {
                analysis_mode: this.mode,
                sram_data: {
                    severity,
                    barriers,
                    risk_profile: profile,
                    bowtie: this.bowtie,
                    fishbone: this.fishbone || null,
                    signoffs,
                },
            };
        }

        async save() {
            if (!this.hazardId) { this._status('Hazard not loaded.', 'srm-err'); return; }
            const btn = this.el.querySelector('[data-srm-save]');
            btn.disabled = true;
            try {
                const result = await HazardsAPI.sramSave(this.hazardId, this._buildSavePayload());
                this._status(`Saved: resultant risk ${result.sram_data.risk_profile.resultant_risk.index} (${result.sram_data.risk_profile.resultant_risk.tolerability})`, 'srm-ok');
                if (typeof this.onSaved === 'function') this.onSaved(result);
            } catch (err) {
                this._status('Save failed: ' + err.message, 'srm-err');
            } finally {
                btn.disabled = false;
            }
        }

        _status(msg, cls) {
            const el = this.el.querySelector('[data-srm-status]');
            if (!el) return;
            el.textContent = msg;
            el.className = 'srm-status ' + (cls || 'srm-ok');
            window.setTimeout(() => { el.className = 'srm-status'; }, 6000);
        }
    }

    // ── Combined RCA + SRAM panel (CAN/CAP page) ────────────────────────────
    function attachCombined(container, opts) {
        const el = typeof container === 'string' ? document.getElementById(container) : container;
        if (!el) throw new Error('[SRM] container not found: ' + container);
        opts = opts || {};

        const fishboneController = opts.fishboneController || null;
        const initialSeverityLetter = opts.severityLetter || null;

        const state = {
            mode: 'COMBINED',
            severityLetter: initialSeverityLetter || 'E',
            ncm: (opts.saved && opts.saved.barriers && opts.saved.barriers.ncb) || [],
            signoffs: Object.assign({ name: '', role: '', date: '' }, (opts.saved && opts.saved.signoffs) || {}),
        };

        function promoteCauses() {
            const list = el.querySelector('[data-srm-promotion-list]');
            if (!list) return;
            let causes = [];
            if (fishboneController && typeof fishboneController.getData === 'function') {
                causes = fishboneController.getData().root_causes || [];
            }
            const promotedIds = state.ncm.map(b => b.source_root_cause_id).filter(Boolean);
            if (!causes.length) {
                list.innerHTML = '<div class="srm-promoted-note">Root causes added above appear here for promotion to NCM.</div>';
                return;
            }
            list.innerHTML = causes.map(c => {
                const promoted = promotedIds.indexOf(c.id) >= 0;
                return `
                    <div class="srm-promote-row">
                        <span class="srm-promote-text"><strong>${esc(c.category)}</strong> — ${esc(c.description || '')}</span>
                        ${promoted
                            ? '<span class="srm-promoted-note"><i class="fas fa-check-circle"></i> Promoted to NCM</span>'
                            : `<button type="button" class="srm-promote-btn" data-promote="${esc(c.id)}"><i class="fas fa-arrow-up"></i> Promote to NCM</button>`}
                    </div>`;
            }).join('');
            list.querySelectorAll('[data-promote]').forEach(btn => {
                btn.addEventListener('click', () => {
                    const cause = causes.find(c => c.id === btn.dataset.promote);
                    if (!cause) return;
                    const barrier = {
                        id: uid('ncm'), name: (cause.description || '').trim() || `${cause.category} root cause`,
                        description: cause.description, category: cause.category,
                        source_root_cause_id: cause.id, quality: defaultQuality(),
                    };
                    const res = computeBqv(barrier.quality);
                    barrier.bqv = res.bqv; barrier.bsv = res.bsv; barrier.robustness = res.robustness;
                    state.ncm.push(barrier);
                    renderNcm();
                    promoteCauses();
                    update();
                });
            });
        }

        function renderNcm() {
            const list = el.querySelector('[data-srm-ncm-list]');
            if (!list) return;
            if (!state.ncm.length) {
                list.innerHTML = '<div class="srm-hint">No New Control Measures promoted yet.</div>';
                return;
            }
            list.innerHTML = state.ncm.map(b => barrierPillHtml(b, 'srm-ncb')).join('');
            bindBarrierPills(list, state.ncm, 'srm-ncb', {
                renderBarriers: renderNcm,
                updateLive: update,
            });
        }

        function update() {
            const severity = { severity_letter: state.severityLetter, descriptor: '' };
            const profile = evaluateRiskProfile(severity, { ecb: [], erb: [], ncb: state.ncm, nrb: [] });

            el.querySelector('[data-srm-initial-index]').textContent = profile.initial_risk.index;
            el.querySelector('[data-srm-initial-tol]').textContent = profile.initial_risk.tolerability;
            el.querySelector('[data-srm-resultant-index]').textContent = profile.resultant_risk.index;
            el.querySelector('[data-srm-resultant-tol]').textContent = profile.resultant_risk.tolerability;
            el.querySelector('[data-srm-resultant-bsv]').textContent = `NCM BSV ${profile.consolidated_bsv}`;
            el.querySelector('[data-srm-authority]').innerHTML =
                `<i class="fas fa-user-shield"></i> Required: ${esc(profile.signoff.authority)}`;
        }

        el.innerHTML = `
            <div class="srm-workspace">
                <div class="srm-mode-selector">
                    <span class="srm-mode-title"><i class="fas fa-arrows-left-right"></i> Analysis Model Selector</span>
                    <label data-mode="FISHBONE_ONLY"><input type="radio" name="cap_srm_mode" value="FISHBONE_ONLY"> Fish-Bone RCA</label>
                    <label data-mode="BOWTIE_SRAM"><input type="radio" name="cap_srm_mode" value="BOWTIE_SRAM"> Bow-Tie SRAM</label>
                    <label data-mode="COMBINED"><input type="radio" name="cap_srm_mode" value="COMBINED" checked> Combined RCA + SRAM</label>
                </div>

                <div class="srm-section" data-cap-part="bowtie">
                    <h3><i class="fas fa-bow-arrow"></i> Bow-Tie SRAM — New Control Measures from Root Causes</h3>
                    <div class="srm-promotion">
                        <div class="srm-promotion-head"><i class="fas fa-arrow-up"></i> Promote Fish-Bone Root Causes to New Control Measures (NCM)</div>
                        <div data-srm-promotion-list></div>
                    </div>
                    <div style="margin-top:0.7rem;">
                        <div class="srm-col-head">New Control Measures (NCM) <span style="font-weight:400;text-transform:none;">— click a pill to rate its Barrier Quality</span></div>
                        <div data-srm-ncm-list></div>
                    </div>
                </div>

                <div class="srm-section">
                    <h3><i class="fas fa-th-large"></i> Before &amp; After Risk Matrix Comparison</h3>
                    <div class="srm-risk-comparison">
                        <div class="srm-risk-box">
                            <div class="srm-risk-label">Current Risk Index</div>
                            <div class="srm-risk-index" data-srm-initial-index>—</div>
                            <div class="srm-risk-tol" data-srm-initial-tol>—</div>
                        </div>
                        <div class="srm-risk-arrow"><i class="fas fa-arrow-right"></i></div>
                        <div class="srm-risk-box">
                            <div class="srm-risk-label">Resultant Risk Index</div>
                            <div class="srm-risk-index" data-srm-resultant-index>—</div>
                            <div class="srm-risk-tol" data-srm-resultant-tol>—</div>
                            <div class="srm-bsv-summary" data-srm-resultant-bsv></div>
                        </div>
                    </div>
                    <div style="margin-top:0.6rem;font-size:0.75rem;color:#64748b;" data-cap-sev-letter>
                        Severity letter: <strong>${esc(state.severityLetter)}</strong>
                    </div>
                </div>

                <div class="srm-section">
                    <h3><i class="fas fa-file-signature"></i> Digital Postholder Sign-Off</h3>
                    <div class="srm-signoff">
                        <span class="srm-authority-badge" data-srm-authority><i class="fas fa-user-shield"></i> Required: —</span>
                        <div class="srm-signoff-grid">
                            <div><label>Postholder Name</label><input type="text" data-srm-sign-name value="${esc(state.signoffs.name || '')}"></div>
                            <div><label>Postholder Role</label><input type="text" data-srm-sign-role value="${esc(state.signoffs.role || '')}"></div>
                            <div><label>Date</label><input type="date" data-srm-sign-date value="${esc(state.signoffs.date || '')}"></div>
                        </div>
                    </div>
                </div>
            </div>`;

        // Mode selector (banner only — Combined is the CAP default).
        el.querySelectorAll('[data-mode] input').forEach(radio => {
            radio.addEventListener('change', () => {
                state.mode = radio.value;
                el.querySelectorAll('[data-mode]').forEach(l => l.classList.toggle('srm-mode-active', l.dataset.mode === state.mode));
                el.querySelector('[data-cap-part="bowtie"]').style.display = state.mode === 'FISHBONE_ONLY' ? 'none' : 'block';
            });
        });
        el.querySelector('[data-mode="COMBINED"]').classList.add('srm-mode-active');

        el.querySelector('[data-srm-sign-name]').addEventListener('input', e => { state.signoffs.name = e.target.value; });
        el.querySelector('[data-srm-sign-role]').addEventListener('input', e => { state.signoffs.role = e.target.value; });
        el.querySelector('[data-srm-sign-date]').addEventListener('change', e => { state.signoffs.date = e.target.value; });

        renderNcm();
        promoteCauses();
        update();

        function setSeverityLetter(letter) {
            if (letter && TOLERABILITY['1' + letter.toUpperCase()]) {
                state.severityLetter = letter.toUpperCase();
                const label = el.querySelector('[data-cap-sev-letter]');
                if (label) label.innerHTML = 'Severity letter: <strong>' + esc(state.severityLetter) + '</strong>';
                update();
            }
        }

        return {
            getMode: () => state.mode,
            setSeverityLetter,
            refreshPromotion: promoteCauses,
            getSramData: () => {
                if (state.mode === 'FISHBONE_ONLY') return null;
                const severity = { severity_letter: state.severityLetter, descriptor: '' };
                const profile = evaluateRiskProfile(severity, { ecb: [], erb: [], ncb: state.ncm, nrb: [] });
                return {
                    analysis_mode: state.mode,
                    severity,
                    barriers: { ecb: [], erb: [], ncb: state.ncm, nrb: [] },
                    risk_profile: profile,
                    signoffs: {
                        name: state.signoffs.name || null,
                        role: state.signoffs.role || null,
                        date: state.signoffs.date || null,
                        authority: profile.signoff.authority,
                    },
                };
            },
        };
    }

    // ── Public API ──────────────────────────────────────────────────────────
    return {
        SEVERITY_KEYS,
        SEVERITY_BANDS,
        BQV_KEYS,
        BQV_BANDS,
        PROBABILITY_CONFIG,
        TOLERABILITY,
        SIGNOFF_AUTHORITY,
        LETTER_TO_NUMERIC,
        FISHBONE_CATEGORIES,
        computeSeverity,
        computeBqv,
        computeProbability,
        evaluateRiskProfile,
        openBarrierQualityModal,
        createWorkspace: (container, opts) => new SrmWorkspace(container, opts),
        attachCombined,
    };
})();

if (typeof window !== 'undefined') {
    window.SRM = SRM;
}