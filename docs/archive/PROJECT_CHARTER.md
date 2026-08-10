AviaSAFE SMS Platform – Project Status (Authoritative)
Vision

The AviaSAFE SMS Platform is an aviation-only Safety Management System (SMS) intelligence platform.

Its purpose is to provide:

Airlines (Service Providers): Real-time understanding of their SMS Maturity and Operational Risks.
CAAN (State): Real-time SSP intelligence by aggregating SMS Maturity and Operational Risks across all operators.

This project is not an investigation management system, CAPA system, QMS, ERP, OEI, or enterprise risk platform.

Product Charter (Non-Negotiable)

The platform has only three core data sources.

1. Safety Culture Survey

Purpose:

Measure SMS Capability.

Framework:

ICAO Annex 19
ICAO Doc 9859
CAR-19

Assessment:

4 ICAO SMS Components (Pillars)
12 ICAO SMS Elements

Outputs:

Overall SMS Maturity Score
Pillar Scores
Element Scores
Department Comparison
Participation Rate
SMS Maturity Trend

The Survey does not generate hazards, risks, occurrences, investigations, or corrective actions.

2. Voluntary Safety Reporting (VSR)

Purpose:

Identify operational hazards before they become accidents.

Classification:

ICAO ADREP / ICAO Taxonomy

Outputs:

Top Hazards
Hazard Trends
Hazard Categories
Risk Distribution
Risk Matrix (future)
Department Distribution
Airport Distribution
Fleet Distribution

VSR identifies hazards only.

3. Mandatory Occurrence Reporting (MOR)

Purpose:

Capture mandatory reportable occurrences.

Classification:

ICAO Taxonomy

Outputs:

Occurrence Trends
Severity
Operational Risk
Investigation Status (kept)

MOR is not an investigation management system.

Dashboards
Airline Dashboard

Must answer only two questions:

1.

How mature is our SMS?

(Source: Survey)

2.

What are our highest operational risks?

(Source: VSR + MOR)

Nothing outside these objectives.

CAAN Dashboard

Must answer:

1.

How mature is each operator's SMS?

2.

What are the highest operational risks across the industry?

3.

How effective is the State Safety Programme (SSP) over time?

The CAAN dashboard aggregates tenant information only.

AI Scope

AI is an assistant only.

Permitted:

ICAO taxonomy classification
Narrative summarization
Confidence score
Trend identification
Emerging hazard identification

AI shall not redefine SMS processes or make official risk assessments.

Risk Assessment (Future Phase)

Current status:

Risk Assessment is not yet implemented.

Future implementation shall follow ICAO Doc 9859.

Required model:

Severity

×

Probability

=

Risk Index

Risk Index shall be calculated using a configurable organizational risk matrix.

AI may suggest severity/probability but the official assessment remains under organizational control.

Seed Dataset

Implemented:

Operators
Buddha Air
Yeti Airlines
Summit Air
Sita Air
Air Dynasty Heli Services
Simrik Air
Data
930 Survey Responses
620 VSR Reports
245 MOR Reports
1,808 Firestore Documents
21 Demo Users

Dataset properties:

Deterministic
Idempotent
Tenant isolated
Repeatable
Operationally realistic
Backend Status

Completed:

Firebase Authentication
Custom Claims
Firestore Security Rules
Tenant Isolation
Report API
Dashboard API
Background AI Processing
Structured Logging
Rate Limiting
Security Headers
Metrics
Cursor Pagination
Firestore Aggregations
Configuration Management
Docker / Cloud Run manifests (future deployment)
API Versioning
Error Handling

Backend is functionally complete for prototype use.

Frontend Status

Completed:

Login
Survey
VSR Submission
MOR Submission
Dashboard API integration
JWT Authentication
Removal of demo/mock dashboard data
Centralized Firebase configuration
Infrastructure Strategy

Prototype:

Firebase Hosting (Spark)
Firestore
Firebase Authentication
Render (Free) for FastAPI backend

Commercial:

Firebase Blaze
Cloud Run
Firestore
Custom domain

Current deployment target:

Firebase Hosting
web.app domain

Custom domain (live target):

sms.aviasafesystems.com

Decisions Made

✓ No OEI integration.

✓ Aviation only.

✓ No feature expansion without approval.

✓ Survey measures SMS capability.

✓ VSR reveals operational hazards.

✓ MOR reveals reportable occurrences.

✓ CAAN monitors SSP effectiveness.

Immediate Work Remaining
Phase 6A

Refactor the seeded data to match the Product Charter.

Survey

Replace custom culture dimensions with:

4 ICAO SMS Components
12 ICAO SMS Elements
VSR

Remove:

corrective_actions
lessons_learned
safety_action_required

Keep:

ICAO taxonomy
severity
occurrence_type
AI classification
confidence
MOR

Keep:

investigation_status

Remove:

reviewed_by
reviewed_at
corrective_actions
lessons_learned
safety_action_required
AI

Limit to:

taxonomy classification
summarization
confidence
trend identification
Future Phase

Implement ICAO Risk Assessment:

Severity

Probability

↓

Risk Matrix

↓

Risk Index

↓

Dashboard visualization

This will complete the SMS Risk Management model in accordance with ICAO Doc 9859.

Governance Rule (Permanent)

No architectural or functional expansion without explicit approval.

If any proposed feature does not directly support one of these three objectives, development must stop and request clarification:

Measure SMS Capability (Survey).
Reveal Operational Risk (VSR & MOR).
Enable CAAN to monitor SSP effectiveness in real time.