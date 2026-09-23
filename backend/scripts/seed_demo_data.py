# ============================================================================
# FILE: seed_demo_data.py
# PATH: backend/scripts/seed_demo_data.py
# PURPOSE: Seed realistic, temporally distributed demo data for the three
#          demo tenants (sita-air fixed wing, air-dynasty rotor wing).
#          CAAN reads aggregates — no CAAN rows are seeded.
#
# TEMPORAL DISTRIBUTION (relative to run date):
#   A: 395-455d ago (13-15mo, OUTSIDE 1y)   E: 35-90d ago (INSIDE 90d)
#   B: 305-365d ago (10-12mo, edge/outside) F: 2-28d ago (INSIDE 30d)
#   C: 215-275d ago (7-9mo, inside 1y)      D: 125-185d ago (4-6mo, inside 1y)
# Expected period counts (Sita reports): 30d=2, 90d=6, 1y=18, older-than-1y=2.
#
# CHAIN: reports -> hazards -> SRM dates -> CANs -> CAPs (+ surveys monthly).
#
# IDEMPOTENCY: per-tenant count guards (reports/hazards/cans/caps/surveys);
#   re-running skips tenants that already hold the expected volume.
#
# DOCUMENTED DEVIATIONS (no business logic bypassed):
#  1. Services stamp created_at/updated_at/first_priority_at = now and offer
#     no backdate knob, while the task requires created_at == occurrence era.
#     Entities are therefore created through the real services (validation,
#     references, SRA derivation, status machines, notifications attempted),
#     then ONLY timestamp columns are backdated via targeted UPDATEs.
#  2. Surveys are seeded via ORM (the submission service requires
#     question-contract answers + open-window checks); this mirrors the
#     repo's own seeder/test practice. Maturity dashboards aggregate the
#     surveys rows live, so no cache writes are needed.
#  3. "Incident" is not an allowed HazardCreate source (creation sources are
#     VSR/MOR/audits/diversions); investigation reports map to MOR hazards.
#  4. "In Process" is a bucket, not a HazardStatus; in-process hazards use
#     the "Under Review" status (which buckets to In Process).
#
# Usage:  python backend/scripts/seed_demo_data.py   (from repo root)
# ============================================================================

import os
import random
import sys
from datetime import datetime, timedelta, timezone

BACKEND = os.path.join(os.getcwd(), "backend")
sys.path.insert(0, BACKEND)

SEED_TAG = "DEMO-SEED-v1"
RNG_SEED = 20260923

WINDOWS = {
    # letter: (min_days_ago, max_days_ago)
    "A": (395, 455),
    "B": (305, 365),
    "C": (215, 275),
    "D": (125, 185),
    "E": (35, 90),
    "F": (2, 28),
}

SRM_TIMELINE_DAYS = {"H": 1, "M": 7, "L": 15}  # CAAN S2.2

# ---------------------------------------------------------------------------
# Report catalogs: (window, source, report_type, topic, occurrence_type,
#                   severity, priority)
# ---------------------------------------------------------------------------

