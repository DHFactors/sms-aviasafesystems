from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from loguru import logger

from app.db.abstract_repository import AbstractRepository
from app.db.firestore_repository import FirestoreRepository


# ICAO Doc 9859 Survey Structure - 4 Components, ~23-28 questions
SURVEY_STRUCTURE = {
    "component_1": {
        "name": "Safety Policy (25%)",
        "weight": 0.25,
        "subcomponents": {
            "management_commitment": {
                "name": "Management commitment",
                "questions": [
                    {"id": "C1_Q1", "text": "Top management demonstrates visible commitment to safety"},
                    {"id": "C1_Q2", "text": "Safety policy is clearly documented and communicated"},
                    {"id": "C1_Q3", "text": "Safety objectives are defined and measurable"},
                ]
            },
            "safety_accountability": {
                "name": "Safety accountability",
                "questions": [
                    {"id": "C1_Q4", "text": "Safety accountabilities are clearly defined"},
                    {"id": "C1_Q5", "text": "Personnel understand their safety responsibilities"},
                ]
            },
            "key_personnel": {
                "name": "Appointment of key safety personnel",
                "questions": [
                    {"id": "C1_Q6", "text": "Key safety personnel are appointed with appropriate authority"},
                    {"id": "C1_Q7", "text": "Safety manager has direct access to accountable executive"},
                ]
            },
            "emergency_response": {
                "name": "Emergency response planning",
                "questions": [
                    {"id": "C1_Q8", "text": "Emergency response plan is documented and current"},
                    {"id": "C1_Q9", "text": "Emergency drills are conducted regularly"},
                ]
            },
        }
    },
    "component_2": {
        "name": "Safety Risk Management (35%)",
        "weight": 0.35,
        "subcomponents": {
            "hazard_identification": {
                "name": "Hazard identification",
                "questions": [
                    {"id": "C2_Q1", "text": "Hazard identification process is systematic"},
                    {"id": "C2_Q2", "text": "All operational areas are covered for hazards"},
                    {"id": "C2_Q3", "text": "Personnel are trained to report hazards"},
                ]
            },
            "risk_assessment": {
                "name": "Risk assessment",
                "questions": [
                    {"id": "C2_Q4", "text": "Risk assessment uses structured matrix"},
                    {"id": "C2_Q5", "text": "Severity and likelihood are consistently evaluated"},
                    {"id": "C2_Q6", "text": "Risk assessments are documented"},
                ]
            },
            "risk_mitigation": {
                "name": "Risk mitigation",
                "questions": [
                    {"id": "C2_Q7", "text": "Mitigations are implemented in timely manner"},
                    {"id": "C2_Q8", "text": "Residual risk is reassessed after controls"},
                ]
            },
        }
    },
    "component_3": {
        "name": "Safety Assurance (25%)",
        "weight": 0.25,
        "subcomponents": {
            "performance_monitoring": {
                "name": "Safety performance monitoring",
                "questions": [
                    {"id": "C3_Q1", "text": "Safety performance indicators are tracked"},
                    {"id": "C3_Q2", "text": "Trend analysis is performed regularly"},
                    {"id": "C3_Q3", "text": "Corrective actions are monitored to completion"},
                ]
            },
            "internal_investigation": {
                "name": "Internal safety investigation",
                "questions": [
                    {"id": "C3_Q4", "text": "Safety events are investigated systematically"},
                    {"id": "C3_Q5", "text": "Investigation findings feed back into risk management"},
                ]
            },
            "reporting_system": {
                "name": "Safety reporting system",
                "questions": [
                    {"id": "C3_Q6", "text": "Reporting system is confidential and non-punitive"},
                    {"id": "C3_Q7", "text": "Reports are acknowledged and feedback provided"},
                ]
            },
        }
    },
    "component_4": {
        "name": "Safety Promotion (15%)",
        "weight": 0.15,
        "subcomponents": {
            "training_education": {
                "name": "Training and education",
                "questions": [
                    {"id": "C4_Q1", "text": "Safety training is role-appropriate and recurrent"},
                    {"id": "C4_Q2", "text": "Competency is assessed after training"},
                ]
            },
            "safety_communication": {
                "name": "Safety communication",
                "questions": [
                    {"id": "C4_Q3", "text": "Safety information is disseminated effectively"},
                    {"id": "C4_Q4", "text": "Lessons learned are shared across organization"},
                ]
            },
        }
    },
}

# Flatten for easy lookup
ALL_QUESTIONS = []
QUESTION_TO_COMPONENT = {}
for comp_id, comp in SURVEY_STRUCTURE.items():
    for sub_id, sub in comp["subcomponents"].items():
        for q in sub["questions"]:
            ALL_QUESTIONS.append({**q, "component": comp_id, "subcomponent": sub_id})
            QUESTION_TO_COMPONENT[q["id"]] = comp_id

COMPONENT_WEIGHTS = {k: v["weight"] for k, v in SURVEY_STRUCTURE.items()}

MATURITY_LEVELS = [
    {"level": 1, "name": "Initial", "label": "Reactive", "range": (0, 39.99), "color": "#dc3545"},
    {"level": 2, "name": "Developing", "label": "Proactive", "range": (40, 59.99), "color": "#fd7e14"},
    {"level": 3, "name": "Implemented", "label": "Managed", "range": (60, 74.99), "color": "#ffc107"},
    {"level": 4, "name": "Advanced", "label": "Predictive", "range": (75, 89.99), "color": "#198754"},
    {"level": 5, "name": "Optimizing", "label": "Continuous Improvement", "range": (90, 100), "color": "#0d6efd"},
]


