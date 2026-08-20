/* ============================================================================
   FILE: team.js
   PATH: public/js/team.js
   PURPOSE: Team Management page (public/settings/team.html). Role-aware for the
            delegated admin hierarchy:
              - TENANT_ADMIN / AIRLINE_ADMIN: full visibility, any applicable
                department, assignable roles DEPT_ADMIN / SAFETY_OFFICER / STAFF.
              - DEPT_ADMIN: department selector locked to the caller's own
                department; role locked to STAFF / Employee.
            Uses GET /api/v1/tenants/{tenantId}/users, GET /api/v1/auth/invites
            and POST /api/v1/auth/invite via ApiClient.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

(function (global) {
    'use strict';

    var INVITER_ROLES = ['SUPER_ADMIN', 'AIRLINE_ADMIN', 'TENANT_ADMIN', 'DEPT_ADMIN'];
    var TENANT_WIDE_ROLES = ['SUPER_ADMIN', 'AIRLINE_ADMIN', 'TENANT_ADMIN'];

    var ROLE_LABELS = {
        SUPER_ADMIN: 'Global Administrator',
        TENANT_ADMIN: 'Safety Manager (Tenant Admin)',
        AIRLINE_ADMIN: 'Safety Manager (Tenant Admin)',
        DEPT_ADMIN: 'Department Admin (HOD)',
        SAFETY_OFFICER: 'Safety Officer',
        STAFF: 'Staff / Employee',
        USER: 'Staff / Employee',
        CAAN_SMD: 'State Safety Regulator',
    };

    var ROLE_CLASSES = {
        SUPER_ADMIN: 'role-admin',
        TENANT_ADMIN: 'role-admin',
        AIRLINE_ADMIN: 'role-admin',
        DEPT_ADMIN: 'role-hod',
        SAFETY_OFFICER: 'role-officer',
        STAFF: 'role-staff',
        USER: 'role-staff',
        CAAN_SMD: 'role-admin',
    };

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function roleLabel(role) {
        return ROLE_LABELS[role] || role || '—';
    }

    function roleBadge(role) {
        var cls = ROLE_CLASSES[role] || 'role-staff';
        return '<span class="role-badge ' + cls + '">' + esc(roleLabel(role)) + '</span>';
    }

    function toast(message) {
        var el = document.getElementById('toast');
        if (!el) return;
        el.textContent = message;
        el.classList.add('show');
        setTimeout(function () { el.classList.remove('show'); }, 2600);
    }

    function showPage() {
        document.getElementById('teamContent').style.display = 'block';
        document.getElementById('pageContent').style.display = 'block';
    }

    function showDenied() {
        document.getElementById('deniedBox').style.display = 'block';
        document.getElementById('pageContent').style.display = 'block';
    }

    function showError(message) {
        document.getElementById('errorMsg').textContent = message;
        document.getElementById('errorBox').style.display = 'block';
        document.getElementById('pageContent').style.display = 'block';
    }

    function populateDepartmentSelect(session, departments) {
        var select = document.getElementById('inviteDepartment');
        select.innerHTML = '';
        if (session.role === 'DEPT_ADMIN') {
            var dept = (session.claims && session.claims.department) || session.department || '';
            var opt = document.createElement('option');
            opt.value = dept;
            opt.textContent = dept || '—';
            select.appendChild(opt);
            select.disabled = true;
            var badge = document.getElementById('scopeBadge');
            if (badge) badge.textContent = 'Department scope: ' + (dept || '—');
        } else {
            var all = departments && departments.length
                ? departments
                : [{ code: 'safety', label: 'Safety' }];
            all.forEach(function (d) {
                var opt = document.createElement('option');
                opt.value = d.code;
                opt.textContent = d.label;
                select.appendChild(opt);
            });
            select.disabled = false;
            var badge = document.getElementById('scopeBadge');
            if (badge) badge.textContent = 'Scope: all departments';
        }
    }

    function populateRoleSelect(session) {
        var select = document.getElementById('inviteRole');
        select.innerHTML = '';
        var options;
        if (session.role === 'DEPT_ADMIN') {
            options = [{ value: 'STAFF', label: 'Staff / Employee' }];
            select.disabled = true;
        } else {
            options = [
                { value: 'DEPT_ADMIN', label: 'Department Admin (HOD)' },
                { value: 'SAFETY_OFFICER', label: 'Safety Officer' },
                { value: 'STAFF', label: 'Staff / Employee' },
            ];
            select.disabled = false;
        }
        options.forEach(function (o) {
            var opt = document.createElement('option');
            opt.value = o.value;
            opt.textContent = o.label;
            select.appendChild(opt);
        });
    }

    function renderUsers(users) {
        var tbody = document.getElementById('usersTableBody');
        if (!users || !users.length) {
            tbody.innerHTML = '<tr><td colspan="4" class="empty">No team members found.</td></tr>';
            return;
        }
        tbody.innerHTML = users.map(function (u) {
            return '<tr>' +
                '<td>' + esc(u.displayName || '—') + '</td>' +
                '<td>' + esc(u.email || '—') + '</td>' +
                '<td>' + roleBadge(u.role) + '</td>' +
                '<td class="dept-tag">' + esc(u.department || '—') + '</td>' +
                '</tr>';
        }).join('');
    }

    function renderInvites(invites) {
        var wrap = document.getElementById('invitesList');
        if (!invites || !invites.length) {
            wrap.innerHTML = '<div class="empty">No active invites.</div>';
            return;
        }
        wrap.innerHTML = invites.map(function (inv) {
            return '<div style="display:flex;justify-content:space-between;align-items:center;padding:0.55rem 0;border-bottom:1px solid #eef2f7;gap:0.75rem;">' +
                '<div>' +
                '<span class="invite-code">' + esc(inv.code) + '</span>' +
                ' <span class="dept-tag">' + esc(inv.department_label || inv.department || '') + ' · ' +
                esc(inv.role_label || roleLabel(inv.role)) + '</span>' +
                '</div>' +
                '<button type="button" class="btn-outline btn-copy" data-code="' + esc(inv.code) + '">' +
                '<i class="fas fa-copy"></i> Copy</button>' +
                '</div>';
        }).join('');
        Array.prototype.forEach.call(wrap.querySelectorAll('[data-code]'), function (btn) {
            btn.addEventListener('click', function () {
                copyToClipboard(btn.getAttribute('data-code'));
            });
        });
    }

    function copyToClipboard(text) {
        function fallback() {
            var ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.select();
            try { document.execCommand('copy'); } catch (e) { /* ignore */ }
            document.body.removeChild(ta);
            toast('Invite code copied');
        }
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(function () {
                toast('Invite code copied');
            }).catch(fallback);
        } else {
            fallback();
        }
    }

    async function loadUsers(session) {
        try {
            var resp = await ApiClient.get('/api/v1/tenants/' + encodeURIComponent(session.tenantId) + '/users');
            renderUsers((resp && resp.data && resp.data.users) || []);
        } catch (err) {
            renderUsers([]);
            console.error('[Team] users load failed:', err);
            toast(err && err.message ? err.message : 'Failed to load team members');
        }
    }

    async function loadInvites() {
        try {
            var resp = await ApiClient.get('/api/v1/auth/invites');
            renderInvites((resp && resp.invites) || []);
        } catch (err) {
            renderInvites([]);
            console.error('[Team] invites load failed:', err);
        }
    }

    async function loadDepartments(session) {
        if (session.role === 'DEPT_ADMIN') {
            populateDepartmentSelect(session, []);
            return;
        }
        try {
            var resp = await ApiClient.get('/api/v1/auth/tenant-lookup?tenant_id=' + encodeURIComponent(session.tenantId));
            populateDepartmentSelect(session, (resp && resp.applicable_departments) || []);
        } catch (err) {
            populateDepartmentSelect(session, []);
            console.error('[Team] department load failed:', err);
        }
    }

    function attachInviteForm() {
        var form = document.getElementById('inviteForm');
        if (!form) return;
        form.addEventListener('submit', async function (e) {
            e.preventDefault();
            var department = document.getElementById('inviteDepartment').value;
            var role = document.getElementById('inviteRole').value;
            if (!department || !role) {
                toast('Select a department and role first');
                return;
            }
            var submit = form.querySelector('button[type="submit"]');
            submit.disabled = true;
            try {
                var resp = await ApiClient.post('/api/v1/auth/invite', { department: department, role: role });
                document.getElementById('inviteResultCode').textContent = (resp && resp.code) || '—';
                document.getElementById('inviteResultDept').textContent = (resp && (resp.department_label || resp.department)) || '';
                document.getElementById('inviteResultRole').textContent = roleLabel((resp && resp.role) || role);
                document.getElementById('inviteResult').style.display = 'block';
                toast('Invite code generated');
                loadInvites();
            } catch (err) {
                console.error('[Team] invite failed:', err);
                toast(err && err.message ? err.message : 'Unable to generate invite');
            } finally {
                submit.disabled = false;
            }
        });
    }

    async function initTeamPage() {
        try {
            await waitForFirebase();
            var session = await getCurrentUser();
            if (!session) {
                window.location.href = '/login.html';
                return;
            }
            if (INVITER_ROLES.indexOf(session.role) === -1) {
                showDenied();
                return;
            }
            if (!session.tenantId) {
                showError('No tenant is associated with this account.');
                return;
            }

            if (typeof window.updateShellTenant === 'function') {
                window.updateShellTenant(
                    (session.tenantId || '').toUpperCase(),
                    session.role === 'DEPT_ADMIN' ? 'Team Management · Department Admin' : 'Team Management · Safety Manager'
                );
            }

            populateRoleSelect(session);
            attachInviteForm();
            showPage();

            await loadDepartments(session);
            await Promise.all([loadUsers(session), loadInvites()]);
        } catch (err) {
            console.error('[Team] init failed:', err);
            showError(err && err.message ? err.message : 'Failed to initialise Team Management.');
        }
    }

    global.initTeamPage = initTeamPage;
})(window);
