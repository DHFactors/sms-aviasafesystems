// Seed 5 additional realistic demo hazards so a tenant register shows ~10.
// Idempotent: skips a tenant that already has >= 10 hazards.
// Uses the same schema/seed_version as seed_caan_demo_data.py.
// Usage:
//   node scripts/firebase/seed-extra-hazards.js [databaseId] [tenantId ...]
//     e.g. node scripts/firebase/seed-extra-hazards.js sms-db buddha-air tara-air
'use strict';

const fs = require('fs');
const path = require('path');
const admin = require('firebase-admin');

const DEFAULT_TENANTS = ['buddha-air'];

const EXTRA = [
    {
        cat: 'LOCI',
        taxonomy: 'Organizational-Facilities',
        title: 'Uncommanded roll during final approach to RWY 20, Kathmandu',
        description: 'ATR 72 reported a sudden uncommanded roll while established on final approach to RWY 20 at KTM in light turbulence. Crew recovered manually; investigation points to possible wake turbulence and rudder deflection sensitivity.',
        source: 'MOR',
        severity: 4,
        probability: 3,
        status: 'Open',
    },
    {
        cat: 'SYS',
        taxonomy: 'Technical',
        title: 'Repeated autopilot altitude-capture faults during cruise',
        description: 'Multiple flights reported autopilot failing to capture selected altitude, requiring manual intervention by crew. Fault intermittent and not reproduced on ground checks; technical log review initiated.',
        source: 'MOR',
        severity: 3,
        probability: 4,
        status: 'Under Review',
    },
    {
        cat: 'FIRE',
        taxonomy: 'Technical',
        title: 'Cargo hold smoke indication during turnaround at Bhairahawa',
        description: 'Cargo hold smoke warning activated during ground turnaround at BWA. Loading suspended, hold inspected, no fire found; suspect sensor fault. Repeat occurrence risk noted for cargo handling procedures.',
        source: 'Safety Inspection',
        severity: 5,
        probability: 2,
        status: 'Open',
    },
    {
        cat: 'WX',
        taxonomy: 'Environmental',
        title: 'Wind shear reported on approach into Pokhara (VNPK)',
        description: 'Pilots reported low-level wind shear and sudden airspeed fluctuations during final approach into VNPK. Go-around executed; wind shear warning system activated on short final.',
        source: 'VSR',
        severity: 3,
        probability: 3,
        status: 'Closed',
    },
    {
        cat: 'CABIN',
        taxonomy: 'Human Factors',
        title: 'Turbulence-related cabin injury during KTM–LUKLA sector',
        description: 'Severe turbulence during mountain sector caused an unrestrained passenger minor injury and unsecured galley equipment shift. Cabin crew securing procedures to be reviewed for short sectors.',
        source: 'VSR',
        severity: 3,
        probability: 3,
        status: 'Open',
    },
];

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

function priorityFor(riskIndex) {
    return riskIndex >= 12 ? 'H' : riskIndex >= 6 ? 'M' : 'L';
}

function riskLevelFor(riskIndex) {
    if (riskIndex <= 5) return 'Low';
    if (riskIndex <= 9) return 'Medium';
    if (riskIndex <= 15) return 'High';
    return 'Very High';
}

async function main() {
    const databaseId = process.argv[2] || 'sms-db';
    const tenants = process.argv.slice(3);
    if (tenants.length === 0) tenants.push(...DEFAULT_TENANTS);

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
    const { getFirestore, Timestamp } = require('firebase-admin/firestore');
    const db = getFirestore(app, databaseId);

    const now = Date.now();
    const DAY = 86400000;
    const offsetsDays = [4, 11, 18, 26, 34];

    for (const tid of tenants) {
        const ref = db.collection('tenants').doc(tid).collection('hazards');
        const snap = await ref.get();
        const docs = snap.docs.map((d) => ({ id: d.id, ...d.data() }));

        if (docs.length >= 10) {
            console.log(`SKIP ${tid}: already ${docs.length} hazards (>= 10)`);
            continue;
        }

        let maxSuffix = -1;
        for (const d of docs) {
            const hid = String(d.hazard_id || d.id);
            const m = hid.match(/-HZ-\d{4}-(\d+)$/);
            if (m) maxSuffix = Math.max(maxSuffix, parseInt(m[1], 10));
        }
        const year = new Date(now).getUTCFullYear();
        let added = 0;
        for (let i = 0; i < EXTRA.length; i++) {
            if (docs.length + added >= 10) break;
            const e = EXTRA[i];
            const created = new Date(now - offsetsDays[i] * DAY);
            const riskIndex = e.severity * e.probability;
            const doc = {
                tenant_id: tid,
                hazard_id: `${tid}-HZ-${year}-${String(maxSuffix + 1 + i).padStart(3, '0')}`,
                title: e.title,
                description: e.description,
                source: e.source,
                occurrence_category: e.cat,
                taxonomy: e.taxonomy,
                severity: e.severity,
                probability: e.probability,
                risk_index: riskIndex,
                risk_level: riskLevelFor(riskIndex),
                priority: priorityFor(riskIndex),
                status: e.status,
                created_by: 'seed-caan-demo',
                created_at: Timestamp.fromDate(created),
                updated_at: Timestamp.fromDate(created),
                seed_version: 'caan-demo-1',
            };
            await ref.add(doc);
            added++;
            console.log(`ADD ${tid}: ${doc.hazard_id} ${doc.occurrence_category} risk=${riskIndex} ${doc.risk_level}`);
        }
        console.log(`DONE ${tid}: total hazards now = ${docs.length + added}`);
    }
    console.log('\nSeed complete.');
}

main().catch((e) => { console.error(e); process.exit(1); });
