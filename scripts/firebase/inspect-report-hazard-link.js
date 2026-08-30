// Audit report <-> hazard linkage for a tenant in a named Firestore database.
// Reads backend/.env for service-account credentials.
// Usage:
//   node scripts/firebase/inspect-report-hazard-link.js <tenantId> [databaseId]
'use strict';

const fs = require('fs');
const path = require('path');
const admin = require('firebase-admin');

function loadEnv() {
    const raw = fs.readFileSync(path.join(__dirname, '..', '..', 'backend', '.env'), 'utf8');
    const env = {};
    for (const line of raw.split(/\r?\n/)) {
        const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)$/);
        if (m && !line.trim().startsWith('#')) {
            let v = m[2];
            if (v.length >= 2 && v[0] === '"' && v[v.length - 1] === '"') v = v.slice(1, -1);
            env[m[1]] = v;
        }
    }
    return env;
}

async function main() {
    const tenantId = process.argv[2];
    const databaseId = process.argv[3] || 'sms-db';
    if (!tenantId) {
        console.error('Usage: node inspect-report-hazard-link.js <tenantId> [databaseId]');
        process.exit(1);
    }
    const env = loadEnv();
    if (!env.FIREBASE_CLIENT_EMAIL || !env.FIREBASE_PRIVATE_KEY) {
        console.error('ERROR: FIREBASE_CLIENT_EMAIL / FIREBASE_PRIVATE_KEY missing from backend/.env');
        process.exit(1);
    }
    const app = admin.initializeApp({
        credential: admin.credential.cert({
            type: 'service_account',
            project_id: env.FIREBASE_PROJECT_ID,
            private_key: (env.FIREBASE_PRIVATE_KEY || '').replace(/\\n/g, '\n'),
            client_email: env.FIREBASE_CLIENT_EMAIL,
            token_uri: env.FIREBASE_TOKEN_URI || 'https://oauth2.googleapis.com/token',
        }),
    });
    const { getFirestore } = require('firebase-admin/firestore');
    const db = getFirestore(app, databaseId);

    const tenRef = db.collection('tenants').doc(tenantId);
    const reportsSnap = await tenRef.collection('reports').get();
    const hazardsSnap = await tenRef.collection('hazards').get();

    const reports = reportsSnap.docs.map((d) => ({ id: d.id, ...d.data() }));
    const hazards = hazardsSnap.docs.map((d) => ({ id: d.id, ...d.data() }));

    console.log(`Tenant=${tenantId} db=${databaseId}`);
    console.log(`  reports = ${reports.length}`);
    console.log(`  hazards = ${hazards.length}`);

    const sourceIds = new Set();
    let hazardsWithSource = 0;
    let hazardsWithoutSource = 0;
    for (const h of hazards) {
        if (h.source_id) { sourceIds.add(h.source_id); hazardsWithSource++; }
        else hazardsWithoutSource++;
    }
    console.log(`  hazards with source_id (auto-linked) = ${hazardsWithSource}`);
    console.log(`  hazards WITHOUT source_id (manual/seed) = ${hazardsWithoutSource}`);

    const linked = reports.filter((r) => sourceIds.has(r.id));
    const unlinked = reports.filter((r) => !sourceIds.has(r.id));
    console.log(`  reports linked to a hazard = ${linked.length}`);
    console.log(`  reports NOT linked = ${unlinked.length}`);

    const cutoff90 = Date.now() - 90 * 86400000;
    const inWindow = reports.filter((r) => {
        const t = r.created_at;
        if (!t) return false;
        const ms = t.toDate ? t.toDate().getTime() : new Date(t).getTime();
        return ms >= cutoff90;
    });
    const inWindowLinked = inWindow.filter((r) => sourceIds.has(r.id));
    console.log(`  reports created in last 90 days = ${inWindow.length}`);
    console.log(`  in-window reports linked = ${inWindowLinked.length}`);
    console.log(`  in-window reports NOT linked = ${inWindow.length - inWindowLinked.length}`);

    const reportTypeCounts = {};
    for (const r of reports) {
        const t = String(r.report_type || r.type || '(none)');
        reportTypeCounts[t] = (reportTypeCounts[t] || 0) + 1;
    }
    console.log('  reports by type:', JSON.stringify(reportTypeCounts));

    const createdBy = {};
    for (const r of reports) {
        const k = String(r.created_by || '(none)');
        createdBy[k] = (createdBy[k] || 0) + 1;
    }
    console.log('  reports by created_by:', JSON.stringify(createdBy));

    const seedCounts = { seed: 0, live: 0 };
    const seedLinked = { seed: 0, live: 0 };
    for (const r of reports) {
        const isSeed = r.seed_version || (r.created_by || '').startsWith('seed');
        const key = isSeed ? 'seed' : 'live';
        seedCounts[key]++;
        if (sourceIds.has(r.id)) seedLinked[key]++;
    }
    console.log(`  reports by origin: seed=${seedCounts.seed} live=${seedCounts.live}`);
    console.log(`  linked by origin: seed=${seedLinked.seed} live=${seedLinked.live}`);

    const hazardsBySource = {};
    for (const h of hazards) {
        const s = h.source_id ? 'auto(from-report)' : (h.created_by || '(none)');
        const k = String(s);
        hazardsBySource[k] = (hazardsBySource[k] || 0) + 1;
    }
    console.log('  hazards by origin:', JSON.stringify(hazardsBySource));

    if (unlinked.length && unlinked.length <= 40) {
        console.log('  unlinked report ids:');
        for (const r of unlinked) {
            console.log(`    - ${r.id} | type=${r.report_type} | created_by=${r.created_by} | seed=${!!r.seed_version}`);
        }
    }
}

main().catch((e) => { console.error(e); process.exit(1); });
