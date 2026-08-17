/**
 * Frontend unit tests for TenantResolver (public/js/tenant_context.js) and the
 * email->department resolver (public/js/department_resolver.js).
 *
 * Both modules are plain JS (no firebase / DOM framework) so they can be
 * exercised in Node with a minimal window/location/sessionStorage shim.
 */
'use strict';

const assert = require('assert');
const TenantResolver = require('../public/js/tenant_context.js');
const {
    resolveDepartmentFromEmail,
    applyDepartmentContext,
    DEFAULT_DEPARTMENT,
} = require('../public/js/department_resolver.js');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let originalLocation = null;
let originalSessionStorage = null;

function setHostname(hostname) {
    global.location = { hostname, search: '', toString: () => hostname };
}

function makeSessionStorage() {
    const store = {};
    return {
        getItem: (k) => (k in store ? store[k] : null),
        setItem: (k, v) => { store[k] = String(v); },
        removeItem: (k) => { delete store[k]; },
        __store: store,
    };
}

function withEnv(hostname, fn) {
    originalLocation = global.location;
    originalSessionStorage = global.sessionStorage;
    setHostname(hostname);
    global.sessionStorage = makeSessionStorage();
    try {
        return fn();
    } finally {
        global.location = originalLocation;
        global.sessionStorage = originalSessionStorage;
    }
}

function makeDoc() {
    const els = {};
    const get = (id) => {
        if (!els[id]) els[id] = { textContent: '', dataset: {}, style: {} };
        return els[id];
    };
    return {
        getElementById: get,
        documentElement: { setAttribute() {} },
        __els: els,
    };
}

// ---------------------------------------------------------------------------
// resolveDepartmentFromEmail
// ---------------------------------------------------------------------------

function test_email_department_mapping() {
    const cases = {
        '145@buddha-air.com': 'Maintenance Department (Part-145)',
        'maintenance@buddha-air.com': 'Maintenance Department (Part-145)',
        'safety@buddha-air.com': 'Corporate Safety Department',
        'sms@buddha-air.com': 'Corporate Safety Department',
        'qa@buddha-air.com': 'Quality Assurance Department',
        'quality@buddha-air.com': 'Quality Assurance Department',
        'camo@buddha-air.com': 'CAMO / Technical Services',
        'flightops@buddha-air.com': 'Flight Operations Department',
        'ops@buddha-air.com': 'Flight Operations Department',
        'ground@buddha-air.com': 'Ground Operations Department',
        'ramp@buddha-air.com': 'Ground Operations Department',
        'cabin@buddha-air.com': 'Cabin Services Department',
        'assd@caanepal.gov.np': 'CAAN - Aerodrome Safety Standards Dept',
        'fssd@caanepal.gov.np': 'CAAN - Flight Safety Standards Dept',
    };
    Object.keys(cases).forEach((email) => {
        assert.strictEqual(resolveDepartmentFromEmail(email), cases[email], `mapping for ${email}`);
    });
}

function test_email_department_fallbacks() {
    assert.strictEqual(resolveDepartmentFromEmail(''), DEFAULT_DEPARTMENT);
    assert.strictEqual(resolveDepartmentFromEmail(null), DEFAULT_DEPARTMENT);
    assert.strictEqual(resolveDepartmentFromEmail('unknown@buddha-air.com'), DEFAULT_DEPARTMENT);
    assert.strictEqual(resolveDepartmentFromEmail('safety_desk@x.com'), 'Corporate Safety Department', 'tokenized suffix match');
    assert.strictEqual(resolveDepartmentFromEmail('145.mro@x.com'), 'Maintenance Department (Part-145)', 'dotted prefix match');
}

// ---------------------------------------------------------------------------
// TenantResolver - demo environment detection
// ---------------------------------------------------------------------------

function test_demo_environment_detection() {
    withEnv('sms-beta.web.app', () => assert.strictEqual(TenantResolver.isDemoEnvironment(), true));
    withEnv('demo.aviasafesystems.com', () => assert.strictEqual(TenantResolver.isDemoEnvironment(), true));
    withEnv('127.0.0.1', () => assert.strictEqual(TenantResolver.isDemoEnvironment(), true));
    withEnv('localhost', () => assert.strictEqual(TenantResolver.isDemoEnvironment(), true));
    withEnv('buddhaair.aviasafesystems.com', () => assert.strictEqual(TenantResolver.isDemoEnvironment(), false));
    withEnv('aerosafety-sms-prod.web.app', () => assert.strictEqual(TenantResolver.isDemoEnvironment(), false));
}

