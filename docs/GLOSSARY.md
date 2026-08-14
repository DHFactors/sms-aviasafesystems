# AviaSAFE SMS & SSP — System Glossary & User Reference Guide

This document defines core terminology, metric calculations, chart legends, and interlinked workflows used across the AviaSAFE Safety Management System (SMS) and State Safety Programme (SSP) dashboards.

---

## 1. Core Workflow & Regulatory Definitions

* **MOR (Mandatory Occurrence Report):** A report required by CAA/ICAO regulations for significant safety events, incidents, or technical defects affecting aircraft airworthiness or operational safety.
* **VSR (Voluntary Safety Report):** A confidential report submitted by frontline personnel highlighting potential hazards, safety concerns, or procedural bottlenecks before an incident occurs.
* **Anon Rate (%):** The percentage of Voluntary Safety Reports submitted anonymously (`is_anonymous: True`). Measures reporting culture psychological safety without compromising reporter identity.
* **CAN (Corrective Action Notice):** A formal notice generated from an identified hazard or audit finding assigned to a specific operational department (Part-145, CAMO, Flight Operations, Safety) requiring risk mitigation.
* **CAP (Corrective Action Plan):** A structured mitigation plan submitted by the responsible department in response to a CAN, detailing root-cause analysis, corrective actions, and implementation deadlines.
* **CAN/CAP Interlink:** The closed-loop workflow where a CAN remains open until the assigned department submits a valid CAP, which is then evaluated, accepted, or escalated by the Safety Office.

---

## 2. Risk Matrix & Hazard Index Definitions

* **Severity Index (A to E):** Measures potential worst-case consequences according to ICAO Doc 9859:
  * **Catastrophic (A):** Equipment destruction, multiple fatalities.
  * **Hazardous (B):** Large reduction in safety margins, physical distress, serious injury.
  * **Major (C):** Significant reduction in safety margins, workload increase, injury.
  * **Minor (D):** Nuisance, operating limitations, minor incident.
  * **Negligible (E):** Little or no safety consequence.
* **Likelihood Index (1 to 5):** Measures event probability:
  * **Frequent (5), Occasional (4), Remote (3), Improbable (2), Extremely Improbable (1)**.
* **Risk Level & Color Coding:**
  * **High Risk (Red / Level 4-5):** Unacceptable risk; immediate corrective action (CAN) required.
  * **Medium Risk (Yellow / Level 3):** Tolerable risk; active monitoring and department CAP required.
  * **Low Risk (Green / Level 1-2):** Acceptable risk; reviewed under routine safety oversight.

---

## 3. State Oversight Metrics (CAAN SMD Dashboard)

* **Active Operators:** Total number of air operators, MROs, aerodromes, and ground handling service providers registered under state oversight.
* **State Hazard Matrix:** Aggregated macro view of cross-tenant high-risk hazards (Level III & IV) mapped against national safety performance indicators (SPIs).
* **SMS Maturity Pillars (ICAO Doc 9859):**
  1. **Policy & Objectives:** Safety management commitment and accountability.
  2. **Risk Management:** Hazard identification and risk assessment processes.
  3. **Safety Assurance:** Safety performance monitoring and data collection.
  4. **Safety Promotion:** Training, communication, and safety culture measurement.

---

## 4. Dashboard Departmental Scoping

* **AIRLINE_ADMIN (`safety@`):** Unscoped executive view across all airline departments, hazard registers, and state reporting metrics.
* **Part-145 Maintenance (`145@`):** Department-scoped view displaying maintenance-specific CAN/CAP tasks and technical hazards.
* **CAMO (`camo@`):** Department-scoped view displaying continuing airworthiness management tasks and airworthiness directives.
* **Flight Operations (`ops@`):** Department-scoped view displaying flight ops tasks, aircrew reporting, and flight diversion logs.