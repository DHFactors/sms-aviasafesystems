/**
 * @module AviaSAFE aviaSDCPS
 * @file public/js/views/sdc.js
 * @version 1.0.0-beta.1 (2026-08-25)
 * @target sms-db / consolidated platform
 *
 * SDC Ingestion controller — drag-and-drop file upload, CSV/Excel/E5X/JSON
 * parsing, ICAO ADREP 2000 schema mapping, validation via /sdc/validate,
 * staging table rendering, and batch commit via /sdc/ingest.
 */

const AviaSDCPSSdc = (function () {
  'use strict';

  let currentFile = null;
  let parsedHeaders = [];
  let parsedRows = [];
  let mappingResults = [];
  let validatedBatchId = null;

  const ACCEPTED = ['.csv', '.xlsx', '.xls', '.e5x', '.xml', '.json'];
  const ACCEPT_MIME = [
    'text/csv',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-excel',
    'application/json',
    'text/xml',
    'application/xml'
  ];

  // ── Helpers ────────────────────────────────────────────────────────────────

  function el(id) { return document.getElementById(id); }

  function showFileInfo(file) {
    const info = el('sdcFileInfo');
    if (!info || !file) return;
    const sizeKB = (file.size / 1024).toFixed(1);
    info.innerHTML = `
      <div class="sdc-file-badge">
        <i class="fa-solid fa-file"></i>
        <span>${file.name}</span>
        <span class="text-muted">${sizeKB} KB</span>
        <button class="sdc-remove-file" id="sdcRemoveFile"><i class="fa-solid fa-xmark"></i></button>
      </div>`;
    el('sdcRemoveFile')?.addEventListener('click', resetUpload);
  }

  function resetUpload() {
    currentFile = null;
    parsedHeaders = [];
    parsedRows = [];
    mappingResults = [];
    validatedBatchId = null;
    el('sdcFileInfo').innerHTML = '';
    el('sdcMappingPanel').style.display = 'none';
    el('sdcStagingConsole').style.display = 'none';
  }

  function isAccepted(file) {
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    return ACCEPTED.includes(ext) || ACCEPT_MIME.includes(file.type);
  }

  // ── CSV Parser ─────────────────────────────────────────────────────────────

  function parseCSV(text) {
    const lines = text.trim().split('\n');
    if (lines.length === 0) return { headers: [], rows: [] };
    const headers = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''));
    const rows = lines.slice(1).map(line => {
      const vals = line.split(',').map(v => v.trim().replace(/^"|"$/g, ''));
      const obj = {};
      headers.forEach((h, i) => { obj[h] = vals[i] || ''; });
      return obj;
    });
    return { headers, rows };
  }

  // ── JSON Parser ────────────────────────────────────────────────────────────

  function parseJSON(text) {
    const raw = JSON.parse(text);
    const arr = Array.isArray(raw) ? raw : (raw.data || raw.records || [raw]);
    if (arr.length === 0) return { headers: [], rows: [] };
    const headers = [...new Set(arr.flatMap(Object.keys))];
    const rows = arr.map(item => {
      const obj = {};
      headers.forEach(h => { obj[h] = item[h] ?? ''; });
      return obj;
    });
    return { headers, rows };
  }

  // ── File Reader ────────────────────────────────────────────────────────────

  async function readFile(file) {
    if (!isAccepted(file)) {
      alert(`Unsupported file type: ${file.name}\nAccepted: ${ACCEPTED.join(', ')}`);
      return;
    }
    currentFile = file;
    showFileInfo(file);

    try {
      const ext = file.name.split('.').pop().toLowerCase();

      if (ext === 'csv') {
        const text = await file.text();
        const result = parseCSV(text);
        parsedHeaders = result.headers;
        parsedRows = result.rows;
      } else if (ext === 'json') {
        const text = await file.text();
        const result = parseJSON(text);
        parsedHeaders = result.headers;
        parsedRows = result.rows;
      } else if (ext === 'xml' || ext === 'e5x') {
        // E5X/XML requires server-side parsing — mark as pending
        parsedHeaders = ['occurrenceDate', 'occurrenceType', 'narrative', 'location', 'severity', 'probability'];
        parsedRows = [];
        showStagingBadges(0, 0, 1);
      } else {
        // xlsx / xls requires server-side parsing
        parsedHeaders = ['Sheet1 — columns detected after upload'];
        parsedRows = [];
        showStagingBadges(0, 0, 1);
      }

      renderMappingPanel();
      el('sdcMappingPanel').style.display = 'block';
      el('sdcStagingConsole').style.display = 'block';
    } catch (err) {
      console.error('[AviaSDCPSSdc] File parse error:', err);
      alert('Failed to parse file: ' + err.message);
    }
  }

  // ── ADREP 2000 Field List ──────────────────────────────────────────────────

  const ADREP_FIELDS = [
    '', 'occurrenceDate', 'occurrenceType', 'narrative', 'location',
    'latitude', 'longitude', 'aircraftReg', 'aircraftType', 'operator',
    'flightPhase', 'severity', 'probability', 'injuries', 'damage',
    'taxonomy', 'humanFactors', 'flightNumber', 'departureAirport',
    'destinationAirport', 'crewCount', 'passengerCount'
  ];

  // ── Mapping Panel ──────────────────────────────────────────────────────────

  function renderMappingPanel() {
    const tbody = el('sdcMappingBody');
    if (!tbody) return;

    if (parsedHeaders.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" class="text-muted" style="text-align:center;padding:1rem;">No columns detected.</td></tr>';
      return;
    }

    tbody.innerHTML = parsedHeaders.map((header, idx) => {
      const sample = parsedRows.length > 0
        ? String(Object.values(parsedRows[0])[idx] || '').substring(0, 40)
        : '—';
      return `
        <tr>
          <td><strong>${header}</strong></td>
          <td class="text-muted">${sample}</td>
          <td>
            <select class="aviasdcps-select sdc-map-select" data-col="${idx}">
              ${ADREP_FIELDS.map(f =>
                `<option value="${f}" ${f.toLowerCase() === header.toLowerCase() ? 'selected' : ''}>${f || '— skip —'}</option>`
              ).join('')}
            </select>
          </td>
          <td><span class="sdc-map-status" data-col="${idx}"></span></td>
        </tr>`;
    }).join('');

    mappingResults = parsedHeaders.map((h, i) => ({ source: h, target: '', index: i }));
    updateMappingStatuses();
  }

  function updateMappingStatuses() {
    document.querySelectorAll('.sdc-map-select').forEach(sel => {
      const idx = parseInt(sel.getAttribute('data-col'), 10);
      const val = sel.value;
      const statusEl = document.querySelector(`.sdc-map-status[data-col="${idx}"]`);
      if (!statusEl) return;
      statusEl.innerHTML = val
        ? '<span class="badge badge-green">Mapped</span>'
        : '<span class="badge badge-muted">Skipped</span>';
      mappingResults[idx].target = val;
    });
  }

  function autoMap() {
    parsedHeaders.forEach((header, idx) => {
      const norm = header.toLowerCase().replace(/[^a-z]/g, '');
      const match = ADREP_FIELDS.find(f => f && f.toLowerCase().replace(/[^a-z]/g, '') === norm);
      const sel = document.querySelector(`.sdc-map-select[data-col="${idx}"]`);
      if (sel && match) sel.value = match;
    });
    updateMappingStatuses();
  }

  // ── Staging Table ──────────────────────────────────────────────────────────

  function renderStagingTable() {
    const tbody = el('sdcStagingBody');
    if (!tbody) return;

    if (parsedRows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="text-muted" style="text-align:center;padding:1.5rem;">No records staged.</td></tr>';
      return;
    }

    const mappedFields = mappingResults.filter(m => m.target);

    tbody.innerHTML = parsedRows.slice(0, 50).map((row, idx) => {
      const dateVal = getFieldVal(row, mappedFields, 'occurrenceDate') || '—';
      const typeVal = getFieldVal(row, mappedFields, 'occurrenceType') || '—';
      const locVal  = getFieldVal(row, mappedFields, 'location') || '—';
      const sevVal  = getFieldVal(row, mappedFields, 'severity') || '—';

      return `
        <tr>
          <td>${idx + 1}</td>
          <td>${dateVal}</td>
          <td>${typeVal}</td>
          <td>${locVal}</td>
          <td>${sevVal}</td>
          <td><span class="badge badge-muted">Pending</span></td>
        </tr>`;
    }).join('');

    if (parsedRows.length > 50) {
      tbody.innerHTML += `<tr><td colspan="6" class="text-muted" style="text-align:center;">… and ${parsedRows.length - 50} more rows</td></tr>`;
    }

    const totalParsed = parsedRows.length;
    const totalWarnings = countWarnings();
    const totalErrors = countErrors();
    showStagingBadges(totalParsed, totalWarnings, totalErrors);
    el('btnValidateBatch').disabled = totalParsed === 0;
  }

  function getFieldVal(row, mappedFields, targetName) {
    const mapping = mappedFields.find(m => m.target === targetName);
    return mapping ? row[mapping.source] : '';
  }

  function countWarnings() {
    const mapped = mappingResults.filter(m => m.target);
    if (mapped.length === 0 && parsedRows.length > 0) return 1;
    if (parsedRows.length > 1000) return 1;
    return 0;
  }

  function countErrors() {
    if (parsedRows.length === 0 && currentFile) return 1;
    return 0;
  }

  function showStagingBadges(parsed, warnings, errors) {
    const bParsed = el('sdcBadgeParsed');
    const bWarn   = el('sdcBadgeWarnings');
    const bErr    = el('sdcBadgeErrors');
    if (bParsed) { bParsed.textContent = `Parsed: ${parsed}`; bParsed.style.display = 'inline'; }
    if (bWarn)   { bWarn.textContent   = `Warnings: ${warnings}`; bWarn.style.display = warnings > 0 ? 'inline' : 'none'; }
    if (bErr)    { bErr.textContent    = `Errors: ${errors}`; bErr.style.display = errors > 0 ? 'inline' : 'none'; }
  }

  // ── Validate Batch → POST /sdc/validate ────────────────────────────────────

  async function validateBatch() {
    const btn = el('btnValidateBatch');
    if (!btn) return;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Validating…';

    try {
      const payload = {
        file_name: currentFile?.name || 'unknown',
        target_schema: el('sdcTargetSchema')?.value || 'adrep',
        mappings: mappingResults.filter(m => m.target),
        rows: parsedRows
      };

      const result = await AviaSDCPSApi.post('/sdc/validate', payload);

      validatedBatchId = result.batch_id || result.id || null;
      const errs  = result.errors  || [];
      const warns = result.warnings || [];

      showStagingBadges(parsedRows.length, warns.length, errs.length);
      el('btnCommitBatch').disabled = errs.length > 0;

      // Update staging table status badges
      document.querySelectorAll('#sdcStagingBody .badge').forEach((badge, i) => {
        if (errs.find(e => e.row === i)) {
          badge.className = 'badge badge-red';
          badge.textContent = 'Error';
        } else if (warns.find(w => w.row === i)) {
          badge.className = 'badge badge-amber';
          badge.textContent = 'Warning';
        } else {
          badge.className = 'badge badge-green';
          badge.textContent = 'Valid';
        }
      });
    } catch (err) {
      console.error('[AviaSDCPSSdc] Validate failed:', err);
      showStagingBadges(parsedRows.length, 0, parsedRows.length);
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-play"></i> Validate Batch';
    }
  }

  // ── Commit Batch → POST /sdc/ingest ───────────────────────────────────────

  async function commitBatch() {
    const btn = el('btnCommitBatch');
    if (!btn) return;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Committing…';

    try {
      const payload = {
        batch_id: validatedBatchId,
        file_name: currentFile?.name || 'unknown',
        target_schema: el('sdcTargetSchema')?.value || 'adrep',
        mappings: mappingResults.filter(m => m.target),
        row_count: parsedRows.length
      };

      const result = await AviaSDCPSApi.post('/sdc/ingest', payload);

      btn.innerHTML = '<i class="fa-solid fa-circle-check"></i> Committed';
      btn.classList.add('committed');

      document.querySelectorAll('#sdcStagingBody .badge').forEach(badge => {
        badge.className = 'badge badge-green';
        badge.textContent = 'Committed';
      });
    } catch (err) {
      console.error('[AviaSDCPSSdc] Commit failed:', err);
      btn.innerHTML = '<i class="fa-solid fa-circle-exclamation"></i> Failed';
      btn.disabled = false;
    }
  }

  // ── Event Bindings ─────────────────────────────────────────────────────────

  function bindEvents() {
    const zone = el('sdcDropzone');
    const fileInput = el('sdcFileInput');

    if (zone) {
      zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('dragover'); });
      zone.addEventListener('dragleave', () => { zone.classList.remove('dragover'); });
      zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) readFile(e.dataTransfer.files[0]);
      });
    }

    fileInput?.addEventListener('change', (e) => {
      if (e.target.files.length > 0) readFile(e.target.files[0]);
    });

    // Mapping events (rebind after render)
    const observer = new MutationObserver(() => {
      document.querySelectorAll('.sdc-map-select').forEach(sel => {
        if (!sel.dataset.bound) {
          sel.addEventListener('change', updateMappingStatuses);
          sel.dataset.bound = '1';
        }
      });
    });
    observer.observe(el('sdcMappingBody') || document.body, { childList: true, subtree: true });

    el('sdcAutoMap')?.addEventListener('click', autoMap);
    el('sdcClearMapping')?.addEventListener('click', () => {
      document.querySelectorAll('.sdc-map-select').forEach(sel => { sel.value = ''; });
      updateMappingStatuses();
    });

    el('btnValidateBatch')?.addEventListener('click', validateBatch);
    el('btnCommitBatch')?.addEventListener('click', commitBatch);
  }

  return {
    init() {
      currentFile = null;
      parsedHeaders = [];
      parsedRows = [];
      mappingResults = [];
      validatedBatchId = null;
      bindEvents();
    }
  };
})();

window.AviaSDCPSSdc = AviaSDCPSSdc;
