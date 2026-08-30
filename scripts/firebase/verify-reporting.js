// Verify SSP report generation + PDF export on the live beta backend using a
// CAAN_SMD account (state-level report, aggregated/anonymized data only).
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..', '..');
const API_KEY = "AIzaSyCdCtUuyOcUIoCBEaiWGbhp6_XwZKHsicc";
const AUTH_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword";
const BASE = "https://aviasafe-unified-platform.onrender.com";
const CREDS = path.join(ROOT, "BETA_CREDENTIALS_2026-08-08.md");

function loadCredentials() {
    const text = fs.readFileSync(CREDS, 'utf8');
    for (const line of text.split(/\r?\n/)) {
        const m = line.match(/^\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*`(.+?)`\s*\|\s*`(.+?)`\s*\|/);
        if (!m) continue;
        const [tenant, role, email, password] = m.slice(1);
        if (tenant === "CAAN" && /SMD|Super/.test(role)) {
            return { tenant, role, email, password };
        }
    }
    throw new Error("No CAAN SMD account found in credentials");
}

async function signIn(email, password) {
    const r = await fetch(`${AUTH_URL}?key=${API_KEY}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, returnSecureToken: true }),
    });
    if (!r.ok) throw new Error(`signIn failed ${r.status}: ${(await r.text()).slice(0, 200)}`);
    const j = await r.json();
    return j.idToken;
}

async function main() {
    const acct = loadCredentials();
    console.log(`Signing in: ${acct.email} (${acct.role})`);
    const token = await signIn(acct.email, acct.password);

    const now = new Date();
    const year = now.getFullYear();
    const quarter = Math.floor(now.getMonth() / 3) + 1;

    console.log(`Generating quarterly SSP report: Q${quarter} ${year} ...`);
    const genRes = await fetch(`${BASE}/api/v1/reporting/quarterly?year=${year}&quarter=${quarter}`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}` },
    });
    const genJson = await genRes.json().catch(() => ({}));
    console.log(`  generate status=${genRes.status} id=${genJson.id || (genJson.data && genJson.data.id)} period=${genJson.period || ''}`);

    const reportId = genJson.id || (genJson.data && genJson.data.id);
    if (!reportId) {
        console.log("  FAILED: no report id returned");
        process.exit(1);
    }

    const expRes = await fetch(`${BASE}/api/v1/reporting/quarterly/${reportId}/export`, {
        headers: { "Authorization": `Bearer ${token}` },
    });
    const buf = Buffer.from(await expRes.arrayBuffer());
    const isPdf = expRes.headers.get('content-type') === 'application/pdf';
    const pdfHead = buf.length > 5 ? buf.slice(0, 5).toString('latin1') : '';
    console.log(`  export status=${expRes.status} bytes=${buf.length} contentType=${expRes.headers.get('content-type')} head=${JSON.stringify(pdfHead)}`);
    console.log(isPdf && pdfHead === '%PDF-' ? "  PDF export OK" : "  FAILED: not a valid PDF");

    const listRes = await fetch(`${BASE}/api/v1/reporting/quarterly`, {
        headers: { "Authorization": `Bearer ${token}` },
    });
    const listJson = await listRes.json().catch(() => []);
    const arr = Array.isArray(listJson) ? listJson : (listJson.data || []);
    console.log(`  list status=${listRes.status} reports=${arr.length}`);

    // Annual report generation + PDF export
    console.log(`Generating annual SSP report: ${year} ...`);
    const aGen = await fetch(`${BASE}/api/v1/reporting/annual?year=${year}`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}` },
    });
    const aJson = await aGen.json().catch(() => ({}));
    console.log(`  generate status=${aGen.status} id=${aJson.id || (aJson.data && aJson.data.id)} period=${aJson.period || ''}`);
    const aId = aJson.id || (aJson.data && aJson.data.id);
    if (aId) {
        const aExp = await fetch(`${BASE}/api/v1/reporting/annual/${aId}/export`, {
            headers: { "Authorization": `Bearer ${token}` },
        });
        const aBuf = Buffer.from(await aExp.arrayBuffer());
        const aHead = aBuf.length > 5 ? aBuf.slice(0, 5).toString('latin1') : '';
        console.log(`  export status=${aExp.status} bytes=${aBuf.length} head=${JSON.stringify(aHead)} valid=${aHead === '%PDF-'}`);
    }
}

main().catch((e) => { console.error("FATAL", e); process.exit(1); });
