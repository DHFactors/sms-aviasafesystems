/**
 * nav-config.js - Single source of truth for ALL navigation items
 * Role-based visibility for Safety Managers, Department Admins,
 * Accountable Executives, and CAAN Regulators.
 *
 * PHASE 4 WAVE 1 (P4-6):
 *  - Canonical role literals supported (RBAC_MODEL.md §1): SUPER_ADMIN,
 *    CAAN_SMD, TENANT_ADMIN, DEPT_ADMIN, SAFETY_OFFICER, STAFF,
 *    ACCOUNTABLE_EXECUTIVE, SAG_MEMBER (+ legacy aliases AIRLINE_ADMIN,
 *    USER, CAAN_ADMIN, CAAN_AUDITOR).
 *  - ACCOUNTABLE_EXECUTIVE maps to the AE role type with a NARROW menu:
 *    Dashboard (/dashboard/ae-dashboard.html), Action Queues (My Tasks),
 *    Trends. No CAN/CAP authoring, no admin.
 *  - SAG_MEMBER maps to the SAG role type. There is currently NO SAG member
 *    dashboard in scope, so SAG is hidden from nav entirely: getVisibleNav
 *    returns [] for SAG (confirmed per P4-6.2).
 *  - Module flag gating (DASHBOARD_CONTRACT.md §9; RBAC Q-R5): groups/items
 *    carry a `module` tag with a CANONICAL flag name
 *    (module_a_survey | module_b_srm | module_b_can_cap |
 *    module_c_regulator). getVisibleNav(user, moduleAccess) hides tagged
 *    entries when the tenant lacks the flag. moduleAccess is read from
 *    tenants.module_access (canonical keys; legacy module1..module4 keys
 *    tolerated). The second argument is OPTIONAL — existing callers
 *    (getVisibleNav(user)) see unfiltered-by-module results as before.
 *  - UMD-wrapped so the same logic is unit-tested in Node
 *    (frontend-tests/test_nav_config.js) and runs in the browser.
 */

