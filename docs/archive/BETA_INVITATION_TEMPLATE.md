# AviaSAFE SMS — Closed Beta Tester Invitation

**Subject:** Invitation: AviaSAFE SMS Closed Beta — Join as a Tester

**To:** {Tester Name}, {Airline / Organization}

---

Dear {Tester Name},

We are pleased to invite you to participate in the **closed beta** of the AviaSAFE Safety Management System (SMS) platform. Your feedback over the next two weeks will directly shape the production release.

## How to Access the Beta

| Item | Value |
|------|-------|
| **Beta URL** | https://sms-beta.web.app |
| **Login credentials** | Issued to you individually by the AviaSAFE administrator — do not share them |
| **Credentials reset** | Contact info@aviasafesystems.com if you cannot log in |

> **Important:** This is an isolated beta environment. All data you enter is stored in a dedicated beta database (`sms-db-beta`) and **cannot affect production data**.

## What We Ask You to Test

Please follow the versioned test checklist while exploring the platform:

- **Checklist:** attached to this email (`docs/BETA_TEST_CHECKLIST.md`)

Focus areas:
1. **Login and role-based access** (Airline Admin vs CAAN_SMD)
2. **Voluntary Safety Reports (VSR)** — submit and view
3. **Hazard registration and risk-matrix calculations**
4. **Corrective Action Plans (CAP)** — create, assign, update
5. **Rate limiting** — sustained activity returns a `429` with `X-RateLimit-*` headers
6. **Cross-tenant isolation** (CAAN_SMD accounts only)

## Feedback

Report any issue using the feedback form:

- **Feedback form:** https://docs.google.com/forms/d/e/16uQxAYybkUoRYjxJ7P15topYd8aXvv1O64YlMa0hWaM/viewform

When reporting, please classify the issue by priority:

| Priority | Type | Examples |
|----------|------|----------|
| **P0** | Blocking | Cannot log in, HTTP 500 errors, data loss/corruption |
| **P1** | High | Feature not working, wrong risk-matrix calculations, broken workflows |
| **P2** | Medium | UI glitches, slow responses, confusing copy |
| **P3** | Low | Typos, cosmetic issues, minor styling |

Include with each report: priority, steps to reproduce, expected vs actual behavior, browser/device, and approximate time.

## Timeline

- **Beta period:** 2 weeks, starting **Friday 7 August 2026**
- **Feedback deadline:** **Friday 21 August 2026**
- Issues reported during the beta will be triaged and prioritized for the production release.

## Security & Just Culture

- All reports are protected under **Just Culture** principles.
- Please use a strong password and do not share your credentials.
- The beta environment is for testing only — do not enter real personal data you would not be comfortable sharing.

---

Thank you for helping us make AviaSAFE safer for everyone.

**AviaSAFE Systems**
*A project by Ghanshyam Acharya*

---

<!-- SENDER NOTES — remove this block before sending -->

**Per-recipient fields to fill before sending:**
- `{Tester Name}` (subject line, To: line, and salutation)
- `{Airline / Organization}` (To: line)

**Defaults already set (edit if needed):**
- Credentials issuer: "the AviaSAFE administrator"
- Support contact: `info@aviasafesystems.com`
- Dates: **7–21 Aug 2026** (2 weeks) — adjust to your launch date
- Checklist: attach `docs/BETA_TEST_CHECKLIST.md` to the email (repo is private — no public link)
