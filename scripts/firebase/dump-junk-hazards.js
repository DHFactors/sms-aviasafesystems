'use strict';
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
    const tenantId = process.argv[2] || 'tara-air';
    const databaseId = process.argv[3] || 'sms-db';
    const db = getFirestore(app, databaseId);
    const snap = await db.collection('tenants').doc(tenantId).collection('hazards')
        .orderBy('created_at').get();
    console.log(`total=${snap.size}`);
    let n = 0;
    snap.forEach((doc) => {
        const d = doc.data() || {};
        if (d.seed_version) return;
        n++;
        if (n <= 8) {
            const ts = d.created_at && d.created_at.toDate ? d.created_at.toDate().toISOString() : d.created_at;
            console.log(JSON.stringify({
                docId: doc.id,
                hazard_id: d.hazard_id,
                title: d.title,
                status: d.status,
                occurrence_category: d.occurrence_category,
                created_by: d.created_by,
                created_at: ts,
            }));
        }
    });
    console.log(`non-seed hazards: ${n}`);
    await app.delete();
})().catch((e) => { console.error(e); process.exit(1); });
