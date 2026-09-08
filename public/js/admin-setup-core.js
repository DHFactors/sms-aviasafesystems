// ============================================================================
// FILE: public/js/admin-setup-core.js
// PATH: public/js/admin-setup-core.js
// PURPOSE: Shared JS for the modular Production Setup suite — the hub and every
//          step page under /admin/setup/. Provides the SUPER_ADMIN auth gate,
//          shared helpers (esc/toast/logout), the confirm modal used by
//          destructive actions, the tenant/regulator lifecycle modal, and the
//          CSV export helpers. Loaded AFTER /js/admin.js.
// AUTHOR: AviaSAFE Systems
// ============================================================================

var currentUser = null;
var pendingConfirm = null; // { type, body?, email?, uid?, setup_key? }
var pendingLifecycle = null; // { type, id }
var EXISTING_TENANTS = [];

function esc(v) { return AdminUI.esc(v); }
function toast(m, t) { AdminUI.toast(m, t); }

function renderAccessDenied() {
    var gate = document.createElement('div');
    gate.style.cssText = 'max-width:520px;margin:5rem auto;text-align:center;background:#fff;border-radius:12px;box-shadow:0 1px 6px rgba(0,0,0,.08);padding:3rem 2rem;';
    gate.innerHTML =
        '<i class="fas fa-lock" style="font-size:3rem;color:#dc3545;"></i>' +
        '<h2 style="color:#0f172a;margin:1rem 0 .5rem;">Access Denied</h2>' +
        '<p>This page is restricted to SUPER_ADMIN users. You are signed in as <strong>' + esc((currentUser && currentUser.email) || 'a user') + '</strong>.</p>' +
        '<button class="btn btn-primary" onclick="logout()">Sign out</button>';
    document.body.appendChild(gate);
}

function logout() {
    firebase.auth().signOut().then(function () { window.location.href = '/'; })
        .catch(function () { window.location.href = '/'; });
}

// ============================================================================
// SHARED CONFIRM MODAL — captures SETUP_SECRET inline for destructive actions
// ============================================================================

function openConfirm(title, html, action) {
    pendingConfirm = action;
    document.getElementById('confirmTitle').textContent = title;
    document.getElementById('confirmText').innerHTML = html;
    // Show setup-key field for destructive actions — prompt inside the warning modal
    var needsKey = action && (action.type === 'demo' || action.type === 'psoe' || action.type === 'stateRisk' || action.type === 'purgeUnified' || action.type === 'purgePsoeDemo' || action.type === 'purgeStateRiskDemo' || action.type === 'deleteDemoTenants' || action.type === 'deleteUser');
    var wrap = document.getElementById('confirmSetupKeyWrap');
    var input = document.getElementById('confirmSetupKey');
    var errEl = document.getElementById('confirmSetupKeyError');
    if (wrap) wrap.style.display = needsKey ? 'block' : 'none';
    if (errEl) { errEl.style.display = 'none'; errEl.textContent = ''; }
    if (input) {
        // Prefill from sessionStorage if already entered this tab
        try { input.value = AdminUI.getSetupKey() || ''; } catch (e) { input.value = ''; }
        input.style.borderColor = '#cbd5e1';
    }
    var modal = document.getElementById('confirmModal');
    if (modal) modal.style.display = 'flex';
    if (needsKey && input) setTimeout(function () { input.focus(); input.select(); }, 50);
}

function closeConfirm() {
    var modal = document.getElementById('confirmModal');
    if (modal) modal.style.display = 'none';
    var errEl = document.getElementById('confirmSetupKeyError');
    if (errEl) { errEl.style.display = 'none'; errEl.textContent = ''; }
    pendingConfirm = null;
}

