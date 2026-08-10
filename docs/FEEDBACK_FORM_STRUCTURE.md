# AviaSAFE SMS — Beta Feedback Form Structure

**Google Form link:** https://docs.google.com/forms/d/e/16uQxAYybkUoRYjxJ7P15topYd8aXvv1O64YlMa0hWaM/viewform

This document defines the fields for the beta feedback form. Create the form in Google Forms using the question types and options below so reports map cleanly onto the P0–P3 triage in `docs/BETA_TEST_CHECKLIST.md`.

---

## Form Fields

| # | Field | Question Type | Required | Options / Notes |
|---|-------|---------------|----------|-----------------|
| 1 | **Tester name** | Short answer | Yes | Full name of the tester |
| 2 | **Airline / Organization** | Dropdown | Yes | One entry per participating organization (e.g., Sita Air, Buddha Air, Tara Air, CAAN, Other) |
| 3 | **Contact email** | Short answer | No | For follow-up on the report |
| 4 | **Issue priority** | Multiple choice | Yes | P0 — Blocking; P1 — High; P2 — Medium; P3 — Low |
| 5 | **Feature area** | Dropdown / Checkbox | Yes | VSR, MOR, Survey, Hazards, Risk Matrix, CAP, Dashboard, Login/Auth, CAAN State Risk, UI/UX, Other |
| 6 | **Issue title** | Short answer | Yes | One-line summary of the problem |
| 7 | **Description of issue** | Paragraph | Yes | What happened; expected vs actual behavior |
| 8 | **Steps to reproduce** | Paragraph | Yes | Numbered steps from a clean login |
| 9 | **Screenshot / screen recording** | File upload | No | Max 10 files, 10 MB each |
| 10 | **Browser** | Dropdown | Yes | Chrome, Firefox, Safari, Edge, Mobile (iOS Safari / Android Chrome), Other |
| 11 | **Operating system** | Dropdown | Yes | Windows, macOS, Linux, iOS, Android, Other |
| 12 | **Approximate time of issue (UTC)** | Short answer | No | Matches beta backend log timestamps for debugging |
| 13 | **Data entry severity** | Multiple choice | No | Was any data lost or corrupted? (Yes / No / Not sure) — escalates automatically to P0 review |

---

## Field Definitions (for the form description / tester guidance)

| Priority | Type | Examples |
|----------|------|----------|
| **P0** | Blocking | Cannot log in, HTTP 500 errors, data loss/corruption |
| **P1** | High | Feature not working, wrong risk-matrix calculations, broken workflows |
| **P2** | Medium | UI glitches, slow responses, confusing copy |
| **P3** | Low | Typos, cosmetic issues, minor styling |

| Feature area | Covers |
|--------------|--------|
| VSR | Voluntary Safety Report submission and listing |
| MOR | Mandatory Occurrence Report |
| Survey | Gap Analysis Survey and results |
| Hazards | Hazard register and hazard lifecycle |
| Risk Matrix | Risk scoring / matrix calculations |
| CAP | Corrective Action Plans |
| Dashboard | SMS maturity score, trend and admin dashboards |
| Login/Auth | Sign-in, token verification, role access |
| CAAN State Risk | National / state risk register |
| UI/UX | Layout, navigation, responsiveness, copy |

---

## Optional Pre-fill

To route testers straight to the form from the invitation email, append pre-fill parameters to the form URL (field IDs come from the created form):

```
https://docs.google.com/forms/d/e/{FORM_ID}/viewform?entry.{FIELD_1_ID}=prefill
```

For unknown IDs, use the Google Forms link created with field-entry-parameter seeding, or leave pre-fill out and keep the plain form link.

---

## After Creation

1. Add the generated link to:
   - `docs/BETA_TEST_CHECKLIST.md` (Feedback form row)
   - `docs/BETA_INVITATION_TEMPLATE.md` (Feedback channel)
2. Add the same link to the placeholder in this document.
3. Share the form with testers (view only; no edits).
4. Export responses to Google Sheets and connect to a weekly triage review using the P0–P3 definitions.
