// Chunk 5 regression: AE dashboard personalization + reference DOM scanner.
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'public/dashboard/ae-dashboard.html'), 'utf8');

const blocks = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const inline = blocks[blocks.length - 1];

const storage = {};
const mkStorage = () => ({
    getItem: k => (k in storage ? storage[k] : null),
    setItem: (k, v) => { storage[k] = String(v); },
    removeItem: k => { delete storage[k]; },
});
const elems = {};
function mkEl(id) {
    return elems[id] || (elems[id] = {
        id, textContent: '', innerHTML: '', value: '', style: {}, href: '',
        classList: { toggle: () => {}, add: () => {}, remove: () => {} },
        addEventListener: () => {}, appendChild: () => {}, querySelector: () => null,
        querySelectorAll: () => [],
    });
}
global.document = {
    title: '',
    readyState: 'complete',
    getElementById: id => mkEl(id),
    querySelector: sel => (sel === '.nav h1' ? mkEl('navH1') : null),
    querySelectorAll: () => [],
    createTreeWalker: () => ({ nextNode: () => false, currentNode: null }),
    createElement: tag => mkEl('dyn-' + tag + Math.random()),
    body: { appendChild: () => {} },
};
global.window = { location: { search: '', pathname: '/dashboard/ae-dashboard.html' }, localStorage: mkStorage(), sessionStorage: mkStorage() };
global.localStorage = global.window.localStorage;
global.sessionStorage = global.window.sessionStorage;
global.NodeFilter = { SHOW_TEXT: 4 };
global.URLSearchParams = URLSearchParams;
global.firebase = { auth: () => ({ onAuthStateChanged: () => {} }) };

new Function(fs.readFileSync(path.join(root, 'public/js/demo-prospects.js'), 'utf8')).call(global.window);

let src = inline
    .replace("firebase.auth().onAuthStateChanged(async function(user) {", "async function __auth(user) {")
    .replace("});\n\nfunction logout()", "}\n\nfunction logout()")
    .replace("window.__aeRefresh = loadDashboard;", "");
src = "function getStoredDemoContext(){ try { return JSON.parse(localStorage.getItem('demoContext')); } catch(e){ return null; } }\n" + src;

const api = new Function('window', 'document', 'localStorage', 'sessionStorage', 'NodeFilter', src +
    '; return { applyPersonalization, formatAllReferences };')
    .call(global.window, global.window, global.document, global.window.localStorage, global.window.sessionStorage, global.NodeFilter);

const assert = (cond, msg) => { if (!cond) { console.error('FAIL:', msg); process.exit(1); } console.log('ok -', msg); };

storage['demoContext'] = JSON.stringify({
    archetypeId: 'demo-fixed-wing', companyName: 'Buddha Air',
    aeName: 'Mr. Birendra Basnet', fleetType: 'ATR 72-500/ATR 42-320',
    baseLocation: 'Tribhuvan Intl (VNKT)', iataCode: 'BA', email: 'ae@buddha-air.com',
});

api.applyPersonalization();
assert(document.title.includes('Buddha Air') && document.title.includes('Accountable Executive Dashboard') && document.title.includes('AviaSAFE'), 'document.title personalized (refined format)');
assert(elems['heroTitle'].textContent === 'Buddha Air', 'hero header = companyName (refined)');
assert(elems['welcomeMsg'].textContent === 'Welcome, Mr. Birendra Basnet', 'welcome message personalized');
assert(elems['fleetBadge'].textContent.includes('ATR 72-500/ATR 42-320') && elems['fleetBadge'].textContent.includes('Operating Base: Tribhuvan Intl (VNKT)'), 'fleet badge personalized');
assert(elems['navH1'].innerHTML.includes('Buddha Air'), 'nav branded');

// formatAllReferences DOM scanner.
const scanRoot = mkEl('scanRoot');
const n1 = { nodeValue: 'Escalated CAP FW-CAP-0012-26 awaiting decision.' };
const n2 = { nodeValue: 'Hazard RW-HZ-0003-25 closed.' };
const n3 = { nodeValue: 'No references here.' };
let nodes = [n1, n2, n3], i = 0;
global.document.createTreeWalker = () => ({
    currentNode: null,
    nextNode() { const n = nodes[i++]; this.currentNode = n || null; return n || false; },
});
const changed = api.formatAllReferences(scanRoot, 'YT');
assert(changed === 2, 'scanner updated 2 text nodes');
assert(n1.nodeValue === 'Escalated CAP YT-CAP-0012-26 awaiting decision.', 'FW swapped to IATA');
assert(n2.nodeValue === 'Hazard YT-HZ-0003-25 closed.', 'RW swapped to IATA');
assert(n3.nodeValue === 'No references here.', 'non-reference text untouched');

console.log('ALL CHUNK 5 PERSONALIZATION CHECKS PASSED');

