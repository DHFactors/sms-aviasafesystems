/* ============================================================================
   FILE: tenant_context.js
   PATH: public/js/tenant_context.js
   VERSION: 1.0.0
   PURPOSE: Subdomain tenant resolver + demo-environment tenant switching.
            Exposes TenantResolver used across all pages for the active tenant
            slug, demo-persona selection (demo hosts only), and tenant
            metadata placeholders (#tenantTitle, #tenantLogo fallback).
   AUTHOR: AviaSAFE Systems
   ============================================================================ */

(function (global) {
    'use strict';

    // Hosts where the demo-persona switcher is available. On every other host
    // (production tenant subdomains) the tenant is strictly locked to the
    // subdomain and demo-switching controls are hidden.
    var DEMO_HOSTNAMES = ['demo.aviasafesystems.com'];

    // Reserved platform subdomains are NEVER treated as tenants. Visiting
    // a reserved host (e.g. www, app, sms) must not auto-scope the login to
    // `?tenant=<reserved>` or show a tenant badge on the root domain.
    var RESERVED_SUBDOMAINS = ['www', 'app', 'api', 'caan', 'admin', 'auth', 'docs', 'sms', 'demo', 'betasms', 'gap-analysis-ssp'];

    var DEMO_TENANT_STORAGE_KEY = (typeof global.storageKey === 'function')
        ? global.storageKey('demo_tenant')
        : 'aviasafe_demo_tenant';
    var DEFAULT_DEMO_TENANT = 'himalaya-airlines-demo';

    // Demo personas shown on the login page (beta/demo hosts only). Each maps
    // to a seeded demo tenant (or the CAAN regulator tenant for the ASSD/FSSD
    // directorates).
    var DEMO_PERSONAS = [
        { key: 'developer', label: 'Developer / System Admin', tenant: 'system' },
        { key: 'fishtail-safety',  label: 'Fishtail Air - Safety Manager',      tenant: 'fishtail-air' },
        { key: 'fishtail-145',     label: 'Fishtail Air - Part-145 Mx Manager', tenant: 'fishtail-air' },
        { key: 'fishtail-camo',    label: 'Fishtail Air - CAMO',                tenant: 'fishtail-air' },
        { key: 'fishtail-ops',     label: 'Fishtail Air - Flight Ops',          tenant: 'fishtail-air' },
        { key: 'fishtail-gops',    label: 'Fishtail Air - Ground Ops',          tenant: 'fishtail-air' },
        { key: 'nepalw-safety',    label: 'Nepal Wings - Safety Manager',       tenant: 'nepal-wings' },
        { key: 'nepalw-145',       label: 'Nepal Wings - Part-145 Mx Manager',  tenant: 'nepal-wings' },
        { key: 'nepalw-camo',      label: 'Nepal Wings - CAMO',                 tenant: 'nepal-wings' },
        { key: 'nepalw-ops',       label: 'Nepal Wings - Flight Ops',           tenant: 'nepal-wings' },
        { key: 'nepalw-gops',      label: 'Nepal Wings - Ground Ops',           tenant: 'nepal-wings' },
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
        // Also clear the auth-synced cache so a stale tenant never survives logout
        try {
            global.sessionStorage.removeItem(DEMO_TENANT_STORAGE_KEY + ':auth');
        } catch (e) { /* ignore */ }
        if (typeof global.__AUTH_TENANT_ID !== 'undefined') {
            try { global.__AUTH_TENANT_ID = null; } catch (e) { /* ignore */ }
        }
    }

    // ── Auth-synced tenant: the source of truth when a user is signed in ──
    // Dashboard pages must never show "air-dynasty-demo" when the signed-in user
    // is safety@fishtailair.com (tenant fishtail-air). The sessionStorage demo
    // persona is ONLY for pre-auth persona switching on the login page.
    function syncDemoTenantWithAuth(user) {
        // user: null (logout) OR { tenantId/tenant_id } OR string tenantId
        try {
            var tenantId = null;
            if (typeof user === 'string') tenantId = user;
            else if (user && (user.tenantId || user.tenant_id)) tenantId = user.tenantId || user.tenant_id;
            // SUPER_ADMIN / CAAN_SMD are cross-tenant — never pin a demo tenant
            var role = user && (user.role || (user.claims && user.claims.role));
            if (role === 'SUPER_ADMIN' || role === 'CAAN_SMD') {
                clearDemoTenant();
                return;
            }
            if (!tenantId) {
                // No tenant on user (logged out, or cross-tenant) — clear stale demo
                clearDemoTenant();
                return;
            }
            var normalized = normalizeTenantId(tenantId);
            // Write both the primary demo key and an auth-cache key so
            // getCurrentTenant() can return it synchronously on next load
            try {
                global.sessionStorage.setItem(DEMO_TENANT_STORAGE_KEY, normalized);
                global.sessionStorage.setItem(DEMO_TENANT_STORAGE_KEY + ':auth', normalized);
            } catch (e2) { /* ignore */ }
            try { global.__AUTH_TENANT_ID = normalized; } catch (e2) { /* ignore */ }
        } catch (e) { /* never block auth */ }
    }

    function getAuthTenantSync() {
        try {
            if (global.__AUTH_TENANT_ID) return global.__AUTH_TENANT_ID;
            // Fallback: check auth-cache key (survives reload within same tab)
            var cached = global.sessionStorage.getItem(DEMO_TENANT_STORAGE_KEY + ':auth');
            if (cached) {
                global.__AUTH_TENANT_ID = cached;
                return cached;
            }
        } catch (e) { /* ignore */ }
        return null;
    }

    // Clear copilot + demo session keys that must not survive a tenant switch.
    // Called on logout and on auth tenant mismatch.
    function clearTenantSession() {
        clearDemoTenant();
        // Copilot widget session limit counters (sessionStorage)
        try {
            var copilotKeys = [
                'aviasafe_copilot_message_count',
                // env-prefixed variant via storageKey('copilot_message_count')
                (typeof global.storageKey === 'function' ? global.storageKey('copilot_message_count') : null),
                'aviasafe:beta:copilot_message_count',
                'aviasafe:prod:copilot_message_count'
            ];
            copilotKeys.forEach(function (k) {
                if (k) global.sessionStorage.removeItem(k);
            });
            // Demo toolbar session flags
            global.sessionStorage.removeItem('demoToolbar');
            global.sessionStorage.removeItem('demoEnabledAt');
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
        // Authenticated users: tenant comes from Firebase auth claims, never from
        // a stale sessionStorage demo persona. This fixes the bug where
        // safety@fishtailair.com still saw "air-dynasty-demo" from a prior persona.
        var authTenant = getAuthTenantSync();
        if (authTenant) return normalizeTenantId(authTenant);
        // Also try synchronous currentUser check (claims may be cached on the
        // Firebase user object after getIdTokenResult has run once)
        try {
            if (global.firebase && global.firebase.auth && global.firebase.auth().currentUser) {
                var u = global.firebase.auth().currentUser;
                // __AUTH_TENANT_ID is set by syncDemoTenantWithAuth on every
                // successful getCurrentUser() / onAuthStateChanged — if present,
                // it already would have been returned above. No extra sync fetch here.
            }
        } catch (e) { /* ignore */ }

        if (isDemoEnvironment()) {
            var stored = getDemoTenant();
            if (stored) {
                // If we're authenticated but getAuthTenantSync missed (race),
                // don't blindly return the stale demo persona — let the caller
                // (ApiClient / dashboard) prefer the async auth tenant instead.
                // Return stored only for unauthenticated/demo persona flows.
                try {
                    var isAuthed = !!(global.firebase && global.firebase.auth && global.firebase.auth().currentUser);
                    if (isAuthed && authTenant === null) {
                        // Don't return demo persona when authed but auth tenant unknown
                        // — fallback to subdomain/default instead of wrong tenant
                        return DEFAULT_DEMO_TENANT;
                    }
                } catch (e2) { /* ignore */ }
                return normalizeTenantId(stored);
            }
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
        syncDemoTenantWithAuth: syncDemoTenantWithAuth,
        getAuthTenantSync: getAuthTenantSync,
        clearTenantSession: clearTenantSession,
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