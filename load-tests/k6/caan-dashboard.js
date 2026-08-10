// k6 scenario: 10 concurrent CAAN users viewing aggregated cross-tenant dashboards.
// Requires a CAAN_SMD (or SUPER_ADMIN) Firebase ID token.
//
// Run:
//   LOADTEST_TOKEN=$(node load-tests/get-token.mjs caan@example.com <password>)
//   k6 run -e LOADTEST_TOKEN=$LOADTEST_TOKEN load-tests/k6/caan-dashboard.js

import http from 'k6/http';
import { check, sleep } from 'k6';
import { BASE_URL, authHeaders, isAccepted } from './common.js';

const CAAN_ENDPOINTS = [
  '/api/dashboard/caan/overview',
  '/api/dashboard/caan/trends',
  '/api/dashboard/caan/risk',
  '/api/dashboard/caan/hazards',
  '/api/dashboard/caan/survey-maturity',
  '/api/dashboard/caan/sms-maturity-assessment',
  '/api/dashboard/caan/benchmark',
];

export const options = {
  scenarios: {
    caanUsers: {
      executor: 'constant-vus',
      vus: 10, // 10 concurrent CAAN users
      duration: '2m',
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<500'], // success criterion: <500ms p95
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const endpoint = CAAN_ENDPOINTS[__ITER % CAAN_ENDPOINTS.length];
  const res = http.get(`${BASE_URL}${endpoint}`, {
    headers: authHeaders(),
    tags: { scenario: 'caan-dashboard' },
  });

  check(res, {
    'caan endpoint responds 200': (r) => r.status === 200,
  });
  check(res, { 'not throttled': (r) => isAccepted(r) });

  sleep(2);
}