SITA_REPORTS = [
    # A (2)
    ("A", "VSR", "voluntary", "Crew uniforms delayed for new joiners",
     "Ground Operations", 2, "L"),
    ("A", "MOR", "mandatory", "Elevator trim runaway indication on climb",
     "Flight Controls", 4, "H"),
    # B (3)
    ("B", "VSR", "voluntary", "Canteen hygiene below standard at base",
     "Ground Operations", 2, "L"),
    ("B", "VSR", "voluntary", "Crew rostering IT portal outage",
     "Technical", 2, "M"),
    ("B", "Internal Audit", "voluntary", "AD/SB compliance tracking gaps",
     "Airworthiness", 3, "M"),
    # C (4)
    ("C", "VSR", "voluntary", "OHS: baggage hall lighting failure",
     "Ground Operations", 3, "M"),
    ("C", "MOR", "mandatory", "Nose wheel steering light flicker on taxi",
     "Landing Gear", 3, "M"),
    ("C", "Internal Audit", "voluntary", "Liaison meeting action overdue",
     "Documentation", 2, "L"),
    ("C", "Flight Diversion", "mandatory", "KEP diversion to JUM for weather",
     "Weather", 3, "M"),
    # D (5)
    ("D", "VSR", "voluntary", "Crew transport delay before dawn departure",
     "Ground Operations", 2, "L"),
    ("D", "VSR", "voluntary", "Classroom projector failure during SEP refresher",
     "Training", 1, "L"),
    ("D", "VSR", "voluntary", "Unescorted visitor near restricted bay",
     "Security", 4, "H"),
    ("D", "MOR", "mandatory", "Engine torque split exceedance on takeoff",
     "Propulsion", 4, "H"),
    ("D", "Internal Audit", "voluntary", "Corrective action closure evidence thin",
     "Documentation", 2, "M"),
    # E (4)
    ("E", "VSR", "voluntary", "Ramp bus speeding on apron service road",
     "Ground Operations", 3, "M"),
    ("E", "VSR", "voluntary", "Load sheet revision mismatch at dispatch",
     "Load Control", 3, "M"),
    ("E", "Flight Diversion", "mandatory", "KTM diversion to LUA for fuel",
     "Fuel", 3, "M"),
    ("E", "Internal Audit", "voluntary", "Equipment planning for winter ops late",
     "Planning", 2, "M"),
    # F (2)
    ("F", "VSR", "voluntary", "Passenger manifest count mismatch at boarding",
     "Ground Operations", 3, "M"),
    ("F", "Flight Diversion", "mandatory", "KEP diversion to RARA for crosswind",
     "Weather", 4, "H"),
]

# report index -> hazard plan for Sita (15 hazards):
# 5 Closed = oldest (A/A/B/B/C); 8 Open across B-E; 2 Under Review recent (E/F)
SITA_HAZARDS = {
    0: ("Closed", False), 1: ("Closed", False),
    2: ("Closed", False), 3: ("Closed", False), 5: ("Closed", False),
    4: ("Open", False), 6: ("Open", False), 7: ("Open", True),
    8: ("Open", False), 9: ("Open", False),
    10: ("Open", False), 11: ("Open", True), 16: ("Open", False),
    17: ("Under Review", False), 18: ("Under Review", False),
}
# Reports 12,13 (D), 15 (E), 19 (F) stay hazard-less (reporting-only).
SITA_CAN_HAZARDS = [0, 1, 9, 11, 16, 18]  # 6 CANs (2 old-closed, 3 open, 1 EIP)

DYNASTY_REPORTS = [
    ("A", "VSR", "voluntary", "Sling load hook inspection overdue",
     "External Load", 3, "M"),
    ("A", "MOR", "mandatory", "Tail rotor vibration above limits in hover",
     "Rotor System", 4, "H"),
    ("B", "VSR", "voluntary", "Pre-flight briefing room noise disruption",
     "Training", 1, "L"),
    ("B", "Internal Audit", "voluntary", "Maintenance schedule slippage on fleet",
     "Airworthiness", 3, "M"),
    ("C", "VSR", "voluntary", "Fuel uplift quantity dispute at remote pad",
     "Fuel", 3, "M"),
    ("C", "MOR", "mandatory", "Hydraulic pressure fluctuation in flight",
     "Hydraulics", 4, "H"),
    ("C", "MOR", "mandatory", "Hard landing inspection findings",
     "Landing", 4, "H"),
    ("D", "VSR", "voluntary", "Weather minima interpretation dispute at dispatch",
     "Weather", 2, "M"),
    ("D", "VSR", "voluntary", "Helipad FOD after construction nearby",
     "Ground Operations", 3, "M"),
    ("D", "Internal Audit", "voluntary", "Spare parts shelf-life tracking gaps",
     "Logistics", 2, "M"),
    ("E", "VSR", "voluntary", "Crew duty time nearing limits on charter",
     "Fatigue", 3, "M"),
    ("E", "VSR", "voluntary", "Passenger weight estimate variance",
     "Load Control", 2, "L"),
    ("E", "MOR", "mandatory", "Main rotor tracking drift detected",
     "Rotor System", 4, "H"),
    ("E", "Internal Audit", "voluntary", "Tool calibration certificates expired",
     "Maintenance", 3, "M"),
    ("F", "MOR", "mandatory", "Precautionary landing due to chip light",
     "Propulsion", 4, "H"),
]
# 12 hazards (report idx -> plan); 4 Closed oldest, 6 Open, 2 Under Review.
# Reports 2 (B briefing), 7 (D weather), 11 (E pax weight) stay hazard-less.
DYNASTY_HAZARD_MAP = {
    0: ("Closed", False), 1: ("Closed", False),
    3: ("Closed", False), 4: ("Open", False),
    5: ("Closed", False), 6: ("Open", False),
    8: ("Open", True), 9: ("Open", False),
    10: ("Open", False), 12: ("Open", False),
    13: ("Under Review", True), 14: ("Under Review", False),
}
DYNASTY_CAN_HAZARDS = [5, 10, 14]  # 3 recent CANs (C/E/F eras)

