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

    var RESERVED_SUBDOMAINS = ['www', 'app', 'api', 'caan', 'admin', 'auth', 'docs', 'sms', 'demo'];

    var DEMO_TENANT_STORAGE_KEY = 'aviasafe_demo_tenant';
    var DEFAULT_DEMO_TENANT = 'himalaya-airlines-demo';

    // Demo personas shown on the login page (beta/demo hosts only). Each maps
    // to a seeded demo tenant (or the CAAN regulator tenant for the ASSD/FSSD
    // directorates).
    var DEMO_PERSONAS = [
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
            if (RESERVED_SUBDOMAINS.indexOf(sub) === -1) return sub;
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
        prettifySlug: prettifySlug,
        resolveTenantTitle: resolveTenantTitle,
        applyTenantContext: applyTenantContext,
    };

    global.TenantResolver = TenantResolver;
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = TenantResolver;
    }
})(typeof window !== 'undefined' ? window : globalThis);