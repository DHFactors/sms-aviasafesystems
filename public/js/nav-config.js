/**
 * nav-config.js - Single source of truth for ALL navigation items
 * Role-based visibility for Safety Managers, Department Admins,
 * Accountable Executives, and CAAN Regulators.
 */

const NAV_CONFIG = {
    // ─── DASHBOARD ─── (All roles)
    dashboard: {
        label: 'Dashboard',
        icon: 'fa-gauge-high',
        roles: ['ALL'],
        items: [
            { id: 'key-indicators', href: '/safety.html', label: 'Key Indicators', roles: ['SAFETY'] },
            { id: 'my-tasks', href: '/dashboard/my-tasks.html', label: 'My Tasks', roles: ['ALL'], badge: true },
            { id: 'ae-dashboard', href: '/dashboard/ae-dashboard.html', label: 'Executive', roles: ['AE'] },
            { id: 'caan-dashboard', href: '/caan.html', label: 'CAAN Oversight', roles: ['CAAN'] },
        ]
    },

    // ─── HAZARD MANAGEMENT ───
    hazards: {
        label: 'Hazard Management',
        icon: 'fa-triangle-exclamation',
        roles: ['SAFETY', 'DEPT_ADMIN', 'AE'],
        items: [
            { id: 'hazard-analysis', href: '/hazard-analysis.html', label: 'Hazard Analysis' },
            { id: 'top-hazards', href: '/top-hazards.html', label: 'Top Hazards' },
            { id: 'risk-register', href: '/risk-register/index.html', label: 'Risk Register' },
            { id: 'sram', href: '/sram/index.html', label: 'Bow-Tie SRAM' },
            { id: 'barrier-register', href: '/barrier-register/index.html', label: 'Barrier Register' },
        ]
    },

    // ─── CORRECTIVE ACTIONS ───
    corrective: {
        label: 'Corrective Actions',
        icon: 'fa-clipboard-check',
        roles: ['SAFETY', 'DEPT_ADMIN', 'AE'],
        items: [
            { id: 'can-register', href: '/can_cap/cans.html', label: 'CAN Register' },
            { id: 'cap-register', href: '/can_cap/caps.html', label: 'CAP Register' },
            { id: 'issue-can', href: '/can_cap/issue.html', label: 'Issue CAN' },
            { id: 'master-register', href: '/dashboard/master-register.html', label: 'Master Register' },
        ]
    },

    // ─── REPORTING ───
    reporting: {
        label: 'Reporting',
        icon: 'fa-pen-to-square',
        roles: ['SAFETY', 'DEPT_ADMIN'],
        items: [
            { id: 'submit-mor', href: '/report/mor.html', label: 'Submit MOR' },
            { id: 'submit-vsr', href: '/reports/new.html', label: 'Submit VSR' },
            { id: 'report-diversion', href: '/flight_diversions/create.html', label: 'Report Diversion' },
            { id: 'reports-center', href: '/reports/index.html', label: 'Reports Center' },
        ]
    },

    // ─── PERFORMANCE ───
    performance: {
        label: 'Performance',
        icon: 'fa-chart-line',
        roles: ['SAFETY', 'CAAN'],
        items: [
            { id: 'sms-maturity', href: '/dashboard/sms-maturity.html', label: 'SMS Maturity' },
            { id: 'spi-dashboard', href: '/dashboard/spi-dashboard.html', label: 'SPI/SPT' },
            { id: 'nhrc-kpis', href: '/dashboard/nhrc-kpis.html', label: 'N-HRC KPIs' },
        ]
    },

    // ─── REGULATOR ───
    regulator: {
        label: 'Regulator',
        icon: 'fa-landmark',
        roles: ['CAAN'],
        items: [
            { id: 'state-maturity', href: '/dashboard/caan-sms-maturity.html', label: 'State SMS Maturity' },
            { id: 'psoe-audit', href: '/audits/psoe.html', label: 'PSOE Audit' },
            { id: 'caan-risk', href: '/caan-state-risk.html', label: 'State Risk Register' },
        ]
    },

    // ─── ADMINISTRATION ───
    administration: {
        label: 'Administration',
        icon: 'fa-gear',
        roles: ['SAFETY', 'SUPER'],
        items: [
            { id: 'team', href: '/settings/team.html', label: 'Team Management' },
            { id: 'settings', href: '/administration.html', label: 'System Settings' },
            { id: 'production', href: '/admin/production-setup.html', label: 'Production Setup', roles: ['SUPER'] },
        ]
    },
};

// ─── Helpers ────────────────────────────────────────────────────────────────

function getUserRoleType(user) {
    if (!user) return 'ALL';
    const email = (user.email || '').toLowerCase();
    const role = user.role || 'USER';

    if (role === 'SUPER_ADMIN') return 'SUPER';
    if (role === 'CAAN_SMD' || role === 'CAAN_ADMIN' || role === 'CAAN_AUDITOR') return 'CAAN';
    if (email.indexOf('ae@') === 0 || email.indexOf('ae.') === 0) return 'AE';
    if (role === 'AIRLINE_ADMIN' || role === 'TENANT_ADMIN') return 'SAFETY';
    if (role === 'DEPT_ADMIN') return 'DEPT_ADMIN';
    return 'ALL';
}

function getVisibleNav(user) {
    const roleType = getUserRoleType(user);
    const result = [];

    for (const [key, group] of Object.entries(NAV_CONFIG)) {
        // Check if group is visible for this role
        if (!group.roles.includes('ALL') && !group.roles.includes(roleType)) continue;

        const items = group.items.filter(item => {
            if (!item.roles) return true;
            return item.roles.includes('ALL') || item.roles.includes(roleType);
        });

        if (items.length) {
            result.push({
                group: group.label,
                icon: group.icon,
                items: items
            });
        }
    }
    return result;
}

// ─── Exports ────────────────────────────────────────────────────────────────

window.NAV_CONFIG = NAV_CONFIG;
window.getUserRoleType = getUserRoleType;
window.getVisibleNav = getVisibleNav;