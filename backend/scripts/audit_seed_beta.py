#!/usr/bin/env python3
"""
Audit the sms-db-beta seed dataset against the beta task requirements:

  - Total tenant count (12 providers + CAAN state regulator = 13)
  - Every tenant id uses hyphens (never underscores)
  - Per-tenant report breakdown: MORs, VSRs, Anonymous VSRs
  - Anonymous VSR rate is non-zero for every provider tenant
  - Hazards + CAN/CAP counts per tenant
  - Survey responses per tenant
  - Role accounts provisioned per tenant (safety/145/camo/ops)

Usage:
    $env:FIREBASE_DATABASE_ID='sms-db-beta'
    python backend/scripts/audit_seed_beta.py
"""

import os
import re
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from app.firebase import initialize_firebase, get_db
from seed.config import (
    OPERATOR_PROFILES,
    CREDENTIAL_TENANT_CODES,
    CREDENTIAL_EMAIL_DOMAINS,
)

failures = 0


def check(cond, label, detail=""):
    global failures
    mark = "PASS" if cond else "FAIL"
    if not cond:
        failures += 1
    print(f"  [{mark}] {label}{'  -- ' + detail if detail else ''}")


def main():
    initialize_firebase()
    db = get_db()

    tenants = {d.id: d.to_dict() or {} for d in db.collection("tenants").get()}
    all_ids = sorted(tenants)

    print("== Tenant registry ==")
    check(len(all_ids) == 13, f"13 total tenants", f"found {len(all_ids)}: {all_ids}")
    expected_providers = {p["id"] for p in OPERATOR_PROFILES}
    check(expected_providers.issubset(set(all_ids)),
          "all 12 provider tenants registered",
          f"missing {sorted(expected_providers - set(all_ids)) or 'none'}")
    check("caan" in all_ids, "CAAN regulator tenant registered")
    check(all(id == id.lower() for id in all_ids), "all tenant ids lowercase")

    print("\n== Hyphenation ==")
    bad = [t for t in all_ids if "_" in t]
    check(not bad, "no underscore in tenant ids", f"bad: {bad or 'none'}")
    expected = expected_providers | {"caan"}
    check(set(all_ids) == expected, "tenant id set exact",
          f"extra {sorted(set(all_ids) - expected) or 'none'}")

    print("\n== Per-tenant dataset ==")
    prov_missing = sorted(expected_providers - set(tenants))
    for p in OPERATOR_PROFILES:
        tid = p["id"]
        if tid not in tenants:
            check(False, f"{tid}: missing tenant doc")
            continue
        sub = {}
        for name in ("reports", "hazards", "can_cap", "surveys", "responses"):
            coll = db.collection("tenants").document(tid).collection(name)
            sub[name] = list(coll.stream())

        mors = [d.to_dict() for d in sub["reports"] if (d.to_dict() or {}).get("report_type") == "mandatory"]
        vsrs = [d.to_dict() for d in sub["reports"] if (d.to_dict() or {}).get("report_type") == "voluntary"]
        anon = [r for r in vsrs if r.get("is_anonymous")]
        anon_rate = (len(anon) / len(sub["reports"])) if sub["reports"] else 0.0
        vsr_anon_rate = (len(anon) / len(vsrs)) if vsrs else 0.0
        cans = [d.to_dict() for d in sub["can_cap"] if "can_reference" in (d.to_dict() or {})]
        caps = []
        for d in sub["can_cap"]:
            caps += list(db.collection("tenants").document(tid)
                         .collection("can_cap").document(d.id).collection("caps").stream())

        exp_total = p["vsr_count"] + p["mor_count"]
        print(f"  -- {tid}: total={len(sub['reports'])} "
              f"VSR={len(vsrs)} MOR={len(mors)} anonVSR={len(anon)} "
              f"vsrAnon={vsr_anon_rate:.0%} hazards={len(sub['hazards'])} "
              f"CANs={len(cans)} CAPs={len(caps)} "
              f"surveys={len(sub['surveys'])} responses={len(sub['responses'])}")
        check(len(sub["reports"]) == exp_total,
              f"{tid}: report total == profile",
              f"got {len(sub['reports'])} vs {exp_total}")
        check(len(mors) == p["mor_count"], f"{tid}: MOR count",
              f"got {len(mors)} vs {p['mor_count']}")
        check(len(vsrs) == p["vsr_count"], f"{tid}: VSR count",
              f"got {len(vsrs)} vs {p['vsr_count']}")
        # Strict 90:10 anonymity ratio on VSRs (10% named personas).
        check(0.80 <= vsr_anon_rate <= 1.0, f"{tid}: VSR anon rate ~90%",
              f"rate={vsr_anon_rate:.0%} (target ~90%)")
        check(len(sub["hazards"]) == p["hazard_count"], f"{tid}: hazard count",
              f"got {len(sub['hazards'])} vs {p['hazard_count']}")
        check(len(cans) == p["can_count"], f"{tid}: CAN count",
              f"got {len(cans)} vs {p['can_count']}")
        check(len(sub["surveys"]) == p["survey_count"], f"{tid}: survey count",
              f"got {len(sub['surveys'])} vs {p['survey_count']}")
        check(len(sub["responses"]) == p["survey_count"], f"{tid}: responses == survey count",
              f"got {len(sub['responses'])} vs {p['survey_count']}")

    print("\n== CAAN regulator ==")
    for name in ("reports", "hazards", "can_cap", "surveys", "responses"):
        coll = db.collection("tenants").document("caan").collection(name)
        n = len(list(coll.stream()))
        check(n == 0, f"caan.{name} empty", f"found {n}")

    print("\n== Departments in hazards + CANs ==")
    for p in OPERATOR_PROFILES:
        tid = p["id"]
        haz_deps = {(d.to_dict() or {}).get("department") for d in
                    db.collection("tenants").document(tid).collection("hazards").stream()}
        can_deps = {(d.to_dict() or {}).get("department") for d in
                    db.collection("tenants").document(tid).collection("can_cap").stream()}
        check("Part-145" in haz_deps and "CAMO" in haz_deps
              and "Flight Operations" in haz_deps and "Safety" in haz_deps,
              f"{tid}: hazards cover all 4 departments", f"{haz_deps}")
        postholder_deps = {"Flight Operations", "CAMO / Engineering",
                           "Ground Operations", "Cabin Services"}
        check(postholder_deps.issubset(can_deps),
              f"{tid}: CANs cover all 4 postholder departments", f"{can_deps}")

    print("\n== Operational profiles (tenants/{tid}/profile) ==")
    from seed.tenant_profiles import (
        TENANT_OPERATIONAL_PROFILES,
        get_aircraft_fleet,
        get_authorized_destinations,
        vsr_occurrence_types_for_tenant,
        mor_occurrence_types_for_tenant,
        hazard_titles_for_tenant,
    )

    for tid, profile in TENANT_OPERATIONAL_PROFILES.items():
        doc_ref = (db.collection("tenants").document(tid)
                   .collection("profile").document("operational"))
        stored = doc_ref.get()
        check(stored.exists, f"{tid}: profile doc stored under tenants/{tid}/profile")
        if not stored.exists:
            continue
        data = stored.to_dict() or {}
        check(data.get("category") == profile.category, f"{tid}: profile category",
              f"{data.get('category')}")
        check(data.get("fleet"), f"{tid}: profile fleet", f"{data.get('fleet')}")
        check(data.get("authorized_destinations"),
              f"{tid}: profile authorized_destinations",
              f"{data.get('authorized_destinations')}")

        # Fleet match: every seeded VSR/MOR aircraft_type comes from the fleet.
        fleet = set(get_aircraft_fleet(tid))
        for d in db.collection("tenants").document(tid).collection("reports").stream():
            data = d.to_dict() or {}
            ac_type = data.get("aircraft_type")
            if ac_type is not None:
                check(ac_type in fleet, f"{tid}: report aircraft in fleet", ac_type)

        # Location match: every seeded report location is authorized.
        authorized = set(get_authorized_destinations(tid))
        for d in db.collection("tenants").document(tid).collection("reports").stream():
            data = d.to_dict() or {}
            check(data.get("location") in authorized, f"{tid}: report location authorized",
                  f"{data.get('location')}")

        # Occurrence realism: report occurrence types + hazard titles in-domain.
        vsr_allowed = set(vsr_occurrence_types_for_tenant(tid, []))
        mor_allowed = set(mor_occurrence_types_for_tenant(tid, []))
        haz_allowed = set(hazard_titles_for_tenant(tid, []))
        for d in db.collection("tenants").document(tid).collection("reports").stream():
            data = d.to_dict() or {}
            pool = vsr_allowed if data.get("report_type") == "voluntary" else mor_allowed
            check(data.get("occurrence_type") in pool, f"{tid}: occurrence type in-domain",
                  f"{data.get('occurrence_type')}")
        for d in db.collection("tenants").document(tid).collection("hazards").stream():
            data = d.to_dict() or {}
            check(data.get("title") in haz_allowed, f"{tid}: hazard title in-domain",
                  f"{data.get('title')}")

    print("\n== Role accounts ==")
    auth = __import__("app.firebase", fromlist=["get_auth"]).get_auth()
    users = {u.uid: u for u in auth.list_users().iterate_all()}
    for p in OPERATOR_PROFILES:
        tid = p["id"]
        code = CREDENTIAL_TENANT_CODES.get(tid)
        uids = [u for u in users if u.endswith(f"-{tid}-001")]
        check(len(uids) == 4, f"{tid}: 4 simplified role accounts",
              f"uids {uids} (code={code})")
        if code:
            domain = CREDENTIAL_EMAIL_DOMAINS.get(tid, f"{tid}.com")
            for role in ("safety", "145", "camo", "ops"):
                email = f"{role}@{domain}"
                check(any(users[u].email == email for u in uids),
                      f"{tid}: {email} provisioned")

    legacy = [u for u in users.values() if (
        u.email and re.match(r"^(safety|ae|manager)\.", u.email or ""))]
    check(not legacy, "no legacy accounts remain", f"{len(legacy)} found")

    print("\n== Aggregate Anon Rate ==")
    all_reports = []
    all_anon = 0
    all_vsrs = 0
    anon_vsrs = 0
    for p in OPERATOR_PROFILES:
        tid = p["id"]
        for d in db.collection("tenants").document(tid).collection("reports").stream():
            data = d.to_dict() or {}
            all_reports.append(data)
            if data.get("is_anonymous"):
                all_anon += 1
            if data.get("report_type") == "voluntary":
                all_vsrs += 1
                if data.get("is_anonymous"):
                    anon_vsrs += 1
    overall = all_anon / len(all_reports) if all_reports else 0.0
    vsr_overall = anon_vsrs / all_vsrs if all_vsrs else 0.0
    print(f"  overall: anon={all_anon}/{len(all_reports)} rate={overall:.0%}")
    print(f"  VSR-only: anon={anon_vsrs}/{all_vsrs} rate={vsr_overall:.0%}")
    # Strict 90:10 VSR anonymity ratio (~63% overall once MORs are included).
    check(0.80 <= vsr_overall <= 1.0, "VSR Anon Rate ~90%",
          f"rate={vsr_overall:.0%} (target ~90%)")
    check(overall > 0.40, "overall Anon Rate reflects 90:10 VSR ratio",
          f"rate={overall:.0%} (expect ~63%)")

    print(f"\n{'FAILURES' if failures else 'ALL CHECKS PASSED'}: {failures}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()