# ============================================================================
# FILE: nhrc.py
# PATH: backend/app/models/nhrc.py
# PURPOSE: N-HRC (National High-Risk Category) data models aligned to Nepal's
#          NASP 2023-2025. Defines the 7 national high-risk categories, the
#          hazard-to-category mapping rules, and the per-category KPI schema
#          used for airline and State-level safety performance dashboards.
# ============================================================================

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime


class NHRCCategory(str, Enum):
    """Nepal's 7 National High-Risk Categories (NASP 2023-2025)"""

    CFIT = "CFIT"  # Controlled Flight Into Terrain
    LOCI = "LOC-I"  # Loss of Control - In Flight
    MAC = "MAC"  # Mid Air Collision
    RE = "RE"  # Runway Excursion
    RI = "RI"  # Runway Incursion
    ARC = "ARC"  # Abnormal Runway Contact
    WS = "WS"  # Wildlife Strike


class NHRCMappingRule(BaseModel):
    """Rule for mapping hazards to N-HRCs"""

    nhrc: NHRCCategory
    taxonomies: List[str]  # HUM, TEC, ENV, WLD, ORG
    keywords: List[str]  # e.g., ["terrain", "approach", "stall"]
    priority_levels: List[str]  # H, M, L
    description: str


class NHRCKPI(BaseModel):
    """N-HRC KPI for a tenant or State"""

    nhrc: NHRCCategory
    name: str
    active_hazards: int
    avg_risk_index: float
    max_risk_index: int
    trend: str  # "increasing", "decreasing", "stable"
    status: str  # "ok", "watch", "action"
    contributing_factors: List[str]
    seIs: List[str]  # Safety Enhancement Initiatives from NASP