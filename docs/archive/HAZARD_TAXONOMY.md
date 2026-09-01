# ICAO/ECCAIRS Hazard Taxonomy 

> **Risk levels (updated RC-2):** the canonical classification is **Low | Medium | High | Very High**,
> derived from the ICAO 5×5 matrix (`risk_index = severity × probability`). Default thresholds:
> `low_max=5`, `medium_max=9`, `high_max=15` (risk index ≤5 → Low; ≤9 → Medium; ≤15 → High; else →
> Very High). Thresholds are tenant-configurable; see
> [risk_matrix.py](../backend/app/services/risk_matrix.py) and [ADMIN_GUIDE.md](./ADMIN_GUIDE.md).

## Occurrence Types 
- Runway Excursion 
- Runway Incursion 
- Airborne Conflict 
- Abnormal Runway Contact 
- Ground Collision 
- System/Component Failure 
- Powerplant Failure 
- Weather Encounter 
- Bird Strike 
- Cabin Safety Event 
- Procedural Deviation 
- ATC Operational Incident 

## Human Factors 
- Situational Awareness (Loss of) 
- Decision Making Error 
- Skill-Based Error 
- Procedural Deviation 
- Communication Issue 
- CRM Breakdown 
- Fatigue 
- Pressure 
- Distraction 
- Workload Management 

## Risk Levels 
- Low 
- Medium 
- High 
- Very High
 
## Phases of Flight 
- Standing 
- Pushback 
- Taxi 
- Takeoff 
- Initial Climb 
- En-route 
- Holding 
- Approach 
- Landing 
- Go-Around 