def _get_level(overall: float) -> Dict[str, Any]:
    for lvl in MATURITY_LEVELS:
        low, high = lvl["range"]
        if low <= overall <= high:
            return lvl
    return MATURITY_LEVELS[-1]


class MaturityScoringService:
    """ICAO-aligned maturity scoring. Uses AbstractRepository for storage in
    tenants/{tenantId}/maturity_assessments. Ensures tenant_id in all queries."""

    COLLECTION_TEMPLATE = "tenants/{tenant_id}/maturity_assessments"

    def __init__(self, repository: Optional[AbstractRepository] = None):
        self.repository: AbstractRepository = repository or FirestoreRepository()

    def _collection(self, tenant_id: str) -> str:
        return f"tenants/{tenant_id}/maturity_assessments"

    def get_survey_structure(self) -> Dict[str, Any]:
        return SURVEY_STRUCTURE

    def calculate_scores(self, answers: Dict[str, int]) -> Dict[str, Any]:
        """Calculate component and overall scores.

        answers: Dict[question_id, score 1-5]
        Returns: {component_scores, overall, level}
        """
        component_scores = {}
        for comp_id, comp in SURVEY_STRUCTURE.items():
            # Collect scores for this component
            comp_qids = [q["id"] for sub in comp["subcomponents"].values() for q in sub["questions"]]
            scores = [answers.get(qid, 0) for qid in comp_qids if qid in answers]
            if not scores:
                score_pct = 0
            else:
                # (sum / max_possible) *100 ; max per question =5
                score_pct = (sum(scores) / (len(comp_qids) * 5)) * 100
            component_scores[comp_id] = round(score_pct, 1)

        # Weighted overall
        overall = sum(component_scores[cid] * COMPONENT_WEIGHTS[cid] for cid in COMPONENT_WEIGHTS)
        overall = round(overall, 1)
        level = _get_level(overall)

        return {
            "component_scores": component_scores,
            "overall_maturity": overall,
            "level": level["level"],
            "level_name": level["name"],
            "level_label": level["label"],
        }

    def generate_gap_analysis(self, component_scores: Dict[str, float], target_level: int = 4) -> Dict[str, Any]:
        """Gap analysis against target level (default Advanced 75%)."""
        # Target threshold is low bound of target level
        target_pct = next((lvl["range"][0] for lvl in MATURITY_LEVELS if lvl["level"] == target_level), 75)
        gaps = {}
        for comp_id, score in component_scores.items():
            gap = round(target_pct - score, 1) if score < target_pct else 0
            gaps[comp_id] = gap
        return {"target_level": target_level, "target_pct": target_pct, "gaps": gaps}

    def generate_recommendations(self, component_scores: Dict[str, float]) -> List[str]:
        """Recommendations based on low-scoring areas (<60%)."""
        recs = []
        # Find lowest component
        sorted_comps = sorted(component_scores.items(), key=lambda x: x[1])
        for comp_id, score in sorted_comps:
            if score < 60:
                comp_name = SURVEY_STRUCTURE[comp_id]["name"]
                recs.append(f"Strengthen {comp_name} (current {score}%) — focus on lowest subcomponents")
        if not recs:
            recs.append("Maintain strengths; target next maturity level with continuous improvement in lowest component")
        return recs

    async def create_assessment(
        self, tenant_id: str, answers: Dict[str, int], assessor_id: str, target_level: int = 4
    ) -> Dict[str, Any]:
        if not tenant_id:
            raise ValueError("tenant_id required")
        # Validate answers 1-5
        for qid, score in answers.items():
            if qid not in QUESTION_TO_COMPONENT:
                raise ValueError(f"Unknown question {qid}")
            if not 1 <= int(score) <= 5:
                raise ValueError(f"Score for {qid} must be 1-5")

        calc = self.calculate_scores(answers)
        gaps = self.generate_gap_analysis(calc["component_scores"], target_level)
        recs = self.generate_recommendations(calc["component_scores"])

        # Historical trend: fetch previous assessments for this tenant
        history = await self.repository.query(
            self._collection(tenant_id),
            filters=[("tenant_id", "==", tenant_id)],
            order_by=[("created_at", "desc")],
            limit=5
        )
        # Build radar data
        radar = {
            "labels": [SURVEY_STRUCTURE[cid]["name"] for cid in SURVEY_STRUCTURE],
            "scores": [calc["component_scores"][cid] for cid in SURVEY_STRUCTURE],
        }

        doc = {
            "tenant_id": tenant_id,
            "assessor_id": assessor_id,
            "answers": answers,
            "component_scores": calc["component_scores"],
            "overall_maturity": calc["overall_maturity"],
            "level": calc["level"],
            "level_name": calc["level_name"],
            "level_label": calc["level_label"],
            "radar_chart_data": radar,
            "gap_analysis": gaps,
            "recommendations": recs,
            "history": [{"overall": h.get("overall_maturity"), "created_at": h.get("created_at")} for h in history],
            "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "updated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        }

        result = await self.repository.create(self._collection(tenant_id), doc)
        logger.info(f"Maturity assessment {result['id']} for tenant {tenant_id} overall={calc['overall_maturity']} level={calc['level']}")
        return result

    async def get_assessment(self, tenant_id: str, assessment_id: str) -> Optional[Dict[str, Any]]:
        if not tenant_id:
            raise ValueError("tenant_id required")
        return await self.repository.get(self._collection(tenant_id), assessment_id)

    async def list_assessments(self, tenant_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        if not tenant_id:
            raise ValueError("tenant_id required")
        return await self.repository.query(
            self._collection(tenant_id),
            filters=[("tenant_id", "==", tenant_id)],
            order_by=[("created_at", "desc")],
            limit=limit
        )
