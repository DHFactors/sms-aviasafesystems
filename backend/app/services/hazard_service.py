import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from loguru import logger

from app.core.config import settings
from app.firebase import get_tenant_collection, get_cross_tenant_collection
from app.services.risk_matrix import (
    compute_risk_index,
    classify_risk,
    risk_outcome,
    get_thresholds,
    get_tolerability_tier,
    normalize_tolerability,
)
from app.services.users import get_user_department


def generate_hazard_id(tenant_id: str, taxonomy: str, year: int, sequence: int) -> str:
    tenant_code = tenant_id[:2].upper()
    taxonomy_code_map = {
        "Organizational-Facilities": "ORG",
        "Organizational-Documentation, Processes and Procedures": "DOC",
        "Technical": "TEC",
        "Wildlife": "WLD",
        "Human Factors": "HUM",
        "Environmental": "ENV",
        "Other": "OTH",
    }
    taxonomy_code = taxonomy_code_map.get(taxonomy, "GEN")[:3].upper()
    return f"{tenant_code}-HZ-{taxonomy_code}-{sequence:02d}-{str(year)[-2:]}"


class HazardService:
    COLLECTION = "hazards"

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    def _get_next_sequence(self, taxonomy: str, year: int) -> int:
        try:
            existing = get_tenant_collection(self.tenant_id, self.COLLECTION).get()
            max_seq = 0
            for doc in existing:
                data = doc.to_dict()
                hid = data.get("hazard_id", "")
                parts = hid.split("-")
                if len(parts) == 5 and parts[4] == str(year)[-2:]:
                    try:
                        seq = int(parts[3])
                        if seq > max_seq:
                            max_seq = seq
                    except ValueError:
                        pass
            return max_seq + 1
        except Exception as e:
            logger.error(f"Failed to get next sequence: {e}")
            return 1

    def create_hazard(self, payload: dict, user: dict) -> dict:
        now = datetime.now(timezone.utc)
        year = now.year

        severity = payload.get("severity")
        probability = payload.get("probability")
        risk_index = payload.get("risk_index")
        risk_level = payload.get("risk_level")
        risk_out = payload.get("risk_outcome")
        tolerability_tier = payload.get("tolerability_tier")

        if severity is not None and probability is not None:
            computed_risk_index = compute_risk_index(severity, probability)
            thresholds = get_thresholds(self.tenant_id)
            if risk_index is None:
                risk_index = computed_risk_index
            if risk_level is None:
                risk_level = classify_risk(computed_risk_index, thresholds)
            if risk_out is None:
                risk_out = risk_outcome(severity, probability, thresholds)
            if tolerability_tier is None:
                tolerability_tier = get_tolerability_tier(computed_risk_index, thresholds)
        elif risk_index is not None and risk_level is None:
            thresholds = get_thresholds(self.tenant_id)
            risk_level = classify_risk(risk_index, thresholds)
            tolerability_tier = get_tolerability_tier(risk_index, thresholds)

        if tolerability_tier is None and risk_level is not None:
            tolerability_tier = normalize_tolerability(risk_level)

        taxonomy = payload.get("taxonomy", "Other")
        sequence = self._get_next_sequence(taxonomy, year)
        hazard_id = generate_hazard_id(self.tenant_id, taxonomy, year, sequence)

        doc_data = {
            "hazard_id": hazard_id,
            "tenant_id": self.tenant_id,
            "title": payload["title"],
            "description": payload["description"],
            "source": payload["source"],
            "source_id": payload.get("source_id"),
            "source_url": payload.get("source_url"),
            "adrep_category": payload.get("adrep_category"),
            "occurrence_type": payload.get("occurrence_type"),
            "taxonomy": taxonomy,
            "taxonomy_specific": payload.get("taxonomy_specific"),
            "consequence": payload.get("consequence"),
            "severity": severity,
            "probability": probability,
            "risk_index": risk_index,
            "risk_level": risk_level,
            "risk_outcome": risk_out,
            "tolerability_tier": tolerability_tier,
            "priority": payload["priority"],
            "recommended_action": payload.get("recommended_action"),
            "corrective_action": payload.get("corrective_action"),
            "assigned_to": payload.get("assigned_to"),
            "assigned_to_uid": payload.get("assigned_to_uid"),
            "department": payload.get("department")
            or (
                get_user_department(
                    uid=payload.get("assigned_to_uid"), email=payload.get("assigned_to")
                )
                if payload.get("assigned_to_uid") or payload.get("assigned_to")
                else ""
            ),
            "srm_conducted": payload.get("srm_conducted", False),
            "srm_date": payload.get("srm_date"),
            "srm_status": payload.get("srm_status"),
            "analysis_mode": payload.get("analysis_mode", "FISHBONE_ONLY"),
            "sram_data": payload.get("sram_data"),
            "status": payload.get("status", "Open"),
            "follow_up_date": payload.get("follow_up_date"),
            "closed_at": payload.get("closed_at"),
            "closed_by": payload.get("closed_by"),
            "remarks": payload.get("remarks"),
            "created_by": user["uid"],
            "created_at": now,
            "updated_at": now,
        }

        doc_data = {k: v for k, v in doc_data.items() if v is not None}

        try:
            ref = get_tenant_collection(self.tenant_id, self.COLLECTION).add(doc_data)
            doc_id = ref[1].id
            doc_data["id"] = doc_id
            logger.info(f"Hazard {hazard_id} ({doc_id}) created for tenant {self.tenant_id}")
            return doc_data
        except Exception as e:
            logger.error(f"Failed to create hazard: {e}")
            raise

    def get_hazard_by_id(self, hazard_id_or_doc_id: str, user: dict) -> Optional[dict]:
        try:
            if user.get("role") in settings.CROSS_TENANT_ROLES:
                docs = get_cross_tenant_collection(self.COLLECTION).get()
                for doc in docs:
                    data = doc.to_dict()
                    if doc.id == hazard_id_or_doc_id or data.get("hazard_id") == hazard_id_or_doc_id:
                        data["id"] = doc.id
                        self._serialize_timestamps(data)
                        return data
                return None
            else:
                docs = get_tenant_collection(self.tenant_id, self.COLLECTION).get()
                for doc in docs:
                    data = doc.to_dict()
                    if doc.id == hazard_id_or_doc_id or data.get("hazard_id") == hazard_id_or_doc_id:
                        data["id"] = doc.id
                        self._serialize_timestamps(data)
                        return data
                return None
        except Exception as e:
            logger.error(f"Failed to get hazard {hazard_id_or_doc_id}: {e}")
            raise

    def list_hazards(self, user: dict, filters: dict = None) -> List[dict]:
        try:
            if user.get("role") in settings.CROSS_TENANT_ROLES:
                docs = get_cross_tenant_collection(self.COLLECTION).get()
            else:
                docs = get_tenant_collection(self.tenant_id, self.COLLECTION).get()

            results = []
            for doc in docs:
                data = doc.to_dict()
                data["id"] = doc.id
                self._serialize_timestamps(data)

                if filters:
                    if filters.get("status") and data.get("status") != filters["status"]:
                        continue
                    if filters.get("priority") and data.get("priority") != filters["priority"]:
                        continue
                    if filters.get("source") and data.get("source") != filters["source"]:
                        continue
                    if filters.get("taxonomy") and data.get("taxonomy") != filters["taxonomy"]:
                        continue
                    if filters.get("tenant_id") and data.get("tenant_id") != filters["tenant_id"]:
                        continue
                    if filters.get("department") and (data.get("department") or "") != filters["department"]:
                        continue
                    if filters.get("search"):
                        search = filters["search"].lower()
                        hid = (data.get("hazard_id") or "").lower()
                        title = (data.get("title") or "").lower()
                        desc = (data.get("description") or "").lower()
                        if search not in hid and search not in title and search not in desc:
                            continue

                results.append(data)

            results.sort(key=lambda r: r.get("created_at", datetime.min), reverse=True)
            return results
        except Exception as e:
            logger.error(f"Failed to list hazards: {e}")
            raise

    def update_hazard(self, hazard_id: str, payload: dict, user: dict) -> Optional[dict]:
        try:
            collection = get_tenant_collection(self.tenant_id, self.COLLECTION)
            docs = collection.get()
            target_doc = None
            target_id = None
            for doc in docs:
                data = doc.to_dict()
                if doc.id == hazard_id or data.get("hazard_id") == hazard_id:
                    target_doc = data
                    target_id = doc.id
                    break

            if not target_doc:
                return None

            ref = collection.document(target_id)

            if "severity" in payload or "probability" in payload:
                sev = payload.get("severity", target_doc.get("severity"))
                prob = payload.get("probability", target_doc.get("probability"))
                if sev is not None and prob is not None:
                    thresholds = get_thresholds(self.tenant_id)
                    computed = compute_risk_index(sev, prob)
                    payload["risk_index"] = computed
                    payload["risk_level"] = classify_risk(computed, thresholds)
                    payload["risk_outcome"] = risk_outcome(sev, prob, thresholds)
                    payload["tolerability_tier"] = get_tolerability_tier(computed, thresholds)
            elif "risk_level" in payload:
                payload["tolerability_tier"] = normalize_tolerability(payload.get("risk_level"))

            if "assigned_to" in payload or "assigned_to_uid" in payload:
                new_uid = payload.get("assigned_to_uid", target_doc.get("assigned_to_uid"))
                new_email = payload.get("assigned_to", target_doc.get("assigned_to"))
                payload["department"] = get_user_department(uid=new_uid, email=new_email)

            payload["updated_at"] = datetime.now(timezone.utc)
            ref.update(payload)

            updated = ref.get().to_dict()
            updated["id"] = target_id
            self._serialize_timestamps(updated)
            return updated
        except Exception as e:
            logger.error(f"Failed to update hazard {hazard_id}: {e}")
            raise

    def update_status(self, hazard_id: str, status: str, user: dict) -> Optional[dict]:
        try:
            collection = get_tenant_collection(self.tenant_id, self.COLLECTION)
            docs = collection.get()
            target_id = None
            for doc in docs:
                data = doc.to_dict()
                if doc.id == hazard_id or data.get("hazard_id") == hazard_id:
                    target_id = doc.id
                    break

            if not target_id:
                return None

            ref = collection.document(target_id)
            now = datetime.now(timezone.utc)
            update_data = {"status": status, "updated_at": now}

            if status == "Closed":
                update_data["closed_at"] = now
                update_data["closed_by"] = user["uid"]

            ref.update(update_data)

            updated = ref.get().to_dict()
            updated["id"] = target_id
            self._serialize_timestamps(updated)
            return updated
        except Exception as e:
            logger.error(f"Failed to update status for hazard {hazard_id}: {e}")
            raise

    def assign_hazard(self, hazard_id: str, assigned_to: str, assigned_to_uid: str, user: dict) -> Optional[dict]:
        try:
            collection = get_tenant_collection(self.tenant_id, self.COLLECTION)
            docs = collection.get()
            target_id = None
            for doc in docs:
                data = doc.to_dict()
                if doc.id == hazard_id or data.get("hazard_id") == hazard_id:
                    target_id = doc.id
                    break

            if not target_id:
                return None

            ref = collection.document(target_id)
            now = datetime.now(timezone.utc)
            ref.update({
                "assigned_to": assigned_to,
                "assigned_to_uid": assigned_to_uid,
                "department": get_user_department(uid=assigned_to_uid, email=assigned_to),
                "updated_at": now,
            })

            updated = ref.get().to_dict()
            updated["id"] = target_id
            self._serialize_timestamps(updated)
            return updated
        except Exception as e:
            logger.error(f"Failed to assign hazard {hazard_id}: {e}")
            raise

    def get_hazard_stats(self, user: dict) -> Dict[str, Any]:
        try:
            if user.get("role") in settings.CROSS_TENANT_ROLES:
                docs = get_cross_tenant_collection(self.COLLECTION).get()
            else:
                docs = get_tenant_collection(self.tenant_id, self.COLLECTION).get()

            stats = {"Open": 0, "Processing": 0, "Under Review": 0, "Closed": 0, "Reopened": 0}
            taxonomy_counts = {}
            priority_counts = {"H": 0, "M": 0, "L": 0}
            risk_level_counts = {}

            for doc in docs:
                data = doc.to_dict()
                status = data.get("status", "Open")
                if status in stats:
                    stats[status] += 1

                taxonomy = data.get("taxonomy", "Other")
                taxonomy_counts[taxonomy] = taxonomy_counts.get(taxonomy, 0) + 1

                priority = data.get("priority")
                if priority in priority_counts:
                    priority_counts[priority] += 1

                rl = data.get("risk_level")
                if rl:
                    risk_level_counts[rl] = risk_level_counts.get(rl, 0) + 1

            return {
                "by_status": stats,
                "by_taxonomy": taxonomy_counts,
                "by_priority": priority_counts,
                "by_risk_level": risk_level_counts,
                "total": sum(stats.values()),
            }
        except Exception as e:
            logger.error(f"Failed to get hazard stats: {e}")
            raise

    @staticmethod
    def _serialize_timestamps(data: dict) -> None:
        for key in ("created_at", "updated_at", "srm_date", "follow_up_date", "closed_at"):
            if key in data and hasattr(data[key], "isoformat"):
                data[key] = data[key].isoformat()