// Bind modal handlers only once the DOM exists. This script is loaded in
// <head> on every /admin/setup/* step page, so direct getElementById() at
// load time would return null and the Confirm button would silently do
// nothing. See bindOnReady() below.
function bindConfirmOkBtn() {
    var confirmOkBtn = document.getElementById('confirmOkBtn');
    if (!confirmOkBtn) return;
    confirmOkBtn.addEventListener('click', function () {
        var action = pendingConfirm;
        if (!action) return;
        // For destructive actions, require setup key from the modal input
        var needsKey = action.type === 'demo' || action.type === 'psoe' || action.type === 'stateRisk' || action.type === 'purgeUnified' || action.type === 'purgePsoeDemo' || action.type === 'purgeStateRiskDemo' || action.type === 'deleteDemoTenants' || action.type === 'deleteUser';
        var setupKey = '';
        if (needsKey) {
            var input = document.getElementById('confirmSetupKey');
            var errEl = document.getElementById('confirmSetupKeyError');
            setupKey = input ? input.value.trim() : '';
            if (!setupKey) {
                if (errEl) { errEl.textContent = 'Setup key is required to authorize this destructive action.'; errEl.style.display = 'block'; }
                if (input) { input.style.borderColor = '#dc2626'; input.focus(); }
                return; // keep modal open
            }
            try { AdminUI.setSetupKey(setupKey); } catch (e) {}
            // Inject into pending body for demo/psoe/stateRisk/deleteUser
            if (action.body) action.body.setup_key = setupKey;
            if (action.type === 'deleteUser') {
                // deleteUser stores email/uid separately; also inject for exec
                action.setup_key = setupKey;
            }
            if (action.type === 'psoe' || action.type === 'stateRisk') {
                action.body.setup_key = setupKey;
            }
        }
        var modal = document.getElementById('confirmModal');
        if (modal) modal.style.display = 'none';
        pendingConfirm = null;
        if (action.type === 'demo') execDemo(action.body);
        else if (action.type === 'psoe') execPsoe(action.body);
        else if (action.type === 'stateRisk') execStateRisk(action.body);
        else if (action.type === 'purgeUnified') execPurgeUnified(action.body);
        else if (action.type === 'purgePsoeDemo') execPurgePsoeDemo(action.body);
        else if (action.type === 'purgeStateRiskDemo') execPurgeStateRiskDemo(action.body);
        else if (action.type === 'deleteDemoTenants') execDeleteDemoTenants(action.body);
        else if (action.type === 'deleteUser') execDeleteUser(action.email, action.uid, action.setup_key);
    });
}

// ============================================================================
// LIFECYCLE MANAGE MODAL — tenants & regulators
// ============================================================================

function openLifecycleModal(type, id, status, fromDate, toDate) {
    pendingLifecycle = { type: type, id: id };
    document.getElementById('lifecycleEntityType').textContent = type === 'regulator' ? 'Regulator' : 'Tenant';
    document.getElementById('lifecycleEntityLabel').innerHTML = 'ID: <code>' + esc(id) + '</code> — current: ' + esc(status || '—');
    var sel = document.getElementById('lifecycleStatus');
    if (sel) sel.value = (status || 'active').toLowerCase();
    var fromEl = document.getElementById('lifecycleFrom');
    var toEl = document.getElementById('lifecycleTo');
    if (fromEl) fromEl.value = fromDate || '';
    if (toEl) toEl.value = toDate || '';
    var keyInput = document.getElementById('lifecycleSetupKey');
    var errEl = document.getElementById('lifecycleSetupKeyError');
    if (errEl) { errEl.style.display = 'none'; errEl.textContent = ''; }
    if (keyInput) {
        try { keyInput.value = AdminUI.getSetupKey() || ''; } catch (e) { keyInput.value = ''; }
        keyInput.style.borderColor = '#cbd5e1';
    }
    var modal = document.getElementById('lifecycleModal');
    if (modal) modal.style.display = 'flex';
    if (keyInput) setTimeout(function () { keyInput.focus(); keyInput.select(); }, 50);
}

function closeLifecycleModal() {
    var modal = document.getElementById('lifecycleModal');
    if (modal) modal.style.display = 'none';
    var errEl = document.getElementById('lifecycleSetupKeyError');
    if (errEl) { errEl.style.display = 'none'; errEl.textContent = ''; }
    pendingLifecycle = null;
}

async function saveLifecycleModal() {
    if (!pendingLifecycle) return;
    var status = (document.getElementById('lifecycleStatus') || {}).value || '';
    var fromDate = (document.getElementById('lifecycleFrom') || {}).value || '';
    var toDate = (document.getElementById('lifecycleTo') || {}).value || '';
    var keyInput = document.getElementById('lifecycleSetupKey');
    var errEl = document.getElementById('lifecycleSetupKeyError');
    var setupKey = keyInput ? keyInput.value.trim() : '';
    if (!setupKey) {
        if (errEl) { errEl.textContent = 'Setup key is required.'; errEl.style.display = 'block'; }
        if (keyInput) { keyInput.style.borderColor = '#dc2626'; keyInput.focus(); }
        return;
    }
    if (fromDate && toDate && fromDate > toDate) {
        if (errEl) { errEl.textContent = 'From date must be before To date.'; errEl.style.display = 'block'; }
        toast('From date must be before To date', 'error');
        return;
    }
    try { AdminUI.setSetupKey(setupKey); } catch (e) {}
    var isReg = pendingLifecycle.type === 'regulator';
    var id = pendingLifecycle.id;
    var path = isReg
        ? '/api/v1/admin/regulators/' + encodeURIComponent(id) + '/status'
        : '/api/v1/admin/tenants/' + encodeURIComponent(id) + '/status';
    var body = { setup_key: setupKey, status: status };
    if (fromDate) { body.from_date = fromDate; body.contract_start_date = fromDate; }
    if (toDate) { body.to_date = toDate; body.contract_end_date = toDate; }
    try {
        var resp = await AdminUI.apiPost(path, body);
        toast((isReg ? 'Regulator ' : 'Tenant ') + id + ' → ' + (resp.regulator ? resp.regulator.status : resp.tenant ? resp.tenant.status : status), 'success');
        closeLifecycleModal();
        if (isReg) loadExistingRegulators(); else loadExistingTenants();
        loadAuditLog();
    } catch (err) {
        if (errEl) { errEl.textContent = err.message || String(err); errEl.style.display = 'block'; }
        toast('Save failed: ' + (err.message || String(err)), 'error');
    }
}

