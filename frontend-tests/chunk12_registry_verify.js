// Chunk 12 verification: PROSPECT_REGISTRY completeness + helper contract.
const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');

const storage = {};
global.window = {
    location: { search: '', pathname: '/login.html' },
    localStorage: { getItem: k => (k in storage ? storage[k] : null), setItem: () => {}, removeItem: () => {} },
};
global.document = { readyState: 'complete', addEventListener: () => {}, createElement: () => ({ style: {}, appendChild: () => {}, addEventListener: () => {} }), body: { appendChild: () => {} } };

new Function(fs.readFileSync(path.join(root, 'public/js/demo-prospects.js'), 'utf8')).call(global.window);
const dp = global.window.DEMO_PROSPECTS;

let fails = 0;
const assert = (cond, msg) => { console.log(`[${cond ? 'PASS' : 'FAIL'}] ${msg}`); if (!cond) fails++; };

// ── Registry size & group split ────────────────────────────────────────────
const keys = Object.keys(dp.PROSPECT_REGISTRY);
assert(keys.length === 20, `20 operators registered (got ${keys.length})`);
const fw = keys.filter(k => dp.PROSPECT_REGISTRY[k].archetypeId === 'demo-fixed-wing');
const rw = keys.filter(k => dp.PROSPECT_REGISTRY[k].archetypeId === 'demo-rotary-wing');
assert(fw.length === 10 && rw.length === 10, `10 fixed-wing / 10 rotary-wing split`);

// ── Per-entry field contract ───────────────────────────────────────────────
const REQUIRED = ['archetypeId', 'companyName', 'aeName', 'fleetType', 'baseLocation', 'iataCode'];
for (const email of keys) {
    const p = dp.PROSPECT_REGISTRY[email];
    for (const f of REQUIRED) assert(p[f] !== undefined && p[f] !== '', `${email}.${f} present`);
    assert(email.startsWith('ae@'), `${email} uses ae@ prefix`);
}

// ── Exact entries from the chunk spec ──────────────────────────────────────
const SPEC = [
    ['ae@buddha-air.com',   'Buddha Air',           'Mr. Birendra Basnet', 'ATR 72-500',      'BA'],
    ['ae@yetiairlines.com', 'Yeti Airlines',        'Executive Name',      'ATR 72-500',      'YT'],
    ['ae@shreeairlines.com','Shree Airlines',       'Executive Name',      'ATR 72-500',      'SH'],
    ['ae@simrikair.com',    'Simrik Air',           'Executive Name',      'ATR 72-500',      'SM'],
    ['ae@sauryaairlines.com','Saurya Airlines',     'Executive Name',      'ATR 72-500',      'SA'],
    ['ae@taraair.com',      'Tara Air',             'Executive Name',      'Dornier 228 (STOL)', 'TA'],
    ['ae@summitair.com',    'Summit Air',           'Executive Name',      'ATR 72-500',      'SU'],
    ['ae@kailashair.com',   'Kailash Air',          'Executive Name',      'Dornier 228',     'KA'],
    ['ae@mountainair.com',  'Mountain Air',         'Executive Name',      'Dornier 228',     'MT'],
    ['ae@airdynasty.com',   'Air Dynasty',          'Executive Name',      'ATR 72-500',      'AD'],
    ['ae@fishtailair.com',  'Fishtail Air',         'Executive Name',      'H125 (AS350 B3e)', 'FA'],
    ['ae@manangair.com',    'Manang Air',           'Executive Name',      'H125',            'MA'],
    ['ae@altitudeair.com',  'Altitude Air',         'Executive Name',      'H125/Bell 206',   'AL'],
    ['ae@prabhuheli.com',   'Prabhu Helicopter',    'Executive Name',      'H125',            'PH'],
    ['ae@simrikheli.com',   'Simrik Helicopter',    'Executive Name',      'H125',            'SH'],
    ['ae@kailashheli.com',  'Kailash Helicopter',   'Executive Name',      'Bell 206',        'KH'],
    ['ae@mountainheli.com', 'Mountain Helicopter',  'Executive Name',      'H125',            'MH'],
    ['ae@fishtailheli.com', 'Fishtail Helicopter',  'Executive Name',      'H125',            'FH'],
    ['ae@airvip.com',       'Air VIP',              'Executive Name',      'H125',            'AV'],
    ['ae@eagleheli.com',    'Eagle Helicopter',     'Executive Name',      'H125',            'EH'],
];
for (const [email, company, aeName, fleet, iata] of SPEC) {
    const p = dp.PROSPECT_REGISTRY[email];
    const ok = p &&
        p.companyName === company &&
        p.aeName === aeName &&
        p.fleetType === fleet &&
        p.iataCode === iata;
    assert(ok, `${email} matches chunk spec (${company} / ${iata})`);
}

// ── Helper contract ─────────────────────────────────────────────────────────
const fa = dp.getProspectByEmail('AE@FISHTAILAIR.COM'); // case-insensitive
assert(fa && fa.iataCode === 'FA', 'getProspectByEmail case-insensitive lookup');
assert(dp.getProspectByEmail('unknown@x.com') === null, 'unknown email -> null');
assert(dp.getArchetypeId('ae@buddha-air.com') === 'demo-fixed-wing', 'getArchetypeId fixed-wing');
assert(dp.getArchetypeId('ae@fishtailair.com') === 'demo-rotary-wing', 'getArchetypeId rotary-wing');
assert(dp.formatReference('FW-HZ-0007-26', 'BA') === 'BA-HZ-0007-26', 'formatReference FW swap');
assert(dp.formatReference('RW-CAN-0003-26', 'FA') === 'FA-CAN-0003-26', 'formatReference RW swap');

console.log(fails ? `\nRESULT: ${fails} FAILURES` : '\nRESULT: CHUNK 12 FULLY SATISFIED BY EXISTING IMPLEMENTATION');
process.exit(fails ? 1 : 0);
