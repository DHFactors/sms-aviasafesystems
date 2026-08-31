from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from loguru import logger

from app.core.config import settings
from app.firebase import get_tenant_collection, get_cross_tenant_collection
from app.services.hazard_service import HazardService
from app.services.can_cap_service import CanCapService, CAN_COLLECTION, CAP_SUBCOLLECTION


HAZARD_COLLECTION = "hazards"
VERIFICATION_SUBCOLLECTION = "verifications"
CLOSURE_SUBCOLLECTION = "closure"


class VerificationService:
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    def _hazard_ref(self, hazard_doc_id: str):
        return get_tenant_collection(self.tenant_id, HAZARD_COLLECTION).document(hazard_doc_id)

    def _verifications_ref(self, hazard_doc_id: str):
        return self._hazard_ref(hazard_doc_id).collection(VERIFICATION_SUBCOLLECTION)

    def _closure_ref(self, hazard_doc_id: str):
        return self._hazard_ref(hazard_doc_id).collection(CLOSURE_SUBCOLLECTION)

    def _resolve_hazard_doc_id(self, hazard_id: str) -> Optional[str]:
        docs = get_tenant_collection(self.tenant_id, HAZARD_COLLECTION).get()
        for doc in docs:
            data = doc.to_dict()
            if doc.id == hazard_id or data.get("hazard_id") == hazard_id:
                return doc.id
        return None

    def _resolve_cap_doc(self, cap_id: str) -> Optional[tuple]:
        cans = get_tenant_collection(self.tenant_id, CAN_COLLECTION).get()
        for can_doc in cans:
            caps = can_doc.reference.collection(CAP_SUBCOLLECTION).get()
            for cap in caps:
                if cap.id == cap_id:
                    return cap, can_doc
        return None, None

    def create_verification(self, hazard_id: str, payload: dict, user: dict) -> dict:
        now = datetime.now(timezone.utc)
        hazard_doc_id = self._resolve_hazard_doc_id(hazard_id)
        if not hazard_doc_id:
            raise ValueError("Hazard not found")

        haz_ref = self._hazard_ref(hazard_doc_id)
        haz_data = haz_ref.get().to_dict()
        if haz_data.get("status") not in ("Under Review", "Pending Closure"):
            raise ValueError("Hazard must be Under Review or Pending Closure")

        cap_doc, _ = self._resolve_cap_doc(payload["cap_id"])
        if not cap_doc:
            raise ValueError("CAP not found")

        outcome = payload["outcome"]

        doc_data = {
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

        ref = self._verifications_ref(hazard_doc_id).add(doc_data)
        doc_id = ref[1].id
        doc_data["id"] = doc_id

        svc_user = {"uid": user["uid"], "role": "AIRLINE_ADMIN", "tenant_id": self.tenant_id}

        if outcome == "Accepted":
            HazardService(self.tenant_id).update_status(hazard_id, "Pending Closure", svc_user)
            logger.info(f"Hazard {hazard_id} → Pending Closure (verification accepted)")

        elif outcome == "Revision Required":
            can_cap_svc = CanCapService(self.tenant_id)
            cap_ref = cap_doc.reference
            cap_ref.update({
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
            haz_ref.update({"overdue": True, "updated_at": now})
            logger.warning(f"Hazard {hazard_id} marked overdue (escalation)")

        return doc_data

    def list_verifications(self, hazard_id: str, user: dict) -> List[dict]:
        if user.get("role") in settings.CROSS_TENANT_ROLES:
            docs = get_cross_tenant_collection(HAZARD_COLLECTION).get()
        else:
            docs = get_tenant_collection(self.tenant_id, HAZARD_COLLECTION).get()

        results = []
        for doc in docs:
            data = doc.to_dict()
            if doc.id == hazard_id or data.get("hazard_id") == hazard_id:
                verifications = doc.reference.collection(VERIFICATION_SUBCOLLECTION).get()
                for v in verifications:
                    vd = v.to_dict()
                    vd["id"] = v.id
                    self._serialize_timestamps(vd)
                    results.append(vd)
                break

        results.sort(key=lambda r: r.get("created_at", datetime.min), reverse=True)
        return results

    def get_verification(self, verification_id: str, user: dict) -> Optional[dict]:
        if user.get("role") in settings.CROSS_TENANT_ROLES:
            haz_docs = get_cross_tenant_collection(HAZARD_COLLECTION).get()
        else:
            haz_docs = get_tenant_collection(self.tenant_id, HAZARD_COLLECTION).get()

        for haz_doc in haz_docs:
            v_docs = haz_doc.reference.collection(VERIFICATION_SUBCOLLECTION).get()
            for v in v_docs:
                if v.id == verification_id:
                    vd = v.to_dict()
                    vd["id"] = v.id
                    self._serialize_timestamps(vd)
                    return vd
        return None

    def create_closure(self, hazard_id: str, payload: dict, user: dict) -> dict:
        now = datetime.now(timezone.utc)
        hazard_doc_id = self._resolve_hazard_doc_id(hazard_id)
        if not hazard_doc_id:
            raise ValueError("Hazard not found")

        haz_ref = self._hazard_ref(hazard_doc_id)
        haz_data = haz_ref.get().to_dict()

        if haz_data.get("status") != "Pending Closure":
            raise ValueError("Hazard must be in Pending Closure status")

        verifications = list(self._verifications_ref(hazard_doc_id).get())
        if not verifications:
            raise ValueError("No verification record found for this hazard")

        latest_v = verifications[-1].to_dict()
        if latest_v.get("outcome") != "Accepted":
            raise ValueError("Latest verification outcome must be Accepted")

        doc_data = {
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

        ref = self._closure_ref(hazard_doc_id).add(doc_data)

        haz_ref.update({
            "status": "Closed",
            "closed_at": now,
            "closed_by": user["uid"],
            "closure_id": ref[1].id,
            "archived": True,
            "updated_at": now,
        })

        doc_data["id"] = ref[1].id
        logger.info(f"Hazard {hazard_id} closed and archived by {user['uid']}")

        return doc_data

    def get_closure(self, hazard_id: str, user: dict) -> Optional[dict]:
        if user.get("role") in settings.CROSS_TENANT_ROLES:
            docs = get_cross_tenant_collection(HAZARD_COLLECTION).get()
        else:
            docs = get_tenant_collection(self.tenant_id, HAZARD_COLLECTION).get()

        for doc in docs:
            data = doc.to_dict()
            if doc.id == hazard_id or data.get("hazard_id") == hazard_id:
                closures = doc.reference.collection(CLOSURE_SUBCOLLECTION).get()
                for c in closures:
                    cd = c.to_dict()
                    cd["id"] = c.id
                    self._serialize_timestamps(cd)
                    return cd
                break
        return None

    def reopen_hazard(self, hazard_id: str, reason: str, user: dict) -> Optional[dict]:
        svc_user = {"uid": user["uid"], "role": "AIRLINE_ADMIN", "tenant_id": self.tenant_id}
        logger.info(f"Hazard {hazard_id} reopened: {reason}")
        updated = HazardService(self.tenant_id).update_status(hazard_id, "Reopened", svc_user)
        # A hazard archived on closure must be fully reactivated on reopen, so
        # clear the Firestore archived flag to keep the document consistent.
        hazard_doc_id = self._resolve_hazard_doc_id(hazard_id)
        if hazard_doc_id:
            self._hazard_ref(hazard_doc_id).update({
                "archived": False,
                "updated_at": datetime.now(timezone.utc),
            })
        return updated

    def get_verification_stats(self, user: dict) -> Dict[str, Any]:
        try:
            if user.get("role") in settings.CROSS_TENANT_ROLES:
                docs = get_cross_tenant_collection(HAZARD_COLLECTION).get()
            else:
                docs = get_tenant_collection(self.tenant_id, HAZARD_COLLECTION).get()

            stats = {
                "pending_verification": 0,
                "under_verification": 0,
                "verified": 0,
                "pending_closure": 0,
                "closed": 0,
                "reopened": 0,
            }

            for doc in docs:
                data = doc.to_dict()
                status = data.get("status", "Open")
                verifications = list(doc.reference.collection(VERIFICATION_SUBCOLLECTION).get())
                has_closure = len(list(doc.reference.collection(CLOSURE_SUBCOLLECTION).get())) > 0

                if status == "Under Review":
                    if len(verifications) == 0:
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