function bindLifecycleModal() {
    var lifecycleModalEl = document.getElementById('lifecycleModal');
    if (!lifecycleModalEl) return;
    lifecycleModalEl.addEventListener('click', function (e) {
        if (e.target === this) closeLifecycleModal();
    });
}

// ============================================================================
// READY GATE — this script is loaded in <head> on every /admin/setup/* page,
// before the modal markup exists. Attach DOM listeners only once the document
// is parsed; run immediately when the document is already ready.
// ============================================================================

function bindOnReady(fn) {
    if (typeof fn !== 'function') return;
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', fn);
    } else {
        fn();
    }
}

bindOnReady(bindConfirmOkBtn);
bindOnReady(bindLifecycleModal);

// ============================================================================
// AUDIT LOG — shared loader. Step 4 (audit-log) renders into #auditArea;
// other steps no-op safely when the element is absent.
// ============================================================================

async function loadAuditLog() {
    var area = document.getElementById('auditArea');
    if (!area) return;
    area.innerHTML = '<div class="loading"><i class="fas fa-spinner fa-spin"></i> Loading audit log...</div>';
    try {
        var resp = await AdminUI.apiGet('/api/v1/admin/seed/logs?limit=5');
        var logs = resp.logs || [];
        if (!logs.length) { area.innerHTML = '<div class="empty-state">No audit entries yet.</div>'; return; }
        var html = '<div style="overflow-x:auto;"><table class="admin-table"><thead><tr>' +
            '<th>When</th><th>Actor</th><th>Action</th><th>Target</th><th>Result</th><th>Detail</th></tr></thead><tbody>';
        logs.forEach(function (l) {
            html += '<tr><td>' + AdminUI.fmtDate(l.timestamp || l.created_at) + '</td>' +
                '<td>' + esc((l.actor && l.actor.email) || l.actor || '—') + '</td>' +
                '<td><code>' + esc(l.action) + '</code></td>' +
                '<td>' + esc(l.target || '—') + '</td>' +
                '<td>' + (l.result === 'error' ? '<span class="badge badge-danger">error</span>' : '<span class="badge badge-success">success</span>') + '</td>' +
                '<td style="max-width:340px;">' + esc(l.detail || '') + '</td></tr>';
        });
        html += '</tbody></table></div>';
        area.innerHTML = html;
    } catch (err) { area.innerHTML = '<div class="status-box error">Failed to load audit log: ' + esc(err.message) + '</div>'; }
}

// ============================================================================
// SUPER_ADMIN DATA EXPORT — CSV downloads (Bearer token via fetch + Blob).
// The endpoints are GET /api/v1/admin/export/* guarded by get_admin_user, so
// each request must carry the Firebase ID token in the Authorization header
// (plain window.location navigation would drop it).
// ============================================================================

function exportStatus(id, msgHtml, type) {
    var el = document.getElementById(id);
    if (el) el.innerHTML = '<div class="status-box ' + (type || 'info') + '">' + msgHtml + '</div>';
}

async function exportCsv(url, statusId) {
    var statusEl = document.getElementById(statusId);
    if (statusEl) statusEl.innerHTML = '<div class="loading"><i class="fas fa-spinner fa-spin"></i> Preparing export...</div>';
    try {
        var token = await ApiClient._getToken();
        if (!token) return;
        var resp = await fetch(ApiClient._baseUrl() + url, {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (resp.status === 401) { window.location.href = '/admin/login.html'; return; }
        if (!resp.ok) {
            var err = await resp.json().catch(function () { return { detail: 'HTTP ' + resp.status }; });
            var detail = err.detail || ('Request failed: ' + resp.status);
            if (Array.isArray(detail)) detail = detail.map(function (e) { return e.msg || JSON.stringify(e); }).join('; ');
            throw new Error(detail);
        }
        var disp = resp.headers.get('Content-Disposition') || '';
        var m = disp.match(/filename="?([^";]+)"?/i);
        var filename = m ? m[1] : ('export_' + Date.now() + '.csv');
        var rowCount = resp.headers.get('X-Row-Count') || '';
        var blob = await resp.blob();
        var a = document.createElement('a');
        var urlObj = URL.createObjectURL(blob);
        a.href = urlObj;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(function () { URL.revokeObjectURL(urlObj); }, 1000);
        exportStatus(statusId, 'Downloaded <strong>' + esc(filename) + '</strong>' +
            (rowCount ? ' <span style="color:#475569;">(' + esc(rowCount) + ' row(s))</span>' : '') + '.', 'success');
    } catch (err) {
        exportStatus(statusId, esc(err && err.message ? err.message : String(err)), 'error');
    }
}