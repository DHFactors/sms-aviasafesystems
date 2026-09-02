/* ============================================================================
   FILE: admin-credentials.js
   PATH: public/js/admin-credentials.js
   PURPOSE: Tenant Credentials wizard logic — 6-step onboarding flow that
            creates an operator tenant together with its Firebase Auth users.
            Emails are checked for availability, generated passwords are shown
            once on success, and the admin can copy them or send the welcome
            email from the success screen.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

(function (global) {
    'use strict';

    var STEPS = [
        { id: 1, label: 'Tenant Info' },
        { id: 2, label: 'Contact' },
        { id: 3, label: 'Contract' },
        { id: 4, label: 'Users' },
        { id: 5, label: 'Review' },
        { id: 6, label: 'Done' },
    ];

    var currentUser = null;
    var currentStep = 1;
    var lastResult = null;
    var userCounter = 0;

    var ROLES = ['AIRLINE_ADMIN', 'AIRLINE_SAFETY', 'AIRLINE_INSPECTOR', 'VIEWER'];

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
        addUserRow();
        addUserRow();
        renderStep();
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
        var isLast = currentStep === STEPS.length;
        document.getElementById('wizNext').style.display = (isLast || currentStep === 5) ? 'none' : '';
        document.getElementById('wizSubmit').style.display = (currentStep === 5) ? '' : 'none';
        document.getElementById('wizBack').disabled = currentStep === 1;
        if (currentStep === 5) renderReview();
    }

    function wizardNext() {
        if (!validateStep(currentStep)) return;
        if (currentStep === 5) { renderReview(); }
        currentStep = Math.min(currentStep + 1, STEPS.length);
        renderStep();
        if (currentStep === 5) renderReview();
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
        if (step === 4) {
            var rows = getUsers();
            if (!rows.length) { AdminUI.toast('Add at least one user.', 'error'); return false; }
            for (var i = 0; i < rows.length; i++) {
                var r = rows[i];
                if (!r.email) { AdminUI.toast('User ' + (i + 1) + ': email is required.', 'error'); return false; }
                var s = document.querySelector('[data-urow="' + i + '"] .email-status');
                if (s && s.getAttribute('data-state') === 'taken') {
                    AdminUI.toast('User ' + (i + 1) + ': email already exists in Auth. Use a different address.', 'error');
                    return false;
                }
            }
            return true;
        }
        return true;
    }

    // ========================================================================
    // USER ROWS (STEP 4)
    // ========================================================================

    function addUserRow() {
        var idx = userCounter;
        userCounter++;
        var list = document.getElementById('userList');
        var div = document.createElement('div');
        div.className = 'user-entry';
        div.setAttribute('data-urow', idx);
        div.innerHTML =
            '<div class="user-head">' +
            '<strong>User #' + (idx + 1) + '</strong>' +
            '<button type="button" class="remove" onclick="removeUserRow(this)" title="Remove user"><i class="fas fa-trash"></i></button>' +
            '</div>' +
            '<div class="form-row">' +
            '<div class="form-group"><label>Full Name</label><input type="text" class="u-name" placeholder="Full name"></div>' +
            '<div class="form-group"><label>Email *</label><input type="email" class="u-email" placeholder="admin@newair.com">' +
            '<div class="email-status" data-state=""></div></div>' +
            '<div class="form-group"><label>Role</label><select class="u-role">' +
            ROLES.map(function (r) { return '<option value="' + r + '"' + (r === 'AIRLINE_ADMIN' ? ' selected' : '') + '>' + r + '</option>'; }).join('') +
            '</select></div>' +
            '</div>';
        var emailInput = div.querySelector('.u-email');
        emailInput.addEventListener('blur', function () { checkEmail(idx); });
        emailInput.addEventListener('input', function () {
            var st = div.querySelector('.email-status');
            st.textContent = '';
            st.setAttribute('data-state', '');
        });
        list.appendChild(div);
        return div;
    }

    function removeUserRow(btn) {
        var div = btn.closest('.user-entry');
        if (document.querySelectorAll('.user-entry').length <= 1) {
            AdminUI.toast('At least one user is required.', 'warn');
            return;
        }
        div.remove();
    }

    function getUsers() {
        var out = [];
        document.querySelectorAll('#userList .user-entry').forEach(function (row) {
            var name = row.querySelector('.u-name').value.trim();
            var email = row.querySelector('.u-email').value.trim();
            var role = row.querySelector('.u-role').value;
            if (email) out.push({ full_name: name, email: email, role: role });
        });
        return out;
    }

    // ========================================================================
    // EMAIL AVAILABILITY CHECK
    // ========================================================================

    async function checkEmail(idx) {
        var rows = document.querySelectorAll('#userList .user-entry');
        if (idx >= rows.length) return;
        var row = rows[idx];
        var email = row.querySelector('.u-email').value.trim();
        var st = row.querySelector('.email-status');
        if (!email) { st.textContent = ''; st.setAttribute('data-state', ''); return; }
        st.className = 'email-status';
        st.setAttribute('data-state', 'checking');
        st.textContent = 'Checking…';
        try {
            var resp = await AdminUI.apiPost('/api/v1/admin/tenants/check-email', {
                setup_key: AdminUI.ensureSetupKey(),
                email: email,
            });
            if (resp.available) {
                st.setAttribute('data-state', 'available');
                st.innerHTML = '<span class="available"><i class="fas fa-circle-check"></i> Available</span>';
            } else {
                st.setAttribute('data-state', 'taken');
                st.innerHTML = '<span class="taken"><i class="fas fa-circle-xmark"></i> Already registered</span>';
            }
        } catch (err) {
            st.setAttribute('data-state', '');
            st.textContent = 'Check failed: ' + err.message;
        }
    }

    // ========================================================================
    // REVIEW (STEP 5)
    // ========================================================================

    function collectPayload() {
        var users = getUsers();
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
            users: users,
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
        html += '<div class="review-block"><h4>Users (' + p.users.length + ')</h4>';
        html += '<div style="overflow-x:auto;"><table class="admin-table"><thead><tr>' +
            '<th>Full Name</th><th>Email</th><th>Role</th>' +
            '</tr></thead><tbody>';
        p.users.forEach(function (u) {
            html += '<tr><td>' + AdminUI.esc(u.full_name || '—') + '</td>' +
                '<td>' + AdminUI.esc(u.email) + '</td>' +
                '<td><code>' + AdminUI.esc(u.role) + '</code></td></tr>';
        });
        html += '</tbody></table></div></div>';
        area.innerHTML = html;
    }

    // ========================================================================
    // SUBMIT (STEP 6)
    // ========================================================================

    async function submitTenant() {
        if (!validateStep(5)) return;
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
            currentStep = 6;
            renderStep();
            renderSuccess(resp);
            AdminUI.toast('Tenant created with credentials.', 'success');
        } catch (err) {
            AdminUI.toast('Create failed: ' + err.message, 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-rocket"></i> Create Tenant &amp; Credentials';
        }
    }

    function renderSuccess(resp) {
        var banner = document.getElementById('tcSuccessBanner');
        banner.innerHTML = '<strong>Tenant created successfully.</strong> ' +
            AdminUI.esc(resp.tenant.name) + ' (' + AdminUI.esc(resp.tenant.tenant_id) + ') — ' +
            (resp.users || []).length + ' user(s) provisioned.';

        var list = document.getElementById('generatedPasswords');
        var users = resp.users || [];
        if (!users.length) {
            list.innerHTML = '<li><div class="meta">No users provisioned.</div></li>';
        } else {
            list.innerHTML = users.map(function (u) {
                var statusBadge = u.status === 'ok'
                    ? '<span class="badge badge-success">ok</span>'
                    : '<span class="badge badge-danger">error</span>';
                var pw = u.status === 'ok'
                    ? '<span class="pw-chip">' + AdminUI.esc(u.password) +
                      ' <button class="copy-btn" onclick="copyText(\'' + AdminUI.esc(u.password) + '\')" title="Copy password"><i class="fas fa-copy"></i></button></span>'
                    : '<span class="status-box error" style="margin:0;padding:6px 10px;">' + AdminUI.esc(u.detail || u.status) + '</span>';
                return '<li><div class="meta"><strong>' + AdminUI.esc(u.email) + '</strong>' +
                    ' <span class="role">' + AdminUI.esc(u.role) + '</span> ' + statusBadge + '</div>' +
                    '<div>' + pw + '</div></li>';
            }).join('');
        }
        document.getElementById('deliveryArea').innerHTML = '';
    }

    // ========================================================================
    // SUCCESS ACTIONS
    // ========================================================================

    function copyText(text) {
        var ok = false;
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(function () { ok = true; });
        } else {
            var ta = document.createElement('textarea');
            ta.value = text;
            document.body.appendChild(ta);
            ta.select();
            try { document.execCommand('copy'); ok = true; } catch (e) { /* noop */ }
            ta.remove();
        }
        AdminUI.toast(ok ? 'Copied to clipboard.' : 'Copy failed.', ok ? 'success' : 'error');
    }

    function copyAllCredentials() {
        if (!lastResult) return;
        var lines = [];
        lines.push(lastResult.tenant.name + ' (' + lastResult.tenant.tenant_id + ') — AviaSAFE SMS credentials');
        lines.push('Login URL: https://sms.aviasafesystems.com');
        lines.push('');
        (lastResult.users || []).forEach(function (u) {
            if (u.status === 'ok') {
                lines.push(u.email + '  /  ' + u.role + '  /  ' + u.password);
            }
        });
        copyText(lines.join('\n'));
    }

    async function sendWelcome() {
        if (!lastResult) return;
        var btn = document.querySelector('.action-bar .btn-primary');
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sending…';
        try {
            var resp = await AdminUI.apiPost('/api/v1/admin/tenants/' + encodeURIComponent(lastResult.tenant.tenant_id) + '/send-welcome', {
                setup_key: AdminUI.ensureSetupKey(),
            });
            var area = document.getElementById('deliveryArea');
            var d = resp.delivery || {};
            var sent = d.sent === true;
            area.innerHTML = '<div class="delivery-note' + (sent ? '' : ' warn') + '">' +
                '<i class="fas ' + (sent ? 'fa-envelope-circle-check' : 'fa-envelope-open-text') + '"></i> ' +
                'Welcome email to <strong>' + AdminUI.esc(resp.admin_email) + '</strong> via <strong>' + AdminUI.esc(d.provider) + '</strong> — ' +
                (sent ? 'sent.' : 'preview only (provider "none").') +
                '</div>';
            AdminUI.toast(sent ? 'Welcome email sent.' : 'Welcome email logged (provider none).', sent ? 'success' : 'warn');
        } catch (err) {
            AdminUI.toast('Send failed: ' + err.message, 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-envelope"></i> Send Welcome Email';
        }
    }

    function viewTenant() {
        window.location.href = '/admin/production-setup.html';
    }

    function startNewTenant() {
        window.location.reload();
    }

    // ========================================================================
    // EXPORTS
    // ========================================================================

    global.addUserRow = addUserRow;
    global.removeUserRow = removeUserRow;
    global.wizardNext = wizardNext;
    global.wizardBack = wizardBack;
    global.submitTenant = submitTenant;
    global.copyText = copyText;
    global.copyAllCredentials = copyAllCredentials;
    global.sendWelcome = sendWelcome;
    global.viewTenant = viewTenant;
    global.startNewTenant = startNewTenant;
    global.logout = logout;
})(window);
