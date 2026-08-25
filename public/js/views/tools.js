/* ============================================================================
   FILE: tools.js
   PATH: public/js/views/tools.js
   VERSION: 1.0.0-beta.1
   PURPOSE: aviaSDCPS Tools view controller — manages interactive Bow-Tie diagrams,
            barrier calculations, and connects to /api/v1/hazards/{id}/sram/calculate
            and /api/v1/admin/risk-matrix endpoints.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

const AviaSDCPSTools = (function () {
  'use strict';

  let activeHazardId = null;
  let selectedMatrixCode = '3C';

  /**
   * Loads hazards dropdown for Bow-Tie target context.
   */
  async function loadHazardDropdown() {
    const select = document.getElementById('toolsHazardSelector');
    if (!select) return;

    try {
      const response = await window.AviaSDCPSApi.get('/dashboard/master-register', {
        page_size: 50,
        by_type: 'hazard'
      });

      const rows = response.rows || [];
      select.innerHTML = '<option value="">Select Target Hazard Context...</option>' +
        rows.map(h => `<option value="${h.id}">[${h.id}] ${h.title || 'Untitled'}</option>`).join('');
    } catch (err) {
      console.error('[AviaSDCPSTools] Error loading hazards selector:', err);
    }
  }

  /**
   * Matrix cell selection and tolerability evaluation.
   */
  function handleMatrixSelection(cell) {
    const code = cell.getAttribute('data-code');
    if (!code) return;

    selectedMatrixCode = code;
    document.querySelectorAll('#icaoRiskMatrix td').forEach(td => td.classList.remove('selected-cell'));
    cell.classList.add('selected-cell');

    const codeDisplay = document.getElementById('selectedRiskCode');
    const badge = document.getElementById('selectedTolerabilityBadge');
    const desc = document.getElementById('tolerabilityDescription');

    if (codeDisplay) codeDisplay.textContent = code;

    if (cell.classList.contains('cell-intolerable')) {
      badge.textContent = 'Intolerable / Unacceptable';
      badge.className = 'badge badge-red';
      desc.textContent = 'Operations must cease immediately until effective risk reduction barriers are installed.';
    } else if (cell.classList.contains('cell-tolerable')) {
      badge.textContent = 'Tolerable (Review Required)';
      badge.className = 'badge badge-amber';
      desc.textContent = 'Acceptable with formal management approval and monitored mitigation controls.';
    } else {
      badge.textContent = 'Acceptable';
      badge.className = 'badge badge-green';
      desc.textContent = 'Risk is acceptable under existing baseline organizational safety controls.';
    }
  }

  /**
   * Saves Bow-Tie / SRAM calculation to backend.
   */
  async function saveSramModel() {
    if (!activeHazardId) {
      alert('Please select a target hazard before saving the assessment.');
      return;
    }

    const payload = {
      hazard_id: activeHazardId,
      top_event: document.getElementById('topEventDescription')?.value || '',
      risk_index: selectedMatrixCode,
      updated_at: new Date().toISOString()
    };

    try {
      await window.AviaSDCPSApi.put(`/hazards/${activeHazardId}/sram/save`, payload);
      alert('SRAM Bow-Tie model saved successfully.');
    } catch (err) {
      console.error('[AviaSDCPSTools] Save failed:', err);
      alert(`Save failed: ${err.message}`);
    }
  }

  /**
   * Event bindings for view switcher, dynamic barrier nodes, and matrix.
   */
  function bindEvents() {
    // Tool switcher tabs (Bow-Tie vs Matrix)
    const toggleBtns = document.querySelectorAll('#toolsViewContainer .toggle-btn');
    toggleBtns.forEach(btn => {
      btn.addEventListener('click', (e) => {
        toggleBtns.forEach(b => b.classList.remove('active'));
        e.currentTarget.classList.add('active');

        const tool = e.currentTarget.getAttribute('data-tool');
        const paneBowTie = document.getElementById('paneBowTie');
        const paneMatrix = document.getElementById('paneMatrix');

        if (tool === 'bowtie') {
          paneBowTie.style.display = 'block';
          paneMatrix.style.display = 'none';
        } else {
          paneBowTie.style.display = 'none';
          paneMatrix.style.display = 'block';
        }
      });
    });

    // Matrix cell clicks
    document.querySelectorAll('#icaoRiskMatrix td[data-code]').forEach(cell => {
      cell.addEventListener('click', () => handleMatrixSelection(cell));
    });

    // Hazard context change
    document.getElementById('toolsHazardSelector')?.addEventListener('change', (e) => {
      activeHazardId = e.target.value;
    });

    // Save button
    document.getElementById('btnSaveSramAssessment')?.addEventListener('click', saveSramModel);
  }

  return {
    init() {
      bindEvents();
      loadHazardDropdown();
    }
  };
})();

window.AviaSDCPSTools = AviaSDCPSTools;