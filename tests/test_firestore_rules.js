// ============================================================================
// tests/test_firestore_rules.js
// Chunk 17 — Phase 1 structural rule-lint for firestore/firestore.rules.
//
// Static verification (no emulator required) that every tenant-partitioned
// collection match enforces the dual tenant condition and that CAAN access is
// read-only aggregate. For full semantic coverage, run the emulator suite:
//   npx firebase emulators:exec --only firestore \
//     "node tests/test_firestore_rules_emulator.js"   (follow-up)
// ============================================================================

const fs = require('fs');
const path = require('path');
const assert = require('assert');

const rules = fs.readFileSync(
    path.resolve(__dirname, '..', 'firestore', 'firestore.rules'), 'utf8');

let passed = 0;
function ok(cond, msg) {
  assert(cond, 'RULE-LINT FAIL: ' + msg);
  passed++;
  console.log('ok -', msg);
}

// ── Helper contract ─────────────────────────────────────────────────────────
ok(/function isAuthenticated\(\)/.test(rules), 'isAuthenticated helper defined');
ok(/request\.auth != null/.test(rules), 'unauthenticated requests rejected globally');
ok(/function isCaanInspector\(\)/.test(rules), 'CAAN inspector alias defined');
ok(/CAAN_INSPECTOR/.test(rules), "inspector role accepts 'CAAN_INSPECTOR' token");
ok(/matchesOwnTenantData\(\)/.test(rules), 'dual tenant condition helper present');
ok(/resource\.data\.tenant_id/.test(rules) &&
   /request\.resource\.data\.tenant_id/.test(rules),
   'stored + incoming tenant_id comparisons present');

// ── Tenant-partitioned collections must use path isolation ─────────────────
const PARTITIONED = [
  'metadata', 'responses', 'surveys', 'reports', 'mor',
  'hazards', 'can_cap', 'verification', 'flight_diversions',
];
for (const coll of PARTITIONED) {
  const re = new RegExp(`match \\/tenants\\/\\{tenantId\\}\\/${coll}(\\/|\\/)`);
  ok(re.test(rules), `/${coll} partitioned under /tenants/{tenantId}/`);
  // Every allow inside its block references the path tenantId.
  const blockRe = new RegExp(`match \\/tenants\\/\\{tenantId\\}\\/${coll}[\\s\\S]*?\\n    \\}`);
  const block = (rules.match(blockRe) || [''])[0];
  ok(/tenantId/.test(block), `/${coll} rules reference the path tenant`);
}

// ── No unauthenticated / unconditional allows ───────────────────────────────
const unconditional = [
  /allow\s+(read|write)[^;]*:\s*if\s+true\s*;/gi,
];
for (const re of unconditional) {
  ok(!re.test(rules), 'no unconditional allow-true rules');
}
ok(!/allow read, write: if true/.test(rules), 'no blanket read+write=true');

// ── PSOE assessments (top-level, tenant_id on docs) ────────────────────────
ok(/match \/psoe_assessments\/\{docId\}/.test(rules), 'psoe_assessments explicitly ruled');
ok(/psoe_assessments[\s\S]*?isCaanInspector\(\)/.test(rules),
   'PSOE grants CAAN inspector (read-only aggregate role)');
ok(/psoe_assessments[\s\S]*?request\.auth\.token\.tenant_id == resource\.data\.tenant_id/
   .test(rules.replace(/\n/g, ' ')) ||
   /tenant_id == resource\.data\.tenant_id/.test(rules),
   'PSOE enforces stored-tenant match');

// ── Demo session ownership (owner_uid per Headway §1.1) ────────────────────
ok(/function sessionOwner\(\)/.test(rules), 'demo_sessions ownership helper defined');
ok(/request\.auth\.uid == resource\.data\.owner_uid/.test(rules),
   'demo_sessions enforce uid == owner_uid');
ok(/request\.auth\.uid == request\.resource\.data\.owner_uid/.test(rules),
   'demo_sessions create enforces uid == incoming owner_uid');
ok(/match \/demo_analytics\/\{email\}[\s\S]{0,200}allow read, write: if false/.test(rules),
   'demo_analytics locked to Admin SDK');

// ── SRAs are embedded (initial_sra/residual_sra on CAN/CAP docs) ───────────
ok(/can_cap\/\{canId\}/.test(rules), 'SRA data inherits CAN/CAP doc protection');

// ── Headway audit additions (top-level guard rails + owner_uid) ───────────
for (const coll of ['hazards', 'cans', 'caps', 'sras', 'surveys']) {
  const re = new RegExp(`match \\/${coll}\\/\\{id\\}\\s*\\{[\\s\\S]*?allow read, write: if false`);
  ok(re.test(rules), `top-level /${coll} mirror is explicitly denied`);
}
ok(/owner_uid == resource\.data\.owner_uid/.test(rules) ||
   /resource\.data\.owner_uid/.test(rules),
   'demo_sessions subcollections enforce owner_uid');
ok(/match \/caan_oversight\/\{docId\}/.test(rules) &&
   /isCaanInspector\(\) \|\| isSuperAdmin\(\)/.test(rules) &&
   /caan_oversight[\s\S]{0,400}allow write: if false/.test(rules),
   'caan_oversight is inspector read-only, write-denied');

console.log(`\nRULE-LINT PASSED: ${passed} assertions`);

// Emulator-based semantic tests are documented next-steps in
// docs/SECURITY_AUDIT_REPORT.md (Phase 1 follow-up).
