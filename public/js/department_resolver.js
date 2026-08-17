/* ============================================================================
   FILE: department_resolver.js
   PATH: public/js/department_resolver.js
   VERSION: 1.1.0
   PURPOSE: Email-prefix -> department resolution used to derive the user's
            department context (hero subtitle, X-User-Department header) from
            the signed-in email before any custom claims arrive.
            Tenant-context aware: department applicability adapts to the
            tenant's operational classification (AIRLINE_FIXED_WING /
            AIRLINE_ROTARY / AMO / AERODROME / GROUND_HANDLING / REGULATOR).
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

(function (global) {
    'use strict';

    // Generic prefix -> department label (used when no tenant context is
    // available, i.e. the caller passes no tenant id / resolver).
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
        'smd': 'CAAN - Safety Management Department (SMD)',
        'assd': 'CAAN - Aerodrome Safety Standards Dept',
        'fssd': 'CAAN - Flight Safety Standards Dept',
    };

    // Classification-aware prefix maps. Each classification exposes only the
    // departments its operational structure may hold.
    //
    // * Airlines: flight_ops + camo + safety + qa.
    // * AMO: base/line maintenance (145) + qa + safety. NO flight ops / CAMO.
    // * Aerodrome: airside ops + ARFF + safety/qa. NO flight ops / CAMO / 145.
    // * Ground handling: ground ops + qa + safety.
    // * Regulator (CAAN directorate): SMD / FSSD / ASSD oversight + safety.
    //
    // safety@ and qa@ stay universal SMS/QA endpoints across every class.
    var PREFIX_BY_CLASSIFICATION = {
        AIRLINE_FIXED_WING: {
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
        },
        AIRLINE_ROTARY: {
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
        },
        AMO: {
            '145': 'Part-145 Maintenance Department',
            'maintenance': 'Part-145 Maintenance Department',
            'safety': 'Corporate Safety Department',
            'sms': 'Corporate Safety Department',
            'qa': 'Quality Assurance Department',
            'quality': 'Quality Assurance Department',
            'base': 'Base Maintenance Department',
            'line': 'Line Maintenance Department',
            'workshop': 'Component Workshop',
        },
        AERODROME: {
            'airside': 'Airside Operations',
            'safety': 'Aerodrome Safety Office',
            'sms': 'Aerodrome Safety Office',
            'qa': 'Quality Assurance Department',
            'quality': 'Quality Assurance Department',
            'arff': 'Rescue & Firefighting (ARFF)',
            'apron': 'Apron Control',
            'ground': 'Ground Operations',
            'ramp': 'Ground Operations',
        },
        GROUND_HANDLING: {
            'ground': 'Ground Operations Department',
            'ramp': 'Ground Operations Department',
            'safety': 'Ground Safety Office',
            'sms': 'Ground Safety Office',
            'qa': 'Quality Assurance Department',
            'quality': 'Quality Assurance Department',
        },
        REGULATOR: {
            'smd': 'CAAN - Safety Management Department (SMD)',
            'fssd': 'CAAN - Flight Safety Standards Dept',
            'assd': 'CAAN - Aerodrome Safety Standards Dept',
            'safety': 'CAAN - Safety Oversight',
            'sms': 'CAAN - Safety Oversight',
        },
    };

    // ICAO ADREP categories that only apply to AOC-holding airlines.
    var FLIGHT_ONLY_CATEGORIES = ['LOCI', 'CFIT', 'MAC', 'ARC', 'WX'];

    var ALL_OCCURRENCE_CATEGORIES = [
        'ARC', 'MAC', 'BIRD', 'CABIN', 'CFIT', 'ENG', 'FIRE', 'GCOL',
        'LOCI', 'PRO', 'RE', 'RI', 'SYS', 'WX', 'OTHER',
    ];

    var DEFAULT_DEPARTMENT = 'Operational Safety Unit';

    // Resolve the tenant's classification via TenantResolver when present.
    function getClassification(tenantId) {
        if (!tenantId) return null;
        if (global.TenantResolver && global.TenantResolver.getTenantClassification) {
            var cls = global.TenantResolver.getTenantClassification(tenantId);
            if (cls) return cls;
        }
        return null;
    }

    function resolveDepartmentFromEmail(email, tenantId) {
        if (!email) return DEFAULT_DEPARTMENT;
        var local = String(email).split('@')[0].toLowerCase().trim();

        var map = DEPARTMENT_BY_PREFIX;
        var cls = getClassification(tenantId);
        if (cls && PREFIX_BY_CLASSIFICATION[cls]) {
            map = PREFIX_BY_CLASSIFICATION[cls];
        }

        if (map[local]) return map[local];
        // Tolerate separators / suffixes, e.g. "145.mro" or "safety_desk".
        var tokens = local.split(/[^a-z0-9]+/);
        for (var i = 0; i < tokens.length; i++) {
            if (map[tokens[i]]) return map[tokens[i]];
        }
        return DEFAULT_DEPARTMENT;
    }

    // ICAO ADREP categories applicable to a tenant's reporting forms. Flight-
    // specific categories populate only for airlines; non-flying providers
    // (AMO, aerodrome, ground handling, regulator) get the ground/maintenance
    // taxonomy. Falls back to the full list when classification is unknown.
    function getApplicableOccurrenceCategories(tenantId) {
        var cls = getClassification(tenantId);
        if (!cls) return ALL_OCCURRENCE_CATEGORIES.slice();
        if (cls === 'AIRLINE_FIXED_WING' || cls === 'AIRLINE_ROTARY') {
            return ALL_OCCURRENCE_CATEGORIES.slice();
        }
        return ALL_OCCURRENCE_CATEGORIES.filter(function (c) {
            return FLIGHT_ONLY_CATEGORIES.indexOf(c) === -1;
        });
    }

    function operatesFlights(tenantId) {
        var cls = getClassification(tenantId);
        return cls === 'AIRLINE_FIXED_WING' || cls === 'AIRLINE_ROTARY';
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
        var dept = resolveDepartmentFromEmail(userEmail || '', tenantId);

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
    global.PREFIX_BY_CLASSIFICATION = PREFIX_BY_CLASSIFICATION;
    global.DEFAULT_DEPARTMENT = DEFAULT_DEPARTMENT;
    global.getApplicableOccurrenceCategories = getApplicableOccurrenceCategories;
    global.operatesFlights = operatesFlights;

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            resolveDepartmentFromEmail: resolveDepartmentFromEmail,
            applyDepartmentContext: applyDepartmentContext,
            DEPARTMENT_BY_PREFIX: DEPARTMENT_BY_PREFIX,
            PREFIX_BY_CLASSIFICATION: PREFIX_BY_CLASSIFICATION,
            DEFAULT_DEPARTMENT: DEFAULT_DEPARTMENT,
            getApplicableOccurrenceCategories: getApplicableOccurrenceCategories,
            operatesFlights: operatesFlights,
        };
    }
})(typeof window !== 'undefined' ? window : globalThis);