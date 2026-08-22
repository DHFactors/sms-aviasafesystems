// Chunk 8 manual-matrix automation (routing + branding per account).
const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');

// Browser shim BEFORE any script evaluation.
const storage = {};
global.window = {
    location: { search: '', pathname: '/login.html' },
    localStorage: {
        getItem: k => (k in storage ? storage[k] : null),
        setItem: (k, v) => { storage[k] = String(v); },
        removeItem: k => { delete storage[k]; },
    },
};
global.document = {
    readyState: 'complete',
    addEventListener: () => {},
    createElement: () => ({ style: {}, appendChild: () => {}, addEventListener: () => {} }),
    body: { appendChild: () => {} },
};

new Function(fs.readFileSync(path.join(root, 'public/js/demo-prospects.js'), 'utf8')).call(global.window);

let fbSrc = fs.readFileSync(path.join(root, 'public/js/firebase.js'), 'utf8')
    .replace("console.log('📦 firebase.js loaded');", '')
    + '\n;window.__fb = { getRoleDestination, resolveTenantContext, formatReference };';
new Function('window', fbSrc).call(global.window, global.window);
const fb = global.window.__fb;

const MATRIX = [
    ['ae@buddha-air.com',  '/dashboard/ae-dashboard.html', 'demo-fixed-wing',  'Buddha Air',   'BA'],
    ['ae@yetiairlines.com','/dashboard/ae-dashboard.html', 'demo-fixed-wing',  'Yeti Airlines','YT'],
    ['ae@fishtailair.com', '/dashboard/ae-dashboard.html', 'demo-rotary-wing', 'Fishtail Air', 'FA'],
    ['ae@manangair.com',   '/dashboard/ae-dashboard.html', 'demo-rotary-wing', 'Manang Air',   'MA'],
];
let fails = 0;
for (const [email, dest, archetype, company, iata] of MATRIX) {
    const d = fb.getRoleDestination({ role: 'AIRLINE_ADMIN', email });
    const ctx = fb.resolveTenantContext({ email });
    const formatted = fb.formatReference('FW-HZ-0001-26', ctx.iataCode);
    const ok = d === dest && ctx.archetypeId === archetype &&
               ctx.companyName === company && ctx.iataCode === iata &&
               formatted === iata + '-HZ-0001-26';
    console.log(`[${ok ? 'PASS' : 'FAIL'}] ${email} -> ${d} | ${ctx.archetypeId} | ${ctx.companyName} | ${ctx.iataCode} | ${formatted}`);
    if (!ok) fails++;
}

// Standard tenants unaffected.
const std = [
    [{ role: 'AIRLINE_ADMIN', email: 'safety@buddha-air.com' }, '/safety.html'],
    [{ role: 'USER', email: '145@fishtailair.com', claims: { department: 'Part-145' } }, '/dashboard/responsible-manager.html'],
    [{ role: 'CAAN_SMD', email: 'smd@caanepal.gov.np' }, '/caan.html'],
];
for (const [u, expected] of std) {
    const d = fb.getRoleDestination(u);
    const ok = d === expected;
    console.log(`[${ok ? 'PASS' : 'FAIL'}] standard ${u.email} -> ${d}`);
    if (!ok) fails++;
}

console.log(fails ? `MATRIX FAILURES: ${fails}` : 'MATRIX ALL PASS');
process.exit(fails ? 1 : 0);
