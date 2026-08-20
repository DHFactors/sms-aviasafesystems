import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from loguru import logger

from app.core.config import settings
from app.core.metrics import record_ai_result
from app.firebase import get_tenant_collection, get_cross_tenant_collection, get_db
from app.services.gemini import analyze_report, classify_mandatory
from app.services.risk_matrix import compute_risk_index, get_risk_level, get_thresholds, get_tolerability_tier
from app.services.repository import ReportRepository


class ReportService:
    COLLECTION = settings.FIREBASE_COLLECTION_REPORTS

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    def create_report(self, payload: dict, user: dict) -> dict:
        now = datetime.now(timezone.utc)

        severity_level = payload.get("severity_level")
        probability_level = payload.get("probability_level")
        risk_index = None
        risk_level = None
        tolerability_tier = None
        if severity_level is not None and probability_level is not None:
            risk_index = compute_risk_index(severity_level, probability_level)
            thresholds = get_thresholds(self.tenant_id)
            risk_level = get_risk_level(risk_index, thresholds)
            tolerability_tier = get_tolerability_tier(risk_index, thresholds)

        doc_data = {
            "tenant_id": self.tenant_id,
            "report_type": payload["report_type"],
            "status": "NEW",
            "ai_status": "PENDING",
            "narrative": payload["narrative"],
            "location": payload["location"],
            "occurrence_date": payload["occurrence_date"],
            "is_anonymous": payload.get("is_anonymous", False),
            "flight_number": payload.get("flight_number"),
            "aircraft_registration": payload.get("aircraft_registration"),
            "occurrence_type": payload.get("occurrence_type"),
            "severity": payload.get("severity"),
            "investigation_status": payload.get("investigation_status"),
            "created_by": user["uid"],
            "created_at": now,
            "updated_at": now,
            "ai_analysis": None,
            "severity_level": severity_level,
            "probability_level": probability_level,
            "risk_index": risk_index,
            "risk_level": risk_level,
            "tolerability_tier": tolerability_tier,
            "risk_assessment": None,
            "ai_suggested_assessment": None,

            "occurrence_class": payload.get("occurrence_class"),
            "latitude": payload.get("latitude"),
            "longitude": payload.get("longitude"),
            "country": payload.get("country"),
            "aircraft_make": payload.get("aircraft_make"),
            "aircraft_model": payload.get("aircraft_model"),
            "aircraft_serial_number": payload.get("aircraft_serial_number"),
            "operator": payload.get("operator"),
            "operator_icao": payload.get("operator_icao"),
            "aircraft_category": payload.get("aircraft_category"),
            "engine_make": payload.get("engine_make"),
            "engine_model": payload.get("engine_model"),
            "engine_serial_number": payload.get("engine_serial_number"),
            "flight_phase": payload.get("flight_phase"),
            "flight_type": payload.get("flight_type"),
            "departure_airport": payload.get("departure_airport"),
            "destination_airport": payload.get("destination_airport"),
            "aircraft_utilisation_hours": payload.get("aircraft_utilisation_hours"),
            "aircraft_utilisation_cycles": payload.get("aircraft_utilisation_cycles"),
            "crew_count": payload.get("crew_count"),
            "passenger_count": payload.get("passenger_count"),
            "fatal_injuries": payload.get("fatal_injuries"),
            "serious_injuries": payload.get("serious_injuries"),
            "minor_injuries": payload.get("minor_injuries"),
            "occurrence_category": payload.get("occurrence_category"),
            "human_factors": payload.get("human_factors"),
            "contributing_factors": payload.get("contributing_factors"),
            "investigation_agency": payload.get("investigation_agency"),
            "reporter_name": payload.get("reporter_name"),
            "reporter_role": payload.get("reporter_role"),
            "reporter_email": payload.get("reporter_email"),
            "reporter_phone": payload.get("reporter_phone"),
            "reporter_organisation": payload.get("reporter_organisation"),
            "reporting_date": payload.get("reporting_date"),
            "etops": payload.get("etops", False),
            "propeller_make": payload.get("propeller_make"),
            "propeller_model": payload.get("propeller_model"),
            "call_sign": payload.get("call_sign"),
            "organisation_comments": payload.get("organisation_comments"),
            "manufacturer_advised": payload.get("manufacturer_advised", False),
            "fdr_data_retained": payload.get("fdr_data_retained", False),
        }

        doc_data = {k: v for k, v in doc_data.items() if v is not None}

        try:
            ref = get_tenant_collection(self.tenant_id, self.COLLECTION).add(doc_data)
            doc_id = ref[1].id
            doc_data["id"] = doc_id
            logger.info(f"Report {doc_id} created for tenant {self.tenant_id}")
            ReportRepository().invalidate_cache(prefix=f"{self.tenant_id}::")
            return doc_data
        except Exception as e:
            logger.error(f"Failed to create report: {e}")
            raise

    def get_reports(self, user: dict) -> List[dict]:
        try:
            if user.get("role") in settings.CROSS_TENANT_ROLES:
                docs = get_cross_tenant_collection(self.COLLECTION).limit(settings.REPO_QUERY_LIMIT).get()
            else:
                docs = get_tenant_collection(self.tenant_id, self.COLLECTION).get()

            results = []
            for doc in docs:
                data = doc.to_dict()
                data["id"] = doc.id
                self._serialize_timestamps(data)
                results.append(data)

            results.sort(key=lambda r: r.get("created_at", datetime.min), reverse=True)
            return results
        except Exception as e:
            logger.error(f"Failed to retrieve reports: {e}")
            raise

    def get_report_by_id(self, report_id: str, user: dict) -> Optional[dict]:
        try:
            if user.get("role") in settings.CROSS_TENANT_ROLES:
                docs = get_cross_tenant_collection(self.COLLECTION).where(
                    "__name__", "==", report_id
                ).get()
                if not docs:
                    return None
                data = docs[0].to_dict()
                data["id"] = docs[0].id
            else:
                doc = (
                    get_tenant_collection(self.tenant_id, self.COLLECTION)
                    .document(report_id)
                    .get()
                )
                if not doc.exists:
                    return None
                data = doc.to_dict()
                data["id"] = doc.id

            self._serialize_timestamps(data)
            return data
        except Exception as e:
            logger.error(f"Failed to retrieve report {report_id}: {e}")
            raise

    def run_ai_analysis(self, report_id: str, narrative: str) -> dict:
        start = time.monotonic()
        ref = get_tenant_collection(self.tenant_id, self.COLLECTION).document(report_id)

        try:
            ref.update({
                "ai_status": "PROCESSING",
                "updated_at": datetime.now(timezone.utc),
            })

            analysis = analyze_report(narrative)
            mandatory = classify_mandatory(narrative)
            elapsed_ms = round((time.monotonic() - start) * 1000, 1)

            ai_analysis = {
                "occurrence_type": analysis.get("occurrence_type"),
                "human_factors": analysis.get("human_factors", []),
                "risk_level": analysis.get("risk_level") or "High",
                "phase_of_flight": analysis.get("phase_of_flight"),
                "confidence": analysis.get("confidence", 0.0),
                "summary": analysis.get("summary"),
                "recommendations": analysis.get("recommendations", []),
                "mandatory_check": mandatory,
                "ai_model": settings.AI_MODEL,
                "prompt_version": settings.AI_PROMPT_VERSION,
                "processing_time_ms": elapsed_ms,
                "processed_at": datetime.now(timezone.utc),
            }

            suggested_severity = analysis.get("suggested_severity")
            suggested_probability = analysis.get("suggested_probability")
            ai_suggested_assessment = None
            if suggested_severity is not None and suggested_probability is not None:
                thresholds = get_thresholds(self.tenant_id)
                ai_risk_index = compute_risk_index(suggested_severity, suggested_probability)
                ai_risk_level = get_risk_level(ai_risk_index, thresholds)
                ai_suggested_assessment = {
                    "suggested_severity": suggested_severity,
                    "suggested_probability": suggested_probability,
                    "suggested_risk_index": ai_risk_index,
                    "suggested_risk_level": ai_risk_level,
                    "tolerability_tier": get_tolerability_tier(ai_risk_index, thresholds),
                    "confidence": analysis.get("confidence", 0.0),
                    "severity_explanation": analysis.get("severity_explanation"),
                    "probability_explanation": analysis.get("probability_explanation"),
                }

            now = datetime.now(timezone.utc)
            update_data = {
                "ai_analysis": ai_analysis,
                "ai_status": "COMPLETED",
                "status": "COMPLETED",
                "updated_at": now,
            }
            if ai_suggested_assessment:
                update_data["ai_suggested_assessment"] = ai_suggested_assessment
            ref.update(update_data)
            logger.info(
                f"AI analysis completed for report {report_id} "
                f"(model={settings.AI_MODEL}, {elapsed_ms}ms)"
            )
            record_ai_result(True)
            return ai_analysis

        except Exception as e:
            elapsed_ms = round((time.monotonic() - start) * 1000, 1)
            logger.error(
                f"AI analysis failed for report {report_id} after "
                f"{elapsed_ms}ms: {e}"
            )
            try:
                ref.update({
                    "ai_status": "FAILED",
                    "updated_at": datetime.now(timezone.utc),
                })
            except Exception as inner:
                logger.error(
                    f"Failed to update ai_status for report {report_id}: {inner}"
                )
            record_ai_result(False)
            return {}

    def confirm_risk_assessment(self, report_id: str, severity: int, probability: int, user: dict, notes: str = None) -> dict:
        try:
            if user.get("role") in settings.CROSS_TENANT_ROLES:
                docs = get_cross_tenant_collection(self.COLLECTION).where(
                    "__name__", "==", report_id
                ).get()
                if not docs:
                    raise ValueError("Report not found")
                ref = docs[0].reference
                report_tenant = (docs[0].to_dict() or {}).get("tenant_id") or self.tenant_id
            else:
                ref = get_tenant_collection(self.tenant_id, self.COLLECTION).document(report_id)
                report_tenant = self.tenant_id

            doc = ref.get()
            if not doc.exists:
                raise ValueError("Report not found")

            risk_index = compute_risk_index(severity, probability)
            thresholds = get_thresholds(report_tenant)
            risk_level = get_risk_level(risk_index, thresholds)
            tolerability_tier = get_tolerability_tier(risk_index, thresholds)
            now = datetime.now(timezone.utc)

            risk_assessment = {
                "severity": severity,
                "probability": probability,
                "risk_index": risk_index,
                "risk_level": risk_level,
                "tolerability_tier": tolerability_tier,
                "assessed_by": user["uid"],
                "assessed_at": now,
                "notes": notes,
            }

            ref.update({
                "severity_level": severity,
                "probability_level": probability,
                "risk_index": risk_index,
                "risk_level": risk_level,
                "tolerability_tier": tolerability_tier,
                "risk_assessment": risk_assessment,
                "reviewed_by": user["uid"],
                "reviewed_at": now,
                "updated_at": now,
            })

            data = doc.to_dict()
            data.update({
                "id": report_id,
                "severity_level": severity,
                "probability_level": probability,
                "risk_index": risk_index,
                "risk_level": risk_level,
                "tolerability_tier": tolerability_tier,
                "risk_assessment": risk_assessment,
                "reviewed_by": user["uid"],
                "reviewed_at": now,
            })
            self._serialize_timestamps(data)
            return data

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to confirm risk assessment for {report_id}: {e}")
            raise

    @staticmethod
    def _serialize_timestamps(data: dict) -> None:
        for key in ("created_at", "updated_at", "occurrence_date", "processed_at", "reviewed_at"):
            if key in data and hasattr(data[key], "isoformat"):
                data[key] = data[key].isoformat()
