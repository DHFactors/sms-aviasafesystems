// k6 scenario: 50 concurrent users viewing airline dashboards.
// Dashboard GET endpoints are NOT rate-limited, so this is a clean latency test.
//
// Run:
//   k6 run -e LOADTEST_TOKEN=$LOADTEST_TOKEN load-tests/k6/dashboard-view.js

import http from 'k6/http';
import { check, sleep } from 'k6';
import { BASE_URL, authHeaders, isAccepted } from './common.js';

const DASHBOARD_ENDPOINTS = [
  '/api/dashboard/overview?days=90',
  '/api/dashboard/trends?days=180',
  '/api/dashboard/hazards?days=90',
  '/api/dashboard/actions?days=90',
  '/api/dashboard/airline/sms-maturity?days=365',
];

export const options = {
  scenarios: {
    viewers: {
      executor: 'constant-vus',
      vus: 50, // 50 concurrent dashboard users
      duration: '2m',
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<500'], // success criterion: <500ms p95
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const endpoint = DASHBOARD_ENDPOINTS[__ITER % DASHBOARD_ENDPOINTS.length];
  const res = http.get(`${BASE_URL}${endpoint}`, {
    headers: authHeaders(),
    tags: { scenario: 'dashboard-view' },
  });

  check(res, {
    'dashboard responds 200': (r) => r.status === 200,
    'response is json': (r) => r.headers['Content-Type'] && r.headers['Content-Type'].includes('application/json'),
  });
  check(res, { 'not throttled': (r) => isAccepted(r) });

  sleep(1);
}
