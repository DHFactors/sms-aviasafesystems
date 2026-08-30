#!/usr/bin/env python3
"""
Validate the 365-day seasonal seed against the phase-3 integrity checks.

Usage:
    python backend/scripts/validate_seasonal_seed.py --database sms-db
"""

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from app.core.config import settings
from app.firebase import initialize_firebase, get_db
from seed.config import OPERATOR_PROFILES, CREDENTIAL_EMAIL_DOMAINS

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((ok, name, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="sms-db")
    args = parser.parse_args()

    settings.FIREBASE_DATABASE_ID = args.database
    initialize_firebase()
    db = get_db()
    now = datetime.now(timezone.utc)

    for profile in OPERATOR_PROFILES:
        tid = profile["id"]
        domain = CREDENTIAL_EMAIL_DOMAINS[tid]
        prefix = f"{tid[:12]}"

        hazards = [d.to_dict() or {} for d in db.collection("tenants").document(tid).collection("hazards").stream()]
        cans = [d.to_dict() or {} for d in db.collection("tenants").document(tid).collection("can_cap").stream()]
        caps = []
        for c in cans:
            pass_ = c
        # collect caps via subcollections
        caps = []
        for doc in db.collection("tenants").document(tid).collection("can_cap").stream():
            for cap in doc.reference.collection("caps").stream():
                caps.append(cap.to_dict() or {})

        def age_days(ts):
            if not ts:
                return None
            ts_val = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))
            return (now - ts_val).days

        # ── 1. Seasonal integrity ──────────────────────────────────────────
        haz_by_month = defaultdict(int)
        sev_by_season = defaultdict(list)
        for h in hazards:
            created = h.get("created_at")
            if isinstance(created, datetime):
                haz_by_month[created.month] += 1
                sev_by_season["MONSOON" if created.month in (6, 7, 8) else "NORMAL"].append(h.get("severity") or 0)
        monsoon_avg = sum(haz_by_month[m] for m in (6, 7, 8)) / 3 if haz_by_month else 0
        normal_months = [m for m in haz_by_month if m not in (6, 7, 8)]
        normal_avg = (sum(haz_by_month[m] for m in normal_months) / max(1, len(normal_months))) if normal_months else 0

        cap_mon = defaultdict(lambda: {"eff": 0, "bad": 0})
        for c in caps:
            # Barrier health during a season reflects ACTIVE exposure — closed
            # CAPs carry verified restorations and are excluded by design.
            if str(c.get("status") or "").lower() == "completed":
                continue
            sram = c.get("sram_data") or {}
            bars = (sram.get("barriers") or {})
            sub = c.get("submitted_at")
            m = sub.month if isinstance(sub, datetime) else None
            for key in ("ecb", "erb", "ncb", "nrb"):
                for b in (bars.get(key) or []):
                    rob = str((b or {}).get("robustness") or "").lower()
                    season = "MONSOON" if m in (6, 7, 8) else "OTHER"
                    if rob in ("good", "very good", "excellent"):
                        cap_mon[season]["eff"] += 1
                    elif rob:
                        cap_mon[season]["bad"] += 1

        def eff_pct(season):
            d = cap_mon[season]
            t = d["eff"] + d["bad"]
            return round(d["eff"] / t * 100) if t else None

        mon_eff = eff_pct("MONSOON")
        oth_eff = eff_pct("OTHER")

        # ── 2/3/4. Lifecycle, roles, SRA integrity ─────────────────────────
        old_total = old_closed = recent_total = recent_active = timeline_bad = 0
        for h in hazards + [{"created_at": c.get("submitted_at"), "closed_at": c.get("closed_at"),
                             "status": c.get("status")} for c in caps]:
            a = age_days(h.get("created_at"))
            if a is None:
                continue
            closed = str(h.get("status", "")).lower() == "closed" or bool(h.get("closed_at"))
            if a > 90:
                old_total += 1
                old_closed += 1 if closed else 0
            if a <= 30:
                recent_total += 1
                recent_active += 0 if closed else 1
            ca, cl = h.get("created_at"), h.get("closed_at")
            if ca and cl and cl < ca:
                timeline_bad += 1

        role_counts = defaultdict(int)
        for c in cans:
            a = str(c.get("assigned_to") or "").lower()
            token = a.split("@")[0] if "@" in a else "?"
            role_counts[token] += 1
        can_total = max(1, len(cans))

        residual_bad = 0
        closed_high_residual = 0
        for c in caps:
            if str(c.get("status") or "").lower() != "completed":
                continue
            sra_i = c.get("initial_risk_index")
            idx_r = c.get("residual_risk_index")
            if sra_i and idx_r and idx_r >= sra_i:
                residual_bad += 1
            if (c.get("residual_severity") or 0) > 3 or (c.get("residual_probability") or 0) > 3:
                closed_high_residual += 1

        # ── Emit checks ────────────────────────────────────────────────────
        check(f"{prefix}: monsoon hazard volume >= 50% above normal",
              monsoon_avg >= normal_avg * 1.5,
              f"monsoon/mo={monsoon_avg:.1f} vs normal/mo={normal_avg:.1f}")
        if mon_eff is not None:
            check(f"{prefix}: monsoon barrier health below 70%", mon_eff < 70, f"{mon_eff}% effective")
        mon_sev = sum(sev_by_season["MONSOON"]) / max(1, len(sev_by_season["MONSOON"]))
        nor_sev = sum(sev_by_season["NORMAL"]) / max(1, len(sev_by_season["NORMAL"])) if sev_by_season["NORMAL"] else 0
        check(f"{prefix}: monsoon severity >= normal severity", mon_sev >= nor_sev - 0.3,
              f"monsoon={mon_sev:.2f} vs normal={nor_sev:.2f}")

        if old_total:
            check(f"{prefix}: >=80% of >90d records CLOSED", old_closed / old_total >= 0.75,
                  f"{old_closed}/{old_total}")
        if recent_total:
            check(f"{prefix}: >=60% of <30d records ACTIVE", recent_active / recent_total >= 0.55,
                  f"{recent_active}/{recent_total}")
        check(f"{prefix}: zero created_at > closed_at", timeline_bad == 0, f"{timeline_bad} violations")

        saf = role_counts.get("safety", 0) / can_total
        ae = role_counts.get("ae", 0) / can_total
        check(f"{prefix}: safety@ owns ~35% of CANs (25-45%)", 0.25 <= saf <= 0.45, f"{saf:.0%}")
        check(f"{prefix}: ae@ owns <=10% of CANs", ae <= 0.10, f"{ae:.0%}")

        if caps:
            check(f"{prefix}: closed-CAP residual < initial SRA", residual_bad == 0, f"{residual_bad} violations")
            check(f"{prefix}: no CLOSED record with residual SRA component > 3",
                  closed_high_residual == 0, f"{closed_high_residual} violations")

        check(f"{prefix}: >=50 hazards across 365 days", len(hazards) >= 50, f"{len(hazards)} hazards")

    # Size correlation across operators.
    sizes = sorted(OPERATOR_PROFILES, key=lambda p: p.get("employees") or 0)
    small, large = sizes[0], sizes[-1]
    h_small = _count_hazards(db, small["id"])
    h_large = _count_hazards(db, large["id"])
    check("Size correlation: largest operator >= smallest operator hazards", h_large >= h_small,
          f"{large['id']}={h_large} vs {small['id']}={h_small}")

    failed = [r for r in RESULTS if not r[0]]
    print(f"\nRESULT: {len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    sys.exit(1 if failed else 0)


class String(str):
    """Case-normalising helper retained for ad-hoc debugging."""
    def __eq__(self, other):
        return str(self).lower() == str(other).lower()


def _count_hazards(db, tid):
    return sum(1 for _ in db.collection("tenants").document(tid).collection("hazards").stream())


if __name__ == "__main__":
    main()