TAXONOMIES = ["Organizational", "Technical", "Human", "Environmental"]
FUNCTIONS = ["OPS", "ENG", "SAF", "DSP", "MNT"]

HAZARD_SOURCE = {  # report source -> HazardCreate source
    "VSR": "VSR", "MOR": "MOR", "Internal Audit": "Internal Audit",
    "Flight Diversion": "Flight Diversion",
}


def load_env(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'").strip('"'))


def ago(days):
    return datetime.now(timezone.utc) - timedelta(days=days)


def in_window(rng, letter):
    lo, hi = WINDOWS[letter]
    return rng.randint(lo, hi)


def main():
    load_env(os.path.join("backend", ".env"))

    from sqlalchemy import text
    from app.db import pg
    from app.db.db_models import Hazard, Report, UserProfile
    from app.db.ids import register_tenant
    from app.db.session import session_scope
    from app.services.report_service import ReportService
    from app.services.hazard_service import HazardService
    from app.services.can_cap_service import CanCapService

    import asyncio

    def run(coro):
        return asyncio.run(coro)

    # -- tiny timestamp-backdate helper (timestamp columns ONLY) --
    def backdate(table, row_id, **cols):
        async def _go():
            async with session_scope() as s:
                sets = ", ".join(f"{c} = :{c}" for c in cols)
                await s.execute(
                    text(f"UPDATE public.{table} SET {sets} WHERE id = :id"),
                    {"id": row_id, **cols},
                )

        run(_go())

    def table_count(model, tid):
        async def _go():
            async with session_scope() as s:
                from sqlalchemy import select, func
                return (await s.execute(
                    select(func.count()).select_from(model).where(
                        model.tenant_id == tid))).scalar()

        return run(_go())

    def safety_user(slug):
        domain = ("sitaair.com.np" if slug == "sita-air"
                  else "air-dynasty.com.np")
        row = pg.fetch_by(UserProfile, "email", f"safety@{domain}")
        if row is None or row.get("role") not in (
                "TENANT_ADMIN", "AIRLINE_ADMIN"):
            raise RuntimeError(f"no safety user for {slug}")
        return {"uid": row["uid"], "email": row["email"],
                "role": "TENANT_ADMIN", "tenant_id": slug}

    # ---------------- surveys ----------------
    def seed_surveys(slug, tid, per_month, rng):
        from app.db.db_models import Survey as SModel, SurveyResponse as RModel

        async def _go(rows):
            async with session_scope() as s:
                for kind, r in rows:
                    s.add(r)

        pending = []
        for m in range(12):
            days = m * 30 + rng.randint(8, 22)
            n = rng.choice(per_month)
            for i in range(n):
                dt = ago(days + rng.randint(0, 6))
                p = [rng.choice([3, 3, 4, 4, 4, 5]) for _ in range(4)]
                overall = max(3, min(4, round(sum(p) / 4)))
                pct = round(70 + rng.random() * 18, 1)
                pending.append(("s", SModel(
                    tenant_id=tid, submitted_at=dt,
                    respondent_id=f"demo-{slug}-{m}-{i}",
                    department=rng.choice(["Flight Operations", "CAMO",
                                           "Part-145", "Safety"]),
                    survey_version="4.0.0", answers={},
                    question_scores={}, element_scores={},
                    safety_policy=p[0], safety_risk_management=p[1],
                    safety_assurance=p[2], safety_promotion=p[3],
                    overall_sms_maturity=overall, overall_score_pct=pct,
                    is_demo=True)))
                pending.append(("r", RModel(
                    tenant_id=tid, respondent_id=f"demo-{slug}-{m}-{i}",
                    answers={}, department="Safety",
                    submitted_at=dt, survey_version="4.0.0", is_demo=True)))
        run(_go(pending))
        return len([1 for k, _ in pending if k == "s"])

    # ---------------- tenants ----------------
    # Marker conventions (all reseeds wipe-then-recreate per tenant, so a
    # crashed run can never duplicate; a complete tenant is skipped):
    #   hazards remarks = SEED_TAG, reports narrative LIKE '[DEMO]%',
    #   cans description LIKE '[DEMO]%', caps action_plan LIKE '[DEMO]%',
    #   surveys/survey_responses respondent_id LIKE 'demo-%'.
    def wipe_demo(slug, tid):
        async def _go():
            async with session_scope() as s:
                from sqlalchemy import delete
                from app.db.db_models import (Can, Cap, Hazard, Report,
                                              Survey as SModel,
                                              SurveyResponse as RModel)
                await s.execute(delete(Cap).where(
                    Cap.tenant_id == tid,
                    Cap.action_plan.like("[DEMO]%")))
                await s.execute(delete(Can).where(
                    Can.tenant_id == tid,
                    Can.description.like("[DEMO]%")))
                await s.execute(delete(Hazard).where(
                    Hazard.tenant_id == tid,
                    Hazard.remarks == SEED_TAG))
                await s.execute(delete(Report).where(
                    Report.tenant_id == tid,
                    Report.narrative.like("[DEMO]%")))
                await s.execute(delete(RModel).where(
                    RModel.tenant_id == tid,
                    RModel.respondent_id.like("demo-%")))
                await s.execute(delete(SModel).where(
                    SModel.tenant_id == tid,
                    SModel.respondent_id.like("demo-%")))

        run(_go())

    plans = [
        ("sita-air", SITA_REPORTS, SITA_HAZARDS, SITA_CAN_HAZARDS,
         {"cans": 6, "caps": 4}, [4, 5], 48),
        ("air-dynasty", DYNASTY_REPORTS, DYNASTY_HAZARD_MAP,
         DYNASTY_CAN_HAZARDS, {"cans": 3, "caps": 3}, [2, 3], 24),
    ]

    for slug, catalog, hz_plan, can_hz, expect, survey_per_month, sur_min in plans:
        tid = register_tenant(slug)
        rng = random.Random(f"{RNG_SEED}-{slug}")
        from app.db.db_models import Can as CanM, Cap as CapM
        from app.db.db_models import Survey as SMod
        n_cap = table_count(CapM, tid)
        n_sur = table_count(SMod, tid)
        if n_cap >= expect["caps"] and n_sur >= sur_min:
            if "--reseed" not in sys.argv:
                print(f"{slug}: already seeded (caps={n_cap}, surveys={n_sur}) — skip")
                continue
            wipe_demo(slug, tid)
            print(f"{slug}: --reseed: wiped demo rows — reseeding")
        if (table_count(Report, tid) > 0 or table_count(Hazard, tid) > 0
                or n_cap > 0 or n_sur > 0):
            wipe_demo(slug, tid)
            print(f"{slug}: wiped partial demo rows — reseeding")
        user = safety_user(slug)
        rep_svc = ReportService(slug)
        hz_svc = HazardService(slug)
        cc_svc = CanCapService(slug)

        # ---- reports (occurrence_date via service; created_at backdated) --
        rep_ids = []
        for i, (win, src, rtype, topic, occ, sev, _pri) in enumerate(catalog):
            d = in_window(rng, win)
            occ_dt = ago(d)
            rep = rep_svc.create_report({
                "report_type": rtype,
                "narrative": f"[DEMO] {topic} ({slug})",
                "occurrence_type": occ,
                "occurrence_date": occ_dt,
                "reporting_date": occ_dt,
                "location": "KTM",
                "severity_level": sev,
                "probability_level": rng.choice([2, 3, 3, 4]),
                "reporter_role": "crew",
            }, user)
            backdate("reports", rep["id"], created_at=occ_dt,
                     updated_at=occ_dt)
            rep_ids.append((rep["id"], occ_dt, src, topic))
        print(f"{slug}: reports={len(rep_ids)}")

        # ---- hazards (identified/created/status/srm via service payload) --
        hz_rows = {}  # catalog idx -> service dict
        fn_i = 0
        for idx, (status, srm_pending) in sorted(hz_plan.items()):
            _rid, occ_dt, src, topic = rep_ids[idx]
            pri = {"VSR": "M", "MOR": "H"}.get(src, "M")
            if rng.random() < 0.25:
                pri = rng.choice(["H", "M", "L"])
            created = occ_dt + timedelta(hours=rng.randint(2, 30))
            srm_date = None
            if not srm_pending and rng.random() < 0.9:
                srm_date = created + timedelta(
                    days=SRM_TIMELINE_DAYS[pri])
            hz = hz_svc.create_hazard_v1({
                "title": f"[DEMO] {topic}",
                "description": f"Demo hazard from {src} report: {topic}. "
                               f"Seeded for period-filter validation.",
                "source": HAZARD_SOURCE[src],
                "source_id": _rid,
                "taxonomy": TAXONOMIES[(fn_i) % 4],
                "function": FUNCTIONS[(fn_i) % 5],
                "severity": rng.randint(2, 5),
                "probability": rng.randint(2, 4),
                "priority": pri,
                "status": status,
                "identified_at": created,
                "created_at": created,
                "priority_date": created,
                "status_date": created,
                "srm_flag": True,
                "srm_date": srm_date,
                "srm_conducted": bool(srm_date),
                "department": rng.choice(["Flight Operations", "CAMO",
                                          "Part-145"]),
                "remarks": SEED_TAG,
            }, user)
            fn_i += 1
            first_pa = created + timedelta(hours=rng.randint(1, 20))
            cols = {"first_priority_at": first_pa, "updated_at": created}
            if status == "Closed":
                hz_svc.update_status(hz["hazard_id"], "Closed", user)
                cols["closed_at"] = created + timedelta(
                    days=rng.randint(40, 120))
                cols["updated_at"] = cols["closed_at"]
            backdate("hazards", hz["id"], **cols)
            hz_rows[idx] = hz
        print(f"{slug}: hazards={len(hz_rows)}")

        # ---- CANs (issued_at via service; created_at backdated) -----------
        now = datetime.now(timezone.utc)
        camo_email = ("camo@sitaair.com.np" if slug == "sita-air"
                      else "camo@air-dynasty.com.np")
        can_rows = {}
        for hidx in can_hz:
            hz = hz_rows[hidx]
            hz_created = hz["created_at"]
            if isinstance(hz_created, str):
                hz_created = datetime.fromisoformat(hz_created)
            if hz_created.tzinfo is None:
                hz_created = hz_created.replace(tzinfo=timezone.utc)
            issued = min(hz_created + timedelta(days=rng.randint(5, 15)),
                         now - timedelta(days=2))
            can = cc_svc.issue_can({
                "title": f"[DEMO] CAN for {hz['hazard_id']}",
                "description": f"[DEMO] corrective action notice ({slug}).",
                "required_action": "Investigate root cause and submit CAP.",
                "hazard_id": hz["hazard_id"],
                "assigned_to": camo_email,
                "department": hz.get("department") or "CAMO",
                "priority": "High" if hz.get("priority") == "H" else "Medium",
                "initial_severity": hz.get("severity") or 3,
                "initial_probability": hz.get("probability") or 3,
                "issued_at": issued,
                "target_completion_date": issued + timedelta(days=45),
            }, user)
            backdate("cans", can["id"], created_at=issued,
                     updated_at=issued)
            can_rows[hidx] = dict(can, issued_at=issued)
        print(f"{slug}: cans={len(can_rows)}")

        # ---- CAPs ----------------------------------------------------------
        if slug == "sita-air":
            # 4 CAPs: 2 oldest Completed, 1 recent In Progress (E window),
            # 1 EIP (F window, escalated within last 30d).
            closed_h, prog_h, eip_h = [0, 1], [16], [18]
            for hidx in closed_h:
                can = can_rows[hidx]
                sub = can["issued_at"] + timedelta(days=rng.randint(3, 10))
                cap = cc_svc.submit_cap(can["id"], {
                    "action_plan": "[DEMO] corrective action plan.",
                    "timeline": "30 days",
                    "target_completion_date": sub + timedelta(days=30),
                    "department": can.get("department") or "CAMO",
                    "submitted_at": sub,
                }, user)
                closed = sub + timedelta(days=rng.randint(20, 40))
                cc_svc.review_cap(cap["id"], {
                    "status": "Completed", "comments": "Verified effective.",
                    "closed_at": closed,
                }, user)
                backdate("caps", cap["id"], created_at=sub,
                         updated_at=closed)
                backdate("cans", can["id"], updated_at=closed,
                         status="Closed")
                # Full lifecycle: verification closure returns the hazard to
                # Closed (issuing the CAN had moved it to Processing, and CAP
                # completion to Under Review — the real status machine).
                hz_svc.update_status(hz_rows[hidx]["hazard_id"], "Closed",
                                     user)
                backdate("hazards", hz_rows[hidx]["id"], closed_at=closed,
                         closed_by=user["email"], updated_at=closed)
            for hidx in prog_h:
                can = can_rows[hidx]
                sub = min(can["issued_at"] + timedelta(days=rng.randint(2, 6)),
                          now - timedelta(days=1))
                cap = cc_svc.submit_cap(can["id"], {
                    "action_plan": "[DEMO] CAP in progress.",
                    "timeline": "45 days",
                    "target_completion_date": sub - timedelta(days=5),
                    "department": can.get("department") or "CAMO",
                    "submitted_at": sub,
                }, user)
                backdate("caps", cap["id"], created_at=sub,
                         updated_at=sub)
            for hidx in eip_h:
                can = can_rows[hidx]
                sub = min(can["issued_at"] + timedelta(days=2),
                          now - timedelta(days=8))
                cap = cc_svc.submit_cap(can["id"], {
                    "action_plan": "[DEMO] EIP candidate CAP.",
                    "timeline": "15 days",
                    "target_completion_date": sub + timedelta(days=15),
                    "department": can.get("department") or "CAMO",
                    "submitted_at": sub,
                }, user)
                esc = min(sub + timedelta(days=rng.randint(2, 5)),
                          now - timedelta(hours=12))
                cc_svc.review_cap(cap["id"], {
                    "status": "In Progress",
                    "comments": "Escalated for AE acknowledgement.",
                    "escalated_to_ae": True,
                    "escalated_by": user["email"],
                    "escalation_reason": "Residual risk exceeds "
                                         "department authority.",
                    "escalated_at": esc,
                }, user)
                backdate("caps", cap["id"], created_at=sub,
                         updated_at=esc)
            print(f"{slug}: caps=4 (2 closed, 1 progress, 1 EIP)")
        else:
            # Dynasty: 3 recent CAPs, all active (2 In Progress, 1 review).
            # The C-era hazard behind the aging CAN is verification-closed so
            # the Closed set stays the oldest (see Sita note above).
            hz5_created = hz_rows[5]["created_at"]
            if isinstance(hz5_created, str):
                hz5_created = datetime.fromisoformat(hz5_created)
            if hz5_created.tzinfo is None:
                hz5_created = hz5_created.replace(tzinfo=timezone.utc)
            hz_svc.update_status(hz_rows[5]["hazard_id"], "Closed", user)
            backdate("hazards", hz_rows[5]["id"],
                     closed_at=hz5_created + timedelta(days=70),
                     closed_by=user["email"],
                     updated_at=hz5_created + timedelta(days=70))
            for j, hidx in enumerate(sorted(can_rows)):
                can = can_rows[hidx]
                sub = min(can["issued_at"] + timedelta(days=rng.randint(2, 6)),
                          now - timedelta(days=1))
                cap = cc_svc.submit_cap(can["id"], {
                    "action_plan": f"[DEMO] dynasty CAP {j + 1}.",
                    "timeline": "30 days",
                    "target_completion_date": sub + timedelta(days=30),
                    "department": can.get("department") or "CAMO",
                    "submitted_at": sub,
                }, user)
                if j == 2:
                    cc_svc.review_cap(cap["id"], {
                        "status": "Under Review",
                        "comments": "Dept review in progress.",
                    }, user)
                backdate("caps", cap["id"], created_at=sub,
                         updated_at=sub)
            print(f"{slug}: caps=3 (active)")

        # ---- surveys (monthly spread, ORM — see header deviation #2) -------
        n_s = seed_surveys(slug, tid,
                           [4, 5] if slug == "sita-air" else [2, 3], rng)
        print(f"{slug}: surveys={n_s}")

    print("SEED-COMPLETE")


if __name__ == "__main__":
    main()
