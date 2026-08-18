/* ============================================================================
   FILE: tenant_context.js
   PATH: public/js/tenant_context.js
   VERSION: 1.0.0
   PURPOSE: Subdomain tenant resolver + demo-environment tenant switching.
            Exposes TenantResolver used across all pages for the active tenant
            slug, demo-persona selection (beta/demo hosts only), and tenant
            metadata placeholders (#tenantTitle, #tenantLogo fallback).
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

(function (global) {
    'use strict';

    // Hosts where the demo-persona switcher is available. On every other host
    // (production tenant subdomains) the tenant is strictly locked to the
    // subdomain and demo-switching controls are hidden.
    var DEMO_HOSTNAMES = ['sms-beta.web.app', 'demo.aviasafesystems.com', '127.0.0.1', 'localhost'];

    // Reserved platform subdomains are NEVER treated as tenants. Visiting
    // betasms.aviasafesystems.com (or any reserved host) must not auto-scope
    // the login to `?tenant=betasms` or show a tenant badge on the root domain.
    var RESERVED_SUBDOMAINS = ['www', 'app', 'api', 'caan', 'admin', 'auth', 'docs', 'sms', 'demo', 'betasms', 'sms-beta', 'gap-analysis-ssp', 'localhost'];

    var DEMO_TENANT_STORAGE_KEY = 'aviasafe_demo_tenant';
    var DEFAULT_DEMO_TENANT = 'himalaya-airlines-demo';

    // Demo personas shown on the login page (beta/demo hosts only). Each maps
    // to a seeded demo tenant (or the CAAN regulator tenant for the ASSD/FSSD
    // directorates).
    var DEMO_PERSONAS = [
        { key: 'developer', label: 'Developer / Super-Admin', tenant: 'developer' },
        { key: 'smd', label: 'SMD (Safety Management Dept - CAAN)', tenant: 'smd' },
        { key: 'fixed-wing', label: 'Fixed-Wing', tenant: 'himalaya-airlines-demo' },
        { key: 'rotary', label: 'Rotary', tenant: 'air-dynasty-demo' },
        { key: 'amo', label: 'AMO', tenant: 'nepal-aero-maintenance-demo' },
        { key: 'airport', label: 'Airport', tenant: 'tia-kathmandu-demo' },
        { key: 'assd', label: 'ASSD', tenant: 'caan' },
        { key: 'fssd', label: 'FSSD', tenant: 'caan' },
    ];

    // Subdomain -> Firestore tenant document id normalization. Public tenant
    // subdomains use a compact slug (buddhaair) while Firestore / the backend
    // use the hyphenated id (buddha-air).
    var SUBDOMAIN_TO_TENANT_ID = {
        'buddhaair': 'buddha-air',
        'airdynasty': 'air-dynasty',
        'ktmmro': 'ktm-mro',
        'pokhara': 'pokhara-aerodrome',
        'himalayaground': 'himalaya-ground-services',
        'yeti': 'yeti-airlines',
        'summit': 'summit-air',
        'sita': 'sita-air',
        'simrik': 'simrik-air',
        'tara': 'tara-air',
        'buddha-air': 'buddha-air',
        'air-dynasty': 'air-dynasty',
        'ktm-mro': 'ktm-mro',
        'pokhara-aerodrome': 'pokhara-aerodrome',
        'himalaya-ground-services': 'himalaya-ground-services',
        'yeti-airlines': 'yeti-airlines',
        'summit-air': 'summit-air',
        'sita-air': 'sita-air',
        'simrik-air': 'simrik-air',
        'tara-air': 'tara-air',
        'himalaya-airlines-demo': 'himalaya-airlines-demo',
        'yeti-tara-demo': 'yeti-tara-demo',
        'air-dynasty-demo': 'air-dynasty-demo',
        'nepal-aero-maintenance-demo': 'nepal-aero-maintenance-demo',
        'tia-kathmandu-demo': 'tia-kathmandu-demo',
        'caan': 'caan',
        'caan-assd': 'caan-assd',
        'caan-fssd': 'caan-fssd',
    };

    // Tenant id -> formal operational classification (mirrors the backend
    // OperationalScope enum in app/models/tenant_profile.py). Used to drive
    // department / prefix resolution and flight-scope-aware taxonomy.
    var TENANT_CLASSIFICATION = {
        'buddha-air': 'AIRLINE_FIXED_WING',
        'yeti-airlines': 'AIRLINE_FIXED_WING',
        'summit-air': 'AIRLINE_FIXED_WING',
        'sita-air': 'AIRLINE_FIXED_WING',
        'tara-air': 'AIRLINE_FIXED_WING',
        'himalaya-airlines-demo': 'AIRLINE_FIXED_WING',
        'yeti-tara-demo': 'AIRLINE_FIXED_WING',
        'air-dynasty': 'AIRLINE_ROTARY',
        'simrik-air': 'AIRLINE_ROTARY',
        'air-dynasty-demo': 'AIRLINE_ROTARY',
        'ktm-mro': 'AMO',
        'nepal-aero-maintenance-demo': 'AMO',
        'pokhara-aerodrome': 'AERODROME',
        'tia-kathmandu-demo': 'AERODROME',
        'himalaya-ground-services': 'GROUND_HANDLING',
        'caan': 'REGULATOR',
        'caan-assd': 'REGULATOR',
        'caan-fssd': 'REGULATOR',
        'smd': 'REGULATOR',
    };

    function getHostname() {
        return (global.location && global.location.hostname) || '';
    }

    function isDemoEnvironment() {
        return DEMO_HOSTNAMES.indexOf(getHostname().toLowerCase()) !== -1;
    }

    function getTenantFromSubdomain() {
        var parts = getHostname().split('.');
        if (parts.length >= 2 && parts[1] === 'aviasafesystems') {
            var sub = parts[0];
            // Reserved platform subdomains are never tenants — return null
            // WITHOUT falling back to the ?tenant= query param so the login
            // never auto-fills or redirects to ?tenant=betasms on root hosts.
            if (RESERVED_SUBDOMAINS.indexOf(sub) !== -1) return null;
            return sub;
        }
        try {
            var params = new URLSearchParams(global.location.search);
            return params.get('tenant') || null;
        } catch (e) {
            return null;
        }
    }

    function getDemoTenant() {
        try {
            return global.sessionStorage.getItem(DEMO_TENANT_STORAGE_KEY);
        } catch (e) {
            return null;
        }
    }

    function setDemoTenant(slug) {
        if (!isDemoEnvironment()) return false;
        try {
            global.sessionStorage.setItem(DEMO_TENANT_STORAGE_KEY, slug);
            return true;
        } catch (e) {
            return false;
        }
    }

    function clearDemoTenant() {
        try {
            global.sessionStorage.removeItem(DEMO_TENANT_STORAGE_KEY);
        } catch (e) { /* ignore */ }
    }

    function normalizeTenantId(slug) {
        if (!slug) return null;
        return SUBDOMAIN_TO_TENANT_ID[slug] || slug;
    }

    // Return the formal operational classification for a tenant (mirrors the
    // backend OperationalScope enum). Falls back to a best-effort inference
    // from the id so unknown demo tenants still resolve sensibly.
    function getTenantClassification(tenantId) {
        if (!tenantId) return null;
        if (TENANT_CLASSIFICATION[tenantId]) return TENANT_CLASSIFICATION[tenantId];
        var id = String(tenantId).toLowerCase();
        if (id.indexOf('mro') !== -1 || id.indexOf('maintenance') !== -1) return 'AMO';
        if (id.indexOf('aerodrome') !== -1 || id.indexOf('airport') !== -1 || id.indexOf('heliport') !== -1) return 'AERODROME';
        if (id.indexOf('ground') !== -1 || id.indexOf('handling') !== -1) return 'GROUND_HANDLING';
        if (id.indexOf('caan') !== -1 || id.indexOf('smd') !== -1) return 'REGULATOR';
        if (id.indexOf('heli') !== -1 || id.indexOf('rotor') !== -1) return 'AIRLINE_ROTARY';
        return 'AIRLINE_FIXED_WING';
    }

    function getCurrentTenant() {
        if (isDemoEnvironment()) {
            var stored = getDemoTenant();
            if (stored) return normalizeTenantId(stored);
            return DEFAULT_DEMO_TENANT;
        }
        var sub = getTenantFromSubdomain();
        if (sub) return normalizeTenantId(sub);
        try {
            var params = new URLSearchParams(global.location.search);
            return params.get('tenant') || null;
        } catch (e) {
            return null;
        }
    }

    function prettifySlug(slug) {
        return String(slug || '')
            .replace(/[-_]/g, ' ')
            .replace(/\b\w/g, function (c) { return c.toUpperCase(); });
    }

    // Resolve the tenant display name: seeded profile (tenant_name) -> tenant
    // doc (name / tenant_name) -> prettified slug fallback.
    async function resolveTenantTitle(tenantId) {
        if (!tenantId) return null;
        try {
            if (global.db && global.db.collection) {
                var profileRef = global.db.collection('tenants').doc(tenantId).collection('profile').doc('operational');
                var snap = await profileRef.get();
                if (snap.exists && snap.data().tenant_name) return snap.data().tenant_name;
                var tenantRef = global.db.collection('tenants').doc(tenantId);
                var t = await tenantRef.get();
                if (t.exists) {
                    var d = t.data() || {};
                    if (d.name) return d.name;
                    if (d.tenant_name) return d.tenant_name;
                    if (d.display_name) return d.display_name;
                }
            }
        } catch (e) {
            // Fall through to the slug-based fallback.
        }
        return prettifySlug(tenantId);
    }

    // Populate #tenantTitle (with #dashHeroTitle / #shellHeroTitle fallbacks),
    // set the data-tenant attribute, and install the #tenantLogo fallback.
    async function applyTenantContext() {
        var tenantId = getCurrentTenant();
        if (!tenantId) return { tenantId: tenantId, title: null };
        if (global.document && global.document.documentElement) {
            global.document.documentElement.setAttribute('data-tenant', tenantId);
        }
        var title = await resolveTenantTitle(tenantId);
        if (global.document) {
            var titleEl = global.document.getElementById('tenantTitle') ||
                global.document.getElementById('dashHeroTitle') ||
                global.document.getElementById('shellHeroTitle');
            if (titleEl) titleEl.textContent = title;
            handleTenantLogo();
        }
        return { tenantId: tenantId, title: title };
    }

    function handleTenantLogo() {
        var logo = global.document.getElementById('tenantLogo');
        if (!logo) return;
        if (logo.tagName === 'IMG') {
            logo.onerror = function () { logo.src = '/img/logo-default.png'; };
            if (!logo.getAttribute('src')) logo.src = '/img/logo-default.png';
        }
    }

    var TenantResolver = {
        DEMO_HOSTNAMES: DEMO_HOSTNAMES,
        DEMO_PERSONAS: DEMO_PERSONAS,
        DEFAULT_DEMO_TENANT: DEFAULT_DEMO_TENANT,
        isDemoEnvironment: isDemoEnvironment,
        getTenantFromSubdomain: getTenantFromSubdomain,
        getCurrentTenant: getCurrentTenant,
        getDemoTenant: getDemoTenant,
        setDemoTenant: setDemoTenant,
        clearDemoTenant: clearDemoTenant,
        normalizeTenantId: normalizeTenantId,
        getTenantClassification: getTenantClassification,
        prettifySlug: prettifySlug,
        resolveTenantTitle: resolveTenantTitle,
        applyTenantContext: applyTenantContext,
    };

    global.TenantResolver = TenantResolver;
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = TenantResolver;
    }
})(typeof window !== 'undefined' ? window : globalThis);