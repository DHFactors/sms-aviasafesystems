// ==============================================================================
// File: public/js/views/hazard_analysis.js
// Description: Full API integration controller for public/hazards/index.html.
//              Handles HFACS 7.0 dataset lookup, ICAO 5x5 tolerability scoring,
//              CAPA registry rendering, and multi-step POST requests to FastAPI.
// ==============================================================================

const API_BASE_URL = '/api/v1/tenants/hazards';

const TOLERABILITY_MAP = {
  "5A": "intolerable", "5B": "intolerable", "5C": "intolerable", "5D": "intolerable", "5E": "intolerable",
  "4A": "intolerable", "4B": "intolerable", "4C": "intolerable", "4D": "tolerable",   "4E": "tolerable",
  "3A": "intolerable", "3B": "intolerable", "3C": "tolerable",   "3D": "tolerable",   "3E": "acceptable",
  "2A": "tolerable",   "2B": "tolerable",   "2C": "tolerable",   "2D": "acceptable",  "2E": "acceptable",
  "1A": "tolerable",   "1B": "acceptable",  "1C": "acceptable",  "1D": "acceptable",  "1E": "acceptable"
};

const SEVERITY_DESCRIPTIONS = {
  "5": "Catastrophic — Aircraft destroyed, multiple fatalities.",
  "4": "Hazardous — Large reduction in safety margins, serious injury.",
  "3": "Major — Significant reduction in safety margins, injury.",
  "2": "Minor — Nuisance, operating limitations, minor incident.",
  "1": "Negligible — Little operational consequence."
};

const PROBABILITY_DESCRIPTIONS = {
  "A": "Frequent — Likely to occur many times.",
  "B": "Occasional — Likely to occur sometimes.",
  "C": "Remote — Unlikely, but possible to occur.",
  "D": "Improbable — Very unlikely to occur.",
  "E": "Extremely Improbable — Almost inconceivable that the event will occur."
};

const DEPT_LABELS = {
  "flight_operations": "Flight Ops",
  "maintenance_145": "Part-145",
  "camo": "CAMO",
  "safety": "Safety Dept",
  "ground_ops": "Ground Ops"
};

let nanocodesData = [];
let currentCapas = [];
let activeSavedHazardId = null;

function getTenantId() {
  return localStorage.getItem('active_tenant_id') || 'fishtail-air';
}

