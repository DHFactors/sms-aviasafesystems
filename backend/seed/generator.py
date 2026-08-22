import random
import hashlib
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

from app.services.risk_matrix import compute_risk_index, get_risk_level

GLOBAL_SEED = 42


class SeededRandom:
    def __init__(self, seed: int = GLOBAL_SEED):
        self._rng = random.Random(seed)

    def seed(self, value: int):
        self._rng = random.Random(value)

    def reset(self, seed: int = GLOBAL_SEED):
        self._rng = random.Random(seed)

    def uniform(self, a: float, b: float) -> float:
        return self._rng.uniform(a, b)

    def gauss(self, mu: float, sigma: float) -> float:
        return self._rng.gauss(mu, sigma)

    def choice(self, seq: List):
        return self._rng.choice(seq)

    def choices(self, seq: List, k: int = 1, weights: Optional[List[float]] = None):
        return self._rng.choices(seq, weights=weights, k=k)

    def randint(self, a: int, b: int) -> int:
        return self._rng.randint(a, b)

    def random(self) -> float:
        return self._rng.random()

    def shuffle(self, seq: List):
        self._rng.shuffle(seq)

    def sample(self, seq: List, k: int):
        return self._rng.sample(seq, k)

    def triangular(self, low: float, high: float, mode: Optional[float] = None) -> float:
        return self._rng.triangular(low, high, mode)


def _make_id(prefix: str, tenant_id: str, index: int) -> str:
    raw = f"{prefix}:{tenant_id}:{index}:{GLOBAL_SEED}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:20]
    return f"{prefix}_{tenant_id}_{h}"


def generate_narrative(
    rng: SeededRandom,
    templates: List[str],
    keywords: Dict[str, List[str]],
) -> str:
    template = rng.choice(templates)
    result = template
    for key, values in keywords.items():
        placeholder = "{" + key + "}"
        if placeholder in result:
            result = result.replace(placeholder, rng.choice(values), 1)
    for key, values in keywords.items():
        placeholder = "{" + key + "}"
        while placeholder in result:
            result = result.replace(placeholder, rng.choice(values), 1)
    return result


def generate_timestamp(
    rng: SeededRandom,
    days_back_min: int = 1,
    days_back_max: int = 365,
) -> datetime:
    # Respect the active seeding window (runner presets may shrink it to 90
    # days for the dev preset) so every generator stays inside the horizon.
    from seed import config as _cfg

    max_days = min(days_back_max, max(days_back_min, _cfg.SEED_WINDOW_DAYS))
    days = rng.randint(days_back_min, max_days)
    hours = rng.randint(0, 23)
    minutes = rng.randint(0, 59)
    now = datetime.now(timezone.utc)
    return now - timedelta(days=days, hours=hours, minutes=minutes)


def generate_risk_score(
    rng: SeededRandom,
    mean: float,
    std: float,
) -> float:
    score = rng.gauss(mean, std)
    return max(0.0, min(1.0, round(score, 2)))


def severity_from_risk(risk_score: float) -> str:
    if risk_score >= 0.75:
        return "Critical"
    elif risk_score >= 0.55:
        return "High"
    elif risk_score >= 0.30:
        return "Medium"
    else:
        return "Low"


def generate_survey_response(
    rng: SeededRandom,
    element_scores: Dict[str, float],
    variance: float,
) -> Dict[str, float]:
    result = {}
    for element, target_mean in element_scores.items():
        score = rng.gauss(target_mean, variance)
        score = max(1.0, min(5.0, round(score, 1)))
        result[element] = score
    return result


ICAO_SEVERITY_LEVELS = [1, 2, 3, 4, 5]
ICAO_PROBABILITY_LEVELS = [1, 2, 3, 4, 5]

SEVERITY_STR_TO_LEVEL = {"Low": 2, "Medium": 3, "High": 4, "Critical": 5}
LEVEL_TO_SEVERITY_STR = {1: "Negligible", 2: "Minor", 3: "Major", 4: "Hazardous", 5: "Catastrophic"}
LEVEL_TO_PROBABILITY_STR = {1: "Extremely Improbable", 2: "Improbable", 3: "Remote", 4: "Occasional", 5: "Frequent"}


def generate_icao_severity(rng: SeededRandom, risk_mean: float, risk_std: float) -> int:
    raw = rng.gauss(risk_mean * 5 + 1, risk_std * 5)
    return max(1, min(5, round(raw)))


def generate_icao_probability(rng: SeededRandom, risk_mean: float, risk_std: float) -> int:
    raw = rng.gauss(risk_mean * 4 + 1, risk_std * 3)
    return max(1, min(5, round(raw)))


def generate_ai_analysis(
    rng: SeededRandom,
    occurrence_type: str,
    narrative: str,
    is_mandatory: bool = False,
) -> Dict[str, Any]:
    n_human_factors = rng.randint(1, 3)
    human_factors = rng.sample(
        [
            "Decision Making Error", "Skill-Based Error", "Perceptual Error",
            "Fatigue", "Complacency", "Pressure", "Lack of Knowledge",
            "Communication Breakdown", "Situational Awareness (Loss of)",
            "Distraction", "Workload Management", "Procedural Non-Compliance",
        ],
        n_human_factors,
    )

    risk_mean = 0.6 if is_mandatory else 0.4
    ai_severity = generate_icao_severity(rng, risk_mean, 0.2)
    ai_probability = generate_icao_probability(rng, risk_mean, 0.2)
    ai_risk_index = compute_risk_index(ai_severity, ai_probability)
    ai_risk_level = get_risk_level(ai_risk_index)
    confidence = round(rng.uniform(0.75, 0.98), 2)

    risk_level_str = severity_from_risk(
        rng.uniform(0.3, 0.9) if is_mandatory else rng.uniform(0.1, 0.7)
    )

    phase_of_flight = rng.choice([
        "Standing", "Taxi", "Takeoff", "Initial Climb",
        "Climb", "Cruise", "Descent", "Approach", "Landing",
    ])

    summary = f"AI analysis identified occurrence type '{occurrence_type}' with {ai_risk_level.lower()} risk level (index {ai_risk_index}). {n_human_factors} human factor(s) identified: {', '.join(human_factors)}."

    n_recs = rng.randint(1, 3)
    recs = [
        rng.choice([
            "Conduct additional training on identified human factors",
            "Review and update relevant SOPs",
            "Issue safety bulletin to all operating crews",
            "Perform root cause analysis on contributing factors",
            "Enhance supervision during high-risk operations",
            "Implement fatigue management strategies",
            "Improve communication protocols between teams",
        ])
        for _ in range(n_recs)
    ]

    result = {
        "occurrence_type": occurrence_type,
        "human_factors": human_factors,
        "suggested_risk_level": risk_level_str,
        "phase_of_flight": phase_of_flight,
        "confidence": confidence,
        "summary": summary,
        "trend_indicators": recs,
    }

    result["ai_suggested_assessment"] = {
        "suggested_severity": ai_severity,
        "suggested_probability": ai_probability,
        "suggested_risk_index": ai_risk_index,
        "suggested_risk_level": ai_risk_level,
        "confidence": confidence,
    }

    if is_mandatory:
        result["mandatory_check"] = {
            "is_mandatory": True,
            "category": rng.choice(["A", "B"]),
            "reason": "Occurrence matches mandatory reporting criteria under CAR-19",
            "matched_criteria": [occurrence_type],
            "confidence": confidence,
        }

    return result



