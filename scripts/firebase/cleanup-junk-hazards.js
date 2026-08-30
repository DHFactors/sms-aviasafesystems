'use strict';
// Backup + delete junk hazards from the beta DB.
// Junk = hazards that are (a) not seeded AND (b) created by a demo/test user
// AND (c) NOT derived from a report (no source_id). Auto-created hazards from
// report submissions carry source_id=<report.id> and must be kept even though
// they have created_by="user_*" and no seed_version.
// Usage: node scripts/firebase/cleanup-junk-hazards.js [databaseId] [--only-tara]
const fs = require('fs');
const path = require('path');
const admin = require('firebase-admin');
const { getFirestore } = require('firebase-admin/firestore');

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
const args = process.argv.slice(2);
const databaseId = args.find((a) => !a.startsWith('--')) || 'sms-db';
const onlyTara = args.includes('--only-tara');

const app = admin.initializeApp({
    credential: admin.credential.cert({
        type: 'service_account',
        project_id: env.FIREBASE_PROJECT_ID,
        private_key: (env.FIREBASE_PRIVATE_KEY || '').replace(/\\n/g, '\n'),
        client_email: env.FIREBASE_CLIENT_EMAIL,
        token_uri: env.FIREBASE_TOKEN_URI || 'https://oauth2.googleapis.com/token',
    }),
});

(async () => {
    const db = getFirestore(app, databaseId);
    const tenantIds = onlyTara ? ['tara-air'] : ['sita-air', 'yeti-airlines', 'summit-air', 'simrik-air', 'buddha-air', 'air-dynasty', 'tara-air'];

    const backup = { databaseId, created_at: new Date().toISOString(), tenants: {} };
    const summary = [];

    for (const tid of tenantIds) {
        const snap = await db.collection('tenants').doc(tid).collection('hazards').get();
        const junk = [];
        const kept = [];
        for (const doc of snap.docs) {
            const d = doc.data() || {};
            const isJunk = !d.seed_version
                && String(d.created_by || '').startsWith('user_')
                && !d.source_id;
            const rec = {
                docId: doc.id,
                hazard_id: d.hazard_id || null,
                title: d.title || null,
                seed_version: d.seed_version || null,
                created_by: d.created_by || null,
                status: d.status || null,
                occurrence_category: d.occurrence_category || null,
                created_at: d.created_at && d.created_at.toDate ? d.created_at.toDate().toISOString() : d.created_at,
            };
            (isJunk ? junk : kept).push(rec);
        }
        backup.tenants[tid] = { junk, kept };

        const batch = db.batch();
        for (const rec of junk) {
            batch.delete(db.collection('tenants').doc(tid).collection('hazards').doc(rec.docId));
        }
        if (junk.length) await batch.commit();

        summary.push({ tenant: tid, total: snap.size, deleted: junk.length, kept: kept.length });
        console.log(`${tid}: total=${snap.size} deleted=${junk.length} kept=${kept.length}`);
    }

    const dir = path.join(__dirname, '..', '..', 'scripts', 'firebase', 'backups');
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    const stamp = new Date().toISOString().replace(/[:T]/g, '-').slice(0, 19);
    const file = path.join(dir, `hazards-backup-${databaseId}-${stamp}.json`);
    fs.writeFileSync(file, JSON.stringify(backup, null, 2));
    console.log(`Backup written: ${file}`);
    console.log('SUMMARY:', JSON.stringify(summary));

    await app.delete();
})().catch((e) => { console.error('FATAL', e); process.exit(1); });
