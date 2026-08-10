from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from collections import Counter, defaultdict
from loguru import logger

from app.core.config import settings
from app.firebase import get_tenant_collection, get_cross_tenant_collection


DIVERSION_COLLECTION = "flight_diversions"


class FlightDiversionService:
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    def _collection(self):
        return get_tenant_collection(self.tenant_id, DIVERSION_COLLECTION)

    def _get_next_sequence(self, year: int) -> int:
        try:
            docs = self._collection().get()
            max_seq = 0
            for doc in docs:
                data = doc.to_dict()
                did = data.get("diversion_id", "")
                if did.startswith(f"DIV-{year}-"):
                    try:
                        seq = int(did.split("-")[-1])
                        if seq > max_seq:
                            max_seq = seq
                    except (IndexError, ValueError):
                        pass
            return max_seq + 1
        except Exception as e:
            logger.error(f"Failed to get next diversion sequence: {e}")
            return 1

    def create_diversion(self, payload: dict, user: dict) -> dict:
        now = datetime.now(timezone.utc)
        year = now.year
        sequence = self._get_next_sequence(year)
        diversion_id = f"DIV-{year}-{sequence:03d}"

        doc_data = {
            "tenant_id": self.tenant_id,
            "diversion_id": diversion_id,
            "date": payload["date"],
            "flight_number": payload["flight_number"],
            "aircraft_registration": payload["aircraft_registration"],
            "sector_from": payload["sector_from"],
            "sector_to": payload["sector_to"],
            "diverted_to": payload["diverted_to"],
            "reason": payload["reason"],
            "reason_details": payload.get("reason_details"),
            "captain": payload.get("captain"),
            "first_officer": payload.get("first_officer"),
            "air_hostess": payload.get("air_hostess"),
            "description": payload["description"],
            "additional_fuel_cost": payload.get("additional_fuel_cost"),
            "passenger_impact": payload.get("passenger_impact"),
            "delay_minutes": payload.get("delay_minutes"),
            "remarks": payload.get("remarks"),
            "status": "Pending",
            "hazard_id": None,
            "hazard_link_url": None,
            "created_by": user.get("uid"),
            "updated_by": None,
            "created_at": now,
            "updated_at": now,
        }

        doc_data = {k: v for k, v in doc_data.items() if v is not None}

        try:
            ref = self._collection().add(doc_data)
            doc_id = ref[1].id
            doc_data["id"] = doc_id
            logger.info(f"Diversion {diversion_id} created for tenant {self.tenant_id}")
            return doc_data
        except Exception as e:
            logger.error(f"Failed to create diversion: {e}")
            raise

    def get_diversion(self, diversion_id: str, user: dict) -> Optional[dict]:
        try:
            if user.get("role") in settings.CROSS_TENANT_ROLES:
                docs = get_cross_tenant_collection(DIVERSION_COLLECTION).get()
            else:
                docs = self._collection().get()

            for doc in docs:
                data = doc.to_dict()
                if doc.id == diversion_id or data.get("diversion_id") == diversion_id:
                    data["id"] = doc.id
                    self._serialize_timestamps(data)
                    return data
            return None
        except Exception as e:
            logger.error(f"Failed to get diversion {diversion_id}: {e}")
            raise

    def list_diversions(self, user: dict, filters: dict = None) -> List[dict]:
        try:
            if user.get("role") in settings.CROSS_TENANT_ROLES:
                docs = get_cross_tenant_collection(DIVERSION_COLLECTION).get()
            else:
                docs = self._collection().get()

            results = []
            for doc in docs:
                data = doc.to_dict()
                data["id"] = doc.id
                self._serialize_timestamps(data)

                if filters:
                    if filters.get("status") and data.get("status") != filters["status"]:
                        continue
                    if filters.get("reason") and data.get("reason") != filters["reason"]:
                        continue
                    if filters.get("aircraft") and data.get("aircraft_registration") != filters["aircraft"]:
                        continue
                    if filters.get("search"):
                        s = filters["search"].lower()
                        did = (data.get("diversion_id") or "").lower()
                        fn = (data.get("flight_number") or "").lower()
                        if s not in did and s not in fn:
                            continue

                results.append(data)

            results.sort(key=lambda r: r.get("date", datetime.min), reverse=True)
            return results
        except Exception as e:
            logger.error(f"Failed to list diversions: {e}")
            raise

    def update_diversion(self, diversion_id: str, payload: dict, user: dict) -> Optional[dict]:
        try:
            docs = self._collection().get()
            target_id = None
            for doc in docs:
                data = doc.to_dict()
                if doc.id == diversion_id or data.get("diversion_id") == diversion_id:
                    target_id = doc.id
                    break

            if not target_id:
                return None

            ref = self._collection().document(target_id)
            payload["updated_at"] = datetime.now(timezone.utc)
            payload["updated_by"] = user.get("uid")
            ref.update(payload)

            updated = ref.get().to_dict()
            updated["id"] = target_id
            self._serialize_timestamps(updated)
            return updated
        except Exception as e:
            logger.error(f"Failed to update diversion {diversion_id}: {e}")
            raise

    def delete_diversion(self, diversion_id: str) -> bool:
        try:
            docs = self._collection().get()
            target_id = None
            for doc in docs:
                data = doc.to_dict()
                if doc.id == diversion_id or data.get("diversion_id") == diversion_id:
                    target_id = doc.id
                    break
            if not target_id:
                return False
            self._collection().document(target_id).delete()
            logger.info(f"Diversion {diversion_id} deleted")
            return True
        except Exception as e:
            logger.error(f"Failed to delete diversion {diversion_id}: {e}")
            raise

    def set_hazard_link(self, diversion_id: str, hazard_id: str, hazard_link_url: str, user: dict) -> Optional[dict]:
        try:
            docs = self._collection().get()
            target_id = None
            for doc in docs:
                data = doc.to_dict()
                if doc.id == diversion_id or data.get("diversion_id") == diversion_id:
                    target_id = doc.id
                    break
            if not target_id:
                return None

            ref = self._collection().document(target_id)
            now = datetime.now(timezone.utc)
            ref.update({
                "hazard_id": hazard_id,
                "hazard_link_url": hazard_link_url,
                "updated_at": now,
                "updated_by": user.get("uid"),
            })

            updated = ref.get().to_dict()
            updated["id"] = target_id
            self._serialize_timestamps(updated)
            return updated
        except Exception as e:
            logger.error(f"Failed to set hazard link for diversion {diversion_id}: {e}")
            raise

    def link_to_hazard(self, diversion_id: str, hazard_id: str, user: dict) -> Optional[dict]:
        try:
            docs = self._collection().get()
            target_id = None
            for doc in docs:
                data = doc.to_dict()
                if doc.id == diversion_id or data.get("diversion_id") == diversion_id:
                    target_id = doc.id
                    break
            if not target_id:
                return None

            ref = self._collection().document(target_id)
            now = datetime.now(timezone.utc)
            ref.update({
                "hazard_id": hazard_id,
                "status": "Linked to Hazard",
                "updated_at": now,
                "updated_by": user.get("uid"),
            })

            updated = ref.get().to_dict()
            updated["id"] = target_id
            self._serialize_timestamps(updated)
            return updated
        except Exception as e:
            logger.error(f"Failed to link diversion {diversion_id} to hazard {hazard_id}: {e}")
            raise

    def unlink_from_hazard(self, diversion_id: str, user: dict) -> Optional[dict]:
        try:
            docs = self._collection().get()
            target_id = None
            for doc in docs:
                data = doc.to_dict()
                if doc.id == diversion_id or data.get("diversion_id") == diversion_id:
                    target_id = doc.id
                    break
            if not target_id:
                return None

            ref = self._collection().document(target_id)
            now = datetime.now(timezone.utc)
            ref.update({
                "hazard_id": None,
                "hazard_link_url": None,
                "status": "Reviewed",
                "updated_at": now,
                "updated_by": user.get("uid"),
            })

            updated = ref.get().to_dict()
            updated["id"] = target_id
            self._serialize_timestamps(updated)
            return updated
        except Exception as e:
            logger.error(f"Failed to unlink diversion {diversion_id}: {e}")
            raise

    def get_stats(self, user: dict) -> Dict[str, Any]:
        try:
            if user.get("role") in settings.CROSS_TENANT_ROLES:
                docs = get_cross_tenant_collection(DIVERSION_COLLECTION).get()
            else:
                docs = self._collection().get()

            diversions = [doc.to_dict() for doc in docs]
            total = len(diversions)
            reason_counts = Counter()
            airport_counts = Counter()
            aircraft_counts = Counter()
            month_counts = defaultdict(int)
            delays = []
            fuel_costs = []
            passengers = []

            for d in diversions:
                reason_counts[d.get("reason", "Other")] += 1
                airport_counts[d.get("diverted_to", "Unknown")] += 1
                aircraft_counts[d.get("aircraft_registration", "Unknown")] += 1

                dt = d.get("date")
                if dt:
                    if hasattr(dt, "strftime"):
                        month_counts[dt.strftime("%Y-%m")] += 1
                    elif isinstance(dt, str):
                        month_counts[dt[:7]] += 1

                delay = d.get("delay_minutes")
                if delay:
                    delays.append(delay)
                fc = d.get("additional_fuel_cost")
                if fc:
                    fuel_costs.append(fc)
                pi = d.get("passenger_impact")
                if pi:
                    passengers.append(pi)

            weather_rate = round((reason_counts.get("Weather", 0) / total * 100) if total > 0 else 0, 1)
            tech_rate = round((reason_counts.get("Technical", 0) / total * 100) if total > 0 else 0, 1)
            avg_delay = round(sum(delays) / len(delays)) if delays else 0

            return {
                "total_diversions": total,
                "by_reason": dict(reason_counts),
                "by_airport": dict(airport_counts),
                "by_aircraft": dict(aircraft_counts),
                "by_month": [{"month": k, "count": v} for k, v in sorted(month_counts.items())],
                "weather_diversion_rate": weather_rate,
                "technical_diversion_rate": tech_rate,
                "avg_delay_minutes": avg_delay,
                "total_fuel_cost_impact": round(sum(fuel_costs), 2),
                "total_passenger_impact": sum(passengers),
            }
        except Exception as e:
            logger.error(f"Failed to get diversion stats: {e}")
            raise

    @staticmethod
    def _serialize_timestamps(data: dict) -> None:
        for key in ("created_at", "updated_at", "date"):
            if key in data and hasattr(data[key], "isoformat"):
                data[key] = data[key].isoformat()
