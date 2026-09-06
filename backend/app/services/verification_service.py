import uuid as _uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from loguru import logger

from app.core.config import settings
from app.db import pg
from app.db.db_models import Can, Cap, Closure, Hazard, Verification
from app.db.ids import tenant_uuid
from app.services.hazard_service import HazardService
from app.services.can_cap_service import CanCapService


HAZARD_COLLECTION = "hazards"
VERIFICATION_SUBCOLLECTION = "verifications"
CLOSURE_SUBCOLLECTION = "closure"


class VerificationService:
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self._tid_uuid = tenant_uuid(tenant_id)

    def _resolve_hazard(self, hazard_id: str) -> Optional[Dict[str, Any]]:
        for row in pg.fetch_all(Hazard, where=[Hazard.tenant_id == self._tid_uuid]):
            if row.get("id") == hazard_id or row.get("hazard_id") == hazard_id:
                return row
        return None

    def _resolve_cap(self, cap_id: str) -> Optional[Dict[str, Any]]:
        for row in pg.fetch_all(Cap, where=[Cap.tenant_id == self._tid_uuid]):
            if (
                row.get("id") == cap_id
                or row.get("cap_reference") == cap_id
                or row.get("finding_number") == cap_id
            ):
                return row
        return None

    def _verifications(self, hazard_uuid: str) -> List[Dict[str, Any]]:
        return pg.fetch_all(
            Verification,
            where=[
                Verification.tenant_id == self._tid_uuid,
                Verification.hazard_id == hazard_uuid,
            ],
        )

    def _closures(self, hazard_uuid: str) -> List[Dict[str, Any]]:
        return pg.fetch_all(
            Closure,
            where=[
                Closure.tenant_id == self._tid_uuid,
                Closure.hazard_id == hazard_uuid,
            ],
        )

    def create_verification(self, hazard_id: str, payload: dict, user: dict) -> dict:
        now = datetime.now(timezone.utc)
        haz_row = self._resolve_hazard(hazard_id)
        if not haz_row:
            raise ValueError("Hazard not found")
        haz_uuid = str(haz_row["id"])

        if haz_row.get("status") not in ("Under Review", "Pending Closure"):
            raise ValueError("Hazard must be Under Review or Pending Closure")

        cap_row = self._resolve_cap(payload["cap_id"])
        if not cap_row:
            raise ValueError("CAP not found")
        cap_uuid = str(cap_row["id"])

        outcome = payload["outcome"]

        doc_data = {
            "id": str(_uuid.uuid4()),
            "hazard_id": hazard_id,
            "cap_id": payload["cap_id"],
            "outcome": outcome,
            "comments": payload.get("comments"),
            "evidence": payload.get("evidence") or [],
            "verified_by": user.get("email", user["uid"]),
            "verified_by_uid": user["uid"],
            "verification_date": payload.get("verification_date") or now,
            "revision_deadline": payload.get("revision_deadline"),
            "revision_notes": payload.get("revision_notes"),
            "created_at": now,
            "updated_at": now,
        }

        stored = dict(doc_data)
        stored["tenant_id"] = self._tid_uuid
        stored["hazard_id"] = haz_uuid
        stored["cap_id"] = cap_uuid
        pg.upsert(Verification, "id", doc_data["id"], stored)

        svc_user = {"uid": user["uid"], "role": "AIRLINE_ADMIN", "tenant_id": self.tenant_id}

        if outcome == "Accepted":
            HazardService(self.tenant_id).update_status(hazard_id, "Pending Closure", svc_user)
            logger.info(f"Hazard {hazard_id} → Pending Closure (verification accepted)")

        elif outcome == "Revision Required":
            can_cap_svc = CanCapService(self.tenant_id)
            pg.update(Cap, "id", cap_uuid, {
                "status": "Revision Required",
                "reviewed_by": user.get("email", user["uid"]),
                "reviewed_by_uid": user["uid"],
                "reviewed_at": now,
                "review_comments": payload.get("comments"),
                "revision_deadline": payload.get("revision_deadline"),
                "revision_notes": payload.get("revision_notes"),
                "updated_at": now,
            })
            HazardService(self.tenant_id).update_status(hazard_id, "Processing", svc_user)
            logger.info(f"Hazard {hazard_id} → Processing (revision required)")

        elif outcome == "Ineffective":
            HazardService(self.tenant_id).update_status(hazard_id, "Reopened", svc_user)
            logger.info(f"Hazard {hazard_id} → Reopened (CAP ineffective)")

        elif outcome == "Overdue":
            pg.update(Hazard, "id", haz_uuid, {"overdue": True, "updated_at": now})
            logger.warning(f"Hazard {hazard_id} marked overdue (escalation)")

        return doc_data

    def list_verifications(self, hazard_id: str, user: dict) -> List[dict]:
        haz_row = self._resolve_hazard(hazard_id)
        if not haz_row:
            return []
        haz_uuid = str(haz_row["id"])
        results = []
        for vd in self._verifications(haz_uuid):
            vd = dict(vd)
            vd["hazard_id"] = hazard_id
            vd["id"] = str(vd.get("id") or "")
            self._serialize_timestamps(vd)
            results.append(vd)

        results.sort(key=lambda r: r.get("created_at", datetime.min), reverse=True)
        return results

    def get_verification(self, verification_id: str, user: dict) -> Optional[dict]:
        for vd in pg.fetch_all(Verification, where=[Verification.tenant_id == self._tid_uuid]):
            if str(vd.get("id") or "") == verification_id:
                vd = dict(vd)
                vd["id"] = str(vd.get("id") or "")
                self._serialize_timestamps(vd)
                return vd
        return None

    def create_closure(self, hazard_id: str, payload: dict, user: dict) -> dict:
        now = datetime.now(timezone.utc)
        haz_row = self._resolve_hazard(hazard_id)
        if not haz_row:
            raise ValueError("Hazard not found")
        haz_uuid = str(haz_row["id"])

        if haz_row.get("status") != "Pending Closure":
            raise ValueError("Hazard must be in Pending Closure status")

        verifications = self._verifications(haz_uuid)
        if not verifications:
            raise ValueError("No verification record found for this hazard")

        latest_v = verifications[-1]
        if latest_v.get("outcome") != "Accepted":
            raise ValueError("Latest verification outcome must be Accepted")

        closure_id = str(_uuid.uuid4())
        doc_data = {
            "id": closure_id,
            "hazard_id": hazard_id,
            "lessons_learned": payload.get("lessons_learned"),
            "recommendations": payload.get("recommendations"),
            "approval_notes": payload.get("approval_notes"),
            "approved_by": user.get("email", user["uid"]),
            "approved_by_uid": user["uid"],
            "approved_at": now,
            "created_at": now,
            "updated_at": now,
        }

        stored = dict(doc_data)
        stored["tenant_id"] = self._tid_uuid
        stored["hazard_id"] = haz_uuid
        pg.upsert(Closure, "id", closure_id, stored)

        pg.update(Hazard, "id", haz_uuid, {
            "status": "Closed",
            "closed_at": now,
            "closed_by": user["uid"],
            "closure_id": closure_id,
            "archived": True,
            "updated_at": now,
        })

        logger.info(f"Hazard {hazard_id} closed and archived by {user['uid']}")

        return doc_data

    def get_closure(self, hazard_id: str, user: dict) -> Optional[dict]:
        haz_row = self._resolve_hazard(hazard_id)
        if not haz_row:
            return None
        closures = self._closures(str(haz_row["id"]))
        if not closures:
            return None
        cd = dict(closures[0])
        cd["hazard_id"] = hazard_id
        cd["id"] = str(cd.get("id") or "")
        self._serialize_timestamps(cd)
        return cd

    def reopen_hazard(self, hazard_id: str, reason: str, user: dict) -> Optional[dict]:
        svc_user = {"uid": user["uid"], "role": "AIRLINE_ADMIN", "tenant_id": self.tenant_id}
        logger.info(f"Hazard {hazard_id} reopened: {reason}")
        updated = HazardService(self.tenant_id).update_status(hazard_id, "Reopened", svc_user)
        haz_row = self._resolve_hazard(hazard_id)
        if haz_row:
            pg.update(Hazard, "id", str(haz_row["id"]), {
                "archived": False,
                "updated_at": datetime.now(timezone.utc),
            })
        return updated

    def get_verification_stats(self, user: dict) -> Dict[str, Any]:
        try:
            haz_rows = pg.fetch_all(Hazard, where=[Hazard.tenant_id == self._tid_uuid])
            verifications = pg.fetch_all(Verification, where=[Verification.tenant_id == self._tid_uuid])
            closures = pg.fetch_all(Closure, where=[Closure.tenant_id == self._tid_uuid])

            v_by_hazard: Dict[str, int] = {}
            for v in verifications:
                key = str(v.get("hazard_id") or "")
                v_by_hazard[key] = v_by_hazard.get(key, 0) + 1
            closed_hazard_ids = {str(c.get("hazard_id") or "") for c in closures}

            stats = {
                "pending_verification": 0,
                "under_verification": 0,
                "verified": 0,
                "pending_closure": 0,
                "closed": 0,
                "reopened": 0,
            }

            for doc in haz_rows:
                haz_uuid = str(doc.get("id") or "")
                status = doc.get("status", "Open")
                v_count = v_by_hazard.get(haz_uuid, 0)
                has_closure = haz_uuid in closed_hazard_ids

                if status == "Under Review":
                    if v_count == 0:
                        stats["pending_verification"] += 1
                    else:
                        stats["under_verification"] += 1
                elif status == "Pending Closure":
                    stats["pending_closure"] += 1
                elif status == "Closed":
                    stats["closed"] += 1
                elif status == "Reopened":
                    stats["reopened"] += 1

                if has_closure:
                    stats["verified"] += 1

            return stats
        except Exception as e:
            logger.error(f"Failed to get verification stats: {e}")
            raise

    @staticmethod
    def _serialize_timestamps(data: dict) -> None:
        for key in ("created_at", "updated_at", "verification_date", "revision_deadline", "approved_at"):
            if key in data and hasattr(data[key], "isoformat"):
                data[key] = data[key].isoformat()