function getAuthHeaders() {
  const headers = {
    'Content-Type': 'application/json',
    'X-Tenant-Id': getTenantId()
  };
  const token = localStorage.getItem('auth_token');
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

// -----------------------------------------------------------------------------
// Dataset and UI Population
// -----------------------------------------------------------------------------
async function loadNanocodes() {
  try {
    const res = await fetch('/data/hfacs_nanocodes.json');
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to load HFACS catalog`);
    const raw = await res.text();
    nanocodesData = JSON.parse(
      raw.split('\n').filter((l) => !l.trim().startsWith('//')).join('\n')
    );
    populateNanocodes();
  } catch (err) {
    console.error('Failed to load HFACS dataset:', err);
  }
}

function populateNanocodes() {
  const filterCat = document.getElementById('hfacsCatFilter')?.value || 'ALL';
  const select = document.getElementById('nanocodeDropdown');
  if (!select) return;
  select.innerHTML = '';

  const filtered = filterCat === 'ALL'
    ? nanocodesData
    : nanocodesData.filter(item => item.cat === filterCat);

  filtered.forEach(item => {
    const opt = document.createElement('option');
    opt.value = item.code;
    opt.textContent = `${item.code} — ${item.def} (${item.sub})`;
    opt.dataset.def = item.def;
    opt.dataset.sub = item.sub;
    opt.dataset.cat = item.cat;
    select.appendChild(opt);
  });
}

function updateRiskDisplay() {
  const sevEl = document.getElementById('severitySelect');
  const probEl = document.getElementById('probabilitySelect');
  const displayEl = document.getElementById('riskTolerabilityDisplay');
  if (!sevEl || !probEl || !displayEl) return;

  const sev = sevEl.value;
  const prob = probEl.value;
  const index = `${sev}${prob}`;
  const tolerability = TOLERABILITY_MAP[index] || "tolerable";

  displayEl.textContent = `${index} — ${tolerability.toUpperCase()}`;

  if (tolerability === "intolerable") displayEl.style.color = "#d9634f";
  else if (tolerability === "tolerable") displayEl.style.color = "#e8a33d";
  else displayEl.style.color = "#7fbf6a";
}

// -----------------------------------------------------------------------------
// CAPA Management
// -----------------------------------------------------------------------------
function getStatusBadge(status) {
  switch (status) {
    case "pending_implementation":
      return '<span class="status-badge status-pending">Pending</span>';
    case "implemented":
      return '<span class="status-badge status-implemented">Implemented</span>';
    case "verified_effective":
      return '<span class="status-badge status-verified">Verified</span>';
    default:
      return `<span class="status-badge status-draft">${escapeHtml(status)}</span>`;
  }
}

function renderCapaTable() {
  const tbody = document.getElementById('capaTableBody');
  if (!tbody) return;
  tbody.innerHTML = '';

  if (currentCapas.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:var(--muted); padding:20px;">No CAPAs registered for this hazard.</td></tr>';
    return;
  }

  currentCapas.forEach((capa, idx) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="code-tag">${escapeHtml(capa.id || `TEMP-${idx + 1}`)}</td>
      <td>
        <strong>${escapeHtml(capa.title)}</strong><br>
        <span style="color: var(--muted); font-size: 11px;">${escapeHtml(capa.details || '')}</span>
      </td>
      <td><span class="code-tag">${escapeHtml(capitalize(capa.action_type))}</span></td>
      <td>${escapeHtml(DEPT_LABELS[capa.responsible_department] || capa.responsible_department)}</td>
      <td><span class="code-tag">${escapeHtml(capa.linked_rca_nanocodes?.[0] || capa.nanocode || 'N/A')}</span></td>
      <td>${escapeHtml(capa.due_date ? capa.due_date.slice(0, 10) : '')}</td>
      <td>${getStatusBadge(capa.status)}</td>
      <td style="text-align: right;">
        <button class="btn" style="padding: 4px 8px; font-size: 11px;" onclick="cycleCapaStatus(${idx})">
          ${capa.status === 'verified_effective' ? 'Reopen' : 'Verify'}
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function handleAddCapa() {
  const titleInput = document.getElementById('capaTitle');
  const typeSelect = document.getElementById('capaType');
  const deptSelect = document.getElementById('capaDept');
  const dueInput = document.getElementById('capaDueDate');
  const nanocodeSelect = document.getElementById('nanocodeDropdown');

  const title = titleInput?.value.trim();
  if (!title) {
    alert('Please provide a CAPA title or mitigation description.');
    return;
  }

  const selectedNanocode = nanocodeSelect?.value || 'PE101';
  const dueVal = dueInput?.value || new Date().toISOString().slice(0, 10);

  const newCapa = {
    id: `CAPA-${new Date().toISOString().slice(5, 7)}${new Date().toISOString().slice(8, 10)}-${String(currentCapas.length + 1).padStart(2, '0')}`,
    title: title,
    details: document.getElementById('rcaFactorNarrative')?.value.trim() || "Mitigation established via Root Cause Analysis.",
    action_type: typeSelect?.value || 'corrective',
    responsible_department: deptSelect?.value || 'flight_operations',
    assignee_email: document.getElementById('assignedOwner')?.value.trim() || `safety@${getTenantId()}.com.np`,
    linked_rca_nanocodes: [selectedNanocode],
    nanocode: selectedNanocode,
    due_date: new Date(dueVal).toISOString(),
    status: 'pending_implementation'
  };

  currentCapas.unshift(newCapa);
  if (titleInput) titleInput.value = '';
  renderCapaTable();
}

function cycleCapaStatus(index) {
  const capa = currentCapas[index];
  if (!capa) return;

  if (capa.status === 'pending_implementation') {
    capa.status = 'implemented';
  } else if (capa.status === 'implemented') {
    capa.status = 'verified_effective';
  } else {
    capa.status = 'pending_implementation';
  }

  renderCapaTable();
}

// -----------------------------------------------------------------------------
// Multi-Step POST Pipeline: Hazard -> RCA Factor -> Assessment -> CAPAs
// -----------------------------------------------------------------------------
async function handleSaveHazard() {
  const saveBtn = document.getElementById('saveHazardBtn');
  const title = document.getElementById('hazardTitle')?.value.trim();
  const description = document.getElementById('hazardDescription')?.value.trim();
  const functionalArea = document.getElementById('functionalArea')?.value;
  const assignedOwner = document.getElementById('assignedOwner')?.value.trim();
  const severity = parseInt(document.getElementById('severitySelect')?.value || '4', 10);
  const probability = document.getElementById('probabilitySelect')?.value || 'D';
  const rcaNarrative = document.getElementById('rcaFactorNarrative')?.value.trim();
  
  const nanocodeSelect = document.getElementById('nanocodeDropdown');
  const selectedOption = nanocodeSelect?.options[nanocodeSelect.selectedIndex];
  const nanocode = selectedOption?.value || 'PE101';
  const nanocodeDef = selectedOption?.dataset.def || 'Environmental Conditions Affecting Vision';
  const nanocodeSub = selectedOption?.dataset.sub || 'Physical Environment';
  const nanocodeCat = selectedOption?.dataset.cat || 'PRECOND';

  if (!title || title.length < 5) {
    alert('Please enter a valid Hazard Title (minimum 5 characters).');
    return;
  }
  if (!description || description.length < 15) {
    alert('Please enter a detailed Hazard Context & Narrative (minimum 15 characters).');
    return;
  }
  if (!rcaNarrative || rcaNarrative.length < 5) {
    alert('Please detail the RCA Causal Factor Narrative.');
    return;
  }

  try {
    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving Hazard & Scoring...';

    // Step 1: POST Root Hazard Document
    const hazardPayload = {
      title: title,
      description: description,
      source_type: "occurrence",
      source_reference_id: null,
      functional_area: functionalArea,
      assigned_owner_email: assignedOwner || `safety@${getTenantId()}.com.np`,
      target_completion_date: null
    };

    const hazardRes = await fetch(API_BASE_URL, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(hazardPayload)
    });

    if (!hazardRes.ok) {
      const err = await hazardRes.json();
      throw new Error(err.detail || `Failed to create hazard (HTTP ${hazardRes.status})`);
    }

    const hazardData = await hazardRes.json();
    const hazardId = hazardData.hazard_id;
    activeSavedHazardId = hazardId;

    // Step 2: POST DoD HFACS 7.0 RCA Nanocode Factor
    const tierMap = { "ACT": 1, "PRECOND": 2, "SUPER": 3, "ORG": 4 };
    const rcaPayload = {
      tier: tierMap[nanocodeCat] || 2,
      category: nanocodeCat,
      subcategory: nanocodeSub,
      nanocode: nanocode,
      definition: nanocodeDef,
      contributing_narrative: rcaNarrative,
      order_sequence: 1
    };

    await fetch(`${API_BASE_URL}/${hazardId}/rca`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(rcaPayload)
    });

    // Step 3: POST ICAO 5x5 Initial Risk Assessment
    const assessmentPayload = {
      assessment_type: "initial",
      severity_score: severity,
      severity_justification: SEVERITY_DESCRIPTIONS[String(severity)] || "Evaluated operational risk margin.",
      probability_score: probability,
      probability_justification: PROBABILITY_DESCRIPTIONS[probability] || "Calculated exposure frequency.",
      matrix_version: "ICAO_5X5_STANDARD"
    };

    await fetch(`${API_BASE_URL}/${hazardId}/assessments`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(assessmentPayload)
    });

    // Step 4: POST Registered CAPAs
    for (const capa of currentCapas) {
      const capaPayload = {
        linked_rca_nanocodes: capa.linked_rca_nanocodes || [nanocode],
        action_type: capa.action_type,
        title: capa.title,
        details: capa.details,
        responsible_department: capa.responsible_department,
        assignee_email: capa.assignee_email || assignedOwner || `safety@${getTenantId()}.com.np`,
        due_date: capa.due_date
      };

      await fetch(`${API_BASE_URL}/${hazardId}/capas`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(capaPayload)
      });
    }

    alert(`✓ Hazard ${hazardId} and all associated RCA factors & CAPAs persisted successfully.`);
    saveBtn.textContent = '✓ Saved Successfully';
    setTimeout(() => {
      saveBtn.disabled = false;
      saveBtn.textContent = 'Save Hazard & RCA Factors';
    }, 3000);

  } catch (error) {
    console.error('Error in save hazard pipeline:', error);
    alert(`❌ Save Failed: ${error.message}`);
    saveBtn.disabled = false;
    saveBtn.textContent = 'Save Hazard & RCA Factors';
  }
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function capitalize(str) {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
}

window.cycleCapaStatus = cycleCapaStatus;

document.addEventListener('DOMContentLoaded', () => {
  loadNanocodes();
  document.getElementById('hfacsCatFilter')?.addEventListener('change', populateNanocodes);
  document.getElementById('severitySelect')?.addEventListener('change', updateRiskDisplay);
  document.getElementById('probabilitySelect')?.addEventListener('change', updateRiskDisplay);
  document.getElementById('addCapaBtn')?.addEventListener('click', handleAddCapa);
  document.getElementById('saveHazardBtn')?.addEventListener('click', handleSaveHazard);

  updateRiskDisplay();
  renderCapaTable();
});