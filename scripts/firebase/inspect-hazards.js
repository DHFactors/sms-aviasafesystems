// Inspect hazards under a tenant in a named Firestore database (beta/prod).
// Reads backend/.env for service-account credentials.
// Usage:
//   node scripts/firebase/inspect-hazards.js <tenantId> [databaseId]
//     e.g. node scripts/firebase/inspect-hazards.js tara-air sms-db
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
        console.error('Usage: node inspect-hazards.js <tenantId> [databaseId]');
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

    const snap = await db.collection('tenants').doc(tenantId).collection('hazards').get();
    console.log(`Tenant=${tenantId} db=${databaseId} hazard_docs=${snap.size}`);

    const bySeed = {};
    const byStatus = {};
    const byCat = {};
    const byCreatedBy = {};
    const byIdPrefix = {};
    const createdTimes = [];
    const sampleFields = new Set();

    snap.forEach((doc) => {
        const d = doc.data() || {};
        const key = (k) => { bySeed[k] = (bySeed[k] || 0) + 1; };
        key(String(d.seed_version || '(none)'));
        const st = String(d.status || '(none)');
        byStatus[st] = (byStatus[st] || 0) + 1;
        const cat = String(d.occurrence_category || d.taxonomy || '(none)');
        byCat[cat] = (byCat[cat] || 0) + 1;
        const cb = String(d.created_by || '(none)');
        byCreatedBy[cb] = (byCreatedBy[cb] || 0) + 1;
        const hid = String(d.hazard_id || doc.id);
        const m = hid.match(/^(.+?-\d{4}-)(\d+)$/);
        const prefix = m ? m[1] : hid;
        byIdPrefix[prefix] = (byIdPrefix[prefix] || 0) + 1;
        if (d.created_at) {
            createdTimes.push(d.created_at && d.created_at.toDate ? d.created_at.toDate() : new Date(d.created_at));
        }
        Object.keys(d).forEach((f) => sampleFields.add(f));
    });

    console.log('--- by seed_version ---');
    console.log(JSON.stringify(bySeed, null, 2));
    console.log('--- by status ---');
    console.log(JSON.stringify(byStatus, null, 2));
    console.log('--- by occurrence_category ---');
    console.log(JSON.stringify(byCat, null, 2));
    console.log('--- by created_by ---');
    console.log(JSON.stringify(byCreatedBy, null, 2));
    console.log('--- by hazard_id prefix (grouped) ---');
    console.log(JSON.stringify(byIdPrefix, null, 2));
    if (createdTimes.length) {
        const min = new Date(Math.min(...createdTimes)).toISOString();
        const max = new Date(Math.max(...createdTimes)).toISOString();
        console.log(`--- created_at range: ${min} .. ${max}`);
    }
    console.log('--- doc fields ---');
    console.log([...sampleFields].join(', '));
}

main().catch((e) => { console.error(e); process.exit(1); });
