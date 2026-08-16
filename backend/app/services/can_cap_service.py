from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from loguru import logger

from app.core.config import settings
from app.firebase import get_tenant_collection, get_cross_tenant_collection
from app.services.hazard_service import HazardService
from app.services.users import get_user_department
from app.services.repository import coerce_utc_datetime
from app.services.risk_matrix import compute_risk_index, get_risk_level, risk_outcome, get_thresholds


CAN_COLLECTION = "can_cap"
CAP_SUBCOLLECTION = "caps"


def generate_can_reference(tenant_id: str, sequence: int) -> str:
    return f"CAN-{sequence:03d}"


def generate_cap_reference(can_reference: str, sequence: int) -> str:
    return f"{can_reference}-CAP-{sequence:03d}"


class CanCapService:
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    def _can_collection(self):
        return get_tenant_collection(self.tenant_id, CAN_COLLECTION)

    def _caps_collection(self, can_doc_id: str):
        return self._can_collection().document(can_doc_id).collection(CAP_SUBCOLLECTION)

    def _get_next_can_sequence(self) -> int:
        try:
            docs = self._can_collection().get()
            max_seq = 0
            for doc in docs:
                data = doc.to_dict()
                ref = data.get("can_reference", "")
                if ref.startswith("CAN-"):
                    try:
                        seq = int(ref.split("-")[1])
                        if seq > max_seq:
                            max_seq = seq
                    except (IndexError, ValueError):
                        pass
            return max_seq + 1
        except Exception as e:
            logger.error(f"Failed to get next CAN sequence: {e}")
            return 1

    def _get_next_cap_sequence(self, can_doc_id: str, can_reference: str) -> int:
        try:
            docs = self._caps_collection(can_doc_id).get()
            return len(docs) + 1
        except Exception as e:
            logger.warning(f"Failed to get next CAP sequence: {e}")
            return 1

    # ── SRA (Safety Risk Assessment) helpers ──

    SEVERITY_LETTERS = ["A", "B", "C", "D", "E"]

    @classmethod
    def classify_sra(cls, severity, probability, thresholds=None):
        """Server-side canonical SRA classification (Risk Index, Level, Outcome).

        Authority lives here (not the client) so stored risk states always
        reflect the tenant's configured 5x5 matrix thresholds.
        """
        if severity is None or probability is None:
            return None
        try:
            sev = int(severity)
            prob = int(probability)
        except (TypeError, ValueError):
            return None
        if not (1 <= sev <= 5 and 1 <= prob <= 5):
            return None
        index = compute_risk_index(sev, prob)
        level = get_risk_level(index, thresholds)
        outcome = risk_outcome(sev, prob, thresholds)
        return {
            "severity": sev,
            "severity_letter": cls.SEVERITY_LETTERS[sev - 1],
            "probability": prob,
            "risk_index": index,
            "risk_level": level,
            "risk_outcome": outcome,
        }

    def _sra_block(self, severity, probability, assessed_by=None, assessed_at=None, provided=None):
        """Merge canonical SRA classification with any provided audit fields."""
        thresholds = get_thresholds(self.tenant_id)
        classified = self.classify_sra(severity, probability, thresholds)
        if classified is None:
            return None
        provided = provided or {}
        classified["assessed_by"] = provided.get("assessed_by") or assessed_by
        classified["assessed_at"] = provided.get("assessed_at") or assessed_at
        return classified

    # ── CAN CRUD ──

    def issue_can(self, payload: dict, user: dict) -> dict:
        now = datetime.now(timezone.utc)
        sequence = self._get_next_can_sequence()
        can_reference = generate_can_reference(self.tenant_id, sequence)

        doc_data = {
            "can_reference": can_reference,
            "hazard_id": payload["hazard_id"],
            "title": payload["title"],
            "description": payload["description"],
            "required_action": payload["required_action"],
            "target_completion_date": payload["target_completion_date"],
            "assigned_to": payload["assigned_to"],
            "assigned_to_uid": payload.get("assigned_to_uid", ""),
            "department": payload.get("department")
            or (
                get_user_department(
                    uid=payload.get("assigned_to_uid"), email=payload.get("assigned_to")
                )
                if payload.get("assigned_to_uid") or payload.get("assigned_to")
                else ""
            ),
            "priority": payload["priority"],
            "status": "Open",
            "issued_by": user.get("email", user["uid"]),
            "issued_by_uid": user["uid"],
            "issued_at": now,
            "tenant_id": self.tenant_id,
            "created_by": user["uid"],
            "created_at": now,
            "updated_at": now,
            # Buddha Air FORM SMSM 8.8.2 — CAN issuance block (all optional)
            "copies_to": payload.get("copies_to"),
            "requested_function": payload.get("requested_function"),
            "addressed_function": payload.get("addressed_function"),
            "initial_severity": payload.get("initial_severity"),
            "initial_probability": payload.get("initial_probability"),
            "initial_risk_index": payload.get("initial_risk_index"),
            "initial_risk_level": payload.get("initial_risk_level"),
            "initial_risk_outcome": payload.get("initial_risk_outcome"),
            "initial_sra": payload.get("initial_sra"),
            "classification_type": payload.get("classification_type"),
            "classification_level": payload.get("classification_level"),
        }

        # Server-side SRA canonicalisation: recompute index/level/outcome from the
        # tenant's configured risk matrix thresholds; never trust the client.
        initial_sra = self._sra_block(
            payload.get("initial_severity"),
            payload.get("initial_probability"),
            assessed_by=user.get("email", user["uid"]),
            assessed_at=now,
            provided=payload.get("initial_sra"),
        )
        if initial_sra:
            doc_data["initial_sra"] = initial_sra
            doc_data["initial_severity"] = initial_sra["severity"]
            doc_data["initial_probability"] = initial_sra["probability"]
            doc_data["initial_risk_index"] = initial_sra["risk_index"]
            doc_data["initial_risk_level"] = initial_sra["risk_level"]
            doc_data["initial_risk_outcome"] = initial_sra["risk_outcome"]
        elif payload.get("initial_risk_index"):
            # Back-compat: legacy clients that only sent an index get a level too.
            thresholds = get_thresholds(self.tenant_id)
            doc_data["initial_risk_level"] = get_risk_level(payload["initial_risk_index"], thresholds)
            doc_data["initial_risk_outcome"] = risk_outcome(
                payload.get("initial_severity") or 1,
                payload.get("initial_probability") or 1,
                thresholds,
            )

        try:
            ref = self._can_collection().add(doc_data)
            doc_id = ref[1].id
            doc_data["id"] = doc_id
            logger.info(f"CAN {can_reference} issued by {user['uid']}")

            # Update hazard status to Processing
            self._update_hazard_status(payload["hazard_id"], "Processing")

            return doc_data
        except Exception as e:
            logger.error(f"Failed to issue CAN: {e}")
            raise

    def get_can(self, can_id: str, user: dict) -> Optional[dict]:
        try:
            if user.get("role") in settings.CROSS_TENANT_ROLES:
                docs = get_cross_tenant_collection(CAN_COLLECTION).get()
            else:
                docs = self._can_collection().get()

            for doc in docs:
                data = doc.to_dict()
                if doc.id == can_id or data.get("can_reference") == can_id:
                    data["id"] = doc.id
                    self._serialize_timestamps(data)

                    # Attach latest CAP
                    try:
                        caps = doc.reference.collection(CAP_SUBCOLLECTION).order_by("created_at", direction="DESCENDING").limit(1).get()
                        if caps:
                            cap_data = caps[0].to_dict()
                            cap_data["id"] = caps[0].id
                            self._serialize_timestamps(cap_data)
                            data["latest_cap"] = cap_data
                    except Exception:
                        pass

                    return data
            return None
        except Exception as e:
            logger.error(f"Failed to get CAN {can_id}: {e}")
            raise

    def list_cans(self, user: dict, filters: dict = None) -> List[dict]:
        try:
            if user.get("role") in settings.CROSS_TENANT_ROLES:
                docs = get_cross_tenant_collection(CAN_COLLECTION).get()
            else:
                docs = self._can_collection().get()

            results = []
            for doc in docs:
                data = doc.to_dict()
                data["id"] = doc.id

                if filters:
                    if filters.get("days"):
                        cutoff = datetime.now(timezone.utc) - timedelta(days=filters["days"])
                        issued = coerce_utc_datetime(
                            data.get("issued_at") or data.get("created_at")
                        )
                        if issued is None or issued < cutoff:
                            continue
                    if filters.get("hazard_id") and data.get("hazard_id") != filters["hazard_id"]:
                        continue
                    if filters.get("status") and data.get("status") != filters["status"]:
                        continue
                    if filters.get("priority") and data.get("priority") != filters["priority"]:
                        continue
                    if filters.get("assigned_to") and data.get("assigned_to") != filters["assigned_to"]:
                        continue
                    if filters.get("department") and (data.get("department") or "") != filters["department"]:
                        continue
                    if filters.get("search"):
                        s = filters["search"].lower()
                        ref = (data.get("can_reference") or "").lower()
                        title = (data.get("title") or "").lower()
                        if s not in ref and s not in title:
                            continue

                self._serialize_timestamps(data)
                results.append(data)

            results.sort(key=lambda r: r.get("created_at", datetime.min), reverse=True)
            return results
        except Exception as e:
            logger.error(f"Failed to list CANs: {e}")
            raise

    def update_can(self, can_id: str, payload: dict, user: dict) -> Optional[dict]:
        try:
            docs = self._can_collection().get()
            target_id = None
            for doc in docs:
                data = doc.to_dict()
                if doc.id == can_id or data.get("can_reference") == can_id:
                    target_id = doc.id
                    break

            if not target_id:
                return None

            ref = self._can_collection().document(target_id)
            if "assigned_to" in payload or "assigned_to_uid" in payload:
                current = ref.get().to_dict() or {}
                new_uid = payload.get("assigned_to_uid", current.get("assigned_to_uid"))
                new_email = payload.get("assigned_to", current.get("assigned_to"))
                payload["department"] = get_user_department(uid=new_uid, email=new_email)
            payload["updated_at"] = datetime.now(timezone.utc)
            ref.update(payload)

            updated = ref.get().to_dict()
            updated["id"] = target_id
            self._serialize_timestamps(updated)
            return updated
        except Exception as e:
            logger.error(f"Failed to update CAN {can_id}: {e}")
            raise

    def update_can_status(self, can_id: str, status: str, user: dict) -> Optional[dict]:
        try:
            docs = self._can_collection().get()
            target_id = None
            for doc in docs:
                data = doc.to_dict()
                if doc.id == can_id or data.get("can_reference") == can_id:
                    target_id = doc.id
                    break

            if not target_id:
                return None

            ref = self._can_collection().document(target_id)
            now = datetime.now(timezone.utc)
            ref.update({"status": status, "updated_at": now})

            updated = ref.get().to_dict()
            updated["id"] = target_id
            self._serialize_timestamps(updated)
            return updated
        except Exception as e:
            logger.error(f"Failed to update CAN status {can_id}: {e}")
            raise

    def delete_can(self, can_id: str) -> bool:
        try:
            docs = self._can_collection().get()
            target_id = None
            for doc in docs:
                data = doc.to_dict()
                if doc.id == can_id or data.get("can_reference") == can_id:
                    target_id = doc.id
                    break

            if not target_id:
                return False

            # Delete CAP sub-collection first
            caps = self._caps_collection(target_id).get()
            for cap in caps:
                cap.reference.delete()

            self._can_collection().document(target_id).delete()
            logger.info(f"CAN {can_id} deleted")
            return True
        except Exception as e:
            logger.error(f"Failed to delete CAN {can_id}: {e}")
            raise

    # ── CAP CRUD ──

    def submit_cap(self, can_id: str, payload: dict, user: dict) -> dict:
        now = datetime.now(timezone.utc)

        # Resolve CAN
        docs = self._can_collection().get()
        can_doc_id = None
        can_ref = None
        can_data = {}
        for doc in docs:
            data = doc.to_dict()
            if doc.id == can_id or data.get("can_reference") == can_id:
                can_doc_id = doc.id
                can_ref = data.get("can_reference")
                can_data = data
                break

        if not can_doc_id:
            raise ValueError("CAN not found")

        can_department = can_data.get("department", "")

        sequence = self._get_next_cap_sequence(can_doc_id, can_ref)
        cap_reference = generate_cap_reference(can_ref, sequence)

        doc_data = {
            "cap_reference": cap_reference,
            "can_id": can_id,
            "department": payload.get("department") or can_department or "",
            "action_plan": payload["action_plan"],
            "timeline": payload["timeline"],
            "resources_required": payload.get("resources_required"),
            "implementation_plan": payload.get("implementation_plan"),
            "target_completion_date": payload["target_completion_date"],
            "status": "In Progress",
            "submitted_by": user.get("email", user["uid"]),
            "submitted_by_uid": user["uid"],
            "submitted_at": now,
            "created_at": now,
            "updated_at": now,
            # Buddha Air FORM SMSM 8.8.2 — CAP submission block (all optional)
            "company_name": payload.get("company_name"),
            "base_location": payload.get("base_location"),
            "area_system_of_interest": payload.get("area_system_of_interest"),
            "finding_number": payload.get("finding_number"),
            "file_ref": payload.get("file_ref"),
            "factual_review": payload.get("factual_review"),
            "rca": payload.get("rca"),
            "short_term_ca": payload.get("short_term_ca"),
            "long_term_ca": payload.get("long_term_ca"),
            "implementation_timeline": payload.get("implementation_timeline"),
            "managerial_approval": payload.get("managerial_approval"),
            "caa_acceptance": payload.get("caa_acceptance"),
            "residual_severity": payload.get("residual_severity"),
            "residual_probability": payload.get("residual_probability"),
            "residual_risk_index": payload.get("residual_risk_index"),
            "residual_risk_level": payload.get("residual_risk_level"),
            "residual_risk_outcome": payload.get("residual_risk_outcome"),
            "residual_sra": payload.get("residual_sra"),
            # Structured RCA (Fishbone / Ishikawa 5M + Management)
            "root_causes": payload.get("root_causes") or None,
            "action_items": payload.get("action_items") or None,
            "process_owner": payload.get("process_owner"),
        }

        # Server-side Residual SRA canonicalisation.
        residual_sra = self._sra_block(
            payload.get("residual_severity"),
            payload.get("residual_probability"),
            assessed_by=user.get("email", user["uid"]),
            assessed_at=now,
            provided=payload.get("residual_sra"),
        )
        if residual_sra:
            doc_data["residual_sra"] = residual_sra
            doc_data["residual_severity"] = residual_sra["severity"]
            doc_data["residual_probability"] = residual_sra["probability"]
            doc_data["residual_risk_index"] = residual_sra["risk_index"]
            doc_data["residual_risk_level"] = residual_sra["risk_level"]
            doc_data["residual_risk_outcome"] = residual_sra["risk_outcome"]
        elif payload.get("residual_risk_index"):
            thresholds = get_thresholds(self.tenant_id)
            doc_data["residual_risk_level"] = get_risk_level(payload["residual_risk_index"], thresholds)
            doc_data["residual_risk_outcome"] = risk_outcome(
                payload.get("residual_severity") or 1,
                payload.get("residual_probability") or 1,
                thresholds,
            )

        try:
            ref = self._caps_collection(can_doc_id).add(doc_data)
            cap_doc_id = ref[1].id
            doc_data["id"] = cap_doc_id
            logger.info(f"CAP {cap_reference} submitted for CAN {can_ref}")

            # Update CAN status to Under Review
            self._can_collection().document(can_doc_id).update({
                "status": "Under Review",
                "updated_at": now,
            })

            return doc_data
        except Exception as e:
            logger.error(f"Failed to submit CAP: {e}")
            raise

    def list_caps(self, can_id: str, user: dict) -> List[dict]:
        try:
            if user.get("role") in settings.CROSS_TENANT_ROLES:
                docs = get_cross_tenant_collection(CAN_COLLECTION).get()
            else:
                docs = self._can_collection().get()
            can_doc = None
            for doc in docs:
                data = doc.to_dict()
                if doc.id == can_id or data.get("can_reference") == can_id:
                    can_doc = doc
                    break

            if not can_doc:
                return []

            caps = can_doc.reference.collection(CAP_SUBCOLLECTION).get()
            results = []
            for cap in caps:
                data = cap.to_dict()
                data["id"] = cap.id
                self._serialize_timestamps(data)
                results.append(data)

            results.sort(key=lambda r: r.get("created_at", datetime.min), reverse=True)
            return results
        except Exception as e:
            logger.error(f"Failed to list CAPs for CAN {can_id}: {e}")
            raise

    def list_all_caps(self, user: dict, filters: dict = None) -> List[dict]:
        """List every CAP across the tenant's CANs, joined with the parent CAN
        (reference + issued date) so pages can show 'date CAN received' and the
        CAN a CAP refers to without an extra round-trip."""
        try:
            if user.get("role") in settings.CROSS_TENANT_ROLES:
                docs = get_cross_tenant_collection(CAN_COLLECTION).get()
            else:
                docs = self._can_collection().get()

            filters = filters or {}
            status_f = filters.get("status")
            can_id_f = filters.get("can_id")
            department_f = filters.get("department")
            days_f = filters.get("days")
            search = (filters.get("search") or "").lower()

            cutoff = None
            if days_f:
                cutoff = datetime.now(timezone.utc) - timedelta(days=days_f)

            results = []
            for can_doc in docs:
                can_data = can_doc.to_dict()
                if can_id_f and can_doc.id != can_id_f and can_data.get("can_reference") != can_id_f:
                    continue
                caps = can_doc.reference.collection(CAP_SUBCOLLECTION).get()
                for cap in caps:
                    data = cap.to_dict()
                    if status_f and data.get("status") != status_f:
                        continue
                    if cutoff:
                        submitted = coerce_utc_datetime(
                            data.get("submitted_at") or data.get("created_at")
                        )
                        if submitted is None or submitted < cutoff:
                            continue
                    data["id"] = cap.id
                    data["can_id"] = can_doc.id
                    data["can_reference"] = can_data.get("can_reference", "")
                    can_issued = can_data.get("issued_at")
                    if hasattr(can_issued, "isoformat"):
                        can_issued = can_issued.isoformat()
                    data["can_issued_at"] = can_issued
                    data["hazard_id"] = can_data.get("hazard_id", "")
                    data["priority"] = can_data.get("priority", "")
                    data["department"] = data.get("department") or can_data.get("department", "")
                    if department_f and (data["department"] or "") != department_f:
                        continue
                    self._serialize_timestamps(data)
                    if search:
                        hay = " ".join(str(v) for v in [
                            data.get("cap_reference", ""),
                            data.get("can_reference", ""),
                            data.get("action_plan", ""),
                            data.get("status", ""),
                        ]).lower()
                        if search not in hay:
                            continue
                    results.append(data)

            results.sort(
                key=lambda r: r.get("submitted_at") or r.get("created_at") or datetime.min,
                reverse=True,
            )
            return results
        except Exception as e:
            logger.error(f"Failed to list all CAPs: {e}")
            raise

    def get_cap(self, cap_id: str, user: dict) -> Optional[dict]:
        try:
            if user.get("role") in settings.CROSS_TENANT_ROLES:
                all_cans = get_cross_tenant_collection(CAN_COLLECTION).get()
            else:
                all_cans = self._can_collection().get()

            for can_doc in all_cans:
                caps = can_doc.reference.collection(CAP_SUBCOLLECTION).get()
                for cap in caps:
                    if cap.id == cap_id:
                        data = cap.to_dict()
                        data["id"] = cap.id
                        self._serialize_timestamps(data)
                        return data
            return None
        except Exception as e:
            logger.error(f"Failed to get CAP {cap_id}: {e}")
            raise

    def update_cap(self, cap_id: str, payload: dict, user: dict) -> Optional[dict]:
        try:
            all_cans = self._can_collection().get()
            for can_doc in all_cans:
                caps = self._caps_collection(can_doc.id).get()
                for cap in caps:
                    if cap.id == cap_id:
                        ref = self._caps_collection(can_doc.id).document(cap.id)
                        payload["updated_at"] = datetime.now(timezone.utc)
                        ref.update(payload)
                        updated = ref.get().to_dict()
                        updated["id"] = cap.id
                        self._serialize_timestamps(updated)
                        return updated
            return None
        except Exception as e:
            logger.error(f"Failed to update CAP {cap_id}: {e}")
            raise

    def review_cap(self, cap_id: str, review: dict, user: dict) -> Optional[dict]:
        try:
            all_cans = self._can_collection().get()
            for can_doc in all_cans:
                caps = self._caps_collection(can_doc.id).get()
                for cap in caps:
                    if cap.id == cap_id:
                        ref = self._caps_collection(can_doc.id).document(cap.id)
                        now = datetime.now(timezone.utc)
                        update_data = {
                            "status": review["status"],
                            "reviewed_by": user.get("email", user["uid"]),
                            "reviewed_by_uid": user["uid"],
                            "reviewed_at": now,
                            "review_comments": review.get("comments"),
                            "updated_at": now,
                            # Buddha Air FORM SMSM 8.8.2 — review / sign-off block
                            "managerial_approval": review.get("managerial_approval"),
                            "caa_acceptance": review.get("caa_acceptance"),
                            "rca": review.get("rca"),
                            "residual_severity": review.get("residual_severity"),
                            "residual_probability": review.get("residual_probability"),
                            "residual_risk_index": review.get("residual_risk_index"),
                            "residual_risk_level": review.get("residual_risk_level"),
                            "residual_risk_outcome": review.get("residual_risk_outcome"),
                            "residual_sra": review.get("residual_sra"),
                            "root_causes": review.get("root_causes"),
                            "action_items": review.get("action_items"),
                            "ca_acceptance": review.get("ca_acceptance"),
                            "manager_approval": review.get("manager_approval"),
                            "manager_confirmation": review.get("manager_confirmation"),
                            "closing_remarks": review.get("closing_remarks"),
                            "sag_sign": review.get("sag_sign"),
                        }
                        # Server-side Residual SRA canonicalisation on review.
                        residual_sra = self._sra_block(
                            review.get("residual_severity"),
                            review.get("residual_probability"),
                            assessed_by=user.get("email", user["uid"]),
                            assessed_at=now,
                            provided=review.get("residual_sra"),
                        )
                        if residual_sra:
                            update_data["residual_sra"] = residual_sra
                            update_data["residual_severity"] = residual_sra["severity"]
                            update_data["residual_probability"] = residual_sra["probability"]
                            update_data["residual_risk_index"] = residual_sra["risk_index"]
                            update_data["residual_risk_level"] = residual_sra["risk_level"]
                            update_data["residual_risk_outcome"] = residual_sra["risk_outcome"]
                        elif review.get("residual_risk_index"):
                            thresholds = get_thresholds(self.tenant_id)
                            update_data["residual_risk_level"] = get_risk_level(
                                review["residual_risk_index"], thresholds
                            )
                            update_data["residual_risk_outcome"] = risk_outcome(
                                review.get("residual_severity") or 1,
                                review.get("residual_probability") or 1,
                                thresholds,
                            )
                        if review.get("sag_sign"):
                            update_data["sag_signed_by"] = review.get("sag_signed_by")
                            update_data["sag_signed_at"] = review.get("sag_signed_at") or now
                        if review.get("revision_deadline"):
                            update_data["revision_deadline"] = review["revision_deadline"]

                        if review["status"] == "Completed":
                            update_data["closed_by"] = review.get("closed_by") or user.get("email", user["uid"])
                            update_data["closed_at"] = review.get("closed_at") or now
                            update_data["closed_signature"] = review.get("closed_signature")

                        ref.update(update_data)

                        # Update CAN status and hazard if accepted
                        can_data = can_doc.to_dict()
                        if review["status"] == "Completed":
                            self._can_collection().document(can_doc.id).update({
                                "status": "Closed",
                                "updated_at": now,
                            })
                            hazard_id = can_data.get("hazard_id")
                            if hazard_id:
                                self._update_hazard_status(hazard_id, "Under Review")

                        updated = ref.get().to_dict()
                        updated["id"] = cap.id
                        self._serialize_timestamps(updated)
                        return updated
            return None
        except Exception as e:
            logger.error(f"Failed to review CAP {cap_id}: {e}")
            raise

    # ── Stats ──

    def get_can_stats(self, user: dict, department: Optional[str] = None) -> Dict[str, Any]:
        try:
            if user.get("role") in settings.CROSS_TENANT_ROLES:
                docs = get_cross_tenant_collection(CAN_COLLECTION).get()
            else:
                docs = self._can_collection().get()

            stats = {"Open": 0, "Under Review": 0, "Closed": 0}
            priority_counts = {"High": 0, "Medium": 0, "Low": 0}
            total = 0

            for doc in docs:
                data = doc.to_dict()
                if department and (data.get("department") or "") != department:
                    continue
                status = data.get("status", "Open")
                if status in stats:
                    stats[status] += 1
                pri = data.get("priority")
                if pri in priority_counts:
                    priority_counts[pri] += 1
                total += 1

            return {
                "by_status": stats,
                "by_priority": priority_counts,
                "total": total,
            }
        except Exception as e:
            logger.error(f"Failed to get CAN stats: {e}")
            raise

    def get_cap_stats(self, user: dict, department: Optional[str] = None) -> Dict[str, Any]:
        try:
            if user.get("role") in settings.CROSS_TENANT_ROLES:
                cans = get_cross_tenant_collection(CAN_COLLECTION).get()
            else:
                cans = self._can_collection().get()

            stats = {"In Progress": 0, "Under Review": 0, "Completed": 0, "Revision Required": 0, "Overdue": 0}
            total = 0

            for can_doc in cans:
                can_data = can_doc.to_dict()
                if department and (can_data.get("department") or "") != department:
                    continue
                caps = can_doc.reference.collection(CAP_SUBCOLLECTION).get()
                for cap in caps:
                    data = cap.to_dict()
                    status = data.get("status", "In Progress")
                    if status in stats:
                        stats[status] += 1
                    total += 1

            return {
                "by_status": stats,
                "total": total,
            }
        except Exception as e:
            logger.error(f"Failed to get CAP stats: {e}")
            raise

    # ── Hazard integration ──

    def _update_hazard_status(self, hazard_id: str, status: str):
        try:
            service = HazardService(self.tenant_id)
            user = {"uid": "system", "role": "AIRLINE_ADMIN", "tenant_id": self.tenant_id}
            service.update_status(hazard_id, status, user)
            logger.info(f"Hazard {hazard_id} status updated to {status} via CAN/CAP")
        except Exception as e:
            logger.warning(f"Failed to update hazard {hazard_id} status: {e}")

    # ── Helpers ──

    @staticmethod
    def _serialize_timestamps(data: dict) -> None:
        for key in ("created_at", "updated_at", "issued_at", "submitted_at", "reviewed_at",
                     "target_completion_date", "revision_deadline", "sag_signed_at", "closed_at"):
            if key in data and hasattr(data[key], "isoformat"):
                data[key] = data[key].isoformat()