(function (root, factory) {
    var api = factory();
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = api;
    }
    // Always publish browser globals (even under Node shims that define
    // window) so pages keep working without a bundler.
    var g = (typeof window !== 'undefined') ? window : root;
    g.NAV_CONFIG = api.NAV_CONFIG;
    g.getUserRoleType = api.getUserRoleType;
    g.getVisibleNav = api.getVisibleNav;
    g.NAV_MODULE_FLAGS = api.NAV_MODULE_FLAGS;
}(typeof self !== 'undefined' ? self : this, function () {
'use strict';

var NAV_CONFIG = {
    // ─── DASHBOARD ─── (All roles; AE sees ONLY this group — narrow menu)
    dashboard: {
        label: 'Dashboard',
        icon: 'fa-gauge-high',
        roles: ['ALL'],
        items: [
            { id: 'key-indicators', href: '/safety.html', label: 'Key Indicators', roles: ['SAFETY'], module: 'module_b_srm' },
            { id: 'my-tasks', href: '/dashboard/my-tasks.html', label: 'My Tasks', roles: ['ALL'], badge: true, module: 'module_b_can_cap' },
            { id: 'ae-dashboard', href: '/dashboard/ae-dashboard.html', label: 'Executive', roles: ['AE'], module: 'module_b_srm' },
            { id: 'ae-trends', href: '/dashboard/ae-dashboard.html#trends', label: 'Trends', roles: ['AE'], module: 'module_b_srm' },
            { id: 'caan-dashboard', href: '/caan.html', label: 'CAAN Oversight', roles: ['CAAN'], module: 'module_c_regulator' },
        ]
    },

    // ─── HAZARD MANAGEMENT ─── (Module B SRM base; AE excluded — read-only
    // executive surface lives on the AE dashboard itself, P4-6.1)
    hazards: {
        label: 'Hazard Management',
        icon: 'fa-triangle-exclamation',
        roles: ['SAFETY', 'DEPT_ADMIN'],
        module: 'module_b_srm',
        items: [
            { id: 'hazard-analysis', href: '/hazard-analysis.html', label: 'Hazard Analysis' },
            { id: 'top-hazards', href: '/top-hazards.html', label: 'Top Hazards' },
            { id: 'risk-register', href: '/risk-register/index.html', label: 'Risk Register' },
            { id: 'sram', href: '/sram/index.html', label: 'Bow-Tie SRAM' },
            { id: 'barrier-register', href: '/barrier-register/index.html', label: 'Barrier Register' },
        ]
    },

    // ─── CORRECTIVE ACTIONS ─── (Module B CAN/CAP add-on; AE excluded —
    // no CAN/CAP authoring, P4-6.1)
    corrective: {
        label: 'Corrective Actions',
        icon: 'fa-clipboard-check',
        roles: ['SAFETY', 'DEPT_ADMIN'],
        module: 'module_b_can_cap',
        items: [
            { id: 'can-register', href: '/can_cap/cans.html', label: 'CAN Register' },
            { id: 'cap-register', href: '/can_cap/caps.html', label: 'CAP Register' },
            { id: 'issue-can', href: '/can_cap/issue.html', label: 'Issue CAN', roles: ['SAFETY'] },
            { id: 'master-register', href: '/dashboard/master-register.html', label: 'Master Register' },
        ]
    },

    // ─── REPORTING ─── (Module B reports)
    reporting: {
        label: 'Reporting',
        icon: 'fa-pen-to-square',
        roles: ['SAFETY', 'DEPT_ADMIN'],
        module: 'module_b_srm',
        items: [
            { id: 'submit-mor', href: '/report/mor.html', label: 'Submit MOR' },
            { id: 'submit-vsr', href: '/reports/new.html', label: 'Submit VSR' },
            { id: 'report-diversion', href: '/flight_diversions/create.html', label: 'Report Diversion' },
            { id: 'reports-center', href: '/reports/index.html', label: 'Reports Center' },
        ]
    },

    // ─── PERFORMANCE ─── (Module A maturity + tenant operational indicators)
    performance: {
        label: 'Performance',
        icon: 'fa-chart-line',
        roles: ['SAFETY', 'CAAN'],
        items: [
            { id: 'sms-maturity', href: '/dashboard/sms-maturity.html', label: 'SMS Maturity', module: 'module_a_survey' },
            { id: 'spi-dashboard', href: '/dashboard/spi-dashboard.html', label: 'SPI/SPT', module: 'module_b_srm' },
            { id: 'nhrc-kpis', href: '/dashboard/nhrc-kpis.html', label: 'N-HRC KPIs', module: 'module_b_srm' },
        ]
    },

    // ─── REGULATOR ─── (Module C; CAAN only)
    regulator: {
        label: 'Regulator',
        icon: 'fa-landmark',
        roles: ['CAAN'],
        module: 'module_c_regulator',
        items: [
            { id: 'state-maturity', href: '/dashboard/caan-sms-maturity.html', label: 'State SMS Maturity' },
            { id: 'psoe-audit', href: '/audits/psoe.html', label: 'PSOE Audit' },
            { id: 'caan-risk', href: '/caan-state-risk.html', label: 'State Risk Register' },
        ]
    },

    // ─── ADMINISTRATION ─── (no module flag — admin surface is role-gated)
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

// ─── Module flags ───────────────────────────────────────────────────────────
// Canonical names per RBAC decision Q-R5 (DASHBOARD_CONTRACT.md §9).
var NAV_MODULE_FLAGS = [
    'module_a_survey',
    'module_b_srm',
    'module_b_can_cap',
    'module_c_regulator',
];

// Legacy numeric keys (live tenants.module_access scheme) → canonical.
var LEGACY_MODULE_MAP = {
    module1: 'module_a_survey',
    module_1: 'module_a_survey',
    module2: 'module_b_srm',
    module_2: 'module_b_srm',
    module3: 'module_c_regulator',
    module_3: 'module_c_regulator',
    module4: 'module_c_regulator',
    module_4: 'module_c_regulator',
};

function truthyFlag(v) {
    return v === true || v === 'true' || v === 1 || v === '1';
}

// Normalize a tenants.module_access bag (canonical + legacy keys,
// {module_access|modules} envelopes) to { canonical: bool }.
function normalizeModuleAccess(bag) {
    var out = {};
    if (!bag || typeof bag !== 'object') return out;
    var src = bag;
    if (src.module_access && typeof src.module_access === 'object') {
        src = src.module_access;
    } else if (src.modules && typeof src.modules === 'object') {
        var merged = {};
        Object.keys(src.modules).forEach(function (k) { merged[k] = src.modules[k]; });
        Object.keys(src).forEach(function (k) {
            if (k !== 'modules' && k !== 'module_access') merged[k] = src[k];
        });
        src = merged;
    }
    Object.keys(src).forEach(function (k) {
        if (k === 'modules' || k === 'module_access') return;
        var canon = LEGACY_MODULE_MAP[k] || k;
        if (NAV_MODULE_FLAGS.indexOf(canon) !== -1) out[canon] = truthyFlag(src[k]);
    });
    // module_b_can_cap subset rule (Q-R6): no independent add-on flag in the
    // backend, so it inherits module_b_srm unless explicitly opted out.
    if (out.module_b_can_cap === undefined && out.module_b_srm !== undefined) {
        out.module_b_can_cap = !!out.module_b_srm;
    }
    return out;
}

function moduleEnabled(normalized, flag) {
    if (!flag) return true;
    var canon = LEGACY_MODULE_MAP[flag] || flag;
    if (NAV_MODULE_FLAGS.indexOf(canon) === -1) return true; // unknown tag: fail-open
    if (canon === 'module_b_can_cap' && normalized.module_b_can_cap === undefined) {
        return !!normalized.module_b_srm;
    }
    return !!normalized[canon];
}

// ─── Helpers ────────────────────────────────────────────────────────────────

// Canonical role literals (RBAC_MODEL.md §1) + legacy aliases → nav role type.
// Role types: SUPER | CAAN | AE | SAFETY | DEPT_ADMIN | SAG | ALL.
// SAG_MEMBER → SAG (no dashboard in scope — hidden from nav, P4-6.2).
// ACCOUNTABLE_EXECUTIVE → AE (narrow menu, P4-6.1).
function getUserRoleType(user) {
    if (!user) return 'ALL';
    var email = (user.email || '').toLowerCase();
    var role = String(user.role || 'USER').toUpperCase();

    if (role === 'SUPER_ADMIN') return 'SUPER';
    if (role === 'CAAN_SMD' || role === 'CAAN_ADMIN' || role === 'CAAN_AUDITOR') return 'CAAN';
    if (role === 'ACCOUNTABLE_EXECUTIVE') return 'AE';
    if (role === 'SAG_MEMBER') return 'SAG';
    // Legacy AE heuristic (firebase.js getRoleDestination): AE accounts are
    // stubbed as TENANT_ADMIN/AIRLINE_ADMIN, so the ae@ email check must run
    // BEFORE the tenant-admin mapping — preserves existing routing behavior.
    if (email.indexOf('ae@') === 0 || email.indexOf('ae.') === 0) return 'AE';
    if (role === 'AIRLINE_ADMIN' || role === 'TENANT_ADMIN' || role === 'SAFETY_OFFICER') return 'SAFETY';
    if (role === 'DEPT_ADMIN') return 'DEPT_ADMIN';
    return 'ALL';
}

// getVisibleNav(user, moduleAccess?) — moduleAccess is OPTIONAL
// (tenants.module_access bag). When omitted/null, no module filtering is
// applied (backward compatible). When provided, groups/items tagged with a
// canonical module flag are hidden if the tenant lacks it (§9).
function getVisibleNav(user, moduleAccess) {
    var roleType = getUserRoleType(user);
    // SAG_MEMBER has no dashboard surface in scope — hide entirely (P4-6.2).
    if (roleType === 'SAG') return [];

    var normalized = null;
    if (moduleAccess !== undefined && moduleAccess !== null) {
        normalized = normalizeModuleAccess(moduleAccess);
    }

    var result = [];

    var keys = Object.keys(NAV_CONFIG);
    for (var i = 0; i < keys.length; i++) {
        var group = NAV_CONFIG[keys[i]];
        // Check if group is visible for this role
        if (group.roles.indexOf('ALL') === -1 && group.roles.indexOf(roleType) === -1) continue;
        // Module-flag gate at group level (§9: hide nav group when module off)
        if (normalized && !moduleEnabled(normalized, group.module)) continue;

        var items = group.items.filter(function (item) {
            if (item.roles && item.roles.indexOf('ALL') === -1 && item.roles.indexOf(roleType) === -1) {
                return false;
            }
            if (normalized && !moduleEnabled(normalized, item.module)) return false;
            return true;
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

return {
    NAV_CONFIG: NAV_CONFIG,
    NAV_MODULE_FLAGS: NAV_MODULE_FLAGS,
    getUserRoleType: getUserRoleType,
    getVisibleNav: getVisibleNav,
    normalizeModuleAccess: normalizeModuleAccess,
};

}));
