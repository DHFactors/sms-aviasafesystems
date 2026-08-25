/* ============================================================================
   FILE: taxonomy.js
   PATH: public/js/views/taxonomy.js
   VERSION: 1.0.0-beta.1
   PURPOSE: aviaSDCPS Taxonomy view controller — manages ICAO ADREP 2000 tree
            rendering, connects to /api/v1/taxonomy/tree and /api/v1/taxonomy/update,
            and handles custom regulatory mappings.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

const AviaSDCPSTaxonomy = (function () {
  'use strict';

  let taxonomyData = [];
  let selectedNode = null;

  /**
   * Fetches the taxonomy hierarchy tree dataset.
   */
  async function loadTaxonomyTree() {
    const container = document.getElementById('taxonomyTreeList');
    if (!container) return;

    try {
      container.innerHTML = '<div class="tree-loading text-muted"><i class="fa-solid fa-spinner fa-spin"></i> Loading taxonomy structure...</div>';

      const scheme = document.getElementById('taxonomySchemeFilter')?.value || 'ICAO_ADREP';
      const response = await window.AviaSDCPSApi.get('/taxonomy/tree', { scheme });

      taxonomyData = response.nodes || response.tree || [
        {
          code: 'ADREP-OPS',
          name: 'Operational Events',
          children: [
            { code: 'LOC-I', name: 'Loss of Control — In-Flight', description: 'In-flight loss of control of the aircraft by flight crew.', level: 'Critical', mapped_hrc: 'LOC-I' },
            { code: 'CFIT', name: 'Controlled Flight Into Terrain', description: 'In-flight collision with terrain, water, or obstacle without prior awareness.', level: 'Critical', mapped_hrc: 'CFIT' },
            { code: 'ARC', name: 'Abnormal Runway Contact', description: 'Hard landing, tail strike, or off-center touchdown events.', level: 'Major', mapped_hrc: 'RS' }
          ]
        },
        {
          code: 'ADREP-SYS',
          name: 'System / Component Malfunction',
          children: [
            { code: 'SCF-PP', name: 'Powerplant Malfunction', description: 'Engine failure, gearbox overheating, or propeller/rotor governing defects.', level: 'Major', mapped_hrc: 'TECH' },
            { code: 'SCF-NP', name: 'Non-Powerplant System Failure', description: 'Hydraulics, electrical, or avionics failures.', level: 'Minor', mapped_hrc: 'TECH' }
          ]
        },
        {
          code: 'ADREP-ENV',
          name: 'Environmental / Meteorological',
          children: [
            { code: 'TURB', name: 'Turbulence Encounter', description: 'Mountain wave or clear air turbulence encounters in flight.', level: 'Minor', mapped_hrc: 'WX' },
            { code: 'WSTRW', name: 'Windshear / Microburst', description: 'Severe convective or localized terrain windshear events.', level: 'Major', mapped_hrc: 'WX' }
          ]
        }
      ];

      renderTree(taxonomyData);
    } catch (err) {
      console.error('[AviaSDCPSTaxonomy] Error loading taxonomy tree:', err);
      container.innerHTML = `<div class="p-3 text-danger"><i class="fa-solid fa-circle-exclamation"></i> Error: ${err.message}</div>`;
    }
  }

  /**
   * Generates DOM nodes for the taxonomy hierarchy tree.
   */
  function renderTree(nodes) {
    const container = document.getElementById('taxonomyTreeList');
    if (!container) return;

    if (!nodes || nodes.length === 0) {
      container.innerHTML = '<div class="p-3 text-muted">No taxonomy nodes found.</div>';
      return;
    }

    container.innerHTML = nodes.map(group => `
      <div class="tree-group">
        <div class="tree-group-header">
          <i class="fa-solid fa-folder-open"></i>
          <span>${group.name}</span>
          <small class="text-muted">(${group.code})</small>
        </div>
        <div class="tree-children">
          ${(group.children || []).map(child => `
            <div class="tree-node-item" data-code="${child.code}">
              <i class="fa-solid fa-tag"></i>
              <span><strong>${child.code}</strong> — ${child.name}</span>
            </div>
          `).join('')}
        </div>
      </div>
    `).join('');

    container.querySelectorAll('.tree-node-item').forEach(item => {
      item.addEventListener('click', (e) => {
        const code = e.currentTarget.getAttribute('data-code');
        selectNode(code);
      });
    });
  }

  /**
   * Loads selected node into the editor panel.
   */
  function selectNode(code) {
    document.querySelectorAll('.tree-node-item').forEach(el => {
      el.classList.toggle('active-node', el.getAttribute('data-code') === code);
    });

    let found = null;
    taxonomyData.forEach(group => {
      const match = (group.children || []).find(c => c.code === code);
      if (match) found = match;
    });

    if (!found) return;
    selectedNode = found;

    document.getElementById('selectedNodeBreadcrumb').textContent = `ADREP / ${found.code}`;
    document.getElementById('btnSaveTaxonomyDetail')?.removeAttribute('disabled');

    const editorBody = document.getElementById('taxonomyEditorBody');
    if (!editorBody) return;

    editorBody.innerHTML = `
      <div class="form-group">
        <label>Taxonomy Code (Unique Identifier)</label>
        <input type="text" class="node-input" value="${found.code}" readonly />
      </div>
      <div class="form-group">
        <label>Category Full Name</label>
        <input type="text" id="editNodeName" class="node-input" value="${found.name}" />
      </div>
      <div class="form-group">
        <label>ADREP Standard Definition</label>
        <textarea id="editNodeDesc" class="center-textarea" style="text-align: left; min-height: 90px;">${found.description || ''}</textarea>
      </div>
      <div class="form-group">
        <label>Mapped High Risk Category (HRC)</label>
        <input type="text" id="editNodeHrc" class="node-input" value="${found.mapped_hrc || 'None'}" />
      </div>
      <div class="form-group">
        <label>Inherent Severity Rating</label>
        <select id="editNodeLevel" class="aviasdcps-select">
          <option value="Critical" ${found.level === 'Critical' ? 'selected' : ''}>Critical (Level A)</option>
          <option value="Major" ${found.level === 'Major' ? 'selected' : ''}>Major (Level B/C)</option>
          <option value="Minor" ${found.level === 'Minor' ? 'selected' : ''}>Minor (Level D/E)</option>
        </select>
      </div>
    `;
  }

  /**
   * Saves updated node metadata to backend.
   */
  async function saveNodeDetail() {
    if (!selectedNode) return;

    const payload = {
      code: selectedNode.code,
      name: document.getElementById('editNodeName')?.value,
      description: document.getElementById('editNodeDesc')?.value,
      mapped_hrc: document.getElementById('editNodeHrc')?.value,
      level: document.getElementById('editNodeLevel')?.value
    };

    try {
      await window.AviaSDCPSApi.put(`/taxonomy/node/${selectedNode.code}`, payload);
      alert(`Taxonomy node [${selectedNode.code}] updated successfully.`);
      loadTaxonomyTree();
    } catch (err) {
      console.error('[AviaSDCPSTaxonomy] Update failed:', err);
      alert(`Save error: ${err.message}`);
    }
  }

  /**
   * Event listeners for search, scheme switcher, and action buttons.
   */
  function bindEvents() {
    document.getElementById('taxonomySchemeFilter')?.addEventListener('change', loadTaxonomyTree);
    document.getElementById('btnSaveTaxonomyDetail')?.addEventListener('click', saveNodeDetail);

    document.getElementById('taxonomySearchInput')?.addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase();
      const filtered = taxonomyData.map(group => ({
        ...group,
        children: (group.children || []).filter(c =>
          c.code.toLowerCase().includes(q) ||
          c.name.toLowerCase().includes(q) ||
          (c.description && c.description.toLowerCase().includes(q))
        )
      })).filter(group => group.children.length > 0);

      renderTree(filtered);
    });

    document.getElementById('btnAddTaxonomyNode')?.addEventListener('click', () => {
      alert('Open New ADREP Taxonomy Node Modal...');
    });

    document.getElementById('btnExportTaxonomyJson')?.addEventListener('click', () => {
      const blob = new Blob([JSON.stringify(taxonomyData, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `adrep-taxonomy-${new Date().toISOString().split('T')[0]}.json`;
      a.click();
      URL.revokeObjectURL(url);
    });
  }

  return {
    init() {
      bindEvents();
      loadTaxonomyTree();
    }
  };
})();

window.AviaSDCPSTaxonomy = AviaSDCPSTaxonomy;