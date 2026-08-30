// Verify GET /api/v1/dashboard/risk-trends on the live beta backend for a
// tenant user (Buddha Air) and confirm tenant isolation + payload shape.
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
    const accounts = [];
    for (const line of text.split(/\r?\n/)) {
        const m = line.match(/^\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*`(.+?)`\s*\|\s*`(.+?)`\s*\|/);
        if (!m) continue;
        const [tenant, role, email, password] = m.slice(1);
        if (tenant === "Login URL" || tenant === "Backend") continue;
        accounts.push({ tenant, role, email, password });
    }
    return accounts;
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
    const accounts = loadCredentials();
    const buddha = accounts.find((a) => a.tenant === "Buddha Air" && a.role.startsWith("Admin"));
    const sita = accounts.find((a) => a.tenant === "Sita Air" && a.role.startsWith("Admin"));
    if (!buddha || !sita) throw new Error("Missing Buddha/Sita admin accounts");

    const [bTok, sTok] = await Promise.all([
        signIn(buddha.email, buddha.password),
        signIn(sita.email, sita.password),
    ]);

    for (const [name, tok] of [["Buddha", bTok], ["Sita", sTok]]) {
        const r = await fetch(`${BASE}/api/v1/dashboard/risk-trends?days=730`, {
            headers: { Authorization: `Bearer ${tok}` },
        });
        const j = await r.json();
        const d = (j && j.data) || {};
        const series = Array.isArray(d.series) ? d.series : [];
        console.log(`${name} status=${r.status} quarters=${JSON.stringify(d.quarters)}`);
        for (const s of series) {
            const pts = (s.points || []).map((p) => p.avg_risk_index);
            console.log(`  ${s.category}: ${JSON.stringify(pts)}`);
        }
    }
}

main().catch((e) => { console.error("FATAL", e); process.exit(1); });
