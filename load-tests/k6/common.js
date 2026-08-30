// Shared helpers for k6 load tests.
//
// Environment variables:
//   LOADTEST_BASE_URL  - API base URL (default: beta backend)
//   LOADTEST_TOKEN     - Firebase ID token (from get-token.mjs)

export const BASE_URL =
  __ENV.LOADTEST_BASE_URL || 'https://aviasafe-unified-platform.onrender.com';

export function authHeaders() {
  const token = __ENV.LOADTEST_TOKEN || '';
  return { Authorization: `Bearer ${token}` };
}

export function jsonHeaders() {
  return { 'Content-Type': 'application/json', ...authHeaders() };
}

// A response is "throttled" by the rate limiter (expected during load runs).
export function isThrottled(res) {
  return res.status === 429;
}

export function isAccepted(res) {
  return res.status >= 200 && res.status < 300;
}