// ---------------------------------------------------------------------------
// TenantResolver - subdomain extraction
// ---------------------------------------------------------------------------

function test_subdomain_extraction() {
    withEnv('buddhaair.aviasafesystems.com', () => {
        assert.strictEqual(TenantResolver.getTenantFromSubdomain(), 'buddhaair');
    });
    withEnv('www.aviasafesystems.com', () => {
        assert.strictEqual(TenantResolver.getTenantFromSubdomain(), null, 'reserved subdomain');
    });
    withEnv('sms.aviasafesystems.com', () => {
        assert.strictEqual(TenantResolver.getTenantFromSubdomain(), null, 'reserved subdomain');
    });
    withEnv('aerosafety-sms-prod.web.app', () => {
        assert.strictEqual(TenantResolver.getTenantFromSubdomain(), null, 'no tenant subdomain');
    });
}

// ---------------------------------------------------------------------------
// TenantResolver - current tenant resolution
// ---------------------------------------------------------------------------

function test_current_tenant_prod_locks_to_subdomain() {
    withEnv('buddhaair.aviasafesystems.com', () => {
        assert.strictEqual(TenantResolver.getCurrentTenant(), 'buddha-air', 'normalizes subdomain slug');
    });
    withEnv('ktmmro.aviasafesystems.com', () => {
        assert.strictEqual(TenantResolver.getCurrentTenant(), 'ktm-mro');
    });
}

function test_current_tenant_demo_uses_default() {
    withEnv('sms-beta.web.app', () => {
        assert.strictEqual(TenantResolver.getCurrentTenant(), 'himalaya-airlines-demo');
    });
}

function test_current_tenant_demo_toggle_via_session() {
    withEnv('sms-beta.web.app', () => {
        assert.strictEqual(TenantResolver.setDemoTenant('air-dynasty-demo'), true);
        assert.strictEqual(TenantResolver.getCurrentTenant(), 'air-dynasty-demo');
        TenantResolver.clearDemoTenant();
        assert.strictEqual(TenantResolver.getCurrentTenant(), 'himalaya-airlines-demo');
    });
}

function test_prod_subdomain_rejects_demo_toggle() {
    withEnv('buddhaair.aviasafesystems.com', () => {
        assert.strictEqual(TenantResolver.setDemoTenant('air-dynasty-demo'), false, 'toggle refused on prod');
        assert.strictEqual(TenantResolver.getCurrentTenant(), 'buddha-air', 'locked to subdomain');
    });
}

// ---------------------------------------------------------------------------
// TenantResolver - display helpers
// ---------------------------------------------------------------------------

function test_prettify_slug() {
    assert.strictEqual(TenantResolver.prettifySlug('buddha-air'), 'Buddha Air');
    assert.strictEqual(TenantResolver.prettifySlug('tia-kathmandu-demo'), 'Tia Kathmandu Demo');
    assert.strictEqual(TenantResolver.prettifySlug(''), '');
}

// ---------------------------------------------------------------------------
// applyDepartmentContext - populates #tenantTitle + #departmentSubtitle
// ---------------------------------------------------------------------------

function test_apply_department_context() {
    return withEnv('buddhaair.aviasafesystems.com', async () => {
        const doc = makeDoc();
        const realGet = global.document;
        global.document = doc;
        try {
            const result = await applyDepartmentContext('145@buddha-air.com');
            assert.strictEqual(result.department, 'Maintenance Department (Part-145)');
            assert.strictEqual(result.tenantId, 'buddha-air');
            assert.strictEqual(doc.__els.departmentSubtitle.textContent, 'Maintenance Department (Part-145)');
            assert.ok(doc.__els.tenantTitle.textContent.length > 0, 'tenant title populated');
        } finally {
            global.document = realGet;
        }
    });
}

// ---------------------------------------------------------------------------

function main() {
    test_email_department_mapping();
    test_email_department_fallbacks();
    test_demo_environment_detection();
    test_subdomain_extraction();
    test_current_tenant_prod_locks_to_subdomain();
    test_current_tenant_demo_uses_default();
    test_current_tenant_demo_toggle_via_session();
    test_prod_subdomain_rejects_demo_toggle();
    test_prettify_slug();
    test_apply_department_context().then(() => {
        console.log('tenant_context + department_resolver: tests passed');
    });
}

main();