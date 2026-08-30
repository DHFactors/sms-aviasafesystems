/* Live verification for Priority 3 (in-product feedback).

   Verifies against the deployed beta stack:
     1. POST /api/v1/feedback returns 201 + stored doc id for an authenticated
        AIRLINE_ADMIN (operator) and a CAAN Super Admin.
     2. Unauthenticated POST is rejected (401/403).
     3. The deployed CAAN and operator pages include the feedback widget
        (js/feedback.js) and the CAAN page includes the SSP report link.

   Usage:  node scripts/firebase/verify-feedback.js
   Reads sign-in credentials from BETA_CREDENTIALS_2026-08-08.md.
*/

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const API_KEY = "AIzaSyCdCtUuyOcUIoCBEaiWGbhp6_XwZKHsicc";
const BACKEND = process.env.BACKEND_URL || "https://aviasafe-unified-platform.onrender.com";
const CREDS = path.join(ROOT, "BETA_CREDENTIALS_2026-08-08.md");

function loadAccounts() {
  const md = fs.readFileSync(CREDS, "utf8");
  const re = /^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|/gm;
  const out = [];
  let m;
  while ((m = re.exec(md))) {
    out.push({ tenant: m[1].trim(), role: m[2].trim(), email: m[3].trim(), password: m[4].trim() });
  }
  return out;
}

async function signIn(email, password) {
  const res = await fetch(`https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=${API_KEY}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, returnSecureToken: true }),
  });
  if (!res.ok) throw new Error(`sign-in failed for ${email}: ${res.status} ${await res.text()}`);
  const data = await res.json();
  return data.idToken;
}

async function postFeedback(token, payload) {
  const res = await fetch(`${BACKEND}/api/v1/feedback`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  const text = await res.text();
  return { status: res.status, text };
}

let failures = 0;
function check(name, cond, detail) {
  if (cond) {
    console.log(`PASS  ${name}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${name}  ->  ${detail}`);
  }
}

(async () => {
  const accounts = loadAccounts();
  const buddha = accounts.find((a) => a.tenant.includes("Buddha") && a.role.includes("Admin"));
  const caan = accounts.find((a) => a.tenant.includes("CAAN") && a.role.includes("Super Admin"));
  if (!buddha || !caan) throw new Error("Could not find Buddha AIRLINE_ADMIN or CAAN Super Admin in credentials file");

  const buddhaToken = await signIn(buddha.email, buddha.password);
  const caanToken = await signIn(caan.email, caan.password);

  // 1. Authenticated POSTs are stored.
  const b = await postFeedback(buddhaToken, {
    subject: "SSM Risk Trends",
    message: "Live verification feedback from operator dashboard (Priority 3).",
    rating: 5,
    page: "/safety.html",
  });
  check(
    "Buddha feedback stored (201 + id)",
    b.status === 201 && JSON.parse(b.text).data && JSON.parse(b.text).data.id,
    `${b.status} ${b.text}`,
  );

  const c = await postFeedback(caanToken, {
    subject: "SSP Reporting",
    message: "Live verification feedback from CAAN dashboard (Priority 3).",
    rating: 4,
    page: "/caan.html",
  });
  check(
    "CAAN feedback stored (201 + id)",
    c.status === 201 && JSON.parse(c.text).data && JSON.parse(c.text).data.id,
    `${c.status} ${c.text}`,
  );

  // 2. Validation: empty message rejected (422).
  const bad = await postFeedback(buddhaToken, { subject: "x", message: "ab" });
  check("Short/invalid payload rejected (422)", bad.status === 422, `${bad.status} ${bad.text}`);

  // 3. Unauthenticated rejected.
  const anon = await postFeedback("not-a-token", { subject: "SSM", message: "hello world" });
  check("Unauthenticated rejected (401/403)", anon.status === 401 || anon.status === 403, `${anon.status} ${anon.text}`);

  // 4. Deployed pages include the widget + CAAN SSP link.
  const pages = [
    { url: "https://sms.aviasafesystems.com/caan.html", has: ["/js/feedback.js", "/reports/generate.html"] },
    { url: "https://sms.aviasafesystems.com/safety.html", has: ["/js/feedback.js"] },
  ];
  for (const p of pages) {
    const res = await fetch(p.url);
    const html = await res.text();
    for (const needle of p.has) {
      check(`page ${p.url} contains ${needle}`, res.status === 200 && html.includes(needle), `${res.status}`);
    }
  }

  console.log(failures === 0 ? "\nALL CHECKS PASSED" : `\n${failures} CHECK(S) FAILED`);
  process.exit(failures === 0 ? 0 : 1);
})().catch((e) => {
  console.error("Verification error:", e.message);
  process.exit(1);
});
