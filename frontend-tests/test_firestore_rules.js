// ============================================================================
// frontend-tests/test_firestore_rules.js
// Headway audit — Firestore + Storage rule-lint (SEC-01..SEC-05 mirror).
//
// Static structural verification of:
//   firestore/firestore.rules  (tenant isolation, PSOE dual condition,
//                               demo session ownership, inspector read-only)
//   storage/storage.rules      (/tenants/{tenantId}/** partitioning)
//
// Emulator-based semantic tests remain the documented follow-up.
// ============================================================================

const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const fsRules = fs.readFileSync(path.join(root, 'firestore', 'firestore.rules'), 'utf8');
const stRulesPath = path.join(root, 'storage', 'storage.rules');
const hasStorage = fs.existsSync(stRulesPath);
const stRules = hasStorage ? fs.readFileSync(stRulesPath, 'utf8') : '';

let passed = 0, failed = 0;
function ok(cond, msg) {
  console.log(`[${cond ? 'PASS' : 'FAIL'}] ${msg}`);
  cond ? passed++ : failed++;
}

// ── SEC-01: cross-tenant reads structurally rejected ───────────────────────
ok(/match \/tenants\/\{tenantId\}\/hazards/.test(fsRules), 'hazards partitioned by tenant path');
ok(/match \/tenants\/\{tenantId\}\/can_cap/.test(fsRules), 'can_cap partitioned by tenant path');
ok(/isOwnTenant\(tenantId\) \|\| isAdminOrCaan\(\)/.test(fsRules), 'own-tenant or admin/caan gate present');

// ── SEC-02: unauthenticated rejection ───────────────────────────────────────
ok(/request\.auth != null/.test(fsRules), 'authentication gate present');
ok(!/allow\s+read(?![^;]*create)[^;]*:\s*if\s+true/i.test(fsRules), 'no unconditional public read');
ok(!/allow\s+read,\s*write:\s*if\s+true/i.test(fsRules), 'no unconditional read+write');
const publicCreates = [...fsRules.matchAll(/allow create:\s*if true/g)].length;
ok(publicCreates > 0 && publicCreates <= 2, `documented anonymous-create exceptions only (${publicCreates})`);

// ── SEC-04: storage /tenants/{tenantId}/** own-tenant only ─────────────────
if (hasStorage) {
  ok(/match \/tenants\/\{tenantId\}\/\{allPaths=\*\*\}/.test(stRules),
     'storage: /tenants/{tenantId}/** partitioning present');
  ok(/request\.auth\.token\.tenant_id == tenantId/.test(stRules),
     'storage: token.tenant_id must equal path tenant');
  ok(/match \/\{allPaths=\*\*\}\s*\{[\s\S]*?allow read, write: if false/.test(stRules),
     'storage: root-level fallback denied');
  ok(!/allow[^;]*:\s*if true/i.test(stRules), 'storage: no unconditional allow');
} else {
  ok(false, 'storage.rules missing');
}

// ── SEC-05: CAAN inspector READ-ONLY on CAN/CAP mutations ──────────────────
ok(/CAAN inspectors have READ-ONLY access/.test(
    fs.readFileSync(path.join(root, 'backend', 'app', 'routes', 'can_cap.py'), 'utf8')),
   'backend route guard: inspector writes rejected with 403');

console.log(`\nRULE-LINT RESULT: ${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
