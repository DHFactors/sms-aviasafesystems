/* ============================================================================
   FILE: department_resolver.js
   PATH: public/js/department_resolver.js
   VERSION: 1.0.0
   PURPOSE: Email-prefix -> department resolution used to derive the user's
            department context (hero subtitle, X-User-Department header) from
            the signed-in email before any custom claims arrive.
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

(function (global) {
    'use strict';

    // Prefix (the local part of the email, before @) -> department label.
    var DEPARTMENT_BY_PREFIX = {
        '145': 'Maintenance Department (Part-145)',
        'maintenance': 'Maintenance Department (Part-145)',
        'safety': 'Corporate Safety Department',
        'sms': 'Corporate Safety Department',
        'qa': 'Quality Assurance Department',
        'quality': 'Quality Assurance Department',
        'camo': 'CAMO / Technical Services',
        'flightops': 'Flight Operations Department',
        'ops': 'Flight Operations Department',
        'ground': 'Ground Operations Department',
        'ramp': 'Ground Operations Department',
        'cabin': 'Cabin Services Department',
        'assd': 'CAAN - Aerodrome Safety Standards Dept',
        'fssd': 'CAAN - Flight Safety Standards Dept',
    };

    var DEFAULT_DEPARTMENT = 'Operational Safety Unit';

    function resolveDepartmentFromEmail(email) {
        if (!email) return DEFAULT_DEPARTMENT;
        var local = String(email).split('@')[0].toLowerCase().trim();
        if (DEPARTMENT_BY_PREFIX[local]) return DEPARTMENT_BY_PREFIX[local];
        // Tolerate separators / suffixes, e.g. "145.mro" or "safety_desk".
        var tokens = local.split(/[^a-z0-9]+/);
        for (var i = 0; i < tokens.length; i++) {
            if (DEPARTMENT_BY_PREFIX[tokens[i]]) return DEPARTMENT_BY_PREFIX[tokens[i]];
        }
        return DEFAULT_DEPARTMENT;
    }

    // Populate #tenantTitle and #departmentSubtitle on dashboard init. Falls
    // back to #dashHeroTitle / #dashHeroUser / #shellHeroTitle / #shellHeroUser
    // so both the uniform hero and the shell hero are covered.
    async function applyDepartmentContext(userEmail) {
        var tenantId = null;
        var title = null;
        if (global.TenantResolver) {
            var ctx = await global.TenantResolver.applyTenantContext();
            tenantId = ctx.tenantId;
            title = ctx.title;
        }
        var dept = resolveDepartmentFromEmail(userEmail || '');

        if (global.document) {
            var subtitleEl = global.document.getElementById('departmentSubtitle') ||
                global.document.getElementById('dashHeroUser') ||
                global.document.getElementById('shellHeroUser');
            if (subtitleEl) subtitleEl.textContent = dept;

            if (title && !global.document.getElementById('tenantTitle')) {
                var titleEl = global.document.getElementById('dashHeroTitle') ||
                    global.document.getElementById('shellHeroTitle');
                if (titleEl) titleEl.textContent = title;
            }
        }

        return { tenantId: tenantId, title: title, department: dept };
    }

    global.resolveDepartmentFromEmail = resolveDepartmentFromEmail;
    global.applyDepartmentContext = applyDepartmentContext;
    global.DEPARTMENT_BY_PREFIX = DEPARTMENT_BY_PREFIX;
    global.DEFAULT_DEPARTMENT = DEFAULT_DEPARTMENT;

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            resolveDepartmentFromEmail: resolveDepartmentFromEmail,
            applyDepartmentContext: applyDepartmentContext,
            DEPARTMENT_BY_PREFIX: DEPARTMENT_BY_PREFIX,
            DEFAULT_DEPARTMENT: DEFAULT_DEPARTMENT,
        };
    }
})(typeof window !== 'undefined' ? window : globalThis);