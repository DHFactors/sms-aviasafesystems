'use strict';
const fs = require('fs');
const path = require('path');
const admin = require('firebase-admin');

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
    for (const dbId of ['sms-db', 'sms-db']) {
        try {
            const db = admin.firestore(app, dbId);
            const r = await db.collection('regulators').get();
            console.log(`${dbId}: regulators=${r.size}`);
        } catch (e) {
            console.log(`${dbId}: ERR ${e.code || ''} ${e.message}`);
        }
    }
    await app.delete();
})().catch((e) => console.log('FATAL', e));
