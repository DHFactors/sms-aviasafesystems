#!/usr/bin/env node
// Mint a Firebase ID token for load testing.
//
// Usage:
//   node load-tests/get-token.mjs safety@tara-air.com 'TARA-Safety-2026'
//   LOADTEST_TOKEN=$(node load-tests/get-token.mjs <email> <password>)
//
// The token is valid for 1 hour. Re-mint it before each load test run.
// Override the web API key with LOADTEST_API_KEY if a different project is used.

const API_KEY = process.env.LOADTEST_API_KEY || 'AIzaSyCdCtUuyOcUIoCBEaiWGbhp6_XwZKHsicc';

const email = process.argv[2] || process.env.LOADTEST_EMAIL;
const password = process.argv[3] || process.env.LOADTEST_PASSWORD;

if (!email || !password) {
  console.error('Usage: node load-tests/get-token.mjs <email> <password>');
  console.error('  or set LOADTEST_EMAIL / LOADTEST_PASSWORD');
  process.exit(1);
}

const res = await fetch(
  `https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=${API_KEY}`,
  {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, returnSecureToken: true }),
  }
);

const json = await res.json();
if (!json.idToken) {
  console.error('Login failed:', JSON.stringify(json));
  process.exit(1);
}

console.log(json.idToken);
