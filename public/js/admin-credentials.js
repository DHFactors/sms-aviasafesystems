/* ============================================================================
   FILE: admin-credentials.js
   PATH: public/js/admin-credentials.js
   PURPOSE: Tenant wizard logic — 5-step onboarding that creates an operator
            tenant only (no Auth users). Single-path user provisioning policy:
            users are always created one at a time after the tenant exists via
            Production Setup Step 3 (POST /api/v1/admin/users). No email
            availability checks and no generated passwords here.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

(function (global) {
    'use strict';

    var STEPS = [
        { id: 1, label: 'Tenant Info' },
        { id: 2, label: 'Contact' },
        { id: 3, label: 'Contract' },
        { id: 4, label: 'Review' },
        { id: 5, label: 'Done' },
    ];

    var currentUser = null;
    var currentStep = 1;
    var lastResult = null;

    // ========================================================================
    // INIT
    // ========================================================================

    document.addEventListener('DOMContentLoaded', function () { init(); });

    async function init() {
        var statusBox = document.getElementById('statusBox');
        statusBox.className = 'status-box info';
        statusBox.textContent = 'Checking authentication...';

        currentUser = await AdminUI.requireAdmin();
        if (!currentUser) return;

        document.getElementById('userDisplay').textContent = currentUser.email;
        document.getElementById('setupKeyInput').value = AdminUI.getSetupKey() || '';
        document.getElementById('setupKeyInput').addEventListener('change', function () {
            AdminUI.setSetupKey(this.value);
            AdminUI.toast('Setup key ' + (this.value ? 'saved for this tab' : 'cleared'));
        });

        statusBox.className = 'status-box success';
        statusBox.textContent = 'Logged in as SUPER_ADMIN (' + currentUser.email + '). Environment: ' +
            ((window.APP_CONFIG && APP_CONFIG.environment) || 'unknown');

        buildProgress();
        populateRegulatorDropdown();
        renderStep();
    }

    async function populateRegulatorDropdown() {
        var sel = document.getElementById('tcRegulator');
        if (!sel) return;
        try {
            var resp = await AdminUI.apiGet('/api/v1/admin/regulators');
            var regs = resp.regulators || [];
            sel.innerHTML = '<option value="">— none —</option>' +
                regs.map(function (r) {
                    return '<option value="' + AdminUI.esc(r.id) + '">' +
                        AdminUI.esc(r.name || r.id) + ' (' + AdminUI.esc(r.id) + ')</option>';
                }).join('');
        } catch (err) { /* dropdown is non-critical; leave current options */ }
    }

    function logout() {
        firebase.auth().signOut().then(function () {
            window.location.href = '/';
        });
    }

    // ========================================================================
    // PROGRESS RAIL
    // ========================================================================

    function buildProgress() {
        var rail = document.getElementById('progressRail');
        rail.innerHTML = STEPS.map(function (s) {
            return '<div class="wizard-step" id="wizStep' + s.id + '">' +
                '<span class="dot">' + s.id + '</span>' + s.label + '</div>';
        }).join('');
    }

    // ========================================================================
    // STEP NAVIGATION
    // ========================================================================

    function renderStep() {
        STEPS.forEach(function (s) {
            var el = document.getElementById('wizStep' + s.id);
            el.classList.toggle('active', s.id === currentStep);
            el.classList.toggle('done', s.id < currentStep);
        });
        for (var i = 1; i <= STEPS.length; i++) {
            document.getElementById('step-panel-' + i).classList.toggle('active', i === currentStep);
        }
        var submitStep = STEPS.length - 1;
        document.getElementById('wizNext').style.display = (currentStep >= submitStep) ? 'none' : '';
        document.getElementById('wizSubmit').style.display = (currentStep === submitStep) ? '' : 'none';
        document.getElementById('wizBack').disabled = currentStep === 1;
        if (currentStep === submitStep) renderReview();
    }

    function wizardNext() {
        if (!validateStep(currentStep)) return;
        currentStep = Math.min(currentStep + 1, STEPS.length);
        renderStep();
        window.scrollTo(0, 0);
    }

    function wizardBack() {
        currentStep = Math.max(currentStep - 1, 1);
        renderStep();
        window.scrollTo(0, 0);
    }

    function validateStep(step) {
        if (step === 1) {
            var tid = document.getElementById('tcTenantId').value.trim();
            var name = document.getElementById('tcTenantName').value.trim();
            if (!tid) { AdminUI.toast('Tenant ID is required.', 'error'); return false; }
            if (!/^[a-z0-9-]+$/.test(tid)) { AdminUI.toast('Tenant ID: lowercase letters, numbers, hyphens only.', 'error'); return false; }
            if (!name) { AdminUI.toast('Organization name is required.', 'error'); return false; }
            return true;
        }
        if (step === 2) {
            if (!document.getElementById('tcContactName').value.trim()) {
                AdminUI.toast('Contact name is required.', 'error');
                return false;
            }
            return true;
        }
        return true;
    }

    // ========================================================================
    // REVIEW (STEP 4)
    // ========================================================================

    function collectPayload() {
        return {
            tenant_id: document.getElementById('tcTenantId').value.trim().toLowerCase(),
            name: document.getElementById('tcTenantName').value.trim(),
            icao: document.getElementById('tcIcao').value.trim().toUpperCase(),
            country: document.getElementById('tcCountry').value.trim() || 'Nepal',
            regulator_id: document.getElementById('tcRegulator').value.trim() || null,
            status: document.getElementById('tcStatus').value,
            contact: {
                name: document.getElementById('tcContactName').value.trim(),
                title: document.getElementById('tcContactTitle').value.trim(),
                email: document.getElementById('tcContactEmail').value.trim(),
                phone: document.getElementById('tcContactPhone').value.trim(),
            },
            contract: {
                date: document.getElementById('tcContractDate').value,
                reference: document.getElementById('tcContractRef').value.trim(),
                expiry: document.getElementById('tcContractExpiry').value,
                type: document.getElementById('tcContractType').value,
                signedBy: document.getElementById('tcContractSignedBy').value.trim(),
                signedDate: document.getElementById('tcContractSignedDate').value,
            },
        };
    }

    function reviewItem(k, v) {
        return '<div class="review-item"><div class="k">' + AdminUI.esc(k) + '</div><div class="v">' + AdminUI.esc(v || '—') + '</div></div>';
    }

    function renderReview() {
        var p = collectPayload();
        var area = document.getElementById('reviewArea');
        var html = '';
        html += '<div class="review-block"><h4>Tenant</h4><div class="review-grid">';
        html += reviewItem('Tenant ID', p.tenant_id);
        html += reviewItem('Name', p.name);
        html += reviewItem('ICAO', p.icao);
        html += reviewItem('Country', p.country);
        html += reviewItem('Regulator', p.regulator_id);
        html += reviewItem('Status', p.status);
        html += '</div></div>';
        html += '<div class="review-block"><h4>Contact</h4><div class="review-grid">';
        html += reviewItem('Name', p.contact.name);
        html += reviewItem('Title', p.contact.title);
        html += reviewItem('Email', p.contact.email);
        html += reviewItem('Phone', p.contact.phone);
        html += '</div></div>';
        html += '<div class="review-block"><h4>Contract</h4><div class="review-grid">';
        html += reviewItem('Date', p.contract.date);
        html += reviewItem('Reference', p.contract.reference);
        html += reviewItem('Expiry', p.contract.expiry);
        html += reviewItem('Type', p.contract.type);
        html += reviewItem('Signed By', p.contract.signedBy);
        html += reviewItem('Signed Date', p.contract.signedDate);
        html += '</div></div>';
        html += '<div class="review-block"><h4>Users</h4>' +
            '<div class="card-sub">Users are created one at a time afterwards via Production Setup Step 3.</div></div>';
        area.innerHTML = html;
    }

    // ========================================================================
    // SUBMIT (STEP 4 -> STEP 5)
    // ========================================================================

    async function submitTenant() {
        if (!validateStep(STEPS.length - 1)) return;
        var btn = document.getElementById('wizSubmit');
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Creating…';
        try {
            var payload = {
                setup_key: AdminUI.ensureSetupKey(),
                tenant: collectPayload(),
            };
            var resp = await AdminUI.apiPost('/api/v1/admin/tenants', payload);
            lastResult = resp;
            currentStep = STEPS.length;
            renderStep();
            renderSuccess(resp);
            AdminUI.toast('Tenant created.', 'success');
        } catch (err) {
            AdminUI.toast('Create failed: ' + err.message, 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-rocket"></i> Create Tenant';
        }
    }

    function renderSuccess(resp) {
        var banner = document.getElementById('tcSuccessBanner');
        banner.innerHTML = '<strong>Tenant created successfully.</strong> ' +
            AdminUI.esc(resp.tenant.name) + ' (' + AdminUI.esc(resp.tenant.tenant_id) + '). ' +
            'Add users via Production Setup Step 3.';
    }

    // ========================================================================
    // SUCCESS ACTIONS
    // ========================================================================

    function viewTenant() {
        window.location.href = '/admin/production-setup.html';
    }

    function startNewTenant() {
        window.location.reload();
    }

    // ========================================================================
    // EXPORTS
    // ========================================================================

    global.wizardNext = wizardNext;
    global.wizardBack = wizardBack;
    global.submitTenant = submitTenant;
    global.viewTenant = viewTenant;
    global.startNewTenant = startNewTenant;
    global.logout = logout;
})(window);