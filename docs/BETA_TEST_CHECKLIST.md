# AviaSAFE SMS — Closed Beta Test Checklist

**Access URL:** https://sms-beta.web.app
**Environment:** Isolated beta — API routes to `aviasafe-unified-platform.onrender.com`, all writes go to the `sms-db-beta` Firestore database. **No production data is touched.**

---

## 1. Authentication & Basic Access

- [ ] Navigate to `https://sms-beta.web.app`
- [ ] Log in with your provided beta credentials
- [ ] Verify role-based access (Airline Admin vs CAAN_SMD)
- [ ] Confirm the `[BETA NOTICE]` banner appears on:
  - Survey page (`/survey/`)
  - CAAN State Risk page (`caan-state-risk.html`)

## 2. Voluntary Safety Reporting (VSR)

- [ ] Submit a new VSR with valid data
- [ ] Verify the report appears in the list view
- [ ] Confirm the report is tagged with the correct `tenant_id`
- [ ] Confirm the write landed in `sms-db-beta` (check beta backend logs)

## 3. Hazard Registration & Risk Matrix

- [ ] Create a hazard from a VSR
- [ ] Verify risk matrix calculation:
  - S3 × P3 = 9 → Medium / Tolerable
  - S2 × P2 = 4 → Low / Acceptable
- [ ] Confirm status transitions (Under Review → Active → Closed)

## 4. Corrective Action Plans (CAP)

- [ ] Create a CAP for an active hazard
- [ ] Assign responsibility to a user
- [ ] Update CAP status (Draft → In Progress → Complete)
- [ ] Verify the audit trail (status/history fields embedded within the `can_cap` and `hazards` documents, plus escalation events written to the `audit_logs` collection)

## 5. Rate Limiting (Redis — beta only)

Rate limits are enforced per **IP address** before login and per **tenant** after authentication.

| Endpoint | Limit | Window |
|----------|-------|--------|
| Login / token verify | **200 attempts** | per hour |
| VSR submit | 50 | per day |
| Survey submit | 100 | per day |
| MOR submit | 20 | per day |
| Dashboard | 500 | per hour |

- [ ] Send ~200 rapid login attempts from one IP
  - The **first 200** requests return `401` (invalid token)
  - Requests **201+** return `429 Too Many Requests`
- [ ] Confirm the `429` response includes the headers:
  - `X-RateLimit-Limit: 200`
  - `X-RateLimit-Remaining: 0`
  - `X-RateLimit-Reset` (epoch of the next hour boundary)
- [ ] Confirm a **different IP can still log in** during that window (limits are per-IP, not shared)
- [ ] Confirm the limit **resets hourly** (at the next UTC hour boundary)

**Redis note:** Rate limiting uses Upstash Redis and is **beta-only** (production does not use Redis). To confirm it is active, check the **beta** service logs (`sms-aviasafesystems-beta`) for the startup line:

```
Connected to Upstash Redis
```

## 6. Cross-Tenant Isolation (CAAN_SMD only)

- [ ] Log in as a CAAN_SMD user
- [ ] View aggregated data across tenants
- [ ] Confirm **no write access** to individual airline data

## 7. Expected Behavior

- [ ] All API calls route to `https://aviasafe-unified-platform.onrender.com`
- [ ] All database writes land in `sms-db-beta`
- [ ] Point-in-Time Recovery (PITR) is enabled on `sms-db-beta`
- [ ] No production data (`sms-db`) is affected by any beta action

---

## Reporting Issues

| Priority | Type | Examples |
|----------|------|----------|
| **P0** | Blocking | Cannot log in, HTTP 500 errors, data loss/corruption |
| **P1** | High | Feature not working, wrong risk-matrix calculations, broken workflows |
| **P2** | Medium | UI glitches, slow responses, confusing copy |
| **P3** | Low | Typos, cosmetic issues, minor styling |

**Feedback form:** https://docs.google.com/forms/d/e/16uQxAYybkUoRYjxJ7P15topYd8aXvv1O64YlMa0hWaM/viewform

When reporting, please include:
1. **Priority** (P0–P3)
2. **Steps to reproduce**
3. **Expected vs actual behavior**
4. Browser and device used
5. Approximate time of the issue
