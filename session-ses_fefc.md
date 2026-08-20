# New session - 2026-08-17T15:03:25.259Z

**Session ID:** ses_fefc04cb5ffeYTL9qRxhPBdVP3
**Created:** 8/17/2026, 8:48:25 PM
**Updated:** 8/19/2026, 7:21:17 PM

---

## Assistant (Build · DeepSeek V4 Flash Free · 5.8s)

_Thinking:_

Now update hazard_service.py create_hazard to persist analysis_mode and sram_data, and the `_to_hazard_response` in routes/hazards.py to include them. Let me edit create_hazard doc_data.

Now persist the new fields in hazard_service.create_h

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\services\\hazard_service.py",
  "newString": "\"srm_conducted\": payload.get(\"srm_conducted\", False),\n            \"srm_date\": payload.get(\"srm_date\"),\n            \"srm_status\": payload.get(\"srm_status\"),\n            \"analysis_mode\": payload.get(\"analysis_mode\", \"FISHBONE_ONLY\"),\n            \"sram_data\": payload.get(\"sram_data\"),",
  "oldString": "\"srm_conducted\": payload.get(\"srm_conducted\", False),\n            \"srm_date\": payload.get(\"srm_date\"),\n            \"srm_status\": payload.get(\"srm_status\"),"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 18.1s)

_Thinking:_

Now update routes/hazards.py:
1. Import the new models + srm_engine + risk_matrix helpers.
2. Add the two endpoints: POST /{hazard_id}/sram/calculate, PUT /{hazard_id}/sram/save.
3. Update `_to_hazard_response` to include analysis_mode and sram_data.

For the save endpoint, I need a helper to persist. I'll use service.update_hazard with a payload including analysis_mode, sram_data, severity, probability, risk_index, risk_level, risk_outcome, srm_conducted, srm_status, srm_date. The update_hazard already recomputes risk_index/risk_level/risk_outcome when severity and probability present — good, since I'll pass severity and probability derived from the SRM resultant.

SEVERITY_LETTER_TO_NUMERIC mapping: A=5..E=1. severity numeric = SEVERITY_LETTER_TO_NUMERIC[letter]; probability = resultant probability_value; risk_index = sev_num * prob; risk_level/outcome computed by update_hazard.

Let me write the endpoints. For validation of sram_data on save:
- Extract severity dict from sram_data.severity; it should contain the 7 input keys. Recompute severity = calculate_severity(**inputs). Compare severity_letter with stored; if mismatch → 422.
- Normalize barriers via evaluate_barriers, recompute risk_profile via evaluate_risk_profile.
- If the provided sram_data.risk_profile disagrees with recomputed resultant index → 422? The spec says "Validates and persists full Bow-Tie / SRAM configuration". I'll recompute and use the authoritative recomputed values, but validate that the provided severity_letter and resultant index match (to catch tampering). Actually, to be lenient and not break legitimate frontend flows, I'll recompute authoritatively and overwrite risk_profile in the stored data, only 422 if severity letter mismatches. This keeps consistency. Let me also 422 if sram_data missing barriers dict.

Sign-offs: accept provided signoffs dict (name/role/date/signature). If absent, build default {authority, status: resultant tolerability}.

Also compute srm_date = now, srm_conducted = True, srm_status = "Conducted".

For the calculate endpoint:
- Compute severity from request.severity (model_dump).
- Compute barriers via evaluate_barriers from the request barrier lists (convert BarrierConfig → dict via model_dump).
- Compute risk_profile.
- Return {severity, barriers, risk_profile, bowtie: request.bowtie}.

Now, an important subtlety with route ordering: FastAPI matches in order of definition. `@router.get("/{hazard_id}")` is registered after `/stats`. My new POST `/sram/calculate` and PUT `/sram/save` — since there are already `PUT /{hazard_id}` (single segment) and the new ones are two segments after the id, no conflict.

But wait: there's a potential ordering issue with `GET /{hazard_id}` matching `GET /stats`? No — /stats is defined before /{hazard_id}, and the frontend calls /api/hazards/stats which works. Fine.

Let me now write the endpoint additions. I'll add them after the assign_hazard endpoint (before the helper functions).

For audit logging, I'll log SRAM_CALCULATED and SRAM_SAVED.

Let me write the edits.

Now add the SRAM endpoints to the hazards route



**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\routes\\hazards.py",
  "newString": "from fastapi import APIRouter, Depends, HTTPException, status, Query, Request\nfrom typing import Dict, Any, Optional, List\nfrom datetime import datetime, timezone\nfrom loguru import logger\n\nfrom app.models.hazard import (\n    HazardCreate,\n    HazardUpdate,\n    HazardResponse,\n    HazardListItem,\n    HazardStatus,\n    HazardSource,\n    HazardTaxonomy,\n    HAZARD_CREATION_SOURCES,\n    AnalysisMode,\n    SramCalculateRequest,\n    SramSaveRequest,\n)\nfrom app.middleware.auth import get_current_user, get_tenant_user, get_safety_manager\nfrom app.services.hazard_service import HazardService\nfrom app.services.audit_service import log_audit, request_context\nfrom app.services import srm_engine",
  "oldString": "from fastapi import APIRouter, Depends, HTTPException, status, Query, Request\nfrom typing import Dict, Any, Optional, List\nfrom loguru import logger\n\nfrom app.models.hazard import HazardCreate, HazardUpdate, HazardResponse, HazardListItem, HazardStatus, HazardSource, HazardTaxonomy, HAZARD_CREATION_SOURCES\nfrom app.middleware.auth import get_current_user, get_tenant_user, get_safety_manager\nfrom app.services.hazard_service import HazardService\nfrom app.services.audit_service import log_audit, request_context"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 33.0s)

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\routes\\hazards.py",
  "newString": "_VALID_SOURCES = {s.value for s in HazardSource}\n_VALID_TAXONOMIES = {t.value for t in HazardTaxonomy}\n_VALID_ANALYSIS_MODES = {m.value for m in AnalysisMode}\n\n\ndef _severity_inputs(data: dict) -> dict:\n    return {\n        \"pax\": int(data.get(\"pax\") or 0),\n        \"worker\": int(data.get(\"worker\") or 0),\n        \"quality\": int(data.get(\"quality\") or 0),\n        \"asset\": int(data.get(\"asset\") or 0),\n        \"rep\": int(data.get(\"rep\") or 0),\n        \"sec\": int(data.get(\"sec\") or 0),\n        \"env\": int(data.get(\"env\") or 0),\n    }\n\n\ndef _barrier_lists(barriers: Any) -> dict:\n    b = barriers or {}\n    if hasattr(b, \"model_dump\"):\n        b = b.model_dump()\n    return {\n        \"ecb\": b.get(\"ecb\") or [],\n        \"erb\": b.get(\"erb\") or [],\n        \"ncb\": b.get(\"ncb\") or [],\n        \"nrb\": b.get(\"nrb\") or [],\n    }\n\n\n@router.post(\"/{hazard_id}/sram/calculate\", response_model=dict)\nasync def calculate_sram(\n    hazard_id: str,\n    payload: SramCalculateRequest,\n    request: Request,\n    user: Dict[str, Any] = Depends(get_current_user),\n):\n    \"\"\"Real-time CAAN CAR-19 SRM calculation — validates the hazard exists but\n    does NOT persist anything (dynamic preview for the Bow-Tie workspace).\"\"\"\n    service = HazardService(user.get(\"tenant_id\", \"default\"))\n    doc = service.get_hazard_by_id(hazard_id, user)\n    if not doc:\n        raise HTTPException(status_code=404, detail=\"Hazard not found\")\n\n    result = srm_engine.analyse(\n        severity_inputs=payload.severity.model_dump(),\n        **_barrier_lists(payload.barriers),\n    )\n    result[\"bowtie\"] = payload.bowtie.model_dump() if payload.bowtie else None\n\n    ip, request_id = request_context(request)\n    log_audit(\n        action=\"SRAM_CALCULATED\",\n        user=user.get(\"email\"),\n        tenant_id=user.get(\"tenant_id\"),\n        target_type=\"hazard\",\n        target_id=hazard_id,\n        ip=ip,\n        request_id=request_id,\n        metadata={\"index\": result[\"risk_profile\"][\"resultant_risk\"][\"index\"]},\n    )\n    return result\n\n\n@router.put(\"/{hazard_id}/sram/save\", response_model=dict)\nasync def save_sram(\n    hazard_id: str,\n    payload: SramSaveRequest,\n    request: Request,\n    user: Dict[str, Any] = Depends(get_tenant_user),\n):\n    \"\"\"Validate and persist a full Bow-Tie / SRAM configuration.\n\n    Recomputes severity and barrier scoring authoritatively, updates the hazard's\n    Master Risk register (severity/probability/risk_index/risk_level/risk_outcome)\n    from the resultant risk, and stores the barrier register inside sram_data.\n    \"\"\"\n    tenant_id = user[\"tenant_id\"]\n    service = HazardService(tenant_id)\n    doc = service.get_hazard_by_id(hazard_id, user)\n    if not doc:\n        raise HTTPException(status_code=404, detail=\"Hazard not found\")\n\n    data = payload.sram_data.model_dump(exclude_none=False)\n    severity_block = data.get(\"severity\") or {}\n    barriers_block = data.get(\"barriers\") or {}\n\n    if not severity_block.get(\"severity_letter\"):\n        raise HTTPException(\n            status_code=422,\n            detail=\"sram_data.severity must contain a computed severity_letter.\",\n        )\n\n    # Authoritative recomputation.\n    inputs = _severity_inputs(severity_block)\n    severity = srm_engine.calculate_severity(**inputs)\n    if severity[\"severity_letter\"] != severity_block.get(\"severity_letter\"):\n        raise HTTPException(\n            status_code=422,\n            detail=(\n                f\"Severity inputs inconsistent: recomputed {severity['severity_letter']} \"\n                f\"({severity['total_score']}) does not match stored \"\n                f\"{severity_block.get('severity_letter')}.\"\n            ),\n        )\n    severity_block.update(severity)\n    severity_block.update(inputs)\n\n    barriers = srm_engine.evaluate_barriers(\n        barriers_block.get(\"ecb\") or [],\n        barriers_block.get(\"erb\") or [],\n        barriers_block.get(\"ncb\") or [],\n        barriers_block.get(\"nrb\") or [],\n    )\n    risk_profile = srm_engine.evaluate_risk_profile(\n        severity, barriers[\"ecb\"], barriers[\"erb\"], barriers[\"ncb\"], barriers[\"nrb\"]\n    )\n\n    # Digital sign-off defaults keyed to the required authority.\n    signoffs = data.get(\"signoffs\") or {}\n    if not signoffs.get(\"authority\"):\n        signoffs[\"authority\"] = risk_profile[\"signoff\"][\"authority\"]\n    if not signoffs.get(\"required_tolerability\"):\n        signoffs[\"required_tolerability\"] = risk_profile[\"resultant_risk\"][\"tolerability\"]\n\n    sram_data = {\n        \"severity\": severity_block,\n        \"barriers\": barriers,\n        \"risk_profile\": risk_profile,\n        \"bowtie\": (data.get(\"bowtie\") or {}),\n        \"fishbone\": data.get(\"fishbone\"),\n        \"signoffs\": signoffs,\n    }\n\n    sev_num = srm_engine.SEVERITY_LETTER_TO_NUMERIC[severity[\"severity_letter\"]]\n    prob = risk_profile[\"resultant_risk\"][\"probability_value\"]\n    now = datetime.now(timezone.utc)\n\n    update_payload = {\n        \"analysis_mode\": payload.analysis_mode.value,\n        \"sram_data\": sram_data,\n        \"severity\": sev_num,\n        \"probability\": prob,\n        \"risk_index\": sev_num * prob,\n        \"srm_conducted\": True,\n        \"srm_date\": now,\n        \"srm_status\": \"Conducted\",\n        \"updated_at\": now,\n    }\n    updated = service.update_hazard(hazard_id, update_payload, user)\n    if not updated:\n        raise HTTPException(status_code=404, detail=\"Hazard not found\")\n\n    ip, request_id = request_context(request)\n    log_audit(\n        action=\"SRAM_SAVED\",\n        user=user.get(\"email\"),\n        tenant_id=tenant_id,\n        target_type=\"hazard\",\n        target_id=hazard_id,\n        ip=ip,\n        request_id=request_id,\n        metadata={\n            \"analysis_mode\": payload.analysis_mode.value,\n            \"resultant_index\": risk_profile[\"resultant_risk\"][\"index\"],\n            \"authority\": signoffs[\"authority\"],\n        },\n    )\n    return {\n        \"id\": updated.get(\"id\"),\n        \"hazard_id\": updated.get(\"hazard_id\"),\n        \"analysis_mode\": updated.get(\"analysis_mode\"),\n        \"sram_data\": updated.get(\"sram_data\"),\n        \"severity\": updated.get(\"severity\"),\n        \"probability\": updated.get(\"probability\"),\n        \"risk_index\": updated.get(\"risk_index\"),\n        \"risk_level\": updated.get(\"risk_level\"),\n        \"risk_outcome\": updated.get(\"risk_outcome\"),\n    }",
  "oldString": "_VALID_SOURCES = {s.value for s in HazardSource}\n_VALID_TAXONOMIES = {t.value for t in HazardTaxonomy}"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 12.6s)

_Thinking:_

Wait — I inserted the endpoints in the middle, before the `_normalize_source` function. The routes were previously ordered: assign_hazard (line ~152), then _VALID_SOURCES. Now the endpoints are inserted right before _VALID_SOURCES which is before the helper functions. That's fine — but they reference helper functions `_severity_inputs`, `_barrier_lists` defined right above them, and `_to_hazard_response` defined later (not used by these endpoints). Good.

However, there's a route ordering concern: `POST /{hazard_id}/sram/calculate` and `PUT /{hazard_id}/sram/save` are now registered AFTER `PUT /{hazard_id}`. Since paths differ in segment count, no conflict. Good.

Now update `_to_hazard_response` to include analysis_mode and sram_data.

Now include the new fields in the hazard response serializer

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\routes\\hazards.py",
  "newString": "\"srm_conducted\": data.get(\"srm_conducted\", False),\n        \"srm_date\": data.get(\"srm_date\"),\n        \"srm_status\": data.get(\"srm_status\"),\n        \"analysis_mode\": data.get(\"analysis_mode\", \"FISHBONE_ONLY\"),\n        \"sram_data\": data.get(\"sram_data\"),",
  "oldString": "\"srm_conducted\": data.get(\"srm_conducted\", False),\n        \"srm_date\": data.get(\"srm_date\"),\n        \"srm_status\": data.get(\"srm_status\"),"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 5.2s)

Now add `sram_data` persistence to the CAP model and service for the Combined-mode promotion

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\models\\can_cap.py",
  "newString": "root_causes: Optional[list] = None\n    action_items: Optional[list] = None\n    # ── CAAN CAR-19 SRM (Bow-Tie) block persisted with the CAP submission ──\n    # sram_data: { analysis_mode, severity, barriers, risk_profile, bowtie, signoffs }\n    sram_data: Optional[dict] = None",
  "oldString": "root_causes: Optional[list] = None\n    action_items: Optional[list] = None"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 6.9s)

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\services\\can_cap_service.py",
  "newString": "# Structured RCA (Fishbone / Ishikawa 5M + Management)\n            \"root_causes\": payload.get(\"root_causes\") or None,\n            \"action_items\": payload.get(\"action_items\") or None,\n            \"process_owner\": payload.get(\"process_owner\"),\n            # CAAN CAR-19 SRM (Bow-Tie) block\n            \"sram_data\": payload.get(\"sram_data\") or None,",
  "oldString": "# Structured RCA (Fishbone / Ishikawa 5M + Management)\n            \"root_causes\": payload.get(\"root_causes\") or None,\n            \"action_items\": payload.get(\"action_items\") or None,\n            \"process_owner\": payload.get(\"process_owner\"),"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 133.1s)

_Thinking:_

Now write the test suite `backend/tests/test_srm_engine.py`. It will:
1. Test the pure engine functions with the official benchmark cases.
2. Test the API endpoints with the mock firebase pattern.

Let me write the tests now. I'll include the mock infrastructure (minimal version) reusing the pattern from test_risk_assessment_lifecycle.py.

Engine tests:
- test_severity_weighted_score_benchmark_wheel_jack: pax=0, worker=4, quality=3, asset=4, rep=1, sec=0, env=0 → score 23, D, Minor.
- test_severity_max_A: all 5 → 65 → A Catastrophic.
- test_severity_boundaries: 52→A, 51→B, 39→B, 38→C, 26→C, 25→D, 13→D, 12→E, 0→E.
- test_bqv_bands: 50→5 Excellent, 42→5, 41→4, 34→4, 33→3, 26→3, 25→2, 18→2, 17→1, 10→1, 9→0, 0→0.
- test_probability_bands per severity.
- test_probability_clamps_above_max → 1, below zero → 5.
- test_probability_invalid_severity_falls_back_E.
- test_evaluate_risk_profile_benchmark_4D_to_1D: existing 4 → 4D Tolerable; consolidated 14 → 1D Acceptable; signoff authority "Safety Manager / SAG Member".
- test_signoff_authorities: intolerable (5A) → Accountable Manager; tolerable (4D) → Risk Owner / Functional Chief.
- test_analyse_integration: full analyse call.

Endpoint tests:
- Mock firebase, create a hazard, then POST calculate and PUT save.
- calculate: 200, returns severity/barriers/risk_profile, and does NOT persist (hazard doc unchanged — check no sram_data on the stored doc).
- save: 200, persists analysis_mode + sram_data; hazard severity/probability/risk_index updated; validates mismatch → 422; 404 for missing hazard.

I need the mock infra for: get_db, get_tenant_collection, get_cross_tenant_collection, initialize_firebase, verify_firebase_token in app.firebase and app.middleware.auth.

For get_tenant_user dependency, it requires the token to have role + tenant_id. AIRLINE_ADMIN_TOKEN gives tenant test_airline. For the calculate endpoint I used get_current_user; for save, get_tenant_user (requires tenant_id). AIRLINE_ADMIN_TOKEN provides tenant_id test_airline.

Also get_user_department in hazard_service create — used when assigned_to present; fine without.

Note: the mock get_tenant_metadata is needed for risk_matrix.get_thresholds (used in create/update). I'll include the metadata mock like the lifecycle test.

Let me write the test file. I'll make it self-contained.

One concern: creating a hazard via API requires the source to be in HAZARD_CREATION_SOURCES. I'll use "Internal Audit".

Also note the save endpoint persists risk_index via update_hazard which recomputes risk_level/risk_outcome using get_thresholds (reads tenant metadata). My metadata mock returns thresholds. Good.

Let me write it.

Now the test suite



**Tool: write**

**Input:**
```json
{
  "content": "\"\"\"\nCAAN CAR-19 / SRM Mathematical Engine tests.\n\nUnit coverage for backend/app/services/srm_engine.py plus the\nPOST /{hazard_id}/sram/calculate and PUT /{hazard_id}/sram/save endpoints,\nbenchmarked against the official SRM Procedure Manual test case:\n\n  Wheel Jack Sunk Incident (Hazard 25-1296):\n    Worker=4, Quality=3, Asset=4, Rep=1 -> Weighted Score 23 -> Severity D\n    Initial probability 4 (Existing BSV ~4) -> Resultant probability 1\n    (Consolidated BSV ~14) -> \"4D\" -> \"1D\" Acceptable\n\"\"\"\n\nfrom datetime import datetime, timezone\nfrom typing import Any, Dict\nfrom unittest.mock import MagicMock\n\nimport pytest\nfrom fastapi.testclient import TestClient\n\nfrom app.main import app\nfrom app.core.config import settings\nfrom app.services import srm_engine\n\n\n# ============================================================================\n# Pure engine unit tests\n# ============================================================================\n\nclass TestSeverity:\n    def test_wheel_jack_benchmark(self):\n        result = srm_engine.calculate_severity(pax=0, worker=4, quality=3, asset=4, rep=1, sec=0, env=0)\n        assert result[\"total_score\"] == 23\n        assert result[\"severity_letter\"] == \"D\"\n        assert result[\"descriptor\"] == \"Minor\"\n\n    def test_max_score_is_catastrophic(self):\n        result = srm_engine.calculate_severity(pax=5, worker=5, quality=5, asset=5, rep=5, sec=5, env=5)\n        assert result[\"total_score\"] == 65\n        assert result[\"severity_letter\"] == \"A\"\n        assert result[\"descriptor\"] == \"Catastrophic\"\n\n    def test_zero_score_is_insignificant(self):\n        result = srm_engine.calculate_severity(0, 0, 0, 0, 0, 0, 0)\n        assert result[\"total_score\"] == 0\n        assert result[\"severity_letter\"] == \"E\"\n        assert result[\"descriptor\"] == \"Insignificant\"\n\n    def test_band_boundaries(self):\n        cases = [(52, \"A\"), (51, \"B\"), (39, \"B\"), (38, \"C\"), (26, \"C\"),\n                 (25, \"D\"), (13, \"D\"), (12, \"E\")]\n        for score, letter in cases:\n            # Find an input combo producing exactly this score.\n            pax = min(5, score // 4)\n            rem = score - pax * 4\n            worker = min(5, rem // 3)\n            rem -= worker * 3\n            quality = min(5, rem // 2)\n            rem -= quality * 2\n            asset = min(5, rem)\n            rem -= asset\n            result = srm_engine.calculate_severity(pax, worker, quality, asset, rem, 0, 0)\n            assert result[\"total_score\"] == score\n            assert result[\"severity_letter\"] == letter, (score, result)\n\n    def test_weighting_factors(self):\n        # One point of PAX (×4) outweighs one point of asset (×1).\n        high = srm_engine.calculate_severity(pax=1, worker=0, quality=0, asset=0, rep=0, sec=0, env=0)\n        low = srm_engine.calculate_severity(pax=0, worker=0, quality=0, asset=4, rep=0, sec=0, env=0)\n        assert high[\"total_score\"] == 4\n        assert low[\"total_score\"] == 4\n\n\nclass TestBqv:\n    def test_excellent_band(self):\n        result = srm_engine.calculate_bqv(5, 5, 5, 5, 5, 5, 5)\n        assert result[\"bqv\"] == 50\n        assert result[\"bsv\"] == 5\n        assert result[\"robustness\"] == \"Excellent\"\n\n    def test_poor_band(self):\n        result = srm_engine.calculate_bqv(1, 1, 1, 1, 1, 1, 1)\n        assert result[\"bqv\"] == 10\n        assert result[\"bsv\"] == 1\n        assert result[\"robustness\"] == \"Poor\"\n\n    def test_ineffective_band(self):\n        result = srm_engine.calculate_bqv(0, 0, 0, 0, 0, 0, 0)\n        assert result[\"bqv\"] == 0\n        assert result[\"bsv\"] == 0\n        assert result[\"robustness\"] == \"Ineffective\"\n\n    def test_bqv_band_boundaries(self):\n        cases = [(50, 5), (42, 5), (41, 4), (34, 4), (33, 3), (26, 3),\n                 (25, 2), (18, 2), (17, 1), (10, 1), (9, 0)]\n        for bqv, bsv in cases:\n            result = srm_engine.calculate_bqv(0, 0, 0, 0, 0, 0, 0)\n            result[\"bqv\"] = bqv\n            result[\"bsv\"], result[\"robustness\"] = (\n                bsv if bsv else 0, \"Excellent\" if bsv == 5 else \"Fair\"\n            )\n            # recompute through the real mapping path\n            eff, rem = divmod(bqv, 3)\n            dis = min(5, rem)\n            rem2 = rem - 2 * dis\n            cost = min(5, rem2)\n            res = srm_engine.calculate_bqv(eff, cost, 0, 0, 0, 0, dis)\n            assert res[\"bsv\"] == bsv, (bqv, res)\n\n\nclass TestProbability:\n    def test_severity_a_bands(self):\n        cfg = srm_engine.PROBABILITY_CONFIG[\"A\"]\n        bands = [(0, 5), (8, 4), (16, 3), (24, 2), (32, 1)]\n        for value, pv in bands:\n            result = srm_engine.calculate_probability(\"A\", value)\n            assert result[\"probability_value\"] == pv, (value, result)\n\n    def test_severity_d_bands(self):\n        bands = [(0, 5), (3, 4), (6, 3), (9, 2), (12, 1)]\n        for value, pv in bands:\n            result = srm_engine.calculate_probability(\"D\", value)\n            assert result[\"probability_value\"] == pv\n\n    def test_severity_e_bands(self):\n        bands = [(0, 5), (2, 4), (4, 3), (6, 2), (8, 1)]\n        for value, pv in bands:\n            result = srm_engine.calculate_probability(\"E\", value)\n            assert result[\"probability_value\"] == pv\n\n    def test_clamp_above_max_to_probability_1(self):\n        result = srm_engine.calculate_probability(\"D\", 999)\n        assert result[\"probability_value\"] == 1\n        assert result[\"descriptor\"] == \"Extremely Improbable\"\n\n    def test_clamp_below_zero_to_probability_5(self):\n        result = srm_engine.calculate_probability(\"D\", -5)\n        assert result[\"probability_value\"] == 5\n        assert result[\"descriptor\"] == \"Certain\"\n\n    def test_unknown_severity_falls_back_to_e(self):\n        result = srm_engine.calculate_probability(\"Z\", 0)\n        assert result[\"probability_value\"] == 5\n\n\nclass TestRiskProfile:\n    def test_wheel_jack_benchmark_4d_to_1d(self):\n        severity = srm_engine.calculate_severity(0, 4, 3, 4, 1, 0, 0)\n        ecb = [{\"bsv\": 2}, {\"bsv\": 2}]\n        erb = []\n        ncb = [{\"bsv\": 4}, {\"bsv\": 3}]\n        nrb = [{\"bsv\": 3}]\n\n        profile = srm_engine.evaluate_risk_profile(severity, ecb, erb, ncb, nrb)\n        assert profile[\"existing_bsv\"] == 4\n        assert profile[\"consolidated_bsv\"] == 14\n        assert profile[\"initial_risk\"][\"index\"] == \"4D\"\n        assert profile[\"initial_risk\"][\"tolerability\"] == \"Tolerable\"\n        assert profile[\"resultant_risk\"][\"index\"] == \"1D\"\n        assert profile[\"resultant_risk\"][\"tolerability\"] == \"Acceptable\"\n        assert profile[\"resultant_risk\"][\"descriptor\"] == \"Extremely Improbable\"\n        assert profile[\"signoff\"][\"authority\"] == \"Safety Manager / SAG Member\"\n\n    def test_signoff_intolerable_is_accountable_manager(self):\n        severity = {\"severity_letter\": \"A\"}\n        profile = srm_engine.evaluate_risk_profile(severity, [], [], [], [])\n        assert profile[\"initial_risk\"][\"index\"] == \"5A\"\n        assert profile[\"initial_risk\"][\"tolerability\"] == \"Intolerable\"\n        assert profile[\"signoff\"][\"authority\"] == \"Accountable Manager\"\n\n    def test_signoff_tolerable_is_risk_owner(self):\n        severity = {\"severity_letter\": \"D\"}\n        profile = srm_engine.evaluate_risk_profile(severity, [{\"bsv\": 4}], [], [], [])\n        assert profile[\"initial_risk\"][\"index\"] == \"4D\"\n        assert profile[\"signoff\"][\"authority\"] == \"Risk Owner / Functional Chief\"\n\n    def test_analyse_pipeline(self):\n        result = srm_engine.analyse(\n            severity_inputs={\"pax\": 0, \"worker\": 4, \"quality\": 3, \"asset\": 4, \"rep\": 1, \"sec\": 0, \"env\": 0},\n            ecb_barriers=[{\"quality\": {\"effectiveness\": 3, \"cost_benefit\": 3, \"practicality\": 3,\n                                       \"acceptability\": 3, \"enforceability\": 3, \"durability\": 3,\n                                       \"disinclination\": 3}, \"name\": \"Wheel Chocks\"}],\n        )\n        assert result[\"severity\"][\"severity_letter\"] == \"D\"\n        assert result[\"barriers\"][\"ecb\"][0][\"bsv\"] == 2  # bqv 24 -> Fair\n        assert result[\"risk_profile\"][\"initial_risk\"][\"index\"][1] == \"D\"\n\n\n# ============================================================================\n# API endpoint tests (in-memory Firestore mock)\n# ============================================================================\n\nclass MockDocumentSnapshot:\n    def __init__(self, data, doc_id=None, ref=None):\n        self._data = dict(data) if data else {}\n        self.id = doc_id or \"mock_id\"\n        self.reference = ref\n        self.exists = True\n\n    def to_dict(self):\n        return dict(self._data)\n\n\nclass MockDocumentReference:\n    def __init__(self, doc_id=None, parent_fs=None):\n        self._stored: Dict[str, Any] = {}\n        self.id = doc_id or \"mock_doc_id\"\n        self._parent_fs = parent_fs\n        self._subcollections: Dict[str, Any] = {}\n\n    def set(self, data):\n        self._stored.update(data)\n\n    def update(self, data):\n        self._stored.update(data)\n\n    def get(self):\n        return MockDocumentSnapshot(self._stored, self.id, ref=self)\n\n    def collection(self, subcollection):\n        if subcollection not in self._subcollections:\n            self._subcollections[subcollection] = MockCollectionReference()\n        return self._subcollections[subcollection]\n\n    def delete(self):\n        pass\n\n\nclass MockCollectionReference:\n    def __init__(self):\n        self._docs: Dict[str, MockDocumentReference] = {}\n        self._add_counter = 0\n\n    def document(self, doc_id=None):\n        if doc_id is None:\n            doc_id = f\"auto_{self._add_counter}\"\n            self._add_counter += 1\n        if doc_id not in self._docs:\n            self._docs[doc_id] = MockDocumentReference(doc_id)\n        return self._docs[doc_id]\n\n    def add(self, data):\n        doc = self.document()\n        doc.set(data)\n        return MagicMock(update_time=None), doc\n\n    def get(self):\n        return [doc.get() for doc in self._docs.values()]\n\n    def limit(self, n):\n        return self\n\n    def where(self, field, op, value):\n        return self\n\n    def order_by(self, field, **kwargs):\n        return self\n\n    def stream(self):\n        return [doc.get() for doc in self._docs.values()]\n\n\nclass MockFirestoreClient:\n    def __init__(self):\n        self._top: Dict[str, MockCollectionReference] = {}\n\n    def collection(self, path):\n        return self._top.setdefault(path, MockCollectionReference())\n\n    def collection_group(self, name):\n        return self.collection(name)\n\n\n@pytest.fixture(autouse=True)\ndef mock_firebase_and_auth(monkeypatch):\n    fs_client = MockFirestoreClient()\n    monkeypatch.setattr(\"app.firebase.get_db\", lambda: fs_client)\n    monkeypatch.setattr(\n        \"app.firebase.get_tenant_collection\",\n        lambda tid, coll: fs_client.collection(\"tenants\").document(tid).collection(coll),\n    )\n    monkeypatch.setattr(\n        \"app.firebase.get_cross_tenant_collection\",\n        lambda coll: fs_client.collection_group(coll),\n    )\n    monkeypatch.setattr(\"app.firebase.initialize_firebase\", lambda: None)\n    monkeypatch.setattr(\"app.firebase.is_firebase_ready\", lambda: True)\n    monkeypatch.setattr(\n        \"app.firebase.get_tenant_metadata\",\n        lambda tid: {\"risk_matrix\": {\"thresholds\": {\"low_max\": 5, \"medium_max\": 9, \"high_max\": 15}}},\n    )\n    monkeypatch.setattr(\"app.firebase._db\", fs_client)\n\n    import app.firebase as fb_mod\n    import app.middleware.auth as auth_mod\n\n    def fake_verify(token):\n        claims = {\"role\": \"USER\", \"tenant_id\": None}\n        if token == \"AIRLINE_ADMIN_TOKEN\":\n            claims = {\"role\": \"AIRLINE_ADMIN\", \"tenant_id\": \"test_airline\"}\n        elif token == \"SAFETY_MANAGER_TOKEN\":\n            claims = {\"role\": \"SAFETY_MANAGER\", \"tenant_id\": \"test_airline\"}\n        return {\"uid\": \"mock_user\", \"email\": \"test@aviasafe.com\", **claims}\n\n    monkeypatch.setattr(fb_mod, \"verify_firebase_token\", fake_verify)\n    monkeypatch.setattr(auth_mod, \"verify_firebase_token\", fake_verify)\n    yield fs_client\n\n\n@pytest.fixture\ndef client(mock_firebase_and_auth):\n    return TestClient(app)\n\n\ndef _auth_header(token=\"AIRLINE_ADMIN_TOKEN\"):\n    return {\"Authorization\": f\"Bearer {token}\"}\n\n\ndef _create_hazard(client, fs):\n    body = {\n        \"title\": \"Wheel Jack Sunk Incident\",\n        \"description\": \"Aircraft wheel jack sunk into apron surface during jacking operations.\",\n        \"source\": \"Internal Audit\",\n        \"source_id\": \"AUD-25-1296\",\n        \"taxonomy\": \"Organizational-Facilities\",\n        \"priority\": \"H\",\n        \"tenant_id\": \"test_airline\",\n    }\n    resp = client.post(\"/api/v1/hazards/\", json=body, headers=_auth_header())\n    assert resp.status_code == 201, resp.text\n    hazard = resp.json()\n    return hazard[\"id\"], hazard\n\n\n_WHEEL_JACK_BARRIERS = {\n    \"ecb\": [\n        {\"name\": \"Wheel Chock Placement Check\", \"bsv\": 2},\n        {\"name\": \"Jack Pad Inspection\", \"bsv\": 2},\n    ],\n    \"erb\": [],\n    \"ncb\": [\n        {\"name\": \"Load-Rated Jacking Plates\", \"bsv\": 4},\n        {\"name\": \"Hardstand Surface Audit\", \"bsv\": 3},\n    ],\n    \"nrb\": [{\"name\": \"Jacking Operations SOP\", \"bsv\": 3}],\n}\n\n\nclass TestSramCalculateEndpoint:\n    def test_calculate_returns_dynamic_metrics_without_persisting(self, client, mock_firebase_and_auth):\n        hazard_id, _ = _create_hazard(client, mock_firebase_and_auth)\n        payload = {\n            \"severity\": {\"pax\": 0, \"worker\": 4, \"quality\": 3, \"asset\": 4, \"rep\": 1, \"sec\": 0, \"env\": 0},\n            \"barriers\": _WHEEL_JACK_BARRIERS,\n        }\n        resp = client.post(\n            f\"/api/v1/hazards/{hazard_id}/sram/calculate\",\n            json=payload,\n            headers=_auth_header(),\n        )\n        assert resp.status_code == 200, resp.text\n        data = resp.json()\n        assert data[\"severity\"][\"total_score\"] == 23\n        assert data[\"severity\"][\"severity_letter\"] == \"D\"\n        assert data[\"risk_profile\"][\"initial_risk\"][\"index\"] == \"4D\"\n        assert data[\"risk_profile\"][\"resultant_risk\"][\"index\"] == \"1D\"\n        assert data[\"risk_profile\"][\"resultant_risk\"][\"tolerability\"] == \"Acceptable\"\n        # NOT persisted.\n        stored = mock_firebase_and_auth.collection(\"tenants\").document(\"test_airline\").collection(\"hazards\").get()\n        assert all(d.to_dict().get(\"sram_data\") is None for d in stored)\n\n    def test_calculate_404_for_missing_hazard(self, client):\n        payload = {\"severity\": {\"pax\": 0, \"worker\": 0, \"quality\": 0, \"asset\": 0, \"rep\": 0, \"sec\": 0, \"env\": 0}}\n        resp = client.post(\"/api/v1/hazards/nope/sram/calculate\", json=payload, headers=_auth_header())\n        assert resp.status_code == 404\n\n    def test_calculate_validates_input_ranges(self, client, mock_firebase_and_auth):\n        hazard_id, _ = _create_hazard(client, mock_firebase_and_auth)\n        payload = {\"severity\": {\"pax\": 9, \"worker\": 0, \"quality\": 0, \"asset\": 0, \"rep\": 0, \"sec\": 0, \"env\": 0}}\n        resp = client.post(\n            f\"/api/v1/hazards/{hazard_id}/sram/calculate\", json=payload, headers=_auth_header()\n        )\n        assert resp.status_code == 422\n\n\nclass TestSramSaveEndpoint:\n    def test_save_persists_full_configuration_and_updates_master_risk(self, client, mock_firebase_and_auth):\n        hazard_id, _ = _create_hazard(client, mock_firebase_and_auth)\n        payload = {\n            \"analysis_mode\": \"BOWTIE_SRAM\",\n            \"sram_data\": {\n                \"severity\": {\n                    \"pax\": 0, \"worker\": 4, \"quality\": 3, \"asset\": 4, \"rep\": 1, \"sec\": 0, \"env\": 0,\n                    \"severity_letter\": \"D\",\n                },\n                \"barriers\": _WHEEL_JACK_BARRIERS,\n                \"signoffs\": {\"name\": \"Capt. Test User\", \"role\": \"Safety Manager\"},\n            },\n        }\n        resp = client.put(\n            f\"/api/v1/hazards/{hazard_id}/sram/save\",\n            json=payload,\n            headers=_auth_header(),\n        )\n        assert resp.status_code == 200, resp.text\n        data = resp.json()\n        assert data[\"analysis_mode\"] == \"BOWTIE_SRAM\"\n        assert data[\"sram_data\"][\"risk_profile\"][\"resultant_risk\"][\"index\"] == \"1D\"\n        assert data[\"sram_data\"][\"signoffs\"][\"authority\"] == \"Safety Manager / SAG Member\"\n        # Master risk register updated (D->2, probability 1).\n        assert data[\"severity\"] == 2\n        assert data[\"probability\"] == 1\n        assert data[\"risk_index\"] == 2\n        assert data[\"risk_level\"] == \"Low\"\n        assert data[\"risk_outcome\"] == \"Acceptable\"\n\n        stored = mock_firebase_and_auth.collection(\"tenants\").document(\"test_airline\").collection(\"hazards\").get()\n        saved = next(d.to_dict() for d in stored if d.id == hazard_id)\n        assert saved[\"analysis_mode\"] == \"BOWTIE_SRAM\"\n        assert saved[\"sram_data\"][\"barriers\"][\"ncb\"][0][\"bsv\"] == 4\n        assert saved[\"srm_status\"] == \"Conducted\"\n\n    def test_save_rejects_inconsistent_severity(self, client, mock_firebase_and_auth):\n        hazard_id, _ = _create_hazard(client, mock_firebase_and_auth)\n        payload = {\n            \"analysis_mode\": \"BOWTIE_SRAM\",\n            \"sram_data\": {\n                \"severity\": {\n                    \"pax\": 0, \"worker\": 4, \"quality\": 3, \"asset\": 4, \"rep\": 1, \"sec\": 0, \"env\": 0,\n                    \"severity_letter\": \"A\",  # tampered: recomputes to D\n                },\n                \"barriers\": _WHEEL_JACK_BARRIERS,\n            },\n        }\n        resp = client.put(\n            f\"/api/v1/hazards/{hazard_id}/sram/save\", json=payload, headers=_auth_header()\n        )\n        assert resp.status_code == 422\n        assert \"inconsistent\" in resp.json()[\"detail\"].lower()\n\n    def test_save_rejects_invalid_analysis_mode(self, client, mock_firebase_and_auth):\n        hazard_id, _ = _create_hazard(client, mock_firebase_and_auth)\n        payload = {\n            \"analysis_mode\": \"TURBO_SRAM\",\n            \"sram_data\": {\n                \"severity\": {\"pax\": 0, \"worker\": 0, \"quality\": 0, \"asset\": 0, \"rep\": 0, \"sec\": 0, \"env\": 0,\n                             \"severity_letter\": \"E\"},\n                \"barriers\": {},\n            },\n        }\n        resp = client.put(\n            f\"/api/v1/hazards/{hazard_id}/sram/save\", json=payload, headers=_auth_header()\n        )\n        assert resp.status_code == 422\n\n    def test_save_404_for_missing_hazard(self, client):\n        payload = {\n            \"analysis_mode\": \"BOWTIE_SRAM\",\n            \"sram_data\": {\n                \"severity\": {\"pax\": 0, \"worker\": 0, \"quality\": 0, \"asset\": 0, \"rep\": 0, \"sec\": 0, \"env\": 0,\n                             \"severity_letter\": \"E\"},\n                \"barriers\": {},\n            },\n        }\n        resp = client.put(\"/api/v1/hazards/nope/sram/save\", json=payload, headers=_auth_header())\n        assert resp.status_code == 404",
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\tests\\test_srm_engine.py"
}
```

**Output:**
```
Wrote file successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 17.2s)

_Thinking:_

Wait, there's a subtle bug in my `test_bqv_band_boundaries` test — I wrote a weird recompute path that doesn't actually test the real mapping properly. Let me reconsider. The test constructs a fake result then recomputes through `calculate_bqv(eff, cost, 0, 0, 0, 0, dis)`. For bqv=42: eff=14, rem=0 → eff=14 > 5! That's invalid input (effectiveness > 5). This is a bad test. Let me rewrite it to directly test `_lookup_band` against BQV_BANDS instead — that's the actual mapping used.

Let me simplify: test that calculate_bqv with specific valid inputs lands in expected bands, or test `_lookup_band` directly.

The `test_bqv_band_boundaries` test is flawed. Let me rewrite it to test the real mapping

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\tests\\test_srm_engine.py",
  "newString": "def test_bqv_band_boundaries(self):\n        for bqv, bsv in [(50, 5), (42, 5), (41, 4), (34, 4), (33, 3), (26, 3),\n                         (25, 2), (18, 2), (17, 1), (10, 1), (9, 0)]:\n            bsv_out, robustness = srm_engine._lookup_band(bqv, srm_engine.BQV_BANDS)\n            assert bsv_out == bsv, (bqv, bsv_out)\n            assert isinstance(robustness, str) and robustness\n\n    def test_bqv_quality_inputs_map_to_bands(self):\n        # (effectiveness, cost, disinclination) weights: 3x + y + 2z.\n        result = srm_engine.calculate_bqv(5, 5, 5, 5, 5, 5, 5)   # 50\n        assert result[\"bsv\"] == 5\n        result = srm_engine.calculate_bqv(4, 4, 4, 4, 4, 4, 4)   # 36\n        assert result[\"bsv\"] == 4\n        result = srm_engine.calculate_bqv(3, 3, 3, 3, 3, 3, 3)   # 24\n        assert result[\"bsv\"] == 2\n        result = srm_engine.calculate_bqv(2, 2, 2, 2, 2, 2, 2)   # 16\n        assert result[\"bsv\"] == 1\n        result = srm_engine.calculate_bqv(1, 1, 1, 1, 1, 1, 1)   # 10\n        assert result[\"bsv\"] == 1",
  "oldString": "def test_bqv_band_boundaries(self):\n        cases = [(50, 5), (42, 5), (41, 4), (34, 4), (33, 3), (26, 3),\n                 (25, 2), (18, 2), (17, 1), (10, 1), (9, 0)]\n        for bqv, bsv in cases:\n            result = srm_engine.calculate_bqv(0, 0, 0, 0, 0, 0, 0)\n            result[\"bqv\"] = bqv\n            result[\"bsv\"], result[\"robustness\"] = (\n                bsv if bsv else 0, \"Excellent\" if bsv == 5 else \"Fair\"\n            )\n            # recompute through the real mapping path\n            eff, rem = divmod(bqv, 3)\n            dis = min(5, rem)\n            rem2 = rem - 2 * dis\n            cost = min(5, rem2)\n            res = srm_engine.calculate_bqv(eff, cost, 0, 0, 0, 0, dis)\n            assert res[\"bsv\"] == bsv, (bqv, res)"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 23.8s)

**Tool: bash**

**Input:**
```json
{
  "command": "python -m pytest tests/test_srm_engine.py -q 2>&1 | Select-Object -Last 20",
  "workdir": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend"
}
```

**Output:**
```
---------------------------- Captured stdout call -----------------------------
2026-08-19 18:36:53.811 | INFO    | -                                    | Normalized tenant_id for test@aviasafe.com: 'test_airline' -> 'test-airline'
2026-08-19 18:36:53.812 | INFO    | -                                    | Authenticated user test@aviasafe.com: role=AIRLINE_ADMIN, tenant_id=test-airline
2026-08-19 18:36:53.813 | INFO    | -                                    | Hazard TE-HZ-ORG-01-26 (auto_0) created for tenant test-airline
2026-08-19 18:36:53.814 | INFO    | b9972882-204a-4711-b8bf-3dd68e789743 | Request ok | {'method': 'POST', 'path': '/api/v1/hazards/', 'status': 201, 'duration_ms': 5.2}
2026-08-19 18:36:53.822 | INFO    | -                                    | Normalized tenant_id for test@aviasafe.com: 'test_airline' -> 'test-airline'
2026-08-19 18:36:53.822 | INFO    | -                                    | Authenticated user test@aviasafe.com: role=AIRLINE_ADMIN, tenant_id=test-airline
2026-08-19 18:36:53.826 | INFO    | ff3dd819-cb69-4f75-92cd-d5d9908c1daa | Request ok | {'method': 'PUT', 'path': '/api/v1/hazards/auto_0/sram/save', 'status': 200, 'duration_ms': 6.1}
============================== warnings summary ===============================
..\..\..\AppData\Local\Programs\Python\Python313\Lib\site-packages\reportlab\lib\rl_safe_eval.py:11
  C:\Users\CEO-LAPTOP\AppData\Local\Programs\Python\Python313\Lib\site-packages\reportlab\lib\rl_safe_eval.py:11: DeprecationWarning: ast.NameConstant is deprecated and will be removed in Python 3.14; use ast.Constant instead
    haveNameConstant = hasattr(ast,'NameConstant')

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ===========================
FAILED tests/test_srm_engine.py::TestBqv::test_bqv_quality_inputs_map_to_bands
FAILED tests/test_srm_engine.py::TestRiskProfile::test_analyse_pipeline - ass...
FAILED tests/test_srm_engine.py::TestSramCalculateEndpoint::test_calculate_returns_dynamic_metrics_without_persisting
FAILED tests/test_srm_engine.py::TestSramSaveEndpoint::test_save_persists_full_configuration_and_updates_master_risk
4 failed, 23 passed, 1 warning in 2.13s

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 37.3s)

**Tool: bash**

**Input:**
```json
{
  "command": "python -m pytest tests/test_srm_engine.py::TestBqv::test_bqv_quality_inputs_map_to_bands tests/test_srm_engine.py::TestRiskProfile::test_analyse_pipeline tests/test_srm_engine.py::TestSramCalculateEndpoint::test_calculate_returns_dynamic_metrics_without_persisting -q 2>&1 | Select-Object -Last 40",
  "workdir": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend"
}
```

**Output:**
```

    @router.post("/{hazard_id}/sram/calculate", response_model=dict)
    async def calculate_sram(
        hazard_id: str,
        payload: SramCalculateRequest,
        request: Request,
        user: Dict[str, Any] = Depends(get_current_user),
    ):
        """Real-time CAAN CAR-19 SRM calculation � validates the hazard exists but
        does NOT persist anything (dynamic preview for the Bow-Tie workspace)."""
        service = HazardService(user.get("tenant_id", "default"))
        doc = service.get_hazard_by_id(hazard_id, user)
        if not doc:
            raise HTTPException(status_code=404, detail="Hazard not found")
    
>       result = srm_engine.analyse(
            severity_inputs=payload.severity.model_dump(),
            **_barrier_lists(payload.barriers),
        )
E       TypeError: analyse() got an unexpected keyword argument 'ecb'

app\routes\hazards.py:212: TypeError
---------------------------- Captured stdout call -----------------------------
2026-08-19 18:37:31.136 | INFO    | -                                    | Normalized tenant_id for test@aviasafe.com: 'test_airline' -> 'test-airline'
2026-08-19 18:37:31.137 | INFO    | -                                    | Authenticated user test@aviasafe.com: role=AIRLINE_ADMIN, tenant_id=test-airline
2026-08-19 18:37:31.146 | INFO    | -                                    | Hazard TE-HZ-ORG-01-26 (auto_0) created for tenant test-airline
2026-08-19 18:37:31.148 | INFO    | e466155e-241e-4cf8-a6e2-86a8016a0cd4 | Request ok | {'method': 'POST', 'path': '/api/v1/hazards/', 'status': 201, 'duration_ms': 17.5}
2026-08-19 18:37:31.155 | INFO    | -                                    | Normalized tenant_id for test@aviasafe.com: 'test_airline' -> 'test-airline'
2026-08-19 18:37:31.155 | INFO    | -                                    | Authenticated user test@aviasafe.com: role=AIRLINE_ADMIN, tenant_id=test-airline
============================== warnings summary ===============================
..\..\..\AppData\Local\Programs\Python\Python313\Lib\site-packages\reportlab\lib\rl_safe_eval.py:11
  C:\Users\CEO-LAPTOP\AppData\Local\Programs\Python\Python313\Lib\site-packages\reportlab\lib\rl_safe_eval.py:11: DeprecationWarning: ast.NameConstant is deprecated and will be removed in Python 3.14; use ast.Constant instead
    haveNameConstant = hasattr(ast,'NameConstant')

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ===========================
FAILED tests/test_srm_engine.py::TestBqv::test_bqv_quality_inputs_map_to_bands
FAILED tests/test_srm_engine.py::TestRiskProfile::test_analyse_pipeline - ass...
FAILED tests/test_srm_engine.py::TestSramCalculateEndpoint::test_calculate_returns_dynamic_metrics_without_persisting
3 failed, 1 warning in 1.03s

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 15.4s)

_Thinking:_

Two bugs:

1. `analyse()` signature uses `ecb_barriers=` etc., but I passed `_barrier_lists(...)` which returns keys `ecb`, `erb`, etc. Fix: pass `**_barrier_lists` doesn't match. Let me make `_barrier_lists` return keys `ecb_barriers`, `erb_barriers`, `ncb_barriers`, `nrb_barriers`. Or change analyse to accept ecb/erb/ncb/nrb. Better: make `_barrier_lists` return the *_barriers keys to match analyse/evaluate_risk_profile signatures.

Actually `evaluate_risk_profile` also uses ecb_barriers etc. In save endpoint I call evaluate_barriers then evaluate_risk_profile with positional args, which is fine. Only the `analyse` call uses **barrier_lists. Let me change `_barrier_lists` to return `ecb_barriers`, etc.

2. test_bqv_quality_inputs_map_to_bands: calculate_bqv(4,4,4,4,4,4,4) = 3*4+4+4+4+4+4+2*4 = 12+4*5+8 = 12+20+8 = 40. I said 36 — wrong. Let me recompute: 3*4=12, five ×4 = 20, 2*4=8 → 40. Band 34-41 → 4. OK so (4,..) → 40 → bsv 4. And (3,..) = 9+15+6 = 30 → band 26-33 → 3, not 2! Let me recompute: 3*3=9, five×3=15, 2*3=6 → 30 → 26-33 → bsv 3 (Good). And (2,..)= 6+10+4=20 → 18-25 → 2 (Fair). (1,..)= 3+5+2=10 → 10-17 → 1. (5,..)=15+25+10=50 → 5.

So fix the test expectations: (4)→40→4, (3)→30→3, (2)→20→2, (1)→10→1. Good, this actually gives a nice sweep 5,4,3,2,1.

3. test_analyse_pipeline: `result["risk_profile"]["initial_risk"]["index"][1] == "D"` — the failure is "ass..." likely assertion error. initial index "4D"? With one ecb barrier bsv 2 → existing_bsv 2 → probability D: band 0-2 → 5 → "5D". So index is "5D", index[1] == "D". That should pass... unless the failure is different. Let me see the actual error. The truncated output shows `test_analyse_pipeline - ass...`. Let me check: with ecb barrier bqv: calculate_bqv(3,3,3,3,3,3,3) = 9+15+6 = 30 → bsv 3, not 2! I asserted bsv==2 ("bqv 24 -> Fair"). 3*3=9, plus 3*5=15, plus 2*3=6 → 30 → Good (3). So bsv is 3. And existing_bsv=3 → D band 3-5 → probability 4 → "4D". So index[1] == "D" passes but bsv==2 fails.

Let me fix: assert bsv == 3 (Good). Actually let me make it clearer: use all-3s → bqv 30 → bsv 3. Assert result["barriers"]["ecb"][0]["bsv"] == 3.

Let me apply the fixes.

Three small bugs to fix: `_barrier_lists` keys, and two test arithmetic errors

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\routes\\hazards.py",
  "newString": "def _barrier_lists(barriers: Any) -> dict:\n    b = barriers or {}\n    if hasattr(b, \"model_dump\"):\n        b = b.model_dump()\n    return {\n        \"ecb_barriers\": b.get(\"ecb\") or [],\n        \"erb_barriers\": b.get(\"erb\") or [],\n        \"ncb_barriers\": b.get(\"ncb\") or [],\n        \"nrb_barriers\": b.get(\"nrb\") or [],\n    }",
  "oldString": "def _barrier_lists(barriers: Any) -> dict:\n    b = barriers or {}\n    if hasattr(b, \"model_dump\"):\n        b = b.model_dump()\n    return {\n        \"ecb\": b.get(\"ecb\") or [],\n        \"erb\": b.get(\"erb\") or [],\n        \"ncb\": b.get(\"ncb\") or [],\n        \"nrb\": b.get(\"nrb\") or [],\n    }"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 7.9s)

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\tests\\test_srm_engine.py",
  "newString": "def test_bqv_quality_inputs_map_to_bands(self):\n        # (effectiveness, cost, disinclination) weights: 3x + 5y + 2z.\n        assert srm_engine.calculate_bqv(5, 5, 5, 5, 5, 5, 5)[\"bsv\"] == 5   # 50\n        assert srm_engine.calculate_bqv(4, 4, 4, 4, 4, 4, 4)[\"bsv\"] == 4   # 40\n        assert srm_engine.calculate_bqv(3, 3, 3, 3, 3, 3, 3)[\"bsv\"] == 3   # 30\n        assert srm_engine.calculate_bqv(2, 2, 2, 2, 2, 2, 2)[\"bsv\"] == 2   # 20\n        assert srm_engine.calculate_bqv(1, 1, 1, 1, 1, 1, 1)[\"bsv\"] == 1   # 10",
  "oldString": "def test_bqv_quality_inputs_map_to_bands(self):\n        # (effectiveness, cost, disinclination) weights: 3x + y + 2z.\n        result = srm_engine.calculate_bqv(5, 5, 5, 5, 5, 5, 5)   # 50\n        assert result[\"bsv\"] == 5\n        result = srm_engine.calculate_bqv(4, 4, 4, 4, 4, 4, 4)   # 36\n        assert result[\"bsv\"] == 4\n        result = srm_engine.calculate_bqv(3, 3, 3, 3, 3, 3, 3)   # 24\n        assert result[\"bsv\"] == 2\n        result = srm_engine.calculate_bqv(2, 2, 2, 2, 2, 2, 2)   # 16\n        assert result[\"bsv\"] == 1\n        result = srm_engine.calculate_bqv(1, 1, 1, 1, 1, 1, 1)   # 10\n        assert result[\"bsv\"] == 1"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 14.3s)

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\tests\\test_srm_engine.py",
  "newString": "assert result[\"severity\"][\"severity_letter\"] == \"D\"\n        assert result[\"barriers\"][\"ecb\"][0][\"bsv\"] == 3  # all-3 quality -> bqv 30 -> Good\n        assert result[\"risk_profile\"][\"initial_risk\"][\"index\"][1] == \"D\"",
  "oldString": "assert result[\"severity\"][\"severity_letter\"] == \"D\"\n        assert result[\"barriers\"][\"ecb\"][0][\"bsv\"] == 2  # bqv 24 -> Fair\n        assert result[\"risk_profile\"][\"initial_risk\"][\"index\"][1] == \"D\""
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 10.1s)

**Tool: bash**

**Input:**
```json
{
  "command": "python -m pytest tests/test_srm_engine.py -q 2>&1 | Select-Object -Last 8",
  "workdir": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend"
}
```

**Output:**
```
..\..\..\AppData\Local\Programs\Python\Python313\Lib\site-packages\reportlab\lib\rl_safe_eval.py:11
  C:\Users\CEO-LAPTOP\AppData\Local\Programs\Python\Python313\Lib\site-packages\reportlab\lib\rl_safe_eval.py:11: DeprecationWarning: ast.NameConstant is deprecated and will be removed in Python 3.14; use ast.Constant instead
    haveNameConstant = hasattr(ast,'NameConstant')

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ===========================
FAILED tests/test_srm_engine.py::TestSramSaveEndpoint::test_save_persists_full_configuration_and_updates_master_risk
1 failed, 26 passed, 1 warning in 0.81s

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 10.0s)

**Tool: bash**

**Input:**
```json
{
  "command": "python -m pytest tests/test_srm_engine.py::TestSramSaveEndpoint::test_save_persists_full_configuration_and_updates_master_risk -q 2>&1 | Select-Object -Last 30",
  "workdir": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend"
}
```

**Output:**
```
        # Master risk register updated (D->2, probability 1).
        assert data["severity"] == 2
        assert data["probability"] == 1
        assert data["risk_index"] == 2
        assert data["risk_level"] == "Low"
        assert data["risk_outcome"] == "Acceptable"
    
        stored = mock_firebase_and_auth.collection("tenants").document("test_airline").collection("hazards").get()
>       saved = next(d.to_dict() for d in stored if d.id == hazard_id)
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       StopIteration

tests\test_srm_engine.py:416: StopIteration
---------------------------- Captured stdout call -----------------------------
2026-08-19 18:38:31.253 | INFO    | -                                    | Normalized tenant_id for test@aviasafe.com: 'test_airline' -> 'test-airline'
2026-08-19 18:38:31.254 | INFO    | -                                    | Authenticated user test@aviasafe.com: role=AIRLINE_ADMIN, tenant_id=test-airline
2026-08-19 18:38:31.261 | INFO    | -                                    | Hazard TE-HZ-ORG-01-26 (auto_0) created for tenant test-airline
2026-08-19 18:38:31.262 | INFO    | 0097939a-a53e-45fd-9946-5dd06cbbf6d9 | Request ok | {'method': 'POST', 'path': '/api/v1/hazards/', 'status': 201, 'duration_ms': 10.8}
2026-08-19 18:38:31.271 | INFO    | -                                    | Normalized tenant_id for test@aviasafe.com: 'test_airline' -> 'test-airline'
2026-08-19 18:38:31.272 | INFO    | -                                    | Authenticated user test@aviasafe.com: role=AIRLINE_ADMIN, tenant_id=test-airline
2026-08-19 18:38:31.274 | INFO    | 97e08d3e-9af0-4837-997e-0b3be4d4082a | Request ok | {'method': 'PUT', 'path': '/api/v1/hazards/auto_0/sram/save', 'status': 200, 'duration_ms': 4.4}
============================== warnings summary ===============================
..\..\..\AppData\Local\Programs\Python\Python313\Lib\site-packages\reportlab\lib\rl_safe_eval.py:11
  C:\Users\CEO-LAPTOP\AppData\Local\Programs\Python\Python313\Lib\site-packages\reportlab\lib\rl_safe_eval.py:11: DeprecationWarning: ast.NameConstant is deprecated and will be removed in Python 3.14; use ast.Constant instead
    haveNameConstant = hasattr(ast,'NameConstant')

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ===========================
FAILED tests/test_srm_engine.py::TestSramSaveEndpoint::test_save_persists_full_configuration_and_updates_master_risk
1 failed, 1 warning in 0.59s

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 12.7s)

_Thinking:_

The issue: the mock `get_tenant_collection` returns a NEW collection each call: `fs_client.collection("tenants").document(tid).collection(coll)`. Wait — `fs_client.collection("tenants")` returns `fs_client._top.setdefault("tenants", ...)`, then `.document(tid)` — but MockCollectionReference.document returns `self._docs[doc_id]` — but each call to `.collection("tenants")` returns the same top collection, and `.document("test_airline")` returns the same MockDocumentReference, and `.collection("hazards")` returns its subcollection. That should be consistent.

But the tenant normalization! The logs show "Normalized tenant_id for test@aviasafe.com: 'test_airline' -> 'test-airline'". So the actual tenant_id used is `test-airline` (hyphenated), not `test_airline`! The create_hazard stored in tenant `test-airline`. So when I query `mock_firebase_and_auth.collection("tenants").document("test_airline")`, that's a different document than `test-airline`.

In test_calculate_returns_dynamic_metrics_without_persisting I also used `.document("test_airline")` and it passed the "NOT persisted" assertion (all sram_data None) because there were zero docs found — vacuously true. That's why it passed. So the real tenant is `test-airline`.

Let me fix both tests to use "test-airline". Actually the hazards are stored under tenant "test-airline" because get_current_user/get_tenant_user normalizes tenant_id. Let me check the normalization. The fake_verify returns tenant_id "test_airline" but the auth middleware normalizes it to "test-airline". So the HazardService tenant is "test-airline".

Fix: in both tests, use `.document("test-airline")`. Let me update.

Tenant ID gets normalized to `test-airline` by auth middleware. Fixing the test look

**Tool: bash**

**Input:**
```json
{
  "command": "Select-String -Path backend\\tests\\test_srm_engine.py -Pattern 'document\\(\"test_airline\"\\)' | ForEach-Object { $_.LineNumber }",
  "workdir": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe"
}
```

**Output:**
```
367
415

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 7.3s)

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\tests\\test_srm_engine.py",
  "newString": "# NOT persisted.\n        stored = mock_firebase_and_auth.collection(\"tenants\").document(\"test-airline\").collection(\"hazards\").get()",
  "oldString": "# NOT persisted.\n        stored = mock_firebase_and_auth.collection(\"tenants\").document(\"test_airline\").collection(\"hazards\").get()"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 4.2s)

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\tests\\test_srm_engine.py",
  "newString": "stored = mock_firebase_and_auth.collection(\"tenants\").document(\"test-airline\").collection(\"hazards\").get()",
  "oldString": "stored = mock_firebase_and_auth.collection(\"tenants\").document(\"test_airline\").collection(\"hazards\").get()"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 13.2s)

**Tool: bash**

**Input:**
```json
{
  "command": "python -m pytest tests/test_srm_engine.py -q 2>&1 | Select-Object -Last 4",
  "workdir": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend"
}
```

**Output:**
```
    haveNameConstant = hasattr(ast,'NameConstant')

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
27 passed, 1 warning in 0.22s

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 43.1s)

_Thinking:_

All 27 SRM tests pass. Now let me run the full backend suite to make sure nothing else broke (e.g., the model changes affecting create/update hazard tests).

27 passed. Full backend suite to catch regressions



**Tool: bash**

**Input:**
```json
{
  "command": "python -m pytest -q 2>&1 | Select-Object -Last 5",
  "timeout": 600000,
  "workdir": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend"
}
```

**Output:**
```
  C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\copilot.py:59: PydanticDeprecatedSince20: The `dict` method is deprecated; use `model_dump` instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.11/migration/
    history = [item.dict() for item in (payload.history or [])]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
447 passed, 4 warnings in 28.95s

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 66.1s)

_Thinking:_

447 passed (420 + 27 new). Backend done. Now update todos and move to frontend.

Let me mark backend todos complete and start the frontend work. The frontend is the biggest part. I'll create `public/js/srm.js` — a self-contained SRM workspace controller, and wire it into `public/hazards/detail.html` and `public/can_cap/cap_submit.html`.

Let me design `srm.js` carefully:

```js
const SRM = {
  // constants
  SEVERITY_KEYS: [
    {key:'pax', label:'Passenger (PAX) Safety', icon:'fa-users'},
    {key:'worker', label:'Worker / Staff Safety', icon:'fa-hard-hat'},
    {key:'quality', label:'Quality / Service', icon:'fa-medal'},
    {key:'asset', label:'Asset / Equipment', icon:'fa-gears'},
    {key:'rep', label:'Reputation', icon:'fa-bullhorn'},
    {key:'sec', label:'Security', icon:'fa-shield-halved'},
    {key:'env', label:'Environment', icon:'fa-leaf'},
  ],
  BQV_KEYS: [
    {key:'effectiveness', label:'Effectiveness', weight:3},
    {key:'cost_benefit', label:'Cost-Benefit', weight:1},
    {key:'practicality', label:'Practicality', weight:1},
    {key:'acceptability', label:'Acceptability', weight:1},
    {key:'enforceability', label:'Enforceability', weight:1},
    {key:'durability', label:'Durability', weight:1},
    {key:'disinclination', label:'Disinclination to Override', weight:2},
  ],
  ...
};
```

The workspace class:

```js
class SrmWorkspace {
  constructor(rootEl, options) {
    // options: { hazardId, mode, savedData, api (HazardsAPI), onSave }
  }
  render() { ... }
  // mode selector
  // fishbone section (via Fishbone.renderEditor if available)
  // bowtie section: sliders, visualizer, bqv modal, risk matrix comparison, signoff, buttons
  // calculate() -> POST
  // save() -> PUT
}
```

Key features:
1. Mode selector: three radio pills.
2. Fish-Bone: render the fishbone editor (interactive 6M). If Fishbone global available.
3. Bow-Tie:
   - Severity sliders (7) 0-5 each, live total score + letter badge.
   - Bow-tie visualizer: threat cards (left), ECM/NCM pills (left-center), top event (center), ERB/NRB pills (right-center), consequence cards (right).
     - Threats: text inputs; each threat can be assigned to ECM/NCM barriers.
     - Barriers: pills with name + bsv badge; click to open BQV modal.
     - Top event: input text.
     - Consequences: text inputs; assigned ERB/NRB barriers.
   - Barrier Quality modal: 7 sliders → live BQV/BSV badge.
   - Before/After risk matrix comparison: shows initial index + tolerability vs resultant.
   - Sign-off container: role authorization badge (from risk profile), name/role/date inputs.
4. Combined: root cause → NCM promotion. When in combined mode, each fishbone root cause gets a "Promote to NCM" action; promoted causes appear as NCM barriers in the bow-tie.
5. Calculate button (POST, no persist) and Save button (PUT persist).

This is a big chunk of code. Let me write it as a robust vanilla JS module. I'll keep it functional and clean.

Given the complexity and that these pages use inline scripts + check-inline-scripts.js verifies inline scripts syntactically, I must be careful with inline script correctness. The srm.js is a separate file so node --check will verify it.

For detail.html integration:
- Add styles for the workspace.
- Add `<div class="card" id="srmCard">...` with `#srmWorkspace` container and `<script src="/js/srm.js">`.
- In the inline script, after renderHazard, init SRM workspace with hazard data.

For cap_submit.html integration:
- Add Analysis Model Selector banner + Combined mode promotion area. Since the fishbone is already there via Fishbone.renderEditor, in Combined mode we promote root causes. I'll integrate SRM into cap_submit:
  - Add `<div id="srmWorkspace">` after the fishbone editor (or replace the residual SRA section? No — keep both).
  - Actually the spec for cap_submit.html: "Integrate the Combined RCA + SRAM workflow (promoting Fish-Bone root causes into Bow-Tie NCM barriers)". So the key deliverable: allow fishbone root causes to be promoted to NCMs, and include the SRM data in the CAP submission.
  - I'll add the Analysis Model Selector banner; when Combined selected, show an SRM section with the promoted NCMs list + before/after risk + signoff. On submit, include sram_data.

To avoid over-complexity in cap_submit, I'll expose a lightweight `SRM.attachCombined(root, {fishboneController})` helper that:
- Renders the mode selector (default Combined).
- In Combined mode, shows NCM promotion panel: lists fishbone root causes with "Promote to NCM" buttons; promoted causes move to an NCM list where each can be BQV-rated (using a simple inline rating or default quality 3s).
- Computes a mini risk profile client-side? No — better to call the calculate endpoint? But cap_submit has a CAN, not necessarily a hazard with an id. The CAN has hazard_id though. Hmm — but the SRM save endpoint is tied to hazards. For CAP, the sram_data is just included in the CAP payload and validated server-side? The can_cap submit doesn't validate sram_data currently.

Simplest correct approach for cap_submit: build sram_data client-side using the SRM engine logic duplicated in JS (mirroring the backend calculations) OR call the hazard calculate endpoint if a hazard_id is available. The CAN has hazard_id (CANCreate requires hazard_id). So cap_submit could load the CAN → hazard_id → use SRM.calculate for the risk profile. But that adds a fetch dependency.

Given scope, I'll implement the promotion panel in cap_submit with client-side computation mirroring the engine (using a small JS copy of the math — the same math as backend, deterministic), and include the resulting sram_data in the CAP submission. This is self-contained and doesn't require a hazard id. The backend will persist it via the new `sram_data` field.

But duplicating the math in JS risks drift. Alternative: call the calculate endpoint with the hazard_id from the CAN when available. Let me check whether CAN fetch returns hazard_id. The CAN model requires hazard_id. CanCapAPI.getCan returns can record. It likely includes hazard_id. Then cap_submit can POST to /api/v1/hazards/{hazard_id}/sram/calculate to get authoritative metrics. If the hazard doesn't exist (edge), fall back to client-side.

Hmm — but actually for the Combined workflow on cap_submit, the "severity" for the SRM should come from the residual SRA or from the hazard's severity inputs. This is getting complicated.

Let me scope cap_submit pragmatically:
- Add the Analysis Model Selector banner (Fish-Bone / Bow-Tie / Combined), default Combined.
- In Combined/BowTie mode, show an SRM section that:
  - Displays the NCM promotion list fed from fishbone root causes.
  - Allows rating each promoted NCM (BQV via modal or defaults).
  - Computes a risk profile by calling the hazard SRM calculate endpoint using the CAN's hazard_id and the hazard's stored severity inputs (if available). If no hazard_id or fetch fails, compute client-side with defaults.
  - Shows before/after + signoff.
  - On submit, includes sram_data in the CAP payload.

That's still a lot. Given the constraint of doing this well, I'll implement a client-side SRM math helper in srm.js (`SRM.compute(severityInputs, barriers)`) that mirrors the backend exactly, and use it for cap_submit's Combined flow. This keeps cap_submit fully self-contained and testable via node. The backend save path is authoritative when used from hazard detail.

Wait — but then the risk numbers in cap_submit come from JS math. The backend will persist them as-is (no server validation on CAP sram_data). Acceptable.

Actually, let me reconsider: keep the cap_submit integration minimal but genuinely useful:
1. Mode selector banner.
2. Combined mode: a "Promote Root Cause to New Control Measure (NCM)" action on each fishbone root cause (adds a button next to root causes; fishbone.js renderEditor already renders cause rows with inputs + remove buttons; I need to inject a promote button). fishbone.js has its own row markup; injecting a button requires either modifying fishbone.js or wrapping. Simpler: add a separate "Promotion Panel" below the fishbone that lists all root causes with Promote buttons (read from fishboneController.getData()), independent of the fishbone internal row UI. That avoids modifying fishbone.js.
3. Promoted NCMs appear in a list with BQV rating (defaults) and bsv badge.
4. Combined with existing residual SRA (severity letter A-E? The residual SRA uses severity 1-5). For the SRM risk profile we need severity A-E. I'll compute severity from the hazard's own SRM severity if present, else from the 7 sliders defaulting 0. Hmm.

OK, I'm overthinking cap_submit. Let me keep it simpler but still functional:
- The promotion panel lists fishbone root causes, each can be "Promote to NCM" → creates an NCM barrier with BQV default quality 3 and bsv computed via JS.
- The SRM section shows: the NCM list with bsv badges, a Before/After risk summary computed from severity (uses the 7-impact sliders defaulting to values, OR from hazard's severity letter if available — I'll use severity letter from the residual SRA? residual severity is 1-5. Map to letter: 5→A,4→B,3→C,2→D,1→E).
- Sign-off container.
- Include sram_data in CAP payload.

I'll use `SRM.compute()` mirroring backend math in JS. Good.

Now let me write `public/js/srm.js`. I need to be careful about correctness since node --check and check-inline-scripts will run, plus frontend test suites. Let me check what frontend integrity checks exist. Earlier summary mentioned `node frontend-tests/check-inline-scripts.js public` (48/48) and frontend suites (dashboard 4, tenant-context, input-guard 12, appcheck). Let me check frontend-tests directory.

Let me look at how the frontend tests run (package.json) to know what checks to run at the end.

Backend fully green (447). Now the frontend. Let me check the frontend test setup first

**Tool: bash**

**Input:**
```json
{
  "command": "Get-ChildItem frontend-tests -Name; Write-Output \"---PKG---\"; Get-Content package.json",
  "workdir": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe"
}
```

**Output:**
```
check-inline-scripts.js
dashboard.test.js
firebase-appcheck-verify.js
input-guard.test.js
tenant-context.test.js
---PKG---
{
  "name": "surveysms",
  "version": "2.0.0",
  "description": "ICAO Annex 19 SMS Survey Platform - Multi-tenant Safety Management System",
  "main": "index.html",
  "scripts": {
    "dev": "serve -l 3000",
    "start": "serve -l 3000",
    "python": "python -m http.server 8000",
    "python3": "python3 -m http.server 8000",
    "php": "php -S localhost:8000",
    "live": "live-server --port=5500",
    "build": "echo 'No build step required'",
    "test": "node frontend-tests/dashboard.test.js"
  },
  "keywords": [
    "safety-management",
    "icao-annex-19",
    "sms",
    "survey",
    "aviation",
    "gap-analysis",
    "multi-tenant"
  ],
  "author": "AviaSafeSystems.com",
  "license": "MIT",
  "devDependencies": {
    "serve": "^14.0.0"
  },
  "repository": {
    "type": "git",
    "url": "https://github.com/aviasafesystems/surveysms"
  },
  "engines": {
    "node": ">=14.0.0"
  },
  "dependencies": {
    "firebase-admin": "^11.11.1"
  }
}

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 12.1s)

_Thinking:_

Now let me look at fishbone.js to understand its API for root causes, so I can integrate promotion in cap_submit. Let me read the relevant parts of fishbone.js (getData, renderEditor, and the cause row structure).

**Tool: read**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\js\\fishbone.js"
}
```

**Output:**
```
<path>C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\js\fishbone.js</path>
<type>file</type>
<content>
1: // ============================================================================
2: // FILE: fishbone.js
3: // PURPOSE: Reusable 6-category Fishbone (Ishikawa / 5M + Management) Root Cause
4: //          Analysis editor and viewer for the CAN/CAP workflow.
5: // CATEGORIES: Man, Machine, Method, Medium (Environment), Management, Material.
6: // FEATURES:
7: //   - dynamic add/remove of cause items per category
8: //   - radio selection of exactly ONE 'Primary Root Cause'
9: //   - structured CAP action items linked 1:1 to root cause IDs
10: // DATA MODEL (stored on the CAP record):
11: //   {
12: //     root_causes:  [{ id, category, description, is_primary }],
13: //     action_items: [{ id, description, root_cause_id, owner, target_date }]
14: //   }
15: // ============================================================================
16: 
17: const Fishbone = (() => {
18:     const CATEGORIES = ['Man', 'Machine', 'Method', 'Medium', 'Management', 'Material'];
19:     const DEFAULT_ACTION = {
20:         Man: 'People, staffing, training, fatigue, human performance',
21:         Machine: 'Equipment, tools, aircraft/component condition, technology',
22:         Method: 'Procedures, processes, documentation, compliance',
23:         Medium: 'Environment (weather, facilities, noise, workspace)',
24:         Management: 'Policies, oversight, supervision, accountability, culture',
25:         Material: 'Parts, materials, consumables, specifications',
26:     };
27: 
28:     function uid(prefix) {
29:         return (prefix || 'rc') + '_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
30:     }
31: 
32:     function normalize(data) {
33:         data = data || {};
34:         return {
35:             root_causes: Array.isArray(data.root_causes) ? data.root_causes : [],
36:             action_items: Array.isArray(data.action_items) ? data.action_items : [],
37:         };
38:     }
39: 
40:     function primaryCauseId(data) {
41:         for (const c of (data.root_causes || [])) {
42:             if (c.is_primary) return c.id;
43:         }
44:         return null;
45:     }
46: 
47:     // ------------------------------------------------------------------
48:     // Validation
49:     // ------------------------------------------------------------------
50: 
51:     function validate(data) {
52:         const errors = [];
53:         const norm = normalize(data);
54:         if (!norm.root_causes.length) errors.push('At least one root cause is required.');
55:         if (norm.root_causes.length && !primaryCauseId(norm)) errors.push('Exactly one Primary Root Cause must be designated.');
56:         for (const c of norm.root_causes) {
57:             if (!c.description || !c.description.trim()) errors.push(`Root cause in "${c.category}" is missing a description.`);
58:         }
59:         for (const a of norm.action_items) {
60:             if (!a.description || !a.description.trim()) errors.push('Action item is missing a description.');
61:             if (!a.root_cause_id) errors.push(`Action item "${a.description}" must be linked to a root cause.`);
62:             else if (!norm.root_causes.some(rc => rc.id === a.root_cause_id)) {
63:                 errors.push(`Action item "${a.description}" links to an unknown root cause.`);
64:             }
65:         }
66:         return errors;
67:     }
68: 
69:     // ------------------------------------------------------------------
70:     // Editor
71:     // ------------------------------------------------------------------
72: 
73:     function renderEditor(container, opts) {
74:         opts = opts || {};
75:         const el = typeof container === 'string' ? document.getElementById(container) : container;
76:         if (!el) throw new Error('[Fishbone] container not found: ' + container);
77: 
78:         const data = normalize(opts.data);
79:         const onChange = opts.onChange || function () {};
80: 
81:         el.innerHTML = '';
82:         const wrap = document.createElement('div');
83:         wrap.className = 'fishbone';
84: 
85:         const head = document.createElement('div');
86:         head.className = 'fishbone-head';
87:         head.innerHTML = `
88:             <div class="fishbone-title"><i class="fas fa-diagnoses"></i> Root Cause Analysis — Fishbone / Ishikawa (5M + Management)</div>
89:             <div class="fishbone-hint">Add causes under each category. Designate exactly one <strong>Primary Root Cause</strong>.</div>
90:         `;
91:         wrap.appendChild(head);
92: 
93:         const grid = document.createElement('div');
94:         grid.className = 'fishbone-grid';
95: 
96:         function renderCategory(cat) {
97:             const panel = document.createElement('div');
98:             panel.className = 'fishbone-category';
99:             panel.dataset.category = cat;
100:             panel.innerHTML = `
101:                 <div class="fishbone-category-head">
102:                     <span class="fishbone-category-name">${cat}</span>
103:                     <span class="fishbone-category-desc">${DEFAULT_ACTION[cat] || ''}</span>
104:                 </div>
105:                 <div class="fishbone-causes"></div>
106:                 <button type="button" class="fishbone-add-cause btn btn-outline btn-sm"><i class="fas fa-plus"></i> Add cause</button>
107:             `;
108: 
109:             const list = panel.querySelector('.fishbone-causes');
110: 
111:             function renderCauses() {
112:                 const causes = data.root_causes.filter(c => c.category === cat);
113:                 list.innerHTML = '';
114:                 if (!causes.length) {
115:                     const empty = document.createElement('div');
116:                     empty.className = 'fishbone-empty';
117:                     empty.textContent = 'No causes identified yet.';
118:                     list.appendChild(empty);
119:                 }
120:                 causes.forEach(cause => {
121:                     const row = document.createElement('div');
122:                     row.className = 'fishbone-cause-row';
123:                     row.innerHTML = `
124:                         <label class="fishbone-primary-radio" title="Mark as Primary Root Cause">
125:                             <input type="radio" name="fishbone_primary" value="${cause.id}" ${cause.is_primary ? 'checked' : ''}>
126:                             <span>Primary</span>
127:                         </label>
128:                         <input type="text" class="form-control fishbone-cause-input" value="${escapeAttr(cause.description || '')}" placeholder="Describe the cause…">
129:                         <button type="button" class="fishbone-remove-cause" title="Remove cause"><i class="fas fa-times"></i></button>
130:                     `;
131:                     const input = row.querySelector('.fishbone-cause-input');
132:                     input.addEventListener('input', () => {
133:                         cause.description = input.value;
134:                         onChange(getData());
135:                     });
136:                     row.querySelector('.fishbone-primary-radio input').addEventListener('change', () => {
137:                         data.root_causes.forEach(c => { c.is_primary = (c.id === cause.id); });
138:                         onChange(getData());
139:                     });
140:                     row.querySelector('.fishbone-remove-cause').addEventListener('click', () => {
141:                         data.root_causes = data.root_causes.filter(c => c.id !== cause.id);
142:                         // Unlink any action items pointing at the removed cause.
143:                         data.action_items.forEach(a => {
144:                             if (a.root_cause_id === cause.id) a.root_cause_id = null;
145:                         });
146:                         renderAll();
147:                         onChange(getData());
148:                     });
149:                     list.appendChild(row);
150:                 });
151:             }
152: 
153:             panel.querySelector('.fishbone-add-cause').addEventListener('click', () => {
154:                 data.root_causes.push({
155:                     id: uid('rc'),
156:                     category: cat,
157:                     description: '',
158:                     is_primary: data.root_causes.length === 0,
159:                 });
160:                 renderAll();
161:                 onChange(getData());
162:             });
163: 
164:             return { panel, renderCauses };
165:         }
166: 
167:         const categoryPanels = {};
168:         CATEGORIES.forEach(cat => {
169:             const { panel, renderCauses } = renderCategory(cat);
170:             categoryPanels[cat] = renderCauses;
171:             grid.appendChild(panel);
172:         });
173:         wrap.appendChild(grid);
174: 
175:         // ------------------------------------------------------------------
176:         // Action Items (1:1 linkage to root causes)
177:         // ------------------------------------------------------------------
178: 
179:         const actionsSection = document.createElement('div');
180:         actionsSection.className = 'fishbone-actions';
181:         actionsSection.innerHTML = `
182:             <div class="fishbone-actions-head">
183:                 <span class="fishbone-actions-title"><i class="fas fa-tasks"></i> Corrective Action Items</span>
184:                 <span class="fishbone-actions-hint">Each action item links 1:1 to an identified root cause.</span>
185:             </div>
186:             <div class="fishbone-actions-table-wrap">
187:                 <table class="fishbone-actions-table">
188:                     <thead>
189:                         <tr>
190:                             <th style="width:38%;">Action Item</th>
191:                             <th style="width:30%;">Linked Root Cause</th>
192:                             <th style="width:16%;">Owner</th>
193:                             <th style="width:12%;">Target Date</th>
194:                             <th style="width:4%;"></th>
195:                         </tr>
196:                     </thead>
197:                     <tbody class="fishbone-actions-body"></tbody>
198:                 </table>
199:             </div>
200:             <button type="button" class="fishbone-add-action btn btn-outline btn-sm"><i class="fas fa-plus"></i> Add action item</button>
201:             <div class="fishbone-actions-errors" style="display:none;"></div>
202:         `;
203:         wrap.appendChild(actionsSection);
204: 
205:         const actionsBody = actionsSection.querySelector('.fishbone-actions-body');
206: 
207:         function causeOptions(selectedId) {
208:             const options = ['<option value="">— select root cause —</option>'];
209:             data.root_causes.forEach(c => {
210:                 const sel = c.id === selectedId ? 'selected' : '';
211:                 options.push(`<option value="${c.id}" ${sel}>${escapeAttr((c.category + ' — ' + (c.description || '')).slice(0, 60))}</option>`);
212:             });
213:             return options.join('');
214:         }
215: 
216:         function renderActions() {
217:             actionsBody.innerHTML = '';
218:             if (!data.action_items.length) {
219:                 const tr = document.createElement('tr');
220:                 tr.innerHTML = '<td colspan="5" class="fishbone-empty">No action items yet. Add one to link a corrective action to a root cause.</td>';
221:                 actionsBody.appendChild(tr);
222:                 return;
223:             }
224:             data.action_items.forEach(item => {
225:                 const tr = document.createElement('tr');
226:                 tr.dataset.actionId = item.id;
227:                 tr.innerHTML = `
228:                     <td><input type="text" class="form-control fishbone-action-desc" value="${escapeAttr(item.description || '')}" placeholder="What will be done?"></td>
229:                     <td><select class="form-control fishbone-action-cause">${causeOptions(item.root_cause_id)}</select></td>
230:                     <td><input type="text" class="form-control fishbone-action-owner" value="${escapeAttr(item.owner || '')}" placeholder="Owner"></td>
231:                     <td><input type="date" class="form-control fishbone-action-date" value="${item.target_date || ''}"></td>
232:                     <td><button type="button" class="fishbone-remove-action" title="Remove"><i class="fas fa-times"></i></button></td>
233:                 `;
234:                 tr.querySelector('.fishbone-action-desc').addEventListener('input', () => {
235:                     item.description = tr.querySelector('.fishbone-action-desc').value;
236:                     refreshCauseOptions();
237:                     onChange(getData());
238:                 });
239:                 tr.querySelector('.fishbone-action-cause').addEventListener('change', (ev) => {
240:                     item.root_cause_id = ev.target.value || null;
241:                     onChange(getData());
242:                 });
243:                 tr.querySelector('.fishbone-action-owner').addEventListener('input', () => {
244:                     item.owner = tr.querySelector('.fishbone-action-owner').value;
245:                     onChange(getData());
246:                 });
247:                 tr.querySelector('.fishbone-action-date').addEventListener('change', () => {
248:                     item.target_date = tr.querySelector('.fishbone-action-date').value || null;
249:                     onChange(getData());
250:                 });
251:                 tr.querySelector('.fishbone-remove-action').addEventListener('click', () => {
252:                     data.action_items = data.action_items.filter(a => a.id !== item.id);
253:                     renderActions();
254:                     onChange(getData());
255:                 });
256:                 actionsBody.appendChild(tr);
257:             });
258:         }
259: 
260:         function refreshCauseOptions() {
261:             const selects = actionsBody.querySelectorAll('.fishbone-action-cause');
262:             selects.forEach(sel => {
263:                 const current = sel.value;
264:                 sel.innerHTML = causeOptions(current);
265:             });
266:         }
267: 
268:         actionsSection.querySelector('.fishbone-add-action').addEventListener('click', () => {
269:             const primaryId = primaryCauseId(data);
270:             data.action_items.push({
271:                 id: uid('ai'),
272:                 description: '',
273:                 root_cause_id: primaryId || null,
274:                 owner: '',
275:                 target_date: null,
276:             });
277:             renderActions();
278:             onChange(getData());
279:         });
280: 
281:         function renderAll() {
282:             CATEGORIES.forEach(cat => categoryPanels[cat]());
283:             renderActions();
284:         }
285: 
286:         function getData() {
287:             const errs = validate(data);
288:             const errEl = actionsSection.querySelector('.fishbone-actions-errors');
289:             if (errs.length) {
290:                 errEl.style.display = 'block';
291:                 errEl.textContent = errs.join(' ');
292:                 errEl.className = 'fishbone-actions-errors fishbone-errors-show';
293:             } else {
294:                 errEl.style.display = 'none';
295:             }
296:             return normalize(data);
297:         }
298: 
299:         renderAll();
300: 
301:         return {
302:             element: wrap,
303:             getData,
304:             validate: () => validate(data),
305:         };
306:     }
307: 
308:     // ------------------------------------------------------------------
309:     // Viewer (read-only)
310:     // ------------------------------------------------------------------
311: 
312:     function renderViewer(container, data) {
313:         const el = typeof container === 'string' ? document.getElementById(container) : container;
314:         if (!el) throw new Error('[Fishbone] container not found: ' + container);
315:         const norm = normalize(data);
316: 
317:         el.innerHTML = '';
318:         const wrap = document.createElement('div');
319:         wrap.className = 'fishbone fishbone-view';
320: 
321:         const head = document.createElement('div');
322:         head.className = 'fishbone-head';
323:         head.innerHTML = `
324:             <div class="fishbone-title"><i class="fas fa-diagnoses"></i> Root Cause Analysis — Fishbone / Ishikawa (5M + Management)</div>
325:         `;
326:         wrap.appendChild(head);
327: 
328:         if (!norm.root_causes.length) {
329:             const none = document.createElement('div');
330:             none.className = 'fishbone-empty';
331:             none.textContent = 'No root causes recorded.';
332:             wrap.appendChild(none);
333:             el.appendChild(wrap);
334:             return { element: wrap };
335:         }
336: 
337:         const grid = document.createElement('div');
338:         grid.className = 'fishbone-grid';
339:         CATEGORIES.forEach(cat => {
340:             const causes = norm.root_causes.filter(c => c.category === cat);
341:             const panel = document.createElement('div');
342:             panel.className = 'fishbone-category';
343:             panel.innerHTML = `
344:                 <div class="fishbone-category-head">
345:                     <span class="fishbone-category-name">${cat}</span>
346:                 </div>
347:                 <div class="fishbone-causes">
348:                     ${causes.length ? causes.map(c => `
349:                         <div class="fishbone-view-cause ${c.is_primary ? 'fishbone-primary' : ''}">
350:                             ${c.is_primary ? '<span class="fishbone-primary-badge"><i class="fas fa-star"></i> Primary</span>' : ''}
351:                             <span class="fishbone-view-text">${escapeHtml(c.description || '')}</span>
352:                         </div>`).join('')
353:                         : '<div class="fishbone-empty">None</div>'}
354:                 </div>
355:             `;
356:             grid.appendChild(panel);
357:         });
358:         wrap.appendChild(grid);
359: 
360:         if (norm.action_items.length) {
361:             const acts = document.createElement('div');
362:             acts.className = 'fishbone-actions';
363:             acts.innerHTML = `<div class="fishbone-actions-head"><span class="fishbone-actions-title"><i class="fas fa-tasks"></i> Corrective Action Items</span></div>`;
364:             const table = document.createElement('table');
365:             table.className = 'fishbone-actions-table';
366:             table.innerHTML = `<thead><tr><th>Action Item</th><th>Linked Root Cause</th><th>Owner</th><th>Target Date</th></tr></thead>`;
367:             const tbody = document.createElement('tbody');
368:             norm.action_items.forEach(a => {
369:                 const cause = norm.root_causes.find(c => c.id === a.root_cause_id);
370:                 const tr = document.createElement('tr');
371:                 tr.innerHTML = `
372:                     <td>${escapeHtml(a.description || '')}</td>
373:                     <td>${cause ? escapeHtml(cause.category + ' — ' + (cause.description || '')) : '<span style="color:#b91c1c;">Unlinked</span>'}</td>
374:                     <td>${escapeHtml(a.owner || '')}</td>
375:                     <td>${a.target_date ? escapeHtml(a.target_date) : '—'}</td>
376:                 `;
377:                 tbody.appendChild(tr);
378:             });
379:             table.appendChild(tbody);
380:             acts.appendChild(table);
381:             wrap.appendChild(acts);
382:         }
383: 
384:         el.appendChild(wrap);
385:         return { element: wrap };
386:     }
387: 
388:     // ------------------------------------------------------------------
389:     // HTML escaping helpers
390:     // ------------------------------------------------------------------
391: 
392:     function escapeHtml(v) {
393:         if (v === null || v === undefined) return '';
394:         return String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
395:     }
396: 
397:     function escapeAttr(v) {
398:         return escapeHtml(v);
399:     }
400: 
401:     return {
402:         CATEGORIES,
403:         renderEditor,
404:         renderViewer,
405:         validate,
406:         normalize,
407:         primaryCauseId,
408:     };
409: })();
410: 
411: if (typeof window !== 'undefined') {
412:     window.Fishbone = Fishbone;
413: }

(End of file - total 413 lines)
</content>
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 40.2s)

_Thinking:_

Now I have all the info I need. Let me write `public/js/srm.js` — a comprehensive, self-contained SRM workspace module. It will:

1. Expose `SRM` global with:
   - Constants (severity keys, bqv keys, severity bands, bqv bands, probability config, tolerability matrix, signoff authorities).
   - Pure compute functions mirroring the backend: `computeSeverity`, `computeBqv`, `computeProbability`, `evaluateRiskProfile`.
   - `SrmWorkspace` class for the hazard detail page.
   - `attachCombined` helper for cap_submit (promotion panel).

The workspace needs to be robust, self-contained, and not depend on jQuery. It uses HazardsAPI for calculate/save (already have the module global). 

Let me design the SrmWorkspace rendering:

```
<div class="srm-workspace">
  <div class="srm-mode-selector">
    <span class="srm-mode-title">Analysis Model Selector</span>
    <label><input type="radio" name="srm_mode" value="FISHBONE_ONLY" checked> Fish-Bone RCA</label>
    <label><input type="radio" name="srm_mode" value="BOWTIE_SRAM"> Bow-Tie SRAM</label>
    <label><input type="radio" name="srm_mode" value="COMBINED"> Combined RCA + SRAM</label>
  </div>

  <div class="srm-section srm-fishbone">
    <h3>6M Root-Cause Diagram (Fish-Bone / Ishikawa)</h3>
    <div id="srmFishboneEditor"></div>
  </div>

  <div class="srm-section srm-bowtie">
    <h3>7-Impact Severity Assessment</h3>
    <div class="srm-severity-grid">
      <!-- sliders -->
    </div>
    <div class="srm-score-badge">
      <span class="srm-score-value">0</span> <span class="srm-severity-letter">E</span> <span class="srm-severity-desc">Insignificant</span>
    </div>

    <h3>Interactive Bow-Tie</h3>
    <div class="srm-bowtie">
      <div class="srm-column srm-threats">
        <div class="srm-col-head">Threats</div>
        <div class="srm-threat-list"></div>
        <button>Add Threat</button>
      </div>
      <div class="srm-column srm-ecm">
        <div class="srm-col-head">Existing Control Measures (ECM)</div>
        <div class="srm-ecm-list"></div>
        <button>Add ECM</button>
      </div>
      <div class="srm-center">
        <div class="srm-top-event">TOP EVENT</div>
        <input>
      </div>
      <div class="srm-column srm-erb">
        <div class="srm-col-head">Existing Recovery Barriers (ERB)</div>
        <div class="srm-erb-list"></div>
        <button>Add ERB</button>
      </div>
      <div class="srm-column srm-consequences">
        <div class="srm-col-head">Consequences</div>
        <div class="srm-consequence-list"></div>
        <button>Add Consequence</button>
      </div>
    </div>

    <h3>New Control Measures (NCM) / New Recovery Barriers (NRB)</h3>
    <div class="srm-new-barriers">
      <div>NCM list</div><div>NRB list</div>
      <button>Add NCM</button><button>Add NRB</button>
    </div>

    <h3>Before & After Risk Matrix</h3>
    <div class="srm-risk-comparison">
      <div class="srm-before">Current: 4D Tolerable</div>
      <i class="fas fa-arrow-right"></i>
      <div class="srm-after">Resultant: 1D Acceptable</div>
    </div>

    <h3>Digital Sign-Off</h3>
    <div class="srm-signoff">
      <div class="srm-authority-badge">Required: Safety Manager / SAG Member</div>
      <input name>, <input role>, <input date>
    </div>

    <div class="srm-actions">
      <button>Calculate (Preview)</button>
      <button>Save Configuration</button>
    </div>
  </div>
</div>
```

The bow-tie visualizer: threat cards → ECM pills → top event → ERB pills → consequence cards. Plus NCM/NRB. For the visualizer, each threat has `barrier_ids` linking to ECM pills; each consequence has `barrier_ids` linking to ERB pills. That's a nice-to-have; the core is the barrier pills with BQV modal and the severity/probability math. I'll implement the linking simply: each threat row has a dropdown to select an ECM barrier; each consequence row has a dropdown to select an ERB barrier. Visually it forms the bow-tie flow.

The BQV modal: a modal overlay with 7 sliders → live BQV/BSV badge. On save, updates the barrier's quality, bqv, bsv.

Barrier pills: show name + bsv badge. Click opens BQV modal. Each has a remove button.

For Combined mode: The fishbone root causes get a "Promote to NCM" button in a promotion panel (separate from fishbone editor to avoid modifying fishbone.js). Promoted causes become NCM barriers (with source_root_cause_id). Additionally when in Combined mode, fishbone section shows and promotion panel is active; in BowTie mode the fishbone is hidden.

Actually — wait. In the hazard detail page, there's no existing fishbone data normally. The fishbone editor starts empty. Fine.

Let me now write srm.js. I need to keep the file syntactically valid (node --check). It's vanilla JS, no TS.

The calculate/save flow:
- `calculate()`: build payload {severity: inputs, barriers: {ecb, erb, ncb, nrb (each with name, quality, bsv)}, bowtie: {...}}. Call HazardsAPI.sramCalculate(hazardId, payload). Then update the UI risk comparison + signoff badge from the response.
- `save()`: build the full sram_data {severity: inputs + computed, barriers, risk_profile, bowtie, fishbone, signoffs} + analysis_mode. Call HazardsAPI.sramSave(hazardId, payload). On success, toast + refresh hazard.

The JS compute functions mirror backend for local preview (before calculate) so the UI feels live. The calculate endpoint is authoritative. I'll implement local compute for instant feedback and call the endpoint on Calculate button for the authoritative result.

Actually to keep behavior simple and authoritative, the local compute gives the live badges; the Calculate button calls the API and refreshes the comparison + signoff from server response. Save persists.

Now the barriers in the payload: each barrier {id, name, quality: {effectiveness,...,disinclination}, bqv, bsv}. evaluate_barriers on server recomputes from quality.

Let me also handle: when the saved hazard already has sram_data, load it to pre-populate the workspace (sliders, barriers, signoffs, mode). Good for re-opening.

Let me write the file now. This will be long (~700 lines). Let me be careful.

Key helper for building sliders:
```js
function sliderRow(key, label, icon, value) {
  return `<div class="srm-slider-row">
    <span class="srm-slider-icon"><i class="fas ${icon}"></i></span>
    <span class="srm-slider-label">${label}</span>
    <input type="range" min="0" max="5" step="1" value="${value}" data-key="${key}">
    <span class="srm-slider-value" data-key-val="${key}">${value}</span>
  </div>`;
}
```

Barrier quality modal:
```js
function openBarrierQualityModal(barrier) { ... }
```

Risk profile compute (JS mirror):
```js
function computeSeverity(inputs) {
  const score = 4*inputs.pax + 3*inputs.worker + 2*inputs.quality + inputs.asset + inputs.rep + inputs.sec + inputs.env;
  const bands = [[52,65,'A','Catastrophic'],[39,51,'B','Major'],[26,38,'C','Moderate'],[13,25,'D','Minor'],[0,12,'E','Insignificant']];
  for (const [lo,hi,letter,desc] of bands) if (score>=lo && score<=hi) return {total_score:score, severity_letter:letter, descriptor:desc};
  return {total_score:score, severity_letter:'E', descriptor:'Insignificant'};
}
function computeBqv(q) {
  const bqv = 3*q.effectiveness + q.cost_benefit + q.practicality + q.acceptability + q.enforceability + q.durability + 2*q.disinclination;
  const bands = [[42,50,5,'Excellent'],[34,41,4,'Very Good'],[26,33,3,'Good'],[18,25,2,'Fair'],[10,17,1,'Poor'],[0,9,0,'Ineffective']];
  for (const [lo,hi,bsv,rb] of bands) if (bqv>=lo && bqv<=hi) return {bqv, bsv, robustness:rb};
}
function computeProbability(sevLetter, cbsv) {
  const cfg = {
    A:[8,40,[[0,7,5],[8,15,4],[16,23,3],[24,31,2],[32,40,1]]],
    B:[6,30,[[0,5,5],[6,11,4],[12,17,3],[18,23,2],[24,30,1]]],
    C:[4,20,[[0,3,5],[4,7,4],[8,11,3],[12,15,2],[16,20,1]]],
    D:[3,15,[[0,2,5],[3,5,4],[6,8,3],[9,11,2],[12,15,1]]],
    E:[2,10,[[0,1,5],[2,3,4],[4,5,3],[6,7,2],[8,10,1]]],
  };
  const [onb, maxv, bands] = cfg[sevLetter] || cfg.E;
  let value = Math.max(0, Math.min(cbsv, maxv));
  for (const [lo,hi,pv] of bands) if (value>=lo && value<=hi) return pv;
  return 1;
}
```

Tolerability matrix + signoff (JS mirror).

Given the size, let me write the whole file now. I'll structure the workspace with clear methods and inner rendering. I must be careful with template literals and escaping. Let me write it.

Also need CSS for the SRM workspace. I'll add a `<style>` block in detail.html and cap_submit.html. To keep pages clean, maybe a shared css file `public/css/srm.css`. There's a css directory. Let me create `public/css/srm.css`.

Let me check the css directory listing quickly — I saw can-cap-print.css, shell.css, variables.css, theme.css, main.css, copilot-widget.css references. I'll create srm.css.

Now, for HazardsAPI additions:
```js
sramCalculate: (hazardId, payload) => ApiClient.post(`/api/hazards/${hazardId}/sram/calculate`, payload),
sramSave: (hazardId, payload) => ApiClient.put(`/api/hazards/${hazardId}/sram/save`, payload),
```
Note: frontend uses the legacy prefix /api/hazards which is the same router. Good — endpoints registered on both prefixes.

Let me write the files. First the CSS.

All context gathered. Now the frontend. First, add SRM API methods to `hazards.js`



**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\js\\hazards.js",
  "newString": "getStats: () => ApiClient.get('/api/hazards/stats'),\n\n    // ── CAAN CAR-19 SRM (Bow-Tie) ──\n    sramCalculate: (hazardId, payload) =>\n        ApiClient.post(`/api/hazards/${hazardId}/sram/calculate`, payload),\n\n    sramSave: (hazardId, payload) =>\n        ApiClient.put(`/api/hazards/${hazardId}/sram/save`, payload),\n};",
  "oldString": "getStats: () => ApiClient.get('/api/hazards/stats'),\n};"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 53.0s)

Now the SRM stylesheet

**Tool: write**

**Input:**
```json
{
  "content": "/* ============================================================================\n   srm.css — CAAN CAR-19 Safety Risk Management (SRM) Bow-Tie workspace\n   Styles for the Analysis Model Selector, 7-impact severity sliders,\n   interactive Bow-Tie visualizer, Barrier Quality modal, before/after risk\n   comparison and digital sign-off container.\n   ============================================================================ */\n\n.srm-workspace { display: block; }\n\n/* ── Analysis Model Selector ─────────────────────────────────────────────── */\n.srm-mode-selector {\n    display: flex; align-items: center; gap: 0.9rem; flex-wrap: wrap;\n    background: #f0f4ff; border: 1px solid #dbe7f5; border-radius: 8px;\n    padding: 0.7rem 1rem; margin-bottom: 1.1rem;\n}\n.srm-mode-title { font-weight: 700; font-size: 0.85rem; color: #0b2a42; }\n.srm-mode-selector label {\n    display: inline-flex; align-items: center; gap: 0.35rem;\n    font-size: 0.82rem; font-weight: 600; color: #1e3a5f; cursor: pointer;\n    padding: 0.35rem 0.7rem; border-radius: 999px; background: #fff;\n    border: 1px solid #d1d9e6; transition: all 0.15s;\n}\n.srm-mode-selector label:hover { border-color: #1a6b8a; }\n.srm-mode-selector label.srm-mode-active {\n    background: #1a6b8a; color: #fff; border-color: #1a6b8a;\n}\n.srm-mode-selector input { accent-color: #1a6b8a; }\n\n.srm-section { margin-bottom: 1.4rem; }\n.srm-section h3 {\n    font-size: 0.88rem; font-weight: 700; color: #0b2a42; margin: 0 0 0.6rem;\n    text-transform: uppercase; letter-spacing: 0.4px;\n}\n.srm-hint { font-size: 0.75rem; color: #64748b; margin: -0.3rem 0 0.6rem; }\n\n/* ── Severity sliders ────────────────────────────────────────────────────── */\n.srm-severity-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.4rem 1.2rem; }\n@media (max-width: 640px) { .srm-severity-grid { grid-template-columns: 1fr; } }\n.srm-slider-row { display: flex; align-items: center; gap: 0.6rem; padding: 0.3rem 0; }\n.srm-slider-icon { width: 1.3rem; text-align: center; color: #1a6b8a; }\n.srm-slider-label { flex: 1; font-size: 0.8rem; color: #334155; font-weight: 500; }\n.srm-slider-row input[type=\"range\"] { flex: 1; accent-color: #1a6b8a; cursor: pointer; }\n.srm-slider-value {\n    width: 1.6rem; text-align: center; font-weight: 700; font-size: 0.85rem;\n    color: #0b2a42; background: #eef2f7; border-radius: 4px; padding: 0.15rem 0;\n}\n\n.srm-score-badge {\n    display: flex; align-items: center; gap: 0.6rem; margin-top: 0.6rem;\n    background: #0b2a42; color: #fff; border-radius: 8px; padding: 0.6rem 1rem;\n    font-size: 0.9rem;\n}\n.srm-score-value { font-size: 1.4rem; font-weight: 800; }\n.srm-severity-letter {\n    font-size: 1.4rem; font-weight: 800; color: #ffd166;\n    border: 2px solid #ffd166; border-radius: 8px; padding: 0.05rem 0.55rem;\n}\n.srm-severity-desc { color: #cbd5e1; font-weight: 600; }\n\n/* ── Bow-Tie visualizer ──────────────────────────────────────────────────── */\n.srm-bowtie {\n    display: grid; grid-template-columns: 1fr 1fr auto 1fr 1fr;\n    gap: 0.6rem; align-items: stretch; margin: 0.4rem 0;\n}\n@media (max-width: 900px) { .srm-bowtie { grid-template-columns: 1fr 1fr; } }\n.srm-bowtie .srm-col {\n    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 0.6rem;\n}\n.srm-col-head {\n    font-size: 0.7rem; font-weight: 700; text-transform: uppercase;\n    letter-spacing: 0.4px; color: #475569; margin-bottom: 0.45rem;\n}\n.srm-card {\n    background: #fff; border: 1px solid #e2e8f0; border-radius: 6px;\n    padding: 0.45rem 0.55rem; margin-bottom: 0.45rem; font-size: 0.8rem;\n}\n.srm-card.srm-threat { border-left: 4px solid #dc3545; }\n.srm-card.srm-consequence { border-left: 4px solid #d97706; }\n.srm-card input, .srm-card select { border: 0; outline: 0; font-size: 0.8rem; width: 100%; background: transparent; }\n.srm-barrier-pill {\n    display: flex; align-items: center; justify-content: space-between; gap: 0.4rem;\n    background: #e3f2fd; border: 1px solid #90caf9; border-radius: 999px;\n    padding: 0.35rem 0.7rem; margin-bottom: 0.4rem; font-size: 0.78rem;\n    font-weight: 600; color: #0d47a1; cursor: pointer; transition: all 0.15s;\n}\n.srm-barrier-pill:hover { background: #bbdefb; }\n.srm-barrier-pill.srm-erb { background: #e8f5e9; border-color: #a5d6a7; color: #1b5e20; }\n.srm-barrier-pill.srm-erb:hover { background: #c8e6c9; }\n.srm-barrier-pill.srm-ncb { background: #fff3e0; border-color: #ffcc80; color: #e65100; }\n.srm-barrier-pill.srm-nrb { background: #f3e5f5; border-color: #ce93d8; color: #6a1b9a; }\n.srm-bsv-badge {\n    background: #0d47a1; color: #fff; border-radius: 999px; font-size: 0.68rem;\n    padding: 0.05rem 0.45rem; font-weight: 700; white-space: nowrap;\n}\n.srm-erb .srm-bsv-badge { background: #1b5e20; }\n.srm-ncb .srm-bsv-badge { background: #e65100; }\n.srm-nrb .srm-bsv-badge { background: #6a1b9a; }\n.srm-pill-remove {\n    background: transparent; border: 0; color: inherit; cursor: pointer;\n    font-size: 0.7rem; opacity: 0.7; padding: 0;\n}\n.srm-pill-remove:hover { opacity: 1; }\n.srm-add-btn {\n    width: 100%; background: #fff; border: 1px dashed #94a3b8; border-radius: 6px;\n    color: #64748b; font-size: 0.75rem; padding: 0.35rem; cursor: pointer;\n}\n.srm-add-btn:hover { border-color: #1a6b8a; color: #1a6b8a; }\n\n.srm-top-event {\n    background: #7f1d1d; color: #fff; border-radius: 8px; text-align: center;\n    padding: 0.9rem 0.8rem; font-weight: 800; font-size: 0.8rem;\n    letter-spacing: 0.5px; display: flex; flex-direction: column; gap: 0.4rem;\n    justify-content: center; min-width: 130px;\n}\n.srm-top-event input {\n    background: rgba(255,255,255,0.15); color: #fff; border: 0; border-radius: 4px;\n    padding: 0.3rem; font-size: 0.78rem; text-align: center; outline: 0;\n}\n\n.srm-new-barriers { display: grid; grid-template-columns: 1fr 1fr; gap: 0.8rem; }\n@media (max-width: 640px) { .srm-new-barriers { grid-template-columns: 1fr; } }\n\n/* ── Promotion panel (Combined RCA + SRAM) ───────────────────────────────── */\n.srm-promotion {\n    background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 0.7rem 0.9rem;\n}\n.srm-promotion-head { font-weight: 700; font-size: 0.82rem; color: #166534; margin-bottom: 0.4rem; }\n.srm-promote-row {\n    display: flex; align-items: center; gap: 0.5rem; background: #fff;\n    border: 1px solid #d1fae5; border-radius: 6px; padding: 0.35rem 0.55rem;\n    margin-bottom: 0.35rem; font-size: 0.78rem;\n}\n.srm-promote-row .srm-promote-text { flex: 1; color: #14532d; }\n.srm-promote-btn {\n    background: #16a34a; color: #fff; border: 0; border-radius: 6px;\n    font-size: 0.7rem; font-weight: 700; padding: 0.25rem 0.6rem; cursor: pointer;\n}\n.srm-promote-btn:hover { background: #15803d; }\n.srm-promoted-note { font-size: 0.72rem; color: #166534; font-style: italic; }\n\n/* ── Before / After risk comparison ──────────────────────────────────────── */\n.srm-risk-comparison {\n    display: flex; align-items: center; gap: 0.9rem; flex-wrap: wrap;\n    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 0.8rem 1rem;\n}\n.srm-risk-box { flex: 1; min-width: 170px; text-align: center; }\n.srm-risk-box .srm-risk-index { font-size: 1.7rem; font-weight: 800; }\n.srm-risk-box .srm-risk-tol { font-size: 0.78rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.4px; }\n.srm-risk-box .srm-risk-label { font-size: 0.72rem; color: #64748b; margin-top: 0.15rem; }\n.srm-risk-arrow { color: #94a3b8; font-size: 1.3rem; }\n.srm-tol-intolerable { color: #dc3545; }\n.srm-tol-tolerable { color: #e65100; }\n.srm-tol-acceptable { color: #2e7d32; }\n.srm-bsv-summary { font-size: 0.78rem; color: #475569; margin-top: 0.4rem; }\n\n/* ── Sign-off ────────────────────────────────────────────────────────────── */\n.srm-signoff {\n    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 0.8rem 1rem;\n}\n.srm-authority-badge {\n    display: inline-flex; align-items: center; gap: 0.4rem; font-size: 0.78rem;\n    font-weight: 700; padding: 0.3rem 0.75rem; border-radius: 999px;\n    background: #0b2a42; color: #fff; margin-bottom: 0.6rem;\n}\n.srm-signoff-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0.6rem; }\n@media (max-width: 640px) { .srm-signoff-grid { grid-template-columns: 1fr; } }\n.srm-signoff-grid label { display: block; font-size: 0.72rem; font-weight: 600; color: #475569; margin-bottom: 0.2rem; }\n.srm-signoff-grid input {\n    width: 100%; padding: 0.4rem 0.55rem; border: 1px solid #d1d5db;\n    border-radius: 6px; font-size: 0.82rem; box-sizing: border-box;\n}\n.srm-signoff-grid input:focus { outline: 0; border-color: #1a6b8a; }\n\n/* ── Actions ─────────────────────────────────────────────────────────────── */\n.srm-actions { display: flex; gap: 0.6rem; margin-top: 1rem; flex-wrap: wrap; }\n.srm-btn {\n    border: 0; border-radius: 6px; font-size: 0.85rem; font-weight: 700;\n    padding: 0.6rem 1.2rem; cursor: pointer; transition: opacity 0.15s;\n}\n.srm-btn:hover { opacity: 0.88; }\n.srm-btn:disabled { opacity: 0.5; cursor: not-allowed; }\n.srm-btn-calc { background: #e3f2fd; color: #0d47a1; }\n.srm-btn-save { background: #0b2a42; color: #fff; }\n.srm-btn-outline { background: #fff; color: #1a6b8a; border: 1px solid #1a6b8a; }\n\n/* ── Barrier Quality modal ───────────────────────────────────────────────── */\n.srm-modal-overlay {\n    position: fixed; inset: 0; background: rgba(11, 42, 66, 0.55);\n    display: flex; align-items: center; justify-content: center; z-index: 9999; padding: 1rem;\n}\n.srm-modal {\n    background: #fff; border-radius: 10px; width: 100%; max-width: 520px;\n    box-shadow: 0 18px 50px rgba(0,0,0,0.3); max-height: 90vh; overflow: auto; padding: 1.2rem 1.4rem;\n}\n.srm-modal h3 { margin: 0 0 0.2rem; font-size: 1rem; color: #0b2a42; }\n.srm-modal .srm-modal-sub { font-size: 0.75rem; color: #64748b; margin-bottom: 0.8rem; }\n.srm-bqv-badge {\n    display: flex; align-items: center; gap: 0.6rem; background: #0b2a42; color: #fff;\n    border-radius: 8px; padding: 0.6rem 1rem; margin-bottom: 0.9rem;\n}\n.srm-bqv-value { font-size: 1.3rem; font-weight: 800; }\n.srm-bsv-chip {\n    font-size: 1.3rem; font-weight: 800; color: #ffd166;\n    border: 2px solid #ffd166; border-radius: 8px; padding: 0.05rem 0.5rem;\n}\n.srm-bsv-robustness { color: #cbd5e1; font-weight: 600; font-size: 0.85rem; }\n.srm-modal-actions { display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 1rem; }\n\n/* ── Status / toast ──────────────────────────────────────────────────────── */\n.srm-status { font-size: 0.78rem; margin-top: 0.6rem; display: none; }\n.srm-status.srm-ok { color: #2e7d32; display: block; }\n.srm-status.srm-err { color: #dc3545; display: block; }",
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\css\\srm.css"
}
```

**Output:**
```
Wrote file successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 169.1s)

_Thinking:_

Now the main `public/js/srm.js`. This is the big one. Let me write it carefully with clean vanilla JS, mirroring the backend math for live preview, plus the SrmWorkspace class and the `attachCombined` helper.

I'll structure:
- SRM module (IIFE-ish object) with:
  - CATEGORIES list (fishbone)
  - compute functions
  - escapeHtml/escapeAttr
  - SrmWorkspace class
  - attachCombined for cap_submit

Let me write it. I'll aim for correctness and completeness. I need to handle:

Workspace state:
```js
{
  hazardId,
  analysisMode: 'FISHBONE_ONLY',
  severityInputs: {pax:0,worker:0,quality:0,asset:0,rep:0,sec:0,env:0},
  barriers: {ecb:[], erb:[], ncb:[], nrb:[]},
  bowtie: {threats:[], top_event:'', consequences:[]},
  fishbone: null,
  signoffs: {name:'', role:'', date:''},
  riskProfile: null, // computed
}
```

Barrier object: {id, name, quality:{...7 defaults 3}, bqv, bsv, robustness, source_root_cause_id, category}

Methods:
- render() — build skeleton DOM, then renderAll sections.
- bindModeSelector()
- renderSeverity(), bindSeverity inputs (input event → update inputs, update badge via computeSeverity, then recompute profile live)
- renderBowtie() — threats, ecm, erb, consequences, top event, ncb/nrb lists
- renderBarrierPills(listEl, list, cls) 
- addThreat/addConsequence/addBarrier(kind)
- openBarrierQualityModal(barrier, cls)
- renderNewBarriers()
- renderFishbone() — if Fishbone available, renderEditor; plus promotion panel (combined mode)
- renderPromotion() — list root causes from fishboneController.getData() with Promote buttons
- computeLive() — update risk comparison + signoff from local compute (using evaluateRiskProfile JS mirror)
- calculate() — call API
- save() — call API
- loadSaved(saved) — populate from hazard.sram_data
- getPayload() for calculate; getSavePayload() for save
- status msg helpers

For the promotion in combined mode: a "Promote to NCM" button per root cause. When clicked, adds to ncb list a barrier {name: description, quality: defaults, source_root_cause_id: rc.id, category: rc.category}. Already-promoted causes show "Promoted ✓" and are skipped.

For cap_submit's attachCombined: 
```js
function attachCombined(container, opts) {
  // opts: { fishboneController (getData), getCanHazard... } 
  // Renders mode selector + NCM promotion panel + risk preview + signoff
  // Returns controller with getSramData() and refresh()
}
```
It reuses the same compute functions and the promotion panel rendering. It doesn't need the full bow-tie visualizer or the severity sliders necessarily, but I could reuse. For cap_submit, keep it focused:
- Mode selector (default COMBINED).
- In Combined mode: promotion panel listing fishbone root causes → NCM list with bqv badges (default quality 3, editable via modal too).
- Before/after risk preview using severity letter derived from... we don't have severity inputs in cap_submit. We have residual SRA severity (1-5). I'll map residual severity 1-5 → letter (5→A...1→E). But severity inputs aren't available. The risk profile needs a severity letter. I'll let the SRM section include the 7 sliders too? For CAP, the residual risk uses A-E from the SRA matrix already (residual_sra.severity_letter exists in the CAP payload as rSra.severity_letter). Actually the cap_submit uses RiskMatrix which yields severity 1-5 and severity_letter? Looking at the code: `residual_sra: { severity: rSev, severity_letter: rSra.severity_letter || null, ... }`. So risk_matrix provides severity_letter. So I can derive severity letter from the residual SRA.

To keep it consistent and simple for cap_submit, the Combined panel will compute the risk profile using the severity letter selected (a small select A-E defaulting from residual SRA letter) — actually simpler: reuse the same 7-slider severity grid so it's uniform. But that duplicates. Hmm.

Given scope/time, I'll make the cap_submit Combined panel reuse the full SrmWorkspace in a "compact" config? That would double-render fishbone. 

Let me simplify the cap_submit integration to satisfy the spec's core ask: "promoting Fish-Bone root causes into Bow-Tie NCM barriers". I'll implement:
1. Analysis Model Selector banner with 3 options, defaulting to COMBINED.
2. A Combined-mode section that:
   - Shows the promotion panel (fishbone root causes → Promote to NCM).
   - Lists promoted NCMs with bsv badges and a per-NCM BQV modal (reuse openBarrierQualityModal).
   - Severity letter selector (A–E) to drive the risk profile (defaults from residual SRA if set).
   - Before/after risk comparison (client-side compute) + signoff authority badge + signoff inputs.
3. On CAP submit, includes `sram_data` in the payload.

That's implementable via a `SRM.attachCombined` function. It reuses SRM compute + modal.

Alright, writing srm.js now. Let me make sure to define helper escape functions locally.

One more consideration: The pages load with `defer`? The scripts are at the bottom of body, so DOM is ready. Inline scripts call on DOMContentLoaded or auth state change.

For detail.html, I'll integrate:
- Add `<link rel="stylesheet" href="/css/srm.css">` in head.
- Add a new card after SRM Status card:
```html
<div class="card">
  <h2><i class="fas fa-diagram-project"></i> CAAN CAR-19 SRM Analysis</h2>
  <div id="srmWorkspace"></div>
</div>
```
- Add `<script src="/js/srm.js"></script>` before the inline script.
- In the inline script, after renderHazard() in renderHazard (or after loadHazard), init:
```js
let srmWorkspace = null;
// in renderHazard() after renderVerificationSection(h):
initSrm(h);

function initSrm(h) {
  if (srmWorkspace || !window.SRM) return;
  const el = document.getElementById('srmWorkspace');
  if (!el) return;
  srmWorkspace = SRM.createWorkspace(el, {
    hazardId: h.id,
    saved: h.sram_data || null,
    mode: h.analysis_mode || 'FISHBONE_ONLY',
  });
}
```

Let me now write srm.js.

I'll be meticulous about JS syntax. Long file. Let me write it.

Also, I need to keep the "Calculate"/"Save" buttons available in all modes? The calculate/save only apply to Bow-Tie SRAM/Combined. In Fish-Bone only mode, the SRM section is hidden and just the fishbone shows. Save in FISHBONE_ONLY mode persists the fishbone data + mode (via save with sram_data.fishbone). Actually the save endpoint requires sram_data.severity with severity_letter. In FISHBONE_ONLY mode we may not have severity. Hmm — the save endpoint 422s without severity_letter.

Options: 
- In FISHBONE_ONLY mode, still show the severity sliders? No — the spec says fishbone-only shows the interactive 6M diagram. But saving fishbone data needs to go somewhere. I can make the "Save Configuration" button in fishbone-only mode just call sramSave with severity defaults (all 0 → E)? That's ugly but consistent. Actually simpler: keep the severity section visible in all modes (it's part of SRM assessment anyway) but the bow-tie visualizer only in BOWTIE_SRAM/COMBINED. That way save always has severity. The spec says "If Fish-Bone selected: display the interactive 6M root-cause diagram." It doesn't say hide everything else. I'll show fishbone + severity always (severity is needed for the hazard register), and show bow-tie visualizer/barriers only in BowTie/Combined, and promotion only in Combined.

Actually to be faithful yet practical: 
- Fish-Bone RCA mode: fishbone editor + severity sliders + risk comparison + signoff + save (persists fishbone + severity). No bow-tie visualizer, no barriers.
- Bow-Tie SRAM: bow-tie visualizer + barriers + severity + risk + signoff, no fishbone/promotion.
- Combined: everything + promotion.

That's clean. Save always possible.

Let me write it.

For loading saved data: populate severityInputs from saved.severity (the input keys), barriers from saved.barriers, bowtie, fishbone, signoffs, mode.

For the fishbone editor data in workspace: use saved.fishbone (root_causes/action_items) or empty.

OK writing now. This will be long.

Now the core SRM frontend module



**Tool: write**

**Input:**
```json
{
  "content": "// ============================================================================\n// FILE: srm.js\n// PURPOSE: CAAN CAR-19 Safety Risk Management (SRM) Bow-Tie workspace for the\n//          hazard detail page and the CAN/CAP Combined RCA + SRAM workflow.\n//\n// Exposes `window.SRM` with:\n//   - Pure computation helpers mirroring backend/app/services/srm_engine.py\n//     (severity A-E, BQV/BSV, probability bands, tolerability + sign-off) for\n//     live client-side previews.\n//   - `createWorkspace(container, opts)` — full Analysis Model Selector +\n//     Bow-Tie workspace used on public/hazards/detail.html. Calls\n//     HazardsAPI.sramCalculate / sramSave for authoritative results.\n//   - `attachCombined(container, opts)` — Combined RCA + SRAM panel used on\n//     public/can_cap/cap_submit.html that promotes Fish-Bone root causes into\n//     Bow-Tie New Control Measures (NCM) and returns a `getSramData()` payload.\n// ============================================================================\n\nconst SRM = (() => {\n\n    // ── Constants (mirror backend/app/services/srm_engine.py) ──────────────\n    const SEVERITY_KEYS = [\n        { key: 'pax', label: 'Passenger (PAX) Safety', icon: 'fa-users' },\n        { key: 'worker', label: 'Worker / Staff Safety', icon: 'fa-hard-hat' },\n        { key: 'quality', label: 'Quality / Service', icon: 'fa-medal' },\n        { key: 'asset', label: 'Asset / Equipment', icon: 'fa-gears' },\n        { key: 'rep', label: 'Reputation / Trust', icon: 'fa-bullhorn' },\n        { key: 'sec', label: 'Security', icon: 'fa-shield-halved' },\n        { key: 'env', label: 'Environment', icon: 'fa-leaf' },\n    ];\n\n    const SEVERITY_BANDS = [\n        [52, 65, 'A', 'Catastrophic'],\n        [39, 51, 'B', 'Major'],\n        [26, 38, 'C', 'Moderate'],\n        [13, 25, 'D', 'Minor'],\n        [0, 12, 'E', 'Insignificant'],\n    ];\n\n    const BQV_KEYS = [\n        { key: 'effectiveness', label: 'Effectiveness', weight: 3 },\n        { key: 'cost_benefit', label: 'Cost-Benefit', weight: 1 },\n        { key: 'practicality', label: 'Practicality', weight: 1 },\n        { key: 'acceptability', label: 'Acceptability', weight: 1 },\n        { key: 'enforceability', label: 'Enforceability', weight: 1 },\n        { key: 'durability', label: 'Durability', weight: 1 },\n        { key: 'disinclination', label: 'Disinclination to Override', weight: 2 },\n    ];\n\n    const BQV_BANDS = [\n        [42, 50, 5, 'Excellent'],\n        [34, 41, 4, 'Very Good'],\n        [26, 33, 3, 'Good'],\n        [18, 25, 2, 'Fair'],\n        [10, 17, 1, 'Poor'],\n        [0, 9, 0, 'Ineffective'],\n    ];\n\n    const PROBABILITY_CONFIG = {\n        A: [8, 40, [[0, 7, 5], [8, 15, 4], [16, 23, 3], [24, 31, 2], [32, 40, 1]]],\n        B: [6, 30, [[0, 5, 5], [6, 11, 4], [12, 17, 3], [18, 23, 2], [24, 30, 1]]],\n        C: [4, 20, [[0, 3, 5], [4, 7, 4], [8, 11, 3], [12, 15, 2], [16, 20, 1]]],\n        D: [3, 15, [[0, 2, 5], [3, 5, 4], [6, 8, 3], [9, 11, 2], [12, 15, 1]]],\n        E: [2, 10, [[0, 1, 5], [2, 3, 4], [4, 5, 3], [6, 7, 2], [8, 10, 1]]],\n    };\n\n    const TOLERABILITY = {\n        '5A': 'Intolerable', '5B': 'Intolerable', '5C': 'Intolerable',\n        '5D': 'Tolerable', '5E': 'Tolerable',\n        '4A': 'Intolerable', '4B': 'Intolerable',\n        '4C': 'Tolerable', '4D': 'Tolerable', '4E': 'Tolerable',\n        '3A': 'Intolerable',\n        '3B': 'Tolerable', '3C': 'Tolerable', '3D': 'Tolerable', '3E': 'Acceptable',\n        '2A': 'Tolerable', '2B': 'Tolerable', '2C': 'Tolerable',\n        '2D': 'Acceptable', '2E': 'Acceptable',\n        '1A': 'Tolerable',\n        '1B': 'Acceptable', '1C': 'Acceptable', '1D': 'Acceptable', '1E': 'Acceptable',\n    };\n\n    const SIGNOFF_AUTHORITY = {\n        Intolerable: 'Accountable Manager',\n        Tolerable: 'Risk Owner / Functional Chief',\n        Acceptable: 'Safety Manager / SAG Member',\n    };\n\n    const LETTER_TO_NUMERIC = { A: 5, B: 4, C: 3, D: 2, E: 1 };\n\n    const FISHBONE_CATEGORIES = ['Man', 'Machine', 'Method', 'Medium', 'Management', 'Material'];\n\n    // ── Helpers ─────────────────────────────────────────────────────────────\n    function esc(v) {\n        if (v === null || v === undefined) return '';\n        return String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;')\n            .replace(/>/g, '&gt;').replace(/\"/g, '&quot;');\n    }\n\n    function uid(prefix) {\n        return (prefix || 'b') + '_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);\n    }\n\n    function defaultQuality() {\n        return {\n            effectiveness: 3, cost_benefit: 3, practicality: 3,\n            acceptability: 3, enforceability: 3, durability: 3, disinclination: 3,\n        };\n    }\n\n    function emptySeverityInputs() {\n        return { pax: 0, worker: 0, quality: 0, asset: 0, rep: 0, sec: 0, env: 0 };\n    }\n\n    // ── Computation (mirrors the backend engine) ────────────────────────────\n    function computeSeverity(inputs) {\n        inputs = inputs || emptySeverityInputs();\n        const score = 4 * (inputs.pax || 0) + 3 * (inputs.worker || 0)\n            + 2 * (inputs.quality || 0) + (inputs.asset || 0)\n            + (inputs.rep || 0) + (inputs.sec || 0) + (inputs.env || 0);\n        for (const [lo, hi, letter, desc] of SEVERITY_BANDS) {\n            if (score >= lo && score <= hi) return { total_score: score, severity_letter: letter, descriptor: desc };\n        }\n        return { total_score: score, severity_letter: 'E', descriptor: 'Insignificant' };\n    }\n\n    function computeBqv(q) {\n        q = q || defaultQuality();\n        const bqv = 3 * (q.effectiveness || 1) + (q.cost_benefit || 1)\n            + (q.practicality || 1) + (q.acceptability || 1)\n            + (q.enforceability || 1) + (q.durability || 1)\n            + 2 * (q.disinclination || 1);\n        for (const [lo, hi, bsv, robustness] of BQV_BANDS) {\n            if (bqv >= lo && bqv <= hi) return { bqv, bsv, robustness };\n        }\n        return { bqv, bsv: 0, robustness: 'Ineffective' };\n    }\n\n    function computeProbability(severityLetter, cbsv) {\n        const cfg = PROBABILITY_CONFIG[(severityLetter || 'E').toUpperCase()] || PROBABILITY_CONFIG.E;\n        const maxv = cfg[1];\n        const bands = cfg[2];\n        const value = Math.max(0, Math.min(cbsv || 0, maxv));\n        for (const [lo, hi, pv] of bands) {\n            if (value >= lo && value <= hi) return pv;\n        }\n        return 1;\n    }\n\n    function tolerability(probabilityValue, severityLetter) {\n        return TOLERABILITY[probabilityValue + severityLetter] || 'Acceptable';\n    }\n\n    function evaluateRiskProfile(severity, barriers) {\n        const lists = {\n            ecb: (barriers && barriers.ecb) || [],\n            erb: (barriers && barriers.erb) || [],\n            ncb: (barriers && barriers.ncb) || [],\n            nrb: (barriers && barriers.nrb) || [],\n        };\n        const sum = (arr) => arr.reduce((acc, b) => acc + (b.bsv || 0), 0);\n        const existingBsv = sum(lists.ecb) + sum(lists.erb);\n        const consolidatedBsv = existingBsv + sum(lists.ncb) + sum(lists.nrb);\n        const letter = (severity && severity.severity_letter) || 'E';\n        const initialP = computeProbability(letter, existingBsv);\n        const resultantP = computeProbability(letter, consolidatedBsv);\n        const initialTol = tolerability(initialP, letter);\n        const resultantTol = tolerability(resultantP, letter);\n        return {\n            existing_bsv: existingBsv,\n            consolidated_bsv: consolidatedBsv,\n            severity_letter: letter,\n            initial_risk: {\n                index: initialP + letter, probability_value: initialP,\n                descriptor: '', tolerability: initialTol,\n            },\n            resultant_risk: {\n                index: resultantP + letter, probability_value: resultantP,\n                descriptor: '', tolerability: resultantTol,\n            },\n            signoff: {\n                authority: SIGNOFF_AUTHORITY[resultantTol],\n                initial_authority: SIGNOFF_AUTHORITY[initialTol],\n                resultant_authority: SIGNOFF_AUTHORITY[resultantTol],\n            },\n        };\n    }\n\n    // ── Barrier Quality modal ───────────────────────────────────────────────\n    function openBarrierQualityModal(barrier, { onSave, title }) {\n        const overlay = document.createElement('div');\n        overlay.className = 'srm-modal-overlay';\n        const q = Object.assign(defaultQuality(), barrier.quality || {});\n\n        const sliderRows = BQV_KEYS.map(k => `\n            <div class=\"srm-slider-row\">\n                <span class=\"srm-slider-icon\"><i class=\"fas fa-sliders-h\"></i></span>\n                <span class=\"srm-slider-label\">${esc(k.label)} ${k.weight > 1 ? '×' + k.weight : ''}</span>\n                <input type=\"range\" min=\"1\" max=\"5\" step=\"1\" value=\"${q[k.key]}\" data-bqv-key=\"${k.key}\">\n                <span class=\"srm-slider-value\" data-bqv-val=\"${k.key}\">${q[k.key]}</span>\n            </div>`).join('');\n\n        overlay.innerHTML = `\n            <div class=\"srm-modal\" role=\"dialog\" aria-modal=\"true\">\n                <h3><i class=\"fas fa-shield-halved\"></i> ${esc(title || 'Barrier Quality Rating')}</h3>\n                <div class=\"srm-modal-sub\">${esc(barrier.name || '')}</div>\n                <div class=\"srm-bqv-badge\">\n                    <span>BQV</span>\n                    <span class=\"srm-bqv-value\" data-bqv-total>${computeBqv(q).bqv}</span>\n                    <span class=\"srm-bsv-chip\" data-bsv>${computeBqv(q).bsv}</span>\n                    <span class=\"srm-bsv-robustness\" data-robustness>${computeBqv(q).robustness}</span>\n                </div>\n                ${sliderRows}\n                <div class=\"srm-modal-actions\">\n                    <button type=\"button\" class=\"srm-btn srm-btn-outline\" data-bqv-cancel>Cancel</button>\n                    <button type=\"button\" class=\"srm-btn srm-btn-save\" data-bqv-ok>Apply Rating</button>\n                </div>\n            </div>`;\n\n        function refresh() {\n            const total = document.querySelector('[data-bqv-total]');\n            const chip = document.querySelector('[data-bsv]');\n            const rob = document.querySelector('[data-robustness]');\n            const res = computeBqv(q);\n            total.textContent = res.bqv;\n            chip.textContent = res.bsv;\n            rob.textContent = res.robustness;\n        }\n\n        overlay.querySelectorAll('[data-bqv-key]').forEach(slider => {\n            slider.addEventListener('input', () => {\n                const key = slider.dataset.bqvKey;\n                q[key] = parseInt(slider.value, 10);\n                overlay.querySelector(`[data-bqv-val=\"${key}\"]`).textContent = q[key];\n                refresh();\n            });\n        });\n        overlay.querySelector('[data-bqv-cancel]').addEventListener('click', () => overlay.remove());\n        overlay.querySelector('[data-bqv-ok]').addEventListener('click', () => {\n            const res = computeBqv(q);\n            barrier.quality = q;\n            barrier.bqv = res.bqv;\n            barrier.bsv = res.bsv;\n            barrier.robustness = res.robustness;\n            overlay.remove();\n            if (typeof onSave === 'function') onSave();\n        });\n        overlay.addEventListener('click', (ev) => {\n            if (ev.target === overlay) overlay.remove();\n        });\n        document.body.appendChild(overlay);\n    }\n\n    // ── Barrier pill rendering ──────────────────────────────────────────────\n    function barrierPillHtml(barrier, cls) {\n        const bsv = barrier.bsv != null ? barrier.bsv : 0;\n        const name = barrier.name || '(unnamed)';\n        const robNote = barrier.robustness ? ` · ${esc(barrier.robustness)}` : '';\n        return `\n            <div class=\"srm-barrier-pill ${cls}\" data-barrier-id=\"${esc(barrier.id || '')}\">\n                <span class=\"srm-pill-name\" title=\"${esc(name)}${robNote}\">${esc(name)}</span>\n                <span class=\"srm-bsv-badge\" title=\"Barrier Score Value (BSV)\">BSV ${bsv}</span>\n                <button type=\"button\" class=\"srm-pill-remove\" title=\"Remove barrier\" data-pill-remove><i class=\"fas fa-times\"></i></button>\n            </div>`;\n    }\n\n    function bindBarrierPills(listEl, barriers, cls, ctx) {\n        listEl.querySelectorAll('[data-barrier-id]').forEach(pill => {\n            const id = pill.dataset.barrierId;\n            const barrier = barriers.find(b => b.id === id);\n            pill.addEventListener('click', (ev) => {\n                if (ev.target.closest('[data-pill-remove]')) return;\n                if (!barrier) return;\n                openBarrierQualityModal(barrier, {\n                    title: (cls === 'srm-erb' ? 'Existing Recovery Barrier' : cls === 'srm-ncb' ? 'New Control Measure' : cls === 'srm-nrb' ? 'New Recovery Barrier' : 'Existing Control Measure') + ' Quality',\n                    onSave: () => { ctx.renderBarriers(); ctx.updateLive(); },\n                });\n            });\n            const rm = pill.querySelector('[data-pill-remove]');\n            if (rm) rm.addEventListener('click', (ev) => {\n                ev.stopPropagation();\n                const idx = barriers.findIndex(b => b.id === id);\n                if (idx >= 0) barriers.splice(idx, 1);\n                ctx.renderBarriers();\n                ctx.updateLive();\n            });\n        });\n    }\n\n    // ── SrmWorkspace (hazard detail page) ───────────────────────────────────\n    class SrmWorkspace {\n        constructor(container, opts) {\n            opts = opts || {};\n            this.el = typeof container === 'string' ? document.getElementById(container) : container;\n            if (!this.el) throw new Error('[SRM] container not found');\n            this.hazardId = opts.hazardId;\n            this.saved = opts.saved || null;\n            this.mode = (opts.mode || 'FISHBONE_ONLY');\n            this.onSaved = opts.onSaved || null;\n\n            this.severityInputs = emptySeverityInputs();\n            this.barriers = { ecb: [], erb: [], ncb: [], nrb: [] };\n            this.bowtie = { threats: [], top_event: '', consequences: [] };\n            this.fishbone = { root_causes: [], action_items: [] };\n            this.signoffs = { name: '', role: '', date: '' };\n            this.riskProfile = null;\n            this.fishboneController = null;\n            this.savedSeverityLetter = null;\n\n            this._loadSaved();\n            this.render();\n        }\n\n        _loadSaved() {\n            if (!this.saved) return;\n            const s = this.saved;\n            if (s.severity && typeof s.severity === 'object') {\n                SEVERITY_KEYS.forEach(k => {\n                    if (s.severity[k.key] != null) this.severityInputs[k.key] = s.severity[k.key];\n                });\n                if (s.severity.severity_letter) this.savedSeverityLetter = s.severity.severity_letter;\n            }\n            if (s.barriers) {\n                this.barriers = {\n                    ecb: (s.barriers.ecb || []).map(b => Object.assign({}, b)),\n                    erb: (s.barriers.erb || []).map(b => Object.assign({}, b)),\n                    ncb: (s.barriers.ncb || []).map(b => Object.assign({}, b)),\n                    nrb: (s.barriers.nrb || []).map(b => Object.assign({}, b)),\n                };\n            }\n            if (s.bowtie) this.bowtie = Object.assign(this.bowtie, s.bowtie);\n            if (s.fishbone) this.fishbone = s.fishbone;\n            if (s.signoffs) this.signoffs = Object.assign(this.signoffs, s.signoffs);\n            if (s.risk_profile) this.riskProfile = s.risk_profile;\n        }\n\n        render() {\n            this.el.innerHTML = `\n                <div class=\"srm-workspace\">\n                    <div class=\"srm-mode-selector\">\n                        <span class=\"srm-mode-title\"><i class=\"fas fa-arrows-left-right\"></i> Analysis Model Selector</span>\n                        <label data-mode=\"FISHBONE_ONLY\"><input type=\"radio\" name=\"srm_mode\" value=\"FISHBONE_ONLY\"> Fish-Bone RCA</label>\n                        <label data-mode=\"BOWTIE_SRAM\"><input type=\"radio\" name=\"srm_mode\" value=\"BOWTIE_SRAM\"> Bow-Tie SRAM</label>\n                        <label data-mode=\"COMBINED\"><input type=\"radio\" name=\"srm_mode\" value=\"COMBINED\"> Combined RCA + SRAM</label>\n                    </div>\n\n                    <div class=\"srm-section\" data-srm-part=\"fishbone\">\n                        <h3><i class=\"fas fa-diagnoses\"></i> 6M Root-Cause Diagram — Interactive Fish-Bone (Ishikawa)</h3>\n                        <div id=\"srmFishboneEditor_${uid('fb')}\" data-srm-fishbone></div>\n                        <div class=\"srm-promotion\" data-srm-promotion style=\"display:none;margin-top:0.7rem;\">\n                            <div class=\"srm-promotion-head\"><i class=\"fas fa-arrow-up\"></i> Promote Root Causes to Bow-Tie New Control Measures (NCM)</div>\n                            <div data-srm-promotion-list></div>\n                            <div class=\"srm-promoted-note\">In Combined mode, root causes you promote become New Control Measures in the Bow-Tie, lowering the resultant risk.</div>\n                        </div>\n                    </div>\n\n                    <div class=\"srm-section\" data-srm-part=\"severity\">\n                        <h3><i class=\"fas fa-balance-scale\"></i> 7-Impact Severity Assessment (0-5 per impact)</h3>\n                        <div class=\"srm-severity-grid\">${this._severityRows()}</div>\n                        <div class=\"srm-score-badge\">\n                            <span>Weighted Score</span>\n                            <span class=\"srm-score-value\" data-srm-score>0</span>\n                            <span class=\"srm-severity-letter\" data-srm-letter>E</span>\n                            <span class=\"srm-severity-desc\" data-srm-desc>Insignificant</span>\n                        </div>\n                    </div>\n\n                    <div class=\"srm-section\" data-srm-part=\"bowtie\" style=\"display:none;\">\n                        <h3><i class=\"fas fa-bow-arrow\"></i> Interactive Bow-Tie</h3>\n                        <div class=\"srm-bowtie\">\n                            <div class=\"srm-col\">\n                                <div class=\"srm-col-head\">Threats</div>\n                                <div data-srm-threats></div>\n                                <button type=\"button\" class=\"srm-add-btn\" data-srm-add-threat><i class=\"fas fa-plus\"></i> Add Threat</button>\n                            </div>\n                            <div class=\"srm-col\">\n                                <div class=\"srm-col-head\">Existing Control Measures (ECM)</div>\n                                <div data-srm-ecm></div>\n                                <button type=\"button\" class=\"srm-add-btn\" data-srm-add-ecm><i class=\"fas fa-plus\"></i> Add ECM</button>\n                            </div>\n                            <div class=\"srm-top-event\">\n                                <span>TOP EVENT</span>\n                                <input type=\"text\" placeholder=\"e.g. Wheel jack sinks into apron\" data-srm-top-event>\n                            </div>\n                            <div class=\"srm-col\">\n                                <div class=\"srm-col-head\">Existing Recovery Barriers (ERB)</div>\n                                <div data-srm-erb></div>\n                                <button type=\"button\" class=\"srm-add-btn\" data-srm-add-erb><i class=\"fas fa-plus\"></i> Add ERB</button>\n                            </div>\n                            <div class=\"srm-col\">\n                                <div class=\"srm-col-head\">Consequences</div>\n                                <div data-srm-consequences></div>\n                                <button type=\"button\" class=\"srm-add-btn\" data-srm-add-consequence><i class=\"fas fa-plus\"></i> Add Consequence</button>\n                            </div>\n                        </div>\n                        <div class=\"srm-new-barriers\" style=\"margin-top:0.7rem;\">\n                            <div class=\"srm-col\">\n                                <div class=\"srm-col-head\">New Control Measures (NCM)</div>\n                                <div data-srm-ncb></div>\n                                <button type=\"button\" class=\"srm-add-btn\" data-srm-add-ncb><i class=\"fas fa-plus\"></i> Add NCM</button>\n                            </div>\n                            <div class=\"srm-col\">\n                                <div class=\"srm-col-head\">New Recovery Barriers (NRB)</div>\n                                <div data-srm-nrb></div>\n                                <button type=\"button\" class=\"srm-add-btn\" data-srm-add-nrb2><i class=\"fas fa-plus\"></i> Add NRB</button>\n                            </div>\n                        </div>\n                    </div>\n\n                    <div class=\"srm-section\">\n                        <h3><i class=\"fas fa-th-large\"></i> Before &amp; After Risk Matrix Comparison</h3>\n                        <div class=\"srm-risk-comparison\">\n                            <div class=\"srm-risk-box\">\n                                <div class=\"srm-risk-label\">Current Risk Index</div>\n                                <div class=\"srm-risk-index\" data-srm-initial-index>—</div>\n                                <div class=\"srm-risk-tol\" data-srm-initial-tol>—</div>\n                                <div class=\"srm-bsv-summary\" data-srm-initial-bsv></div>\n                            </div>\n                            <div class=\"srm-risk-arrow\"><i class=\"fas fa-arrow-right\"></i></div>\n                            <div class=\"srm-risk-box\">\n                                <div class=\"srm-risk-label\">Resultant Risk Index</div>\n                                <div class=\"srm-risk-index\" data-srm-resultant-index>—</div>\n                                <div class=\"srm-risk-tol\" data-srm-resultant-tol>—</div>\n                                <div class=\"srm-bsv-summary\" data-srm-resultant-bsv></div>\n                            </div>\n                        </div>\n                    </div>\n\n                    <div class=\"srm-section\">\n                        <h3><i class=\"fas fa-file-signature\"></i> Digital Postholder Sign-Off</h3>\n                        <div class=\"srm-signoff\">\n                            <span class=\"srm-authority-badge\" data-srm-authority><i class=\"fas fa-user-shield\"></i> Required: —</span>\n                            <div class=\"srm-signoff-grid\">\n                                <div><label>Postholder Name</label><input type=\"text\" data-srm-sign-name placeholder=\"Full name\"></div>\n                                <div><label>Postholder Role</label><input type=\"text\" data-srm-sign-role placeholder=\"e.g. Safety Manager\"></div>\n                                <div><label>Date</label><input type=\"date\" data-srm-sign-date></div>\n                            </div>\n                        </div>\n                    </div>\n\n                    <div class=\"srm-actions\">\n                        <button type=\"button\" class=\"srm-btn srm-btn-calc\" data-srm-calc><i class=\"fas fa-calculator\"></i> Calculate (Preview)</button>\n                        <button type=\"button\" class=\"srm-btn srm-btn-save\" data-srm-save><i class=\"fas fa-save\"></i> Save Configuration</button>\n                        <span class=\"srm-status\" data-srm-status></span>\n                    </div>\n                </div>`;\n\n            this._initFishbone();\n            this._bindEvents();\n            this._applyMode(this.mode);\n            this.renderBarriers();\n            this.renderBowtie();\n            this.updateLive();\n        }\n\n        _severityRows() {\n            return SEVERITY_KEYS.map(k => `\n                <div class=\"srm-slider-row\">\n                    <span class=\"srm-slider-icon\"><i class=\"fas ${k.icon}\"></i></span>\n                    <span class=\"srm-slider-label\">${esc(k.label)}</span>\n                    <input type=\"range\" min=\"0\" max=\"5\" step=\"1\" value=\"${this.severityInputs[k.key] || 0}\" data-sev=\"${k.key}\">\n                    <span class=\"srm-slider-value\" data-sev-val=\"${k.key}\">${this.severityInputs[k.key] || 0}</span>\n                </div>`).join('');\n        }\n\n        _initFishbone() {\n            const holder = this.el.querySelector('[data-srm-fishbone]');\n            if (holder && typeof Fishbone !== 'undefined' && Fishbone.renderEditor) {\n                try {\n                    this.fishboneController = Fishbone.renderEditor(holder, {\n                        data: this.fishbone,\n                        onChange: () => {\n                            this.fishbone = this.fishboneController.getData();\n                            this.renderPromotion();\n                        },\n                    });\n                } catch (err) {\n                    holder.innerHTML = '<div class=\"fishbone-empty\">Fishbone editor unavailable.</div>';\n                }\n            } else if (holder) {\n                holder.innerHTML = '<div class=\"fishbone-empty\">Fishbone editor script not loaded.</div>';\n            }\n        }\n\n        _bindEvents() {\n            // Mode selector.\n            this.el.querySelectorAll('[data-mode] input').forEach(radio => {\n                radio.addEventListener('change', () => {\n                    if (radio.checked) this._applyMode(radio.value);\n                });\n            });\n\n            // Severity sliders.\n            this.el.querySelectorAll('[data-sev]').forEach(slider => {\n                slider.addEventListener('input', () => {\n                    const key = slider.dataset.sev;\n                    const val = parseInt(slider.value, 10);\n                    this.severityInputs[key] = val;\n                    this.el.querySelector(`[data-sev-val=\"${key}\"]`).textContent = val;\n                    this.updateLive();\n                });\n            });\n\n            // Bow-tie add buttons.\n            this.el.querySelector('[data-srm-add-threat]').addEventListener('click', () => this._addBowtieItem('threats'));\n            this.el.querySelector('[data-srm-add-consequence]').addEventListener('click', () => this._addBowtieItem('consequences'));\n            this.el.querySelector('[data-srm-add-ecm]').addEventListener('click', () => this._addBarrier('ecb', 'srm-ecm'));\n            this.el.querySelector('[data-srm-add-erb]').addEventListener('click', () => this._addBarrier('erb', 'srm-erb'));\n            this.el.querySelector('[data-srm-add-ncb]').addEventListener('click', () => this._addBarrier('ncb', 'srm-ncb'));\n            this.el.querySelector('[data-srm-add-nrb2]').addEventListener('click', () => this._addBarrier('nrb', 'srm-nrb'));\n\n            const topEventInput = this.el.querySelector('[data-srm-top-event]');\n            topEventInput.value = this.bowtie.top_event || '';\n            topEventInput.addEventListener('input', () => { this.bowtie.top_event = topEventInput.value; });\n\n            // Sign-off.\n            const nameIn = this.el.querySelector('[data-srm-sign-name]');\n            const roleIn = this.el.querySelector('[data-srm-sign-role]');\n            const dateIn = this.el.querySelector('[data-srm-sign-date]');\n            nameIn.value = this.signoffs.name || '';\n            roleIn.value = this.signoffs.role || '';\n            dateIn.value = this.signoffs.date || '';\n            nameIn.addEventListener('input', () => { this.signoffs.name = nameIn.value; });\n            roleIn.addEventListener('input', () => { this.signoffs.role = roleIn.value; });\n            dateIn.addEventListener('change', () => { this.signoffs.date = dateIn.value; });\n\n            // Actions.\n            this.el.querySelector('[data-srm-calc]').addEventListener('click', () => this.calculate());\n            this.el.querySelector('[data-srm-save]').addEventListener('click', () => this.save());\n        }\n\n        _applyMode(mode) {\n            this.mode = mode;\n            this.el.querySelectorAll('[data-mode]').forEach(label => {\n                const active = label.dataset.mode === mode;\n                label.classList.toggle('srm-mode-active', active);\n                const radio = label.querySelector('input');\n                if (active) radio.checked = true;\n            });\n\n            const fishbonePart = this.el.querySelector('[data-srm-part=\"fishbone\"]');\n            const bowtiePart = this.el.querySelector('[data-srm-part=\"bowtie\"]');\n            const promotion = this.el.querySelector('[data-srm-promotion]');\n\n            fishbonePart.style.display = (mode === 'FISHBONE_ONLY' || mode === 'COMBINED') ? 'block' : 'none';\n            bowtiePart.style.display = (mode === 'BOWTIE_SRAM' || mode === 'COMBINED') ? 'block' : 'none';\n            promotion.style.display = mode === 'COMBINED' ? 'block' : 'none';\n            if (mode === 'COMBINED') this.renderPromotion();\n        }\n\n        renderPromotion() {\n            const list = this.el.querySelector('[data-srm-promotion-list]');\n            if (!list) return;\n            const causes = (this.fishbone && this.fishbone.root_causes) || [];\n            const promotedIds = (this.barriers.ncb || [])\n                .map(b => b.source_root_cause_id).filter(Boolean);\n\n            if (!causes.length) {\n                list.innerHTML = '<div class=\"srm-promoted-note\">Add root causes above, then promote them here as New Control Measures.</div>';\n                return;\n            }\n\n            list.innerHTML = causes.map(c => {\n                const promoted = promotedIds.indexOf(c.id) >= 0;\n                return `\n                    <div class=\"srm-promote-row\">\n                        <span class=\"srm-promote-text\"><strong>${esc(c.category)}</strong> — ${esc(c.description || '')}</span>\n                        ${promoted\n                            ? '<span class=\"srm-promoted-note\"><i class=\"fas fa-check-circle\"></i> Promoted to NCM</span>'\n                            : `<button type=\"button\" class=\"srm-promote-btn\" data-promote=\"${esc(c.id)}\"><i class=\"fas fa-arrow-up\"></i> Promote to NCM</button>`}\n                    </div>`;\n            }).join('');\n\n            list.querySelectorAll('[data-promote]').forEach(btn => {\n                btn.addEventListener('click', () => {\n                    const cause = causes.find(c => c.id === btn.dataset.promote);\n                    if (!cause) return;\n                    const barrier = {\n                        id: uid('ncm'),\n                        name: (cause.description || '').trim() || `${cause.category} root cause`,\n                        description: cause.description,\n                        category: cause.category,\n                        source_root_cause_id: cause.id,\n                        quality: defaultQuality(),\n                    };\n                    const res = computeBqv(barrier.quality);\n                    barrier.bqv = res.bqv;\n                    barrier.bsv = res.bsv;\n                    barrier.robustness = res.robustness;\n                    this.barriers.ncb.push(barrier);\n                    this.renderBarriers();\n                    this.renderPromotion();\n                    this.updateLive();\n                });\n            });\n        }\n\n        _addBowtieItem(kind) {\n            this.bowtie[kind].push({ id: uid('bt'), label: '', barrier_ids: [] });\n            this.renderBowtie();\n        }\n\n        renderBowtie() {\n            const threatsEl = this.el.querySelector('[data-srm-threats]');\n            const consEl = this.el.querySelector('[data-srm-consequences]');\n            if (!threatsEl || !consEl) return;\n\n            const ecm = this.barriers.ecb;\n            const erb = this.barriers.erb;\n\n            const renderItem = (item, placeholder, ecmOpts) => `\n                <div class=\"srm-card srm-threat\">\n                    <input type=\"text\" value=\"${esc(item.label || '')}\" placeholder=\"${placeholder}\" data-bt-label=\"${esc(item.id)}\">\n                    <select data-bt-ecm=\"${esc(item.id)}\">\n                        <option value=\"\">— link ECM barrier —</option>\n                        ${(ecmOpts || []).map(b => `<option value=\"${esc(b.id)}\" ${(item.barrier_ids || []).indexOf(b.id) >= 0 ? 'selected' : ''}>${esc(b.name || 'ECM')}</option>`).join('')}\n                    </select>\n                    <button type=\"button\" class=\"srm-pill-remove\" title=\"Remove\" data-bt-remove=\"${esc(item.id)}\"><i class=\"fas fa-times\"></i></button>\n                </div>`;\n\n            threatsEl.innerHTML = (this.bowtie.threats || []).map(t => renderItem(t, 'e.g. Unsafe apron surface', ecm)).join('')\n                || '<div class=\"srm-hint\">Add a threat to build the left side of the Bow-Tie.</div>';\n            consEl.innerHTML = (this.bowtie.consequences || []).map(c => `\n                <div class=\"srm-card srm-consequence\">\n                    <input type=\"text\" value=\"${esc(c.label || '')}\" placeholder=\"e.g. Aircraft/crew injury\" data-bt-label=\"${esc(c.id)}\">\n                    <select data-bt-erb=\"${esc(c.id)}\">\n                        <option value=\"\">— link ERB barrier —</option>\n                        ${(erb || []).map(b => `<option value=\"${esc(b.id)}\" ${(c.barrier_ids || []).indexOf(b.id) >= 0 ? 'selected' : ''}>${esc(b.name || 'ERB')}</option>`).join('')}\n                    </select>\n                    <button type=\"button\" class=\"srm-pill-remove\" title=\"Remove\" data-bt-remove=\"${esc(c.id)}\"><i class=\"fas fa-times\"></i></button>\n                </div>`).join('')\n                || '<div class=\"srm-hint\">Add a consequence to build the right side of the Bow-Tie.</div>';\n\n            threatsEl.querySelectorAll('[data-bt-label]').forEach(inp => {\n                inp.addEventListener('input', () => {\n                    const item = this.bowtie.threats.find(t => t.id === inp.dataset.btLabel);\n                    if (item) item.label = inp.value;\n                });\n            });\n            threatsEl.querySelectorAll('[data-bt-ecm]').forEach(sel => {\n                sel.addEventListener('change', () => {\n                    const item = this.bowtie.threats.find(t => t.id === sel.dataset.btEcm);\n                    if (item) item.barrier_ids = sel.value ? [sel.value] : [];\n                });\n            });\n            consEl.querySelectorAll('[data-bt-label]').forEach(inp => {\n                inp.addEventListener('input', () => {\n                    const item = this.bowtie.consequences.find(c => c.id === inp.dataset.btLabel);\n                    if (item) item.label = inp.value;\n                });\n            });\n            consEl.querySelectorAll('[data-bt-erb]').forEach(sel => {\n                sel.addEventListener('change', () => {\n                    const item = this.bowtie.consequences.find(c => c.id === sel.dataset.btErb);\n                    if (item) item.barrier_ids = sel.value ? [sel.value] : [];\n                });\n            });\n            threatsEl.querySelectorAll('[data-bt-remove]').forEach(btn => {\n                btn.addEventListener('click', () => {\n                    this.bowtie.threats = this.bowtie.threats.filter(t => t.id !== btn.dataset.btRemove);\n                    this.renderBowtie();\n                });\n            });\n            consEl.querySelectorAll('[data-bt-remove]').forEach(btn => {\n                btn.addEventListener('click', () => {\n                    this.bowtie.consequences = this.bowtie.consequences.filter(c => c.id !== btn.dataset.btRemove);\n                    this.renderBowtie();\n                });\n            });\n        }\n\n        _addBarrier(listKey, cls) {\n            const barrier = { id: uid('b'), name: '', quality: defaultQuality() };\n            const res = computeBqv(barrier.quality);\n            barrier.bqv = res.bqv;\n            barrier.bsv = res.bsv;\n            barrier.robustness = res.robustness;\n            this.barriers[listKey].push(barrier);\n            this.renderBarriers();\n            this.updateLive();\n        }\n\n        renderBarriers() {\n            const map = {\n                ecb: ['[data-srm-ecm]', 'srm-ecm'],\n                erb: ['[data-srm-erb]', 'srm-erb'],\n                ncb: ['[data-srm-ncb]', 'srm-ncb'],\n                nrb: ['[data-srm-nrb]', 'srm-nrb'],\n            };\n            Object.keys(map).forEach(key => {\n                const [sel, cls] = map[key];\n                const listEl = this.el.querySelector(sel);\n                if (!listEl) return;\n                const barriers = this.barriers[key];\n                listEl.innerHTML = barriers.length\n                    ? barriers.map(b => barrierPillHtml(b, cls)).join('')\n                    : '<div class=\"srm-hint\">No barriers added.</div>';\n                bindBarrierPills(listEl, barriers, cls, this);\n            });\n        }\n\n        updateLive() {\n            const severity = computeSeverity(this.severityInputs);\n            this.el.querySelector('[data-srm-score]').textContent = severity.total_score;\n            this.el.querySelector('[data-srm-letter]').textContent = severity.severity_letter;\n            this.el.querySelector('[data-srm-desc]').textContent = severity.descriptor;\n\n            const profile = evaluateRiskProfile(severity, this.barriers);\n            this.riskProfile = profile;\n            this._renderComparison(profile);\n\n            const authority = profile.signoff.authority;\n            const badge = this.el.querySelector('[data-srm-authority]');\n            badge.innerHTML = `<i class=\"fas fa-user-shield\"></i> Required: ${esc(authority)}`;\n\n            const tol = profile.resultant_risk.tolerability;\n            badge.style.background = tol === 'Intolerable' ? '#7f1d1d' : tol === 'Tolerable' ? '#b45309' : '#14532d';\n        }\n\n        _renderComparison(profile) {\n            const setIndex = (sel, risk) => {\n                const idx = this.el.querySelector(sel + '-index');\n                const tol = this.el.querySelector(sel + '-tol');\n                const bsv = this.el.querySelector(sel + '-bsv');\n                idx.textContent = risk.index;\n                tol.textContent = risk.tolerability;\n                tol.className = 'srm-risk-tol ' + (risk.tolerability === 'Intolerable' ? 'srm-tol-intolerable' : risk.tolerability === 'Tolerable' ? 'srm-tol-tolerable' : 'srm-tol-acceptable');\n                bsv.textContent = '';\n            };\n            setIndex('[data-srm-initial]', profile.initial_risk);\n            setIndex('[data-srm-resultant]', profile.resultant_risk);\n            this.el.querySelector('[data-srm-initial-bsv]').textContent =\n                `Existing BSV ${profile.existing_bsv}`;\n            this.el.querySelector('[data-srm-resultant-bsv]').textContent =\n                `Consolidated BSV ${profile.consolidated_bsv}`;\n        }\n\n        _buildCalculatePayload() {\n            const barriers = {};\n            Object.keys(this.barriers).forEach(key => {\n                barriers[key] = this.barriers[key].map(b => ({\n                    id: b.id,\n                    name: b.name,\n                    description: b.description,\n                    category: b.category,\n                    source_root_cause_id: b.source_root_cause_id,\n                    quality: b.quality,\n                    bqv: b.bqv,\n                    bsv: b.bsv,\n                }));\n            });\n            return {\n                severity: Object.assign({}, this.severityInputs),\n                barriers,\n                bowtie: this.bowtie,\n            };\n        }\n\n        async calculate() {\n            if (!this.hazardId) { this._status('Hazard not loaded.', 'srm-err'); return; }\n            const btn = this.el.querySelector('[data-srm-calc]');\n            btn.disabled = true;\n            try {\n                const result = await HazardsAPI.sramCalculate(this.hazardId, this._buildCalculatePayload());\n                this.riskProfile = result.risk_profile;\n                this._renderComparison(result.risk_profile);\n                const authority = result.risk_profile.signoff.authority;\n                this.el.querySelector('[data-srm-authority]').innerHTML =\n                    `<i class=\"fas fa-user-shield\"></i> Required: ${esc(authority)}`;\n                // Adopt authoritative barrier scores.\n                if (result.barriers) {\n                    ['ecb', 'erb', 'ncb', 'nrb'].forEach(key => {\n                        if (Array.isArray(result.barriers[key])) {\n                            result.barriers[key].forEach(rb => {\n                                const local = this.barriers[key].find(b => b.id === rb.id);\n                                if (local) { local.bsv = rb.bsv; local.bqv = rb.bqv; local.robustness = rb.robustness; }\n                            });\n                        }\n                    });\n                    this.renderBarriers();\n                }\n                this._status(`Calculated: ${result.risk_profile.initial_risk.index} → ${result.risk_profile.resultant_risk.index} (${result.risk_profile.resultant_risk.tolerability})`, 'srm-ok');\n            } catch (err) {\n                this._status('Calculate failed: ' + err.message, 'srm-err');\n            } finally {\n                btn.disabled = false;\n            }\n        }\n\n        _buildSavePayload() {\n            const severity = Object.assign({}, this.severityInputs, computeSeverity(this.severityInputs));\n            const barriers = {};\n            Object.keys(this.barriers).forEach(key => {\n                barriers[key] = this.barriers[key].map(b => ({\n                    id: b.id,\n                    name: b.name,\n                    description: b.description,\n                    category: b.category,\n                    source_root_cause_id: b.source_root_cause_id,\n                    quality: b.quality,\n                    bqv: b.bqv,\n                    bsv: b.bsv,\n                    robustness: b.robustness,\n                }));\n            });\n            const profile = this.riskProfile || evaluateRiskProfile(severity, this.barriers);\n            const authority = profile.signoff.authority;\n            const signoffs = {\n                name: this.signoffs.name || null,\n                role: this.signoffs.role || null,\n                date: this.signoffs.date || null,\n                authority,\n            };\n            return {\n                analysis_mode: this.mode,\n                sram_data: {\n                    severity,\n                    barriers,\n                    risk_profile: profile,\n                    bowtie: this.bowtie,\n                    fishbone: this.fishbone || null,\n                    signoffs,\n                },\n            };\n        }\n\n        async save() {\n            if (!this.hazardId) { this._status('Hazard not loaded.', 'srm-err'); return; }\n            const btn = this.el.querySelector('[data-srm-save]');\n            btn.disabled = true;\n            try {\n                const result = await HazardsAPI.sramSave(this.hazardId, this._buildSavePayload());\n                this._status(`Saved: resultant risk ${result.sram_data.risk_profile.resultant_risk.index} (${result.sram_data.risk_profile.resultant_risk.tolerability})`, 'srm-ok');\n                if (typeof this.onSaved === 'function') this.onSaved(result);\n            } catch (err) {\n                this._status('Save failed: ' + err.message, 'srm-err');\n            } finally {\n                btn.disabled = false;\n            }\n        }\n\n        _status(msg, cls) {\n            const el = this.el.querySelector('[data-srm-status]');\n            if (!el) return;\n            el.textContent = msg;\n            el.className = 'srm-status ' + (cls || 'srm-ok');\n            window.setTimeout(() => { el.className = 'srm-status'; }, 6000);\n        }\n    }\n\n    // ── Combined RCA + SRAM panel (CAN/CAP page) ────────────────────────────\n    function attachCombined(container, opts) {\n        const el = typeof container === 'string' ? document.getElementById(container) : container;\n        if (!el) throw new Error('[SRM] container not found: ' + container);\n        opts = opts || {};\n\n        const fishboneController = opts.fishboneController || null;\n        const initialSeverityLetter = opts.severityLetter || null;\n\n        const state = {\n            mode: 'COMBINED',\n            severityLetter: initialSeverityLetter || 'E',\n            ncm: (opts.saved && opts.saved.barriers && opts.saved.barriers.ncb) || [],\n            signoffs: Object.assign({ name: '', role: '', date: '' }, (opts.saved && opts.saved.signoffs) || {}),\n        };\n\n        function promoteCauses() {\n            const list = el.querySelector('[data-srm-promotion-list]');\n            if (!list) return;\n            let causes = [];\n            if (fishboneController && typeof fishboneController.getData === 'function') {\n                causes = fishboneController.getData().root_causes || [];\n            }\n            const promotedIds = state.ncm.map(b => b.source_root_cause_id).filter(Boolean);\n            if (!causes.length) {\n                list.innerHTML = '<div class=\"srm-promoted-note\">Root causes added above appear here for promotion to NCM.</div>';\n                return;\n            }\n            list.innerHTML = causes.map(c => {\n                const promoted = promotedIds.indexOf(c.id) >= 0;\n                return `\n                    <div class=\"srm-promote-row\">\n                        <span class=\"srm-promote-text\"><strong>${esc(c.category)}</strong> — ${esc(c.description || '')}</span>\n                        ${promoted\n                            ? '<span class=\"srm-promoted-note\"><i class=\"fas fa-check-circle\"></i> Promoted to NCM</span>'\n                            : `<button type=\"button\" class=\"srm-promote-btn\" data-promote=\"${esc(c.id)}\"><i class=\"fas fa-arrow-up\"></i> Promote to NCM</button>`}\n                    </div>`;\n            }).join('');\n            list.querySelectorAll('[data-promote]').forEach(btn => {\n                btn.addEventListener('click', () => {\n                    const cause = causes.find(c => c.id === btn.dataset.promote);\n                    if (!cause) return;\n                    const barrier = {\n                        id: uid('ncm'), name: (cause.description || '').trim() || `${cause.category} root cause`,\n                        description: cause.description, category: cause.category,\n                        source_root_cause_id: cause.id, quality: defaultQuality(),\n                    };\n                    const res = computeBqv(barrier.quality);\n                    barrier.bqv = res.bqv; barrier.bsv = res.bsv; barrier.robustness = res.robustness;\n                    state.ncm.push(barrier);\n                    renderNcm();\n                    promoteCauses();\n                    update();\n                });\n            });\n        }\n\n        function renderNcm() {\n            const list = el.querySelector('[data-srm-ncm-list]');\n            if (!list) return;\n            if (!state.ncm.length) {\n                list.innerHTML = '<div class=\"srm-hint\">No New Control Measures promoted yet.</div>';\n                return;\n            }\n            list.innerHTML = state.ncm.map(b => barrierPillHtml(b, 'srm-ncb')).join('');\n            bindBarrierPills(list, state.ncm, 'srm-ncb', {\n                renderBarriers: renderNcm,\n                updateLive: update,\n            });\n        }\n\n        function update() {\n            const severity = { severity_letter: state.severityLetter, descriptor: '' };\n            const profile = evaluateRiskProfile(severity, { ecb: [], erb: [], ncb: state.ncm, nrb: [] });\n\n            el.querySelector('[data-srm-initial-index]').textContent = profile.initial_risk.index;\n            el.querySelector('[data-srm-initial-tol]').textContent = profile.initial_risk.tolerability;\n            el.querySelector('[data-srm-resultant-index]').textContent = profile.resultant_risk.index;\n            el.querySelector('[data-srm-resultant-tol]').textContent = profile.resultant_risk.tolerability;\n            el.querySelector('[data-srm-resultant-bsv]').textContent = `NCM BSV ${profile.consolidated_bsv}`;\n            el.querySelector('[data-srm-authority]').innerHTML =\n                `<i class=\"fas fa-user-shield\"></i> Required: ${esc(profile.signoff.authority)}`;\n        }\n\n        el.innerHTML = `\n            <div class=\"srm-workspace\">\n                <div class=\"srm-mode-selector\">\n                    <span class=\"srm-mode-title\"><i class=\"fas fa-arrows-left-right\"></i> Analysis Model Selector</span>\n                    <label data-mode=\"FISHBONE_ONLY\"><input type=\"radio\" name=\"cap_srm_mode\" value=\"FISHBONE_ONLY\"> Fish-Bone RCA</label>\n                    <label data-mode=\"BOWTIE_SRAM\"><input type=\"radio\" name=\"cap_srm_mode\" value=\"BOWTIE_SRAM\"> Bow-Tie SRAM</label>\n                    <label data-mode=\"COMBINED\"><input type=\"radio\" name=\"cap_srm_mode\" value=\"COMBINED\" checked> Combined RCA + SRAM</label>\n                </div>\n\n                <div class=\"srm-section\" data-cap-part=\"bowtie\">\n                    <h3><i class=\"fas fa-bow-arrow\"></i> Bow-Tie SRAM — New Control Measures from Root Causes</h3>\n                    <div class=\"srm-promotion\">\n                        <div class=\"srm-promotion-head\"><i class=\"fas fa-arrow-up\"></i> Promote Fish-Bone Root Causes to New Control Measures (NCM)</div>\n                        <div data-srm-promotion-list></div>\n                    </div>\n                    <div style=\"margin-top:0.7rem;\">\n                        <div class=\"srm-col-head\">New Control Measures (NCM) <span style=\"font-weight:400;text-transform:none;\">— click a pill to rate its Barrier Quality</span></div>\n                        <div data-srm-ncm-list></div>\n                    </div>\n                </div>\n\n                <div class=\"srm-section\">\n                    <h3><i class=\"fas fa-th-large\"></i> Before &amp; After Risk Matrix Comparison</h3>\n                    <div class=\"srm-risk-comparison\">\n                        <div class=\"srm-risk-box\">\n                            <div class=\"srm-risk-label\">Current Risk Index</div>\n                            <div class=\"srm-risk-index\" data-srm-initial-index>—</div>\n                            <div class=\"srm-risk-tol\" data-srm-initial-tol>—</div>\n                        </div>\n                        <div class=\"srm-risk-arrow\"><i class=\"fas fa-arrow-right\"></i></div>\n                        <div class=\"srm-risk-box\">\n                            <div class=\"srm-risk-label\">Resultant Risk Index</div>\n                            <div class=\"srm-risk-index\" data-srm-resultant-index>—</div>\n                            <div class=\"srm-risk-tol\" data-srm-resultant-tol>—</div>\n                            <div class=\"srm-bsv-summary\" data-srm-resultant-bsv></div>\n                        </div>\n                    </div>\n                    <div style=\"margin-top:0.6rem;font-size:0.75rem;color:#64748b;\">\n                        Severity letter: <strong>${esc(state.severityLetter)}</strong>\n                    </div>\n                </div>\n\n                <div class=\"srm-section\">\n                    <h3><i class=\"fas fa-file-signature\"></i> Digital Postholder Sign-Off</h3>\n                    <div class=\"srm-signoff\">\n                        <span class=\"srm-authority-badge\" data-srm-authority><i class=\"fas fa-user-shield\"></i> Required: —</span>\n                        <div class=\"srm-signoff-grid\">\n                            <div><label>Postholder Name</label><input type=\"text\" data-srm-sign-name value=\"${esc(state.signoffs.name || '')}\"></div>\n                            <div><label>Postholder Role</label><input type=\"text\" data-srm-sign-role value=\"${esc(state.signoffs.role || '')}\"></div>\n                            <div><label>Date</label><input type=\"date\" data-srm-sign-date value=\"${esc(state.signoffs.date || '')}\"></div>\n                        </div>\n                    </div>\n                </div>\n            </div>`;\n\n        // Mode selector (banner only — Combined is the CAP default).\n        el.querySelectorAll('[data-mode] input').forEach(radio => {\n            radio.addEventListener('change', () => {\n                state.mode = radio.value;\n                el.querySelectorAll('[data-mode]').forEach(l => l.classList.toggle('srm-mode-active', l.dataset.mode === state.mode));\n                el.querySelector('[data-cap-part=\"bowtie\"]').style.display = state.mode === 'FISHBONE_ONLY' ? 'none' : 'block';\n            });\n        });\n        el.querySelector('[data-mode=\"COMBINED\"]').classList.add('srm-mode-active');\n\n        el.querySelector('[data-srm-sign-name]').addEventListener('input', e => { state.signoffs.name = e.target.value; });\n        el.querySelector('[data-srm-sign-role]').addEventListener('input', e => { state.signoffs.role = e.target.value; });\n        el.querySelector('[data-srm-sign-date]').addEventListener('change', e => { state.signoffs.date = e.target.value; });\n\n        renderNcm();\n        promoteCauses();\n        update();\n\n        return {\n            getMode: () => state.mode,\n            getSramData: () => {\n                if (state.mode === 'FISHBONE_ONLY') return null;\n                const severity = { severity_letter: state.severityLetter, descriptor: '' };\n                const profile = evaluateRiskProfile(severity, { ecb: [], erb: [], ncb: state.ncm, nrb: [] });\n                return {\n                    analysis_mode: state.mode,\n                    severity,\n                    barriers: { ecb: [], erb: [], ncb: state.ncm, nrb: [] },\n                    risk_profile: profile,\n                    signoffs: {\n                        name: state.signoffs.name || null,\n                        role: state.signoffs.role || null,\n                        date: state.signoffs.date || null,\n                        authority: profile.signoff.authority,\n                    },\n                };\n            },\n        };\n    }\n\n    // ── Public API ──────────────────────────────────────────────────────────\n    return {\n        SEVERITY_KEYS,\n        SEVERITY_BANDS,\n        BQV_KEYS,\n        BQV_BANDS,\n        PROBABILITY_CONFIG,\n        TOLERABILITY,\n        SIGNOFF_AUTHORITY,\n        LETTER_TO_NUMERIC,\n        FISHBONE_CATEGORIES,\n        computeSeverity,\n        computeBqv,\n        computeProbability,\n        evaluateRiskProfile,\n        openBarrierQualityModal,\n        createWorkspace: (container, opts) => new SrmWorkspace(container, opts),\n        attachCombined,\n    };\n})();\n\nif (typeof window !== 'undefined') {\n    window.SRM = SRM;\n}",
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\js\\srm.js"
}
```

**Output:**
```
Wrote file successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 9.3s)

_Thinking:_

Now let me verify srm.js is syntactically valid with node --check.





**Tool: bash**

**Input:**
```json
{
  "command": "node --check public/js/srm.js && node --check public/js/hazards.js && echo \"SYNTAX OK\"",
  "workdir": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe"
}
```

**Output:**
```
SYNTAX OK

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 6.6s)

_Thinking:_

Now integrate into `public/hazards/detail.html`:
1. Add srm.css link in head.
2. Add SRM card after the SRM Status card.
3. Add srm.js script tag before the inline script.
4. In the inline script, initialize the workspace in renderHazard.

Let me edit detail.html.

Now integrate the workspace into the

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\hazards\\detail.html",
  "newString": "<link rel=\"stylesheet\" href=\"/css/variables.css\">\n    <link rel=\"stylesheet\" href=\"/css/main.css\">\n    <link rel=\"stylesheet\" href=\"/css/srm.css\">",
  "oldString": "<link rel=\"stylesheet\" href=\"/css/variables.css\">\n    <link rel=\"stylesheet\" href=\"/css/main.css\">"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 11.0s)

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\hazards\\detail.html",
  "newString": "        <div class=\"card\">\n            <h2><i class=\"fas fa-clipboard-list\"></i> SRM Status</h2>\n            <div class=\"detail-grid\">\n                <div class=\"detail-field\"><div class=\"label\">SRM Conducted</div><div class=\"value\" id=\"fieldSrmConducted\"></div></div>\n                <div class=\"detail-field\"><div class=\"label\">SRM Date</div><div class=\"value\" id=\"fieldSrmDate\"></div></div>\n                <div class=\"detail-field\"><div class=\"label\">SRM Status</div><div class=\"value\" id=\"fieldSrmStatus\"></div></div>\n            </div>\n        </div>\n\n        <div class=\"card\">\n            <h2><i class=\"fas fa-diagram-project\"></i> CAAN CAR-19 SRM Analysis</h2>\n            <div id=\"srmWorkspace\"></div>\n        </div>",
  "oldString": "        <div class=\"card\">\n            <h2><i class=\"fas fa-clipboard-list\"></i> SRM Status</h2>\n            <div class=\"detail-grid\">\n                <div class=\"detail-field\"><div class=\"label\">SRM Conducted</div><div class=\"value\" id=\"fieldSrmConducted\"></div></div>\n                <div class=\"detail-field\"><div class=\"label\">SRM Date</div><div class=\"value\" id=\"fieldSrmDate\"></div></div>\n                <div class=\"detail-field\"><div class=\"label\">SRM Status</div><div class=\"value\" id=\"fieldSrmStatus\"></div></div>\n            </div>\n        </div>"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 6.3s)

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\hazards\\detail.html",
  "newString": "<script src=\"/js/firebase.js\"></script>\n<script src=\"/js/api/client.js\"></script>\n<script src=\"/js/hazards.js\"></script>\n<script src=\"/js/verification.js\"></script>\n<script src=\"/js/fishbone.js\"></script>\n<script src=\"/js/srm.js\"></script>\n<script>\nlet hazardData = null;\nlet currentUser = null;\nlet currentUserRole = null;\nlet srmWorkspace = null;",
  "oldString": "<script src=\"/js/firebase.js\"></script>\n<script src=\"/js/api/client.js\"></script>\n<script src=\"/js/hazards.js\"></script>\n<script src=\"/js/verification.js\"></script>\n<script>\nlet hazardData = null;\nlet currentUser = null;\nlet currentUserRole = null;"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 7.0s)

_Thinking:_

Now initialize the workspace in renderHazard. I'll add `initSrm(h)` after `renderVerificationSection(h)`. Let me edit the renderHazard function and add the initSrm function.

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\hazards\\detail.html",
  "newString": "    renderRiskDisplay(h);\n    renderStatusButtons(h);\n    populateEditForm(h);\n    renderVerificationSection(h);\n    initSrm(h);\n}\n\nfunction initSrm(h) {\n    const el = document.getElementById('srmWorkspace');\n    if (!el || typeof SRM === 'undefined' || !SRM.createWorkspace) return;\n    try {\n        if (!srmWorkspace) {\n            srmWorkspace = SRM.createWorkspace(el, {\n                hazardId: h.id,\n                saved: h.sram_data || null,\n                mode: h.analysis_mode || 'FISHBONE_ONLY',\n            });\n        }\n    } catch (err) {\n        console.error('SRM workspace init failed:', err);\n        el.innerHTML = '<p style=\"font-size:0.85rem;color:#dc3545;\">SRM workspace could not be initialised.</p>';\n    }\n}",
  "oldString": "    renderRiskDisplay(h);\n    renderStatusButtons(h);\n    populateEditForm(h);\n    renderVerificationSection(h);\n}"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 8.6s)

_Thinking:_

Now integrate into `public/can_cap/cap_submit.html`:
1. Add srm.css link.
2. Add srm.js script.
3. Add a Combined SRM section (after fishbone editor) with `<div id="srmCombinedPanel"></div>`.
4. In the inline script: create the combined controller after initFishbone, and include sram_data in submitCap payload.

The severity letter for cap_submit: derive from the residual SRA severity if available. RiskMatrix controller has getValue() with severity (1-5) and severity_letter. Since the residual SRA is initialized async (initResidualSra is async), I can capture the letter after it loads. Simplest: at submit time, read rSra.severity_letter and pass to combined controller? But the combined panel is rendered at load with a default letter. I could allow the controller to set severity letter dynamically. Simpler: after initResidualSra resolves, update combined controller's severity letter and re-render. But the attachCombined controller doesn't expose a setSeverityLetter.

Let me add to attachCombined a returned `setSeverityLetter(letter)` method that updates state + re-renders. Let me add that to srm.js.

Actually, let me modify attachCombined to expose `setSeverityLetter`. I'll add it to the returned object, and have it update the letter display.

Let me update srm.js attachCombined return.

Now integrate into `cap_submit.html`. First expose a `setSeverityLetter` on the combined controller

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\js\\srm.js",
  "newString": "        renderNcm();\n        promoteCauses();\n        update();\n\n        function setSeverityLetter(letter) {\n            if (letter && TOLERABILITY['1' + letter.toUpperCase()]) {\n                state.severityLetter = letter.toUpperCase();\n                const label = el.querySelector('[data-cap-sev-letter]');\n                if (label) label.innerHTML = 'Severity letter: <strong>' + esc(state.severityLetter) + '</strong>';\n                update();\n            }\n        }\n\n        return {\n            getMode: () => state.mode,\n            setSeverityLetter,\n            getSramData: () => {",
  "oldString": "        renderNcm();\n        promoteCauses();\n        update();\n\n        return {\n            getMode: () => state.mode,\n            getSramData: () => {"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 5.6s)

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\js\\srm.js",
  "newString": "<div style=\"margin-top:0.6rem;font-size:0.75rem;color:#64748b;\" data-cap-sev-letter>\n                        Severity letter: <strong>${esc(state.severityLetter)}</strong>\n                    </div>",
  "oldString": "<div style=\"margin-top:0.6rem;font-size:0.75rem;color:#64748b;\">\n                        Severity letter: <strong>${esc(state.severityLetter)}</strong>\n                    </div>"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 5.6s)

**Tool: bash**

**Input:**
```json
{
  "command": "node --check public/js/srm.js && echo OK",
  "workdir": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe"
}
```

**Output:**
```
OK

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 5.7s)

Now edit `cap_submit.html`

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\can_cap\\cap_submit.html",
  "newString": "<link rel=\"stylesheet\" href=\"/css/variables.css\">\n    <link rel=\"stylesheet\" href=\"/css/main.css\">\n    <link rel=\"stylesheet\" href=\"/css/can-cap-print.css\">\n    <link rel=\"stylesheet\" href=\"/css/srm.css\">",
  "oldString": "<link rel=\"stylesheet\" href=\"/css/variables.css\">\n    <link rel=\"stylesheet\" href=\"/css/main.css\">\n    <link rel=\"stylesheet\" href=\"/css/can-cap-print.css\">"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 5.7s)

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\can_cap\\cap_submit.html",
  "newString": "            <div id=\"fishboneEditor\"></div>\n\n            <div style=\"font-size:0.95rem;font-weight:700;color:#0b2a42;margin:1.25rem 0 0.6rem;text-transform:uppercase;letter-spacing:0.5px;\">\n                <i class=\"fas fa-bow-arrow\"></i> CAAN CAR-19 SRM — Combined RCA + SRAM\n            </div>\n            <div id=\"srmCombinedPanel\"></div>",
  "oldString": "            <div id=\"fishboneEditor\"></div>"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 5.7s)

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\can_cap\\cap_submit.html",
  "newString": "<script src=\"/js/risk_matrix.js\"></script>\n<script src=\"/js/fishbone.js\"></script>\n<script src=\"/js/can_cap.js\"></script>\n<script src=\"/js/srm.js\"></script>\n<script>\nlet canId = null;\nlet fishboneController = null;\nlet residualSraController = null;\nlet srmCombined = null;",
  "oldString": "<script src=\"/js/risk_matrix.js\"></script>\n<script src=\"/js/fishbone.js\"></script>\n<script src=\"/js/can_cap.js\"></script>\n<script>\nlet canId = null;\nlet fishboneController = null;\nlet residualSraController = null;"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 37.6s)

_Thinking:_

Now update the inline script in cap_submit.html:
1. In initFishbone, after creating fishboneController, init the combined panel (after DOM has the element).
2. In initResidualSra, after the controller loads, sync severity letter to the combined panel.
3. In submitCap, include sram_data.

The auth flow: onAuthStateChanged calls loadCanInfo, initResidualSra, initFishbone. I'll init the combined panel inside initFishbone (needs fishboneController reference). The combined panel references fishboneController's getData at render/promote time — since promoteCauses reads fishboneController.getData() live, it's fine if the combined panel is created before root causes exist.

But the fishboneController is assigned inside initFishbone via `fishboneController = Fishbone.renderEditor(...)`. So create combined panel after that assignment.

initResidualSra is async; after it resolves, set severity letter on combined panel. Let me modify initResidualSra to sync.

Let me edit these functions.





**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\can_cap\\cap_submit.html",
  "newString": "function initFishbone() {\n    try {\n        fishboneController = Fishbone.renderEditor('fishboneEditor', {\n            data: { root_causes: [], action_items: [] },\n            onChange: () => {\n                if (srmCombined && typeof srmCombined.refreshPromotion === 'function') {\n                    srmCombined.refreshPromotion();\n                }\n            },\n        });\n        initSrmCombined();\n    } catch (err) {\n        console.error('Fishbone init failed:', err);\n    }\n}\n\nfunction initSrmCombined() {\n    const el = document.getElementById('srmCombinedPanel');\n    if (!el || typeof SRM === 'undefined' || !SRM.attachCombined) return;\n    try {\n        srmCombined = SRM.attachCombined(el, {\n            fishboneController,\n            severityLetter: null,\n        });\n    } catch (err) {\n        console.error('SRM combined init failed:', err);\n        el.innerHTML = '<p style=\"font-size:0.85rem;color:#dc3545;\">SRM Combined panel could not be initialised.</p>';\n    }\n}\n\nasync function initResidualSra() {\n    try {\n        residualSraController = await RiskMatrix.render('residualSraMatrix', {\n            mode: 'interactive',\n            showHeader: true,\n            showSummary: true,\n        });\n        if (srmCombined && residualSraController && typeof residualSraController.getValue === 'function') {\n            const v = residualSraController.getValue();\n            if (v && v.severity_letter) srmCombined.setSeverityLetter(v.severity_letter);\n        }\n    } catch (err) {\n        console.error('RiskMatrix init failed:', err);\n    }\n}",
  "oldString": "function initFishbone() {\n    try {\n        fishboneController = Fishbone.renderEditor('fishboneEditor', {\n            data: { root_causes: [], action_items: [] },\n            onChange: () => {},\n        });\n    } catch (err) {\n        console.error('Fishbone init failed:', err);\n    }\n}\n\nasync function initResidualSra() {\n    try {\n        residualSraController = await RiskMatrix.render('residualSraMatrix', {\n            mode: 'interactive',\n            showHeader: true,\n            showSummary: true,\n        });\n    } catch (err) {\n        console.error('RiskMatrix init failed:', err);\n    }\n}"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 10.3s)

_Thinking:_

Now the srmCombined controller needs a `refreshPromotion()` method (used in fishbone onChange). Let me add it to attachCombined's return object. It should re-run promoteCauses() so newly added root causes appear. Let me add it.

Add the `refreshPromotion` method to the combined controller



**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\js\\srm.js",
  "newString": "return {\n            getMode: () => state.mode,\n            setSeverityLetter,\n            refreshPromotion: promoteCauses,\n            getSramData: () => {",
  "oldString": "return {\n            getMode: () => state.mode,\n            setSeverityLetter,\n            getSramData: () => {"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 6.6s)

Now include `sram_data` in the CAP submit payload



**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\can_cap\\cap_submit.html",
  "newString": "root_causes: fishData.root_causes && fishData.root_causes.length ? fishData.root_causes : null,\n        action_items: fishData.action_items && fishData.action_items.length ? fishData.action_items : null,\n        sram_data: srmCombined && srmCombined.getSramData ? srmCombined.getSramData() : null,",
  "oldString": "root_causes: fishData.root_causes && fishData.root_causes.length ? fishData.root_causes : null,\n        action_items: fishData.action_items && fishData.action_items.length ? fishData.action_items : null,"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 13.8s)

_Thinking:_

Now let me check the CAPReview and other places that read root_causes in can_cap route to see if sram_data needs to be included in responses. It's fine — the submit stores it. The `_to_cap_response` in can_cap.py might want to include sram_data. Let me check the response serializers. But since CAPResponse model doesn't include sram_data, the route response may drop it. That's acceptable — persistence is the goal. But for display later it might be nice. Given scope, persistence is enough.

Now let me run the frontend integrity checks:
1. node --check on all js files? check-inline-scripts.js checks inline scripts in html.
2. Run check-inline-scripts.js public
3. Run the frontend test suites: dashboard.test.js, input-guard.test.js, tenant-context.test.js.

Let me first run check-inline-scripts.js (it scans inline <script> blocks and checks syntax). My edits added inline JS to detail.html and cap_submit.html. Let me run it.

Now run the frontend integrity checks



**Tool: bash**

**Input:**
```json
{
  "command": "node frontend-tests/check-inline-scripts.js public 2>&1 | Select-Object -Last 10",
  "workdir": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe"
}
```

**Output:**
```
Checked inline scripts: 48, failures: 0

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 5.0s)

**Tool: bash**

**Input:**
```json
{
  "command": "node frontend-tests/dashboard.test.js 2>&1 | Select-Object -Last 5; Write-Output \"---INPUT-GUARD---\"; node frontend-tests/input-guard.test.js 2>&1 | Select-Object -Last 5; Write-Output \"---TENANT-CTX---\"; node frontend-tests/tenant-context.test.js 2>&1 | Select-Object -Last 5",
  "workdir": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe"
}
```

**Output:**
```
dashboard-render: 4 tests passed
---INPUT-GUARD---
input-guard: 12 tests passed
---TENANT-CTX---
tenant_context + department_resolver: tests passed

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 7.0s)

_Thinking:_

All frontend checks pass. Now let me also do a quick sanity test of the srm.js module in Node to make sure the compute functions work (mirroring backend). I can require it? It uses `window` at the end — guarded. Let me write a quick node test to eval the SRM module and run the wheel jack benchmark through computeSeverity + evaluateRiskProfile.

Since srm.js is an IIFE assigning to `const SRM`, I can load it in node via `require`? It's not a module. I'll use `vm` or just `node -e` with fs read + eval. Let me do a quick check.

Let me sanity-check the JS engine math mirrors the backend benchmark

**Tool: bash**

**Input:**
```json
{
  "command": "node -e \"\nconst fs = require('fs');\nconst vm = require('vm');\nconst ctx = { window: {} };\nvm.createContext(ctx);\nvm.runInContext(fs.readFileSync('public/js/srm.js','utf8'), ctx);\nconst S = ctx.window.SRM;\nconst sev = S.computeSeverity({pax:0,worker:4,quality:3,asset:4,rep:1,sec:0,env:0});\nconsole.log('severity:', JSON.stringify(sev));\nconst prof = S.evaluateRiskProfile(sev, {ecb:[{bsv:2},{bsv:2}], erb:[], ncb:[{bsv:4},{bsv:3}], nrb:[{bsv:3}]});\nconsole.log('initial:', prof.initial_risk.index, prof.initial_risk.tolerability);\nconsole.log('resultant:', prof.resultant_risk.index, prof.resultant_risk.tolerability);\nconsole.log('authority:', prof.signoff.authority);\nconst bqv = S.computeBqv({effectiveness:5,cost_benefit:4,practicality:4,acceptability:5,enforceability:5,durability:4,disinclination:4});\nconsole.log('bqv:', JSON.stringify(bqv));\n\"",
  "workdir": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe"
}
```

**Output:**
```
severity: {"total_score":23,"severity_letter":"D","descriptor":"Minor"}
initial: 4D Tolerable
resultant: 1D Acceptable
authority: Safety Manager / SAG Member
bqv: {"bqv":45,"bsv":5,"robustness":"Excellent"}

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 41.3s)

_Thinking:_

JS engine matches the backend exactly (23→D, 4D→1D Acceptable, bqv 45→5 Excellent). 

Now let me run the full backend suite once more to be safe (I changed can_cap model + service). Then update todos, then commit/push/deploy.

Actually I ran backend at 447 before the can_cap model/service changes. Let me re-run full backend to confirm no regression from the can_cap additions.

JS math matches backend exactly. Re-run full backend suite to confirm the can_cap changes didn't regress anything

**Tool: bash**

**Input:**
```json
{
  "command": "python -m pytest -q 2>&1 | Select-Object -Last 4",
  "timeout": 600000,
  "workdir": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend"
}
```

**Output:**
```
    history = [item.dict() for item in (payload.history or [])]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
447 passed, 4 warnings in 26.56s

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 6.4s)

_Thinking:_

All green. Now update todos, then commit, sync branch, push, and deploy Firebase hosting (since public/ files changed). Let me update the todo list.

**Tool: todowrite**

**Input:**
```json
{
  "todos": [
    {
      "content": "Create backend/app/services/srm_engine.py with calculate_severity, calculate_bqv, calculate_probability, evaluate_risk_profile",
      "priority": "high",
      "status": "completed"
    },
    {
      "content": "Add SRAM models (severity inputs, barriers, risk profile, signoffs) to backend/app/models/hazard.py",
      "priority": "high",
      "status": "completed"
    },
    {
      "content": "Add POST /hazards/{id}/sram/calculate and PUT /hazards/{id}/sram/save endpoints in routes/hazards.py; persist analysis_mode + sram_data via hazard_service.py",
      "priority": "high",
      "status": "completed"
    },
    {
      "content": "Write backend/tests/test_srm_engine.py incl. Wheel Jack Sunk benchmark (4D->1D) + endpoint tests",
      "priority": "high",
      "status": "completed"
    },
    {
      "content": "Frontend: Analysis Model Selector + Bow-Tie SRM workspace in public/hazards/detail.html (sliders, visualizer, BQV modal, risk matrix comparison, sign-off)",
      "priority": "high",
      "status": "completed"
    },
    {
      "content": "Frontend: Combined RCA+SRAM (promote fishbone root causes to NCM) in public/can_cap/cap_submit.html",
      "priority": "high",
      "status": "completed"
    },
    {
      "content": "Add HazardsAPI.sramCalculate/sramSave methods to public/js/hazards.js (+ client.js if needed)",
      "priority": "medium",
      "status": "completed"
    },
    {
      "content": "Run full pytest + frontend integrity checks (node --check, inline scripts, frontend suites)",
      "priority": "high",
      "status": "completed"
    },
    {
      "content": "Commit, sync feat branch, push both branches, verify deploy",
      "priority": "high",
      "status": "in_progress"
    }
  ]
}
```

**Output:**
```
[
  {
    "content": "Create backend/app/services/srm_engine.py with calculate_severity, calculate_bqv, calculate_probability, evaluate_risk_profile",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Add SRAM models (severity inputs, barriers, risk profile, signoffs) to backend/app/models/hazard.py",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Add POST /hazards/{id}/sram/calculate and PUT /hazards/{id}/sram/save endpoints in routes/hazards.py; persist analysis_mode + sram_data via hazard_service.py",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Write backend/tests/test_srm_engine.py incl. Wheel Jack Sunk benchmark (4D->1D) + endpoint tests",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Frontend: Analysis Model Selector + Bow-Tie SRM workspace in public/hazards/detail.html (sliders, visualizer, BQV modal, risk matrix comparison, sign-off)",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Frontend: Combined RCA+SRAM (promote fishbone root causes to NCM) in public/can_cap/cap_submit.html",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Add HazardsAPI.sramCalculate/sramSave methods to public/js/hazards.js (+ client.js if needed)",
    "status": "completed",
    "priority": "medium"
  },
  {
    "content": "Run full pytest + frontend integrity checks (node --check, inline scripts, frontend suites)",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Commit, sync feat branch, push both branches, verify deploy",
    "status": "in_progress",
    "priority": "high"
  }
]
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 3.9s)

**Tool: bash**

**Input:**
```json
{
  "command": "git status --short",
  "workdir": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe"
}
```

**Output:**
```
 M backend/app/models/can_cap.py
 M backend/app/models/hazard.py
 M backend/app/routes/hazards.py
 M backend/app/services/can_cap_service.py
 M backend/app/services/hazard_service.py
 M public/can_cap/cap_submit.html
 M public/hazards/detail.html
 M public/js/hazards.js
?? "Survey Questions for AviaSAFE-SMS.pdf"
?? "Survey Questions for AviaSAFE-SMS.txt"
?? aviasafe_sms_hybrid_landing_page.html
?? backend/app/services/srm_engine.py
?? backend/tests/test_srm_engine.py
?? opencode_design_system_plan.md
?? public/css/srm.css
?? public/js/srm.js

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 5.5s)

**Tool: bash**

**Input:**
```json
{
  "command": "git add backend/app/models/can_cap.py backend/app/models/hazard.py backend/app/routes/hazards.py backend/app/services/can_cap_service.py backend/app/services/hazard_service.py backend/app/services/srm_engine.py backend/tests/test_srm_engine.py public/can_cap/cap_submit.html public/hazards/detail.html public/js/hazards.js public/js/srm.js public/css/srm.css && git commit -m \"feat(srm): CAAN CAR-19 SRM mathematical engine, Bow-Tie analysis model selector, and Combined RCA+SRAM promotion\"",
  "workdir": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe"
}
```

**Output:**
```
warning: in the working copy of 'backend/app/models/can_cap.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'backend/app/models/hazard.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'backend/app/routes/hazards.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'backend/app/services/can_cap_service.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'backend/app/services/hazard_service.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'public/js/hazards.js', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'backend/app/services/srm_engine.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'backend/tests/test_srm_engine.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'public/css/srm.css', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'public/js/srm.js', LF will be replaced by CRLF the next time Git touches it
[main 6547d87] feat(srm): CAAN CAR-19 SRM mathematical engine, Bow-Tie analysis model selector, and Combined RCA+SRAM promotion
 12 files changed, 2436 insertions(+), 3 deletions(-)
 create mode 100644 backend/app/services/srm_engine.py
 create mode 100644 backend/tests/test_srm_engine.py
 create mode 100644 public/css/srm.css
 create mode 100644 public/js/srm.js

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 9.6s)

**Tool: bash**

**Input:**
```json
{
  "command": "git branch -f feat/betasms-self-service main && git push origin main feat/betasms-self-service 2>&1 | Select-Object -Last 6",
  "workdir": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe"
}
```

**Output:**
```
[31;1mTo https://github.com/DHFactors/sms-aviasafesystems.git[0m
[31;1m   57a8992..6547d87  feat/betasms-self-service -> feat/betasms-self-service[0m
[31;1m   57a8992..6547d87  main -> main[0m

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 118.1s)

_Thinking:_

Pushed. Backend will auto-redeploy on Render. Now deploy Firebase hosting (public/ files changed). Then verify deployment (live page 200 + API health).

Pushed. Now deploy Firebase hosting and verify



**Tool: bash**

**Input:**
```json
{
  "command": "firebase deploy --project aerosafety-sms-prod --only hosting:aerosafety-sms-beta,hosting:aerosafety-sms-prod 2>&1 | Select-Object -Last 12",
  "timeout": 300000,
  "workdir": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe"
}
```

**Output:**
```
[32m[1m+  hosting[aerosafety-sms-beta]:[22m[39m version finalized
[36m[1mi  hosting[aerosafety-sms-beta]:[22m[39m releasing new version...
[32m[1m+  hosting[aerosafety-sms-prod]:[22m[39m version finalized
[36m[1mi  hosting[aerosafety-sms-prod]:[22m[39m releasing new version...
[32m[1m+  hosting[aerosafety-sms-beta]:[22m[39m release complete
[32m[1m+  hosting[aerosafety-sms-prod]:[22m[39m release complete

[32m[1m+ [22m[39m [1m[4mDeploy complete![24m[22m

[1mProject Console:[22m https://console.firebase.google.com/project/aerosafety-sms-prod/overview
[1mHosting URL:[22m https://aerosafety-sms-beta.web.app
[1mHosting URL:[22m https://aerosafety-sms-prod.web.app

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 10.5s)

**Tool: bash**

**Input:**
```json
{
  "command": "(Invoke-WebRequest -SkipHttpErrorCheck -UseBasicParsing \"https://aerosafety-sms-beta.web.app/hazards/detail.html\").StatusCode; (Invoke-WebRequest -SkipHttpErrorCheck -UseBasicParsing \"https://aerosafety-sms-beta.web.app/js/srm.js\").StatusCode; (Invoke-WebRequest -SkipHttpErrorCheck -UseBasicParsing \"https://aerosafety-sms-beta.web.app/css/srm.css\").StatusCode",
  "workdir": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe"
}
```

**Output:**
```
200
200
200

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 7.3s)

_Thinking:_

Hosting deployed, page + new assets return 200. Now verify backend health (Render redeploy may take a bit). Let me check the health endpoint of the beta backend.

Hosting live. Verify the backend redeployed healthy

**Tool: bash**

**Input:**
```json
{
  "command": "(Invoke-WebRequest -SkipHttpErrorCheck -UseBasicParsing \"https://sms-aviasafesystems-beta.onrender.com/health\").StatusCode; (Invoke-WebRequest -SkipHttpErrorCheck -UseBasicParsing \"https://sms-aviasafesystems-beta.onrender.com/health\").Content",
  "timeout": 60000,
  "workdir": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe"
}
```

**Output:**
```
200
{"status":"healthy","firebase":"connected","service":"AviaSAFE SMS API","version":"1.0.0"}

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 6.2s)

**Tool: todowrite**

**Input:**
```json
{
  "todos": [
    {
      "content": "Create backend/app/services/srm_engine.py with calculate_severity, calculate_bqv, calculate_probability, evaluate_risk_profile",
      "priority": "high",
      "status": "completed"
    },
    {
      "content": "Add SRAM models (severity inputs, barriers, risk profile, signoffs) to backend/app/models/hazard.py",
      "priority": "high",
      "status": "completed"
    },
    {
      "content": "Add POST /hazards/{id}/sram/calculate and PUT /hazards/{id}/sram/save endpoints in routes/hazards.py; persist analysis_mode + sram_data via hazard_service.py",
      "priority": "high",
      "status": "completed"
    },
    {
      "content": "Write backend/tests/test_srm_engine.py incl. Wheel Jack Sunk benchmark (4D->1D) + endpoint tests",
      "priority": "high",
      "status": "completed"
    },
    {
      "content": "Frontend: Analysis Model Selector + Bow-Tie SRM workspace in public/hazards/detail.html (sliders, visualizer, BQV modal, risk matrix comparison, sign-off)",
      "priority": "high",
      "status": "completed"
    },
    {
      "content": "Frontend: Combined RCA+SRAM (promote fishbone root causes to NCM) in public/can_cap/cap_submit.html",
      "priority": "high",
      "status": "completed"
    },
    {
      "content": "Add HazardsAPI.sramCalculate/sramSave methods to public/js/hazards.js (+ client.js if needed)",
      "priority": "medium",
      "status": "completed"
    },
    {
      "content": "Run full pytest + frontend integrity checks (node --check, inline scripts, frontend suites)",
      "priority": "high",
      "status": "completed"
    },
    {
      "content": "Commit, sync feat branch, push both branches, verify deploy",
      "priority": "high",
      "status": "completed"
    }
  ]
}
```

**Output:**
```
[
  {
    "content": "Create backend/app/services/srm_engine.py with calculate_severity, calculate_bqv, calculate_probability, evaluate_risk_profile",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Add SRAM models (severity inputs, barriers, risk profile, signoffs) to backend/app/models/hazard.py",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Add POST /hazards/{id}/sram/calculate and PUT /hazards/{id}/sram/save endpoints in routes/hazards.py; persist analysis_mode + sram_data via hazard_service.py",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Write backend/tests/test_srm_engine.py incl. Wheel Jack Sunk benchmark (4D->1D) + endpoint tests",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Frontend: Analysis Model Selector + Bow-Tie SRM workspace in public/hazards/detail.html (sliders, visualizer, BQV modal, risk matrix comparison, sign-off)",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Frontend: Combined RCA+SRAM (promote fishbone root causes to NCM) in public/can_cap/cap_submit.html",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Add HazardsAPI.sramCalculate/sramSave methods to public/js/hazards.js (+ client.js if needed)",
    "status": "completed",
    "priority": "medium"
  },
  {
    "content": "Run full pytest + frontend integrity checks (node --check, inline scripts, frontend suites)",
    "status": "completed",
    "priority": "high"
  },
  {
    "content": "Commit, sync feat branch, push both branches, verify deploy",
    "status": "completed",
    "priority": "high"
  }
]
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 14.3s)

Phase 2 complete. Commit `6547d87`, pushed to `main` + `feat/betasms-self-service`, both Firebase hosting targets deployed, backend healthy.

**Backend**
- `backend/app/services/srm_engine.py` — pure CAAN CAR-19 engine: `calculate_severity` (7-impact weighted, 0-65, A-E), `calculate_bqv` (BQV→BSV, 10-50), `calculate_probability` (ONB bands A-E), `evaluate_risk_profile` (Existing vs Consolidated BSV → before/after index, tolerability matrix, sign-off authority). Verified against the Wheel Jack benchmark: **23→D, 4D→1D Acceptable**, authority "Safety Manager / SAG Member".
- `models/hazard.py` — `AnalysisMode` enum + `SeverityInput`, `BarrierQuality`, `BarrierConfig`, `SramBarriers`, `BowtieConfig`, `SramData`, `SramCalculateRequest`, `SramSaveRequest`; `analysis_mode` (default `FISHBONE_ONLY`) + `sram_data` on create/update.
- `routes/hazards.py` — `POST /{id}/sram/calculate` (dynamic, no persist) and `PUT /{id}/sram/save` (authoritative recompute + 422 on tampered severity; updates Master Risk register severity/probability/risk_index/risk_level/risk_outcome, SRM conducted flag). Both mounted under `/api/v1/hazards` and `/api/hazards`. Audit-logged.
- `can_cap.py`/`can_cap_service.py` — persist `sram_data` on CAP submissions (Combined mode).

**Frontend**
- `public/js/srm.js` + `public/css/srm.css` — Analysis Model Selector, interactive 6M fishbone, 7-impact sliders with live letter badge, Bow-Tie visualizer (Threats→ECM→Top Event→ERB→Consequences + NCM/NRB), Barrier Quality modal (BQV/BSV badge), Before/After risk comparison, digital sign-off with required-authority badge. JS math mirrors backend (23→D, 4D→1D).
- `hazards/detail.html` — full SRM workspace card. `cap_submit.html` — Combined RCA+SRAM panel promoting fishbone root causes to NCM, severity letter synced from residual SRA, `sram_data` included in the CAP payload. `HazardsAPI.sramCalculate/sramSave` added.

**Verification** — backend **447 passed** (27 new SRM tests); `check-inline-scripts` 48/48; dashboard 4, input-guard 12, tenant-context pass; `node --check` clean; live page + `/js/srm.js` + `/css/srm.css` 200; backend `/health` healthy.

---

## User

Implement Departmental Admin (HOD) Delegation in User Management & Invites:

1. Backend RBAC & Invite Enforcement (backend/app/routes/auth.py & backend/app/services/auth_service.py):
- Update User / Token Claims:
  * Ensure user records in Firestore contain: uid, email, tenant_id, role, department, status.
  * Role Hierarchy:
    - SUPER_ADMIN: Global administrative privileges.
    - TENANT_ADMIN (Safety Manager): Full administrative rights across the entire tenant.
    - DEPT_ADMIN (HOD): Administrative rights strictly restricted to caller's assigned department.
    - SAFETY_OFFICER: Operational safety review across tenant.
    - STAFF / EMPLOYEE: Departmental member reporting and read access.

- Update POST /api/v1/auth/invite (and /api/auth/invite):
  * Inspect caller's auth context (role, tenant_id, department).
  * If caller role == "TENANT_ADMIN":
    - Can generate invite codes for ANY valid department.
    - Can assign roles: ["DEPT_ADMIN", "SAFETY_OFFICER", "STAFF"].
  * If caller role == "DEPT_ADMIN":
    - Enforce target department == caller's department (override or reject mismatches with 403 Forbidden).
    - Restrict assignable role strictly to "STAFF" (reject privilege escalation to DEPT_ADMIN or TENANT_ADMIN with 403 Forbidden).
  * Persist the invite document with: { code, tenant_id, department, role, created_by, created_at, status: "ACTIVE" }.

2. Join / Registration Endpoint Updates (backend/app/routes/auth.py):
- When resolving invite code in /api/v1/auth/join:
  * Read the assigned 'department' and 'role' directly from the valid invite document.
  * Bind the new user to caller's tenant_id, target department, and target role in Firestore.

3. Frontend Team Management View (public/settings/team.html or team management modal):
- When logged in as DEPT_ADMIN:
  * Filter the displayed team list to show only members of caller's own department.
  * In the "Invite Team Member" form / modal:
    - Lock the "Department" selector (display caller's department as read-only).
    - Lock the "Role" dropdown to "STAFF / Employee" (disabled/hidden escalation options).
- When logged in as TENANT_ADMIN:
  * Maintain full visibility across all departments with active filter dropdowns and full role assignment capability.

4. Unit Tests (tests/test_dept_admin_rbac.py):
- Write comprehensive tests verifying:
  * TENANT_ADMIN can invite DEPT_ADMIN and STAFF to any department.
  * DEPT_ADMIN can invite STAFF to their own department.
  * DEPT_ADMIN inviting to another department returns HTTP 403 Forbidden.
  * DEPT_ADMIN attempting to assign TENANT_ADMIN or DEPT_ADMIN role returns HTTP 403 Forbidden.
  * Successful registration with a department-scoped invite assigns the correct department and role to the new user.

5. Verification & Deployment:
- Run full pytest test suite (including new RBAC tests and existing 447 tests).
- Run frontend integrity checks (check-inline-scripts, node --check).
- Commit with a descriptive message, push to main and feat/betasms-self-service, and verify backend /health and Firebase hosting deploy. 

---

## Assistant (Build · DeepSeek V4 Flash Free · 15.3s)

_Thinking:_

This is another large multi-part task. Let me plan and explore the relevant files first.

Key files:
- backend/app/routes/auth.py (invite, join endpoints)
- backend/app/services/auth_service.py (does this exist? Let me check)
- User/claims handling in Firestore
- Frontend team management view — where is it? Let me search for team management / invite UI.

Let me explore:
1. backend/app/routes/auth.py — read invite/join endpoints
2. backend/app/services/ — check for auth_service.py
3. Search for invite endpoint frontend (settings/team.html or team management modal)
4. backend/app/middleware/auth.py — role handling
5. backend/tests/test_auth.py — existing invite/join tests

Let me start.

Phase task. Let me explore the auth/invite backend and find the team management front

**Tool: read**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\routes\\auth.py"
}
```

**Output:**
```
<path>C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\auth.py</path>
<type>file</type>
<content>
1: # ============================================================================
2: # FILE: auth.py
3: # PATH: backend/app/routes/auth.py
4: # VERSION: 1.0.0
5: # DATE CREATED: 2026-07-03
6: # DATE REVISED: 2026-08-19
7: # PURPOSE: Authentication endpoints with Firebase Auth integration.
8: # AUTHOR: Ghanshyam Acharya
9: # CODE OWNER: AviaSafeSystems
10: # ============================================================================
11: 
12: import asyncio
13: from fastapi import APIRouter, HTTPException, Depends, Request, Query, BackgroundTasks
14: from fastapi.responses import JSONResponse
15: from pydantic import BaseModel, EmailStr, Field
16: from typing import Optional
17: from datetime import datetime, timezone
18: 
19: from app.core.config import settings
20: from app.firebase import get_auth, get_db, verify_firebase_token, create_custom_claims
21: from app.middleware.rate_limit import (
22:     rate_limit,
23:     enforce_login_rate_limit,
24:     record_login_failure,
25:     clear_login_failures,
26: )
27: from app.middleware.auth import resolve_user_context
28: from app.middleware.app_check import verify_app_check
29: from app.models.tenant_profile import OperationalScope
30: from app.services.audit_service import log_audit, request_context
31: from app.services.users import upsert_user_doc
32: from app.services import login_service
33: from app.services.gmail_dispatcher import send_registration_acknowledgment
34: from app.services.tenant_registration import (
35:     DEPARTMENT_LABELS,
36:     DISPOSABLE_EMAIL_MESSAGE,
37:     DisposableEmailError,
38:     validate_corporate_email,
39:     register_tenant,
40:     join_team,
41:     resolve_tenant,
42:     verify_invite,
43:     DuplicateEmailError,
44: )
45: 
46: router = APIRouter()
47: 
48: 
49: class LoginRequest(BaseModel):
50:     id_token: str
51: 
52: 
53: class LoginCredentials(BaseModel):
54:     email: EmailStr
55:     password: str
56: 
57: 
58: class LoginResponse(BaseModel):
59:     uid: str
60:     email: str
61:     role: str
62:     tenant_id: Optional[str]
63:     custom_claims: dict
64: 
65: 
66: @router.post("/login")
67: async def login_endpoint(
68:     request: Request,
69:     body: LoginCredentials,
70:     _app_check: None = Depends(verify_app_check),
71: ):
72:     """Server-side credential verification with anti-credential-stuffing lockout.
73: 
74:     Verifies the email/password against Firebase Identity Toolkit (the same
75:     backend that powers client-side sign-in), then returns a one-time custom
76:     token the client exchanges through the Firebase SDK. Failed attempts are
77:     tracked in a per-IP sliding window (5 failures / 15 minutes); the 6th
78:     attempt is rejected with 429 + Retry-After before the provider is even
79:     contacted.
80:     """
81:     await enforce_login_rate_limit(request)
82: 
83:     try:
84:         user = await login_service.verify_credentials(body.email, body.password)
85:     except login_service.LoginProviderError:
86:         raise HTTPException(
87:             status_code=503,
88:             detail="Authentication provider unavailable. Please try again shortly.",
89:         )
90: 
91:     if not user:
92:         await record_login_failure(request)
93:         raise HTTPException(status_code=401, detail="Invalid email or password")
94: 
95:     await clear_login_failures(request)
96:     custom_token = await asyncio.to_thread(login_service.mint_custom_token, user["uid"])
97: 
98:     ip, request_id = request_context(request)
99:     log_audit(
100:         action="LOGIN",
101:         user=user.get("email") or body.email,
102:         tenant_id=None,
103:         ip=ip,
104:         request_id=request_id,
105:     )
106:     return {
107:         "success": True,
108:         "custom_token": custom_token,
109:         "uid": user["uid"],
110:         "email": user.get("email") or body.email,
111:     }
112: 
113: 
114: class RegisterRequest(BaseModel):
115:     email: EmailStr
116:     password: str
117:     full_name: str
118:     organization: str
119:     role: str = settings.ROLE_DEFAULT_REGISTRATION
120:     tenant_id: Optional[str] = None
121: 
122: 
123: @router.post("/verify")
124: @rate_limit("auth_attempts")
125: async def verify_token(request: Request, body: LoginRequest):
126:     decoded_token = verify_firebase_token(body.id_token)
127:     if not decoded_token:
128:         raise HTTPException(status_code=401, detail="Invalid token")
129:     role = decoded_token.get('role', settings.ROLE_DEFAULT)
130:     tenant_id = decoded_token.get('tenant_id')
131:     resolved = resolve_user_context(decoded_token.get('email', ''), role, tenant_id)
132:     ip, request_id = request_context(request)
133:     log_audit(
134:         action="LOGIN",
135:         user=decoded_token.get('email', ''),
136:         tenant_id=resolved["tenant_id"],
137:         ip=ip,
138:         request_id=request_id,
139:     )
140:     return {
141:         "uid": decoded_token['uid'],
142:         "email": decoded_token.get('email', ''),
143:         "role": resolved["role"],
144:         "tenant_id": resolved["tenant_id"],
145:     }
146: 
147: @router.post("/register")
148: @rate_limit("register")
149: async def register_user(
150:     request: Request,
151:     body: RegisterRequest,
152:     _app_check: None = Depends(verify_app_check),
153: ):
154:     try:
155:         allowed_roles = {settings.ROLE_DEFAULT_REGISTRATION}
156:         if body.role not in allowed_roles:
157:             raise HTTPException(
158:                 status_code=403,
159:                 detail=f"Registration role must be one of: {', '.join(allowed_roles)}"
160:             )
161:         try:
162:             validate_corporate_email(body.email)
163:         except DisposableEmailError:
164:             raise HTTPException(status_code=400, detail=DISPOSABLE_EMAIL_MESSAGE)
165: 
166:         auth = get_auth()
167:         user = auth.create_user(
168:             email=body.email,
169:             password=body.password,
170:             display_name=body.full_name,
171:             email_verified=False,
172:         )
173: 
174:         claims = {"role": body.role}
175:         if body.tenant_id:
176:             claims["tenant_id"] = body.tenant_id
177: 
178:         auth.set_custom_user_claims(user.uid, claims)
179: 
180:         now = datetime.now(timezone.utc)
181:         upsert_user_doc(user.uid, {
182:             "uid": user.uid,
183:             "email": user.email,
184:             "display_name": body.full_name,
185:             "role": body.role,
186:             "tenant_id": body.tenant_id,
187:             "created_at": now,
188:             "updated_at": now,
189:         })
190: 
191:         ip, request_id = request_context(request)
192:         log_audit(
193:             action="REGISTER",
194:             user=body.email,
195:             tenant_id=body.tenant_id,
196:             ip=ip,
197:             request_id=request_id,
198:         )
199: 
200:         return {
201:             "success": True,
202:             "uid": user.uid,
203:             "email": user.email,
204:             "role": body.role,
205:             "tenant_id": body.tenant_id,
206:         }
207: 
208:     except HTTPException:
209:         raise
210:     except Exception as e:
211:         raise HTTPException(status_code=400, detail=str(e))
212: 
213: @router.post("/refresh")
214: async def refresh_token(request: Request):
215:     """Refresh Firebase ID token."""
216:     # Client handles token refresh using Firebase SDK
217:     # This endpoint just returns a success response
218:     return {"success": True, "message": "Token refresh handled by client"}
219: 
220: 
221: class RegisterTenantRequest(BaseModel):
222:     organization_name: str = Field(..., min_length=2, max_length=120)
223:     classification: OperationalScope
224:     admin_full_name: str = Field(..., min_length=1)
225:     admin_title: str = Field(..., min_length=1)
226:     email: EmailStr
227:     password: str
228:     confirm_password: str
229:     beta_access_key: Optional[str] = None
230: 
231: 
232: @router.post("/register-tenant")
233: @rate_limit("register_tenant")
234: async def register_tenant_endpoint(
235:     request: Request,
236:     body: RegisterTenantRequest,
237:     background_tasks: BackgroundTasks,
238:     _app_check: None = Depends(verify_app_check),
239: ):
240:     """Self-service tenant registration (beta portal).
241: 
242:     Provisions the primary administrator (AIRLINE_ADMIN / safety), initialises
243:     the operational profile at ``tenants/{tenant_id}/profile/operational`` and
244:     issues a unique team invite code for colleague onboarding.
245: 
246:     After honeypot validation (frontend), the disposable-email check and
247:     database provisioning have all passed, a Gmail acknowledgment is scheduled
248:     in the background — SMTP problems never block or roll back a valid record.
249:     """
250:     if body.password != body.confirm_password:
251:         raise HTTPException(status_code=422, detail="Passwords do not match")
252:     try:
253:         result = register_tenant(
254:             organization_name=body.organization_name,
255:             classification=body.classification.value,
256:             admin_full_name=body.admin_full_name,
257:             admin_title=body.admin_title,
258:             email=body.email,
259:             password=body.password,
260:             beta_access_key=body.beta_access_key,
261:             request=request,
262:         )
263:     except DisposableEmailError as e:
264:         raise HTTPException(status_code=400, detail=str(e))
265:     except PermissionError as e:
266:         raise HTTPException(status_code=403, detail=str(e))
267:     except ValueError as e:
268:         raise HTTPException(status_code=422, detail=str(e))
269:     except RuntimeError as e:
270:         raise HTTPException(status_code=500, detail=str(e))
271: 
272:     # Provisioning succeeded: schedule the registration acknowledgment. It runs
273:     # after the response is sent and never raises, so a mail outage cannot
274:     # surface an error to the applicant or roll back the tenant.
275:     background_tasks.add_task(
276:         send_registration_acknowledgment,
277:         to_email=body.email,
278:         contact_name=body.admin_full_name,
279:         organization_name=body.organization_name,
280:     )
281: 
282:     return {"success": True, **result}
283: 
284: 
285: @router.get("/verify-invite")
286: @rate_limit("verify_invite")
287: async def verify_invite_endpoint(
288:     request: Request,
289:     code: Optional[str] = Query(None, description="Team invite code"),
290:     _app_check: None = Depends(verify_app_check),
291: ):
292:     """Real-time invite-code verification for /join.html.
293: 
294:     Confirms the code belongs to an active tenant and returns the organization
295:     name, tenant id and operational category so the join form can greet the
296:     invitee. Deliberately reveals nothing about the tenant when the code is
297:     unknown or inactive.
298:     """
299:     try:
300:         result = verify_invite(get_db(), code)
301:     except LookupError:
302:         return JSONResponse(
303:             status_code=404,
304:             content={"valid": False, "error": "Invalid or expired invite code"},
305:         )
306:     except ValueError:
307:         return JSONResponse(
308:             status_code=400,
309:             content={"valid": False, "error": "Invalid or expired invite code"},
310:         )
311:     return result
312: 
313: 
314: class JoinTeamRequest(BaseModel):
315:     invite_code: Optional[str] = None
316:     tenant_id: Optional[str] = None
317:     full_name: str = Field(..., min_length=1)
318:     email: EmailStr
319:     password: str
320:     confirm_password: str
321:     department: str = Field(..., min_length=1)
322:     operational_role: Optional[str] = Field(None, max_length=100)
323: 
324: 
325: @router.post("/join-team")
326: @rate_limit("join_team")
327: async def join_team_endpoint(
328:     request: Request,
329:     body: JoinTeamRequest,
330:     _app_check: None = Depends(verify_app_check),
331: ):
332:     """Self-register a department postholder under an existing tenant."""
333:     if body.password != body.confirm_password:
334:         raise HTTPException(status_code=422, detail="Passwords do not match")
335:     try:
336:         result = join_team(
337:             invite_code=body.invite_code,
338:             tenant_id=body.tenant_id,
339:             full_name=body.full_name,
340:             email=body.email,
341:             password=body.password,
342:             department=body.department,
343:             operational_role=body.operational_role,
344:             request=request,
345:         )
346:     except DuplicateEmailError as e:
347:         raise HTTPException(
348:             status_code=409,
349:             detail="An account with this email address already exists.",
350:         )
351:     except DisposableEmailError as e:
352:         raise HTTPException(status_code=400, detail=str(e))
353:     except LookupError as e:
354:         raise HTTPException(status_code=404, detail=str(e))
355:     except ValueError as e:
356:         raise HTTPException(status_code=422, detail=str(e))
357:     except RuntimeError as e:
358:         raise HTTPException(status_code=500, detail=str(e))
359: 
360:     return {"success": True, **result}
361: 
362: 
363: @router.get("/tenant-lookup")
364: @rate_limit("auth_attempts")
365: async def tenant_lookup_endpoint(
366:     request: Request,
367:     code: Optional[str] = Query(None, description="Team invite code"),
368:     tenant_id: Optional[str] = Query(None, description="Tenant id / slug"),
369:     _app_check: None = Depends(verify_app_check),
370: ):
371:     """Public tenant lookup for /join.html.
372: 
373:     Resolves a tenant from its invite code (or a ?tenant= tenant id) so the
374:     join form can render only the departments applicable to that
375:     classification. Reveals only the org name + department codes — the caller
376:     must already know the invite code to get this far.
377:     """
378:     try:
379:         tid, tenant_doc = resolve_tenant(get_db(), code, tenant_id)
380:     except LookupError as e:
381:         raise HTTPException(status_code=404, detail=str(e))
382:     except ValueError as e:
383:         raise HTTPException(status_code=422, detail=str(e))
384: 
385:     departments = tenant_doc.get("applicable_departments") or []
386:     return {
387:         "success": True,
388:         "tenant_id": tid,
389:         "tenant_name": tenant_doc.get("name"),
390:         "classification": tenant_doc.get("tenant_type") or tenant_doc.get("classification"),
391:         "operates_flights": tenant_doc.get("operates_flights"),
392:         "applicable_departments": [
393:             {"code": d, "label": DEPARTMENT_LABELS.get(d, d)} for d in departments
394:         ],
395:     }

(End of file - total 395 lines)
</content>
```

**Tool: glob**

**Input:**
```json
{
  "pattern": "backend/app/services/auth*.py"
}
```

**Output:**
```
No files found
```

**Tool: grep**

**Input:**
```json
{
  "pattern": "invite|Invite|team|Team",
  "include": "*.html",
  "path": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public"
}
```

**Output:**
```
Found 49 matches
C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\contact.html:
  Line 44:         <p>Have questions about AviaSAFE SMS? Reach out to our team — we usually respond within one business day.</p>


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\join.html:
  Line 6:     <title>Join Your Team | AviaSAFE SMS</title>

  Line 103:             <p>Join your organization's safety team</p>

  Line 109:                     <label for="inviteCode">Organization Invite Code</label>

  Line 110:                     <input type="text" id="inviteCode" class="form-control"

  Line 131:                         <option value="">— Enter a valid invite code to load departments —</option>

  Line 169:                     <i class="fas fa-user-plus"></i> Join Team

  Line 202: // TEAM ONBOARDING — real-time invite-code verification, mandatory invitee

  Line 203: // profile, and least-privilege provisioning via /api/v1/auth/join-team.

  Line 204: // On success the invitee is signed in automatically and routed to their

  Line 268: // Real-time invite verification against /api/v1/auth/verify-invite.

  Line 269: async function verifyInvite(code) {

  Line 270:     renderVerifyStatus('checking', 'Verifying invite code…');

  Line 272:         var resp = await fetch(getApiBaseUrl() + '/api/v1/auth/verify-invite?code=' + encodeURIComponent(code), {

  Line 284:         disableDepartments('— Enter a valid invite code to load departments —');

  Line 311:             disableDepartments('— Invite code not found —');

  Line 334:         document.getElementById('inviteCode').value = code.toUpperCase();

  Line 335:         verifyInvite(code.toUpperCase());

  Line 339: // Real-time verification with a 300ms debounce on the invite code field.

  Line 340: var inviteDebounce = null;

  Line 341: document.getElementById('inviteCode').addEventListener('input', function () {

  Line 343:     clearTimeout(inviteDebounce);

  Line 348:         disableDepartments('— Enter a valid invite code to load departments —');

  Line 351:     inviteDebounce = setTimeout(function () {

  Line 352:         verifyInvite(value);

  Line 394:     var inviteCode = document.getElementById('inviteCode').value.trim().toUpperCase();

  Line 403:     if (!inviteCode || !fullName || !email || !department || !operationalRole || !password) {

  Line 408:         showError('Please enter a valid, verified invite code before joining.');

  Line 438:         invite_code: inviteCode,

  Line 457:         var resp = await fetch(getApiBaseUrl() + '/api/v1/auth/join-team', {

  Line 471:             showError((data && data.detail) || 'Unable to join. Check the invite code and try again.');


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\index.html:
  Line 586:                                 Register your Airline, AMO, Aerodrome, or CAA for a full multi-tenant SMS workspace. Generate invite codes for your departmental postholders.

  Line 594:                     <!-- Card 2: Join with Invite Code -->

  Line 600:                             <h4 class="text-2xl font-bold text-slate-900 mb-2">Have an Invite Code?</h4>

  Line 602:                                 Postholders, pilots, engineers, and ground staff joining an existing organization. Enter your unique invite code to auto-connect your profile.

  Line 606:                             <i class="fa-solid fa-ticket text-emerald-600"></i> Join Team with Invite Code


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\register.html:
  Line 59:         .success-box .invite-code {

  Line 106:                     <p class="form-hint">Determines flight-operation scope and the departments your team can hold.</p>

  Line 164:                 <p style="margin-top: var(--spacing-xs);"><strong>Team Invite Code:</strong>

  Line 165:                     <span class="invite-code" id="successInviteCode"></span></p>

  Line 168:                 Share the invite code with department postholders (Flight Ops, CAMO, Part-145, QA, Airside) so they can

  Line 169:                 join your team. Sign in with your administrator email to access the full dashboard.

  Line 173:                     <i class="fas fa-users"></i> Continue to Team Onboarding

  Line 345:             document.getElementById('successInviteCode').textContent = data.team_invite_code;

  Line 347:                 encodeURIComponent(data.tenant_id) + '&code=' + encodeURIComponent(data.team_invite_code);


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\login.html:
  Line 152:             <a href="/join.html">Join Your Team</a>


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\report\mor.html:
  Line 425:                     <div class="form-hint">Factual description only — analysis will be performed by the safety team and AI after submission.</div>


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\report\vsr.html:
  Line 164:                             <div class="toggle-subtext">Your identity will not be recorded. The safety team cannot follow up, but your report will still be investigated.</div>

  Line 404:                     <div class="form-hint">Factual description only — analysis is performed by the safety team and AI after submission.</div>

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 8.9s)

_Thinking:_

The current auth flow uses `/api/v1/auth/join-team` and `/api/v1/auth/verify-invite`. The task references:
- `POST /api/v1/auth/invite` (and `/api/auth/invite`)
- `POST /api/v1/auth/join`

Hmm, these endpoints don't exist in the current auth.py. Let me search more broadly for "invite" endpoints across the backend — maybe there's an admin invite endpoint elsewhere. Let me search the whole backend for "invite" and for `team` management. Also the task mentions a service `auth_service.py` which doesn't exist. And `settings/team.html` frontend which doesn't exist either.

Let me search the backend for invite-related code (routes/admin.py? can_cap? user management?).

The spec references endpoints/services that may not exist yet. Let me search the backend more broadly

**Tool: grep**

**Input:**
```json
{
  "include": "*.py",
  "pattern": "invite|Invite|team_invite|join_team|verify_invite",
  "path": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend"
}
```

**Output:**
```
Found 100 matches (more matches available)
C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\tests\test_auth.py:
  Line 1: """Self-service onboarding safeguards: real-time invite verification and

  Line 5:   * GET  /api/v1/auth/verify-invite  (valid / invalid / inactive / blank code,

  Line 10: Invite verification deliberately reveals nothing when a code is unknown or

  Line 165:                  departments=None, invite_code="ABC123", active=True, status=None):

  Line 172:         "team_invite_code": invite_code,

  Line 180: def _join_body(tid="yeti-airlines", department="flight_ops", invite_code="ABC123",

  Line 183:         "invite_code": invite_code,

  Line 198: # GET /api/v1/auth/verify-invite

  Line 201: def test_verify_invite_valid_code(monkeypatch):

  Line 204:     _seed_tenant(db, invite_code="ABC123")

  Line 206:     resp = TestClient(app).get("/api/v1/auth/verify-invite?code=ABC123")

  Line 215: def test_verify_invite_is_case_insensitive(monkeypatch):

  Line 218:     _seed_tenant(db, invite_code="ABC123")

  Line 220:     resp = TestClient(app).get("/api/v1/auth/verify-invite?code=abc123")

  Line 225: def test_verify_invite_invalid_code(monkeypatch):

  Line 227:     resp = TestClient(app).get("/api/v1/auth/verify-invite?code=ZZZZZZ")

  Line 231:     assert body["error"] == "Invalid or expired invite code"

  Line 234: def test_verify_invite_blank_code(monkeypatch):

  Line 236:     resp = TestClient(app).get("/api/v1/auth/verify-invite")

  Line 241: def test_verify_invite_inactive_tenant_rejected(monkeypatch):

  Line 244:     _seed_tenant(db, invite_code="OFF000", active=False)

  Line 246:     resp = TestClient(app).get("/api/v1/auth/verify-invite?code=OFF000")

  Line 250:     assert body["error"] == "Invalid or expired invite code"

  Line 253: def test_verify_invite_suspended_status_rejected(monkeypatch):

  Line 256:     _seed_tenant(db, invite_code="SUS000", status="inactive")

  Line 258:     resp = TestClient(app).get("/api/v1/auth/verify-invite?code=SUS000")

  Line 267: def test_join_team_duplicate_email_returns_409(monkeypatch):

  Line 286: def test_join_team_duplicate_email_never_creates_user_doc(monkeypatch):

  Line 302: def test_join_team_stores_operational_role(monkeypatch):

  Line 324: def test_join_team_weak_password_rejected(monkeypatch):

  Line 341: def test_join_team_password_with_uppercase_and_digit_accepted(monkeypatch):


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\core\config.py:
  Line 55:     # requires the enterprise access key / admin invite code) and beta sandbox


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\middleware\rate_limit.py:
  Line 51:     "join_team":     (30, 3600),     # 30/hour per IP (team-member onboarding)

  Line 63: #   verify_invite: 10 invite-verification attempts / hour / IP

  Line 70:     "verify_invite": (10, 3600),


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\middleware\app_check.py:
  Line 5: #          endpoints — self-service registration, team onboarding, invite


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\tests\test_anti_spam_guardrails.py:
  Line 8:   * GET  /api/v1/auth/verify-invite     - sliding-window limit (10/hour/IP)

  Line 284:                invite_code="ABC123", **overrides):

  Line 286:         "invite_code": invite_code,

  Line 298: def _seed_tenant(db, tid="yeti-airlines", invite_code="ABC123", active=True):

  Line 305:         "team_invite_code": invite_code,

  Line 448: def test_join_team_disposable_email_rejected(monkeypatch):

  Line 463: def test_join_team_corporate_email_still_accepted(monkeypatch):

  Line 678: # GET /api/v1/auth/verify-invite - sliding-window rate limit

  Line 681: def test_verify_invite_rate_limit_429_with_retry_after(monkeypatch):

  Line 684:     _seed_tenant(db, invite_code="ABC123")

  Line 689:         resp = client.get("/api/v1/auth/verify-invite?code=ABC123")

  Line 692:     resp = client.get("/api/v1/auth/verify-invite?code=ABC123")


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\auth.py:
  Line 40:     join_team,

  Line 42:     verify_invite,

  Line 244:     issues a unique team invite code for colleague onboarding.

  Line 285: @router.get("/verify-invite")

  Line 286: @rate_limit("verify_invite")

  Line 287: async def verify_invite_endpoint(

  Line 289:     code: Optional[str] = Query(None, description="Team invite code"),

  Line 292:     """Real-time invite-code verification for /join.html.

  Line 296:     invitee. Deliberately reveals nothing about the tenant when the code is

  Line 300:         result = verify_invite(get_db(), code)

  Line 304:             content={"valid": False, "error": "Invalid or expired invite code"},

  Line 309:             content={"valid": False, "error": "Invalid or expired invite code"},

  Line 315:     invite_code: Optional[str] = None

  Line 326: @rate_limit("join_team")

  Line 327: async def join_team_endpoint(

  Line 336:         result = join_team(

  Line 337:             invite_code=body.invite_code,

  Line 367:     code: Optional[str] = Query(None, description="Team invite code"),

  Line 373:     Resolves a tenant from its invite code (or a ?tenant= tenant id) so the

  Line 376:     must already know the invite code to get this far.


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\tests\test_self_service_registration.py:
  Line 5:     operational-profile initialisation, invite-code issuance, beta access key)

  Line 6:   * POST /api/v1/auth/join-team        (invite-code / tenant-id resolution,

  Line 231:                  departments=None, invite_code="ABC123"):

  Line 238:         "team_invite_code": invite_code,

  Line 300: def test_register_tenant_issues_6char_invite_code(monkeypatch):

  Line 306:     code = resp.json()["team_invite_code"]

  Line 308:     assert db.tenants["summit-air"]["team_invite_code"] == code

  Line 484: def _join_body(tid="yeti-airlines", department="flight_ops", invite_code="ABC123", **overrides):

  Line 486:         "invite_code": invite_code,

  Line 499: def test_join_team_by_invite_code(monkeypatch):

  Line 526: def test_join_team_camo_department_label(monkeypatch):

  Line 541: def test_join_team_part145_department_label(monkeypatch):

  Line 548:                 invite_code="MRO000")

  Line 552:         json=_join_body(tid="ktm-mro", invite_code="MRO000",

  Line 560: def test_join_team_by_tenant_id_without_code(monkeypatch):

  Line 568:         json=_join_body(invite_code=None),

  Line 574: def test_join_team_amo_rejects_flight_departments(monkeypatch):

  Line 582:                 invite_code="MRO000")

  Line 587:             json=_join_body(tid="ktm-mro", invite_code="MRO000", department=dept),

  Line 594:         json=_join_body(tid="ktm-mro", invite_code="MRO000", department="maintenance_145"),

  Line 599: def test_join_team_unknown_invite_code(monkeypatch):

  Line 601:     resp = TestClient(app).post("/api/v1/auth/join-team", json=_join_body(invite_code="ZZZZZZ"))

  Line 605: def test_join_team_unknown_tenant_id(monkeypatch):

  Line 611: def test_join_team_password_mismatch(monkeypatch):

  Line 620: def test_join_team_missing_locator(monkeypatch):

  Line 624:         json=_join_body(tid=None, invite_code=None),

  Line 629: def test_join_team_mismatched_invite_code_rejected(monkeypatch):

  Line 630:     """A tenant_id with a non-matching invite code must not join."""

  Line 634:     _seed_tenant(db, invite_code="ABC123")

  Line 638:         json=_join_body(tid="yeti-airlines", invite_code="ZZZ999"),

  Line 648: def test_tenant_lookup_by_invite_code(monkeypatch):

  Line 651:     _seed_tenant(db, invite_code="ABC123")


(Results truncated. Consider using a more specific path or pattern.)
```

---

## User

---

## Assistant (Compaction · DeepSeek V4 Flash Free · 40.2s)

_Thinking:_

Let me construct the new summary by combining the prior summary with the conversation that followed.

Key events in the conversation (after the prior summary):
1. The Gmail REST migration was completed: 
   - Removed unused `asyncio` import from gmail_dispatcher.py
   - Verified auth.py route call site (lines 255-284) — Starlette awaits async background tasks, no change needed
   - Rewrote `backend/scripts/test_smtp_live.py` → `backend/scripts/test_gmail_live.py` (REST diagnostic), deleted old script via `git rm`
   - Rewrote `backend/tests/test_gmail_dispatcher.py` for REST flow with fake httpx.AsyncClient; fixed RFC 2047 subject decoding issue with `_decoded_header`; 10 passed
   - Full backend suite: 420 passed (423 - 13 old + 10 new)
   - Committed `2c6ad3a`, pushed to main + feat/betasms-self-service
2. User asked "update project status please" — assistant reported status
3. User requested email deliverability optimization in gmail_dispatcher.py:
   - Added MIMEMultipart("alternative") with plain-text fallback + HTML
   - Added `Auto-Submitted: auto-generated` and `X-Auto-Response-Suppress: All` headers
   - Updated tests, 10 passed (gmail) / 420 passed (full)
   - Committed `57a8992`, pushed both branches
4. User requested Phase 2: CAAN CAR-19 / SRM Mathematical Engine & Analysis Model Selector:
   - Created `backend/app/services/srm_engine.py` with calculate_severity, calculate_bqv, calculate_probability, evaluate_risk_profile (+ evaluate_barrier, evaluate_barriers, analyse helpers)
   - Verified engine against benchmark: Wheel Jack Sunk (pax=0, worker=4, quality=3, asset=4, rep=1 → 23 → D; existing BSV 4 → 4D Tolerable; consolidated BSV 14 → 1D Acceptable; signoff Safety Manager / SAG Member)
   - Added models to `backend/app/models/hazard.py`: AnalysisMode enum, SeverityInput, BarrierQuality, BarrierConfig, SramBarriers, BowtieElement, BowtieConfig, SramCalculateRequest, SramData, SramSaveRequest; added analysis_mode + sram_data to HazardCreate/HazardUpdate; added Dict/Any to typing import
   - Persist fields in `hazard_service.py` create_hazard doc_data
   - Added endpoints to `routes/hazards.py`: POST /{hazard_id}/sram/calculate, PUT /{hazard_id}/sram/save + helpers `_severity_inputs`, `_barrier_lists`; updated `_to_hazard_response`; save updates Master Risk register (severity, probability, risk_index, srm_conducted, srm_date, srm_status), validates severity consistency (422 on mismatch), 422 on invalid analysis_mode, logs SRAM_CALCULATED/SRAM_SAVED audits
   - Added `sram_data: Optional[dict] = None` to CAPFormFields in `models/can_cap.py` and persistence in `can_cap_service.py` submit_cap
   - Wrote `backend/tests/test_srm_engine.py` with 27 tests (engine unit + endpoint tests using MockFirestoreClient pattern); fixed `_barrier_lists` keys (ecb_barriers etc.), fixed bqv band boundary test, fixed tenant id test-airline vs test_airline
   - Full backend suite: 447 passed
   - Frontend: added `sramCalculate`/`sramSave` to `public/js/hazards.js`; created `public/css/srm.css` (SRM workspace styles); created `public/js/srm.js` (SRM module: computeSeverity/computeBqv/computeProbability/evaluateRiskProfile mirrors, SrmWorkspace class, attachCombined helper, openBarrierQualityModal, barrierPillHtml); integrated into `public/hazards/detail.html` (srm.css link, SRM card with #srmWorkspace, srm.js script, initSrm() in renderHazard); integrated into `public/can_cap/cap_submit.html` (srm.css link, srmCombinedPanel div after fishbone editor, srm.js script, initFishbone → initSrmCombined, initResidualSra syncs severity letter via srmCombined.setSeverityLetter, added refreshPromotion method to attachCombined return)
   - node --check on srm.js and hazards.js passes

The conversation ends mid-task: still need to:
- Verify cap_submit.html inline script integration (the submitCap function needs to include sram_data in the payload — wait, I edited initFishbone and initResidualSra, but did I update submitCap to include srm_data? Looking at the conversation, I planned to but the last edits were: initFishbone/initResidualSra edit, then adding refreshPromotion to srm.js. The submitCap modification wasn't done yet in the visible conversation. Actually let me re-read: The user chose Option 1 mapping. Then the edits to cap_submit were:
  1. Add srm.css link (done)
  2. Add srmCombinedPanel div (done)
  3. Add srm.js script tag + let declarations (done)
  4. Replace initFishbone + initResidualSra (done)
  5. Add refreshPromotion to attachCombined return (done)
  
  The "submitCap include sram_data" edit has NOT been done yet as of the last message. So that's a next step.
- Also need to ensure the fishbone onChange passes refreshPromotion correctly (done)
- Frontend integrity checks: node --check (done for srm.js, hazards.js), check-inline-scripts.js, frontend suites — not yet run
- Full pytest — already run (447 passed) after backend changes, but frontend changes don't affect pytest. Should re-run to be safe? Backend hasn't changed since 447 passed. So fine.
- Commit, sync branch, push both branches, verify deploy
- The user's Phase 2 asked for tests + "Run full pytest test suite and frontend integrity checks" + "Commit, push to main and feat/betasms-self-service, and verify deployment" — these are pending.

Also note: previous deliverability round committed `57a8992`; Phase 2 is now the active work — not yet committed.

Key facts to carry forward:
- Branch reality: main = feat/betasms-self-service; HEAD is `57a8992` (deliverability commit) with Phase 2 changes uncommitted in working tree (config.py was committed in 2c6ad3a; wait no — config.py changes were part of 2c6ad3a. The new uncommitted files: srm_engine.py, srm.js, srm.css, test_srm_engine.py, models/hazard.py, routes/hazards.py, hazard_service.py, models/can_cap.py, can_cap_service.py, hazards.js, detail.html, cap_submit.html)
- Never commit: Survey Questions PDF/TXT, aviasafe_sms_hybrid_landing_page.html, opencode_design_system_plan.md, *-sa.json
- Deploy commands: render auto-redeploys backend on push to main; firebase hosting deploy: `firebase deploy --project aerosafety-sms-prod --only hosting:aerosafety-sms-beta,hosting:aerosafety-sms-prod`; live URLs
- PowerShell shell: no rg, use Select-String or grep tool
- Frontend mapping decision: user chose Option 1 — map to real pages: public/hazards/detail.html and public/can_cap/cap_submit.html
- Verification baseline: backend 447 passed after Phase 2 tests (420 + 27); frontend suites + node --check + check-inline-scripts.js public (48/48) previously all pass; new srm.js/hazards.js syntax OK
- Gmail dispatcher REST + deliverability: done, committed 2c6ad3a + 57a8992

Current HEAD: 57a8992 (committed). Phase 2 changes uncommitted.

Next Move:
1. Update submitCap in cap_submit.html inline script to include sram_data from srmCombined.getSramData() in the payload (the pending integration piece)
2. Run frontend integrity checks: node --check (or node frontend-tests/check-inline-scripts.js public), frontend suites (dashboard, input-guard, tenant-context)
3. Possibly re-run backend pytest quickly to confirm (already 447 passed — optional)
4. Commit Phase 2, git branch -f feat/betasms-self-service main, push both branches, verify Render redeploy + check /health
5. Consider firebase hosting deploy? Phase 2 changes public/ files (detail.html, cap_submit.html, srm.js, srm.css, hazards.js) — so YES, a Firebase hosting deploy IS needed this time, unlike the Gmail round. Add firebase deploy.

Wait — the user says "verify deployment". Since public/ files changed, need both backend redeploy (push) and firebase hosting deploy. Note this in Next Move.

Also note tests: the user asked to run full pytest — done (447 passed). Frontend integrity checks pending.

Also audit: the SRM workspace initSrm in detail.html — need to verify inline script still valid (check-inline-scripts will catch).

Relevant files list:
- backend/app/services/srm_engine.py (new)
- backend/app/routes/hazards.py (endpoints)
- backend/app/models/hazard.py (SRAM models)
- backend/app/models/can_cap.py (sram_data field)
- backend/app/services/can_cap_service.py (sram_data persisted)
- backend/app/services/hazard_service.py (analysis_mode/sram_data in create)
- backend/tests/test_srm_engine.py (27 tests)
- public/js/srm.js (new)
- public/css/srm.css (new)
- public/js/hazards.js (sramCalculate/sramSave)
- public/hazards/detail.html (SRM workspace integration)
- public/can_cap/cap_submit.html (Combined integration — submitCap payload still needs sram_data)
- Gmail files (completed, for reference): gmail_dispatcher.py, scripts/test_gmail_live.py, tests/test_gmail_dispatcher.py

Blockers: none. Note the submitCap sram_data inclusion is a known pending piece.

Important details to preserve:
- SRM engine spec details (weights, bands, ONB config, tolerability matrix, signoff authorities) — put key ones in Important Details for continuation
- Endpoint paths: POST /api/v1/hazards/{hazard_id}/sram/calculate and PUT /{hazard_id}/sram/save (also available under legacy /api/hazards/...)
- Save validation: 422 if severity letter mismatch, 422 if invalid analysis_mode; needs severity_letter in sram_data.severity
- Tenant normalization: test-airline
- Starlette background tasks await async; auth.py unchanged
- API prefixes: API_PREFIX_HAZARDS = /api/v1/hazards, legacy = /api/hazards

Let me structure the output.

## Objective
- Complete Phase 2: CAAN CAR-19 / SRM Mathematical Engine & Analysis Model Selector — backend SRM engine + API endpoints + Firestore persistence, Analysis Model Selector UI in `public/hazards/detail.html` (Bow-Tie SRAM workspace) and Combined RCA+SRAM promotion in `public/can_cap/cap_submit.html`, engine/endpoint tests, full verification, commit/push to `main` + `feat/betasms-self-service`, and deploy (backend auto-redeploy + Firebase hosting since `public/` changed).
- (Prior rounds shipped: Gmail REST migration at `2c6ad3a`; email deliverability plain-text/headers at `57a8992`.)

## Important Details
- **Branch reality**: `main` = `feat/betasms-self-service` = origin. Committed HEAD is `57a8992` (deliverability round). All Phase 2 changes are currently **uncommitted in the working tree**. Workflow: commit, `git branch -f feat/betasms-self-service main`, push both; Render redeploys backend on push.
- **Frontend file mapping (user-confirmed Option 1)**: requested `hazard-detail.html`/`capa.html` don't exist → use `public/hazards/detail.html` and `public/can_cap/cap_submit.html`. Reuse `fishbone.js` (`Fishbone.renderEditor`) and `HazardsAPI`.
- **Never commit**: `Survey Questions for AviaSAFE-SMS.pdf`, `Survey Questions for AviaSAFE-SMS.txt`, `aviasafe_sms_hybrid_landing_page.html`, `opencode_design_system_plan.md`, `*-sa.json`.
- **Deploy**: push → Render backend redeploy; **Firebase hosting deploy IS required this round** (public/ files changed): `firebase deploy --project aerosafety-sms-prod --only hosting:aerosafety-sms-beta,hosting:aerosafety-sms-prod`; APIs `https://sms-aviasafesystems-beta.onrender.com`, `https://sms.aviasafesystems.com`.
- **Shell**: PowerShell; use grep tool or `Select-String` (no `rg`).
- **SRM engine spec (implemented)**: severity = 4·pax + 3·worker + 2·quality + asset + rep + sec + env (0-65; ≥52 A Catastrophic, 39-51 B, 26-38 C, 13-25 D, 0-12 E); BQV = 3·effectiveness + cost_benefit + practicality + acceptability + enforceability + durability + 2·disinclination (bands 42-50→5 Excellent … 10-17→1 Poor, 0-9→0 Ineffective); probability bands per severity ONB (A:8/40 … E:2/10), higher CBSV → lower probability; tolerability matrix Intolerable/Tolerable/Acceptable; sign-off: Intolerable→Accountable Manager, Tolerable→Risk Owner / Functional Chief, Acceptable→Safety Manager / SAG Member.
- **Endpoint facts**: `POST /api/v1/hazards/{hazard_id}/sram/calculate` (no persist) and `PUT /api/v1/hazards/{hazard_id}/sram/save` (persists `analysis_mode` + `sram_data`, updates Master Risk register via severity letter→numeric A=5…E=1 × resultant probability; also mounted on legacy `/api/hazards/...`). Save 422s when recomputed severity letter ≠ stored `severity_letter`, or on invalid `analysis_mode`; requires `sram_data.severity.severity_letter`. Audits `SRAM_CALCULATED`/`SRAM_SAVED`.
- **Frontend math**: `public/js/srm.js` mirrors the engine (`computeSeverity`, `computeBqv`, `computeProbability`, `evaluateRiskProfile`) for live preview; works with `HazardsAPI.sramCalculate`/`sramSave` (legacy `/api/hazards/...`).
- **Worker detail**: `srmCombined.setSeverityLetter(letter)` and `refreshPromotion()` exposed; note `srmCombined.refreshPromotion` is called from fishbone onChange — it was bound as a plain function reference on the object, fine.
- Starlette `BackgroundTasks` awaits async callables — no `auth.py` change needed (Gmail round).

## Work State
### Completed
- Gmail REST migration (`2c6ad3a`): async httpx OAuth2 REST dispatcher, `config.py` GMAIL_CLIENT_ID/SECRET/REFRESH_TOKEN/SENDER_EMAIL/NOTIFICATION_BCC, `test_gmail_live.py` (old `test_smtp_live.py` deleted), rewritten `test_gmail_dispatcher.py` (RFC 2047 subject decode helper `_decoded_header`), auth.py verified no change needed, backend 420 passed.
- Email deliverability (`57a8992`): plain-text alternative + HTML in `MIMEMultipart("alternative")`, headers `Auto-Submitted: auto-generated` + `X-Auto-Response-Suppress: All`, tests updated, backend 420 passed.
- Phase 2 backend complete:
  - `services/srm_engine.py`: `calculate_severity`, `calculate_bqv`, `calculate_probability`, `evaluate_barrier`, `evaluate_barriers`, `evaluate_risk_profile`, `analyse`, constants (SEVERITY_BANDS, BQV_BANDS, PROBABILITY_CONFIG, TOLERABILITY_MATRIX, SIGNOFF_AUTHORITY, SEVERITY_LETTER_TO_NUMERIC). Verified against benchmark: Wheel Jack Sunk (worker=4, quality=3, asset=4, rep=1 → score 23 → D; existing BSV 4 → 4D Tolerable; CBSV 14 → 1D Acceptable; sign-off "Safety Manager / SAG Member").
  - `models/hazard.py`: `AnalysisMode` enum, `SeverityInput`, `BarrierQuality`, `BarrierConfig`, `SramBarriers`, `BowtieElement`, `BowtieConfig`, `SramCalculateRequest`, `SramData`, `SramSaveRequest`; `analysis_mode`/`sram_data` on HazardCreate/HazardUpdate.
  - `services/hazard_service.py`: persists `analysis_mode` (default FISHBONE_ONLY) + `sram_data` in create.
  - `routes/hazards.py`: SRAM calculate/save endpoints + `_severity_inputs`, `_barrier_lists` helpers; `_to_hazard_response` includes `analysis_mode`/`sram_data`.
  - `models/can_cap.py` (`sram_data` on CAPFormFields) + `services/can_cap_service.py` submit_cap persists `sram_data`.
  - `tests/test_srm_engine.py`: 27 passed (engine bands/boundaries, Wheel Jack benchmark 4D→1D, sign-off mapping, API calculate-not-persist/404/422, save-persists/updates-master-risk/422-mismatch/404). Full backend **447 passed**.
- Phase 2 frontend (syntax-checked OK):
  - `js/hazards.js`: `sramCalculate`, `sramSave`.
  - `css/srm.css` (new): workspace, mode selector, sliders, bow-tie, pills, BQV modal, risk comparison, sign-off styles.
  - `js/srm.js` (new): `SRM.createWorkspace` (full workspace: mode selector, fishbone via Fishbone.renderEditor, 7 sliders, interactive bow-tie threats/ECM→top event→ERB/consequences + NCM/NRB, BQV modal, before/after, sign-off, Calculate/Save), `SRM.attachCombined` (cap_submit: promotion panel + NCM pills + risk comparison + sign-off, `getSramData()`/`setSeverityLetter`/`refreshPromotion`).
  - `hazards/detail.html`: srm.css link, `#srmWorkspace` card after SRM Status card, srm.js script, `srmWorkspace` global + `initSrm(h)` called in `renderHazard`.
  - `cap_submit.html`: srm.css link, `#srmCombinedPanel` div after `#fishboneEditor`, srm.js script, `srmCombined` global, `initFishbone`→`initSrmCombined()` (passes fishboneController), `initResidualSra` syncs `srmCombined.setSeverityLetter(v.severity_letter)` from `residualSraController.getValue()`.

### Active
- Phase 2 frontend — **`submitCap` in `cap_submit.html` inline script has NOT yet been updated to include `sram_data` from `srmCombined.getSramData()` in the CAP payload** (the backend `CAPFormFields.sram_data` + service persistence are ready).
- Phase 2 verification: `node --check public/js/srm.js` + `hazards.js` passed; `node frontend-tests/check-inline-scripts.js public`, dashboard/input-guard/tenant-context frontend suites, and full `pytest` re-run pending.
- Phase 2 not yet committed/pushed/deployed.

### Blocked
- (none)

## Next Move
1. Update `submitCap` in `public/can_cap/cap_submit.html` to build the payload with `sram_data: srmCombined ? srmCombined.getSramData() : null` (skip when mode FISHBONE_ONLY — `getSramData()` already returns null).
2. Run frontend integrity checks: `node frontend-tests/check-inline-scripts.js public` plus dashboard/input-guard/tenant-context suites; re-run `python -m pytest -q` in `backend/` to confirm 447 stable.
3. Fix any failures, then commit Phase 2 (all touched files), `git branch -f feat/betasms-self-service main`, push `main` + `feat/betasms-self-service` (Render backend redeploy).
4. Deploy Firebase hosting (`... --only hosting:aerosafety-sms-beta,hosting:aerosafety-sms-prod`) since `public/` files changed; verify backend `/health` and a hazard-detail page load 200.
5. Report completion; note remaining manual step if any (e.g., none expected — env vars for Gmail already set on Render dashboard).

## Relevant Files
- `backend/app/services/srm_engine.py`: new CAAN CAR-19 SRM engine (done).
- `backend/app/routes/hazards.py`: SRAM calculate/save endpoints.
- `backend/app/models/hazard.py`: SRAM models + `analysis_mode`/`sram_data`.
- `backend/app/models/can_cap.py` + `backend/app/services/can_cap_service.py`: `sram_data` on CAP submit.
- `backend/tests/test_srm_engine.py`: 27 tests, mock-Firestore pattern; tenant lookup uses `test-airline` (auth normalizes).
- `public/js/srm.js`: SRM workspace + combined panel controllers.
- `public/css/srm.css`: SRM workspace styles.
- `public/js/hazards.js`: `sramCalculate`/`sramSave`.
- `public/hazards/detail.html`: SRM workspace card + `initSrm`.
- `public/can_cap/cap_submit.html`: Combined panel + `initSrmCombined`/`initResidualSra`; **`submitCap` still needs `sram_data` inclusion**.
- Gmail round (reference, done): `backend/app/services/gmail_dispatcher.py`, `backend/tests/test_gmail_dispatcher.py`, `backend/scripts/test_gmail_live.py`.

---

## User

---

## Assistant (Build · DeepSeek V4 Flash Free · 10.2s)

_Thinking:_

The task spec describes endpoints `POST /api/v1/auth/invite` (and `/api/auth/invite`) and `/api/v1/auth/join` that don't currently exist. The existing flow uses:
- `/api/v1/auth/verify-invite` (GET)
- `/api/v1/auth/join-team` (POST) — this is the "join" flow
- `/api/v1/auth/tenant-lookup` (GET)
- `/api/v1/auth/register-tenant` (POST) — issues a team invite code on the tenant doc

There's no admin "invite" endpoint that creates a department-scoped invite document. There's no `backend/app/services/auth_service.py` (the invite logic lives in `backend/app/services/tenant_registration.py`). There's no `public/settings/team.html` frontend.

So the spec is describing a desired design, but the actual codebase has different naming. I need to decide how to map this. Options:

1. Build new endpoints `/api/v1/auth/invite` (POST, protected, role-aware) + `/api/v1/auth/join` (POST, replaces join-team?) — this is what the spec literally asks. But there's an existing `/join-team` endpoint and `join.html` frontend that uses it. Creating a parallel `/join` could be redundant/confusing. However, the spec explicitly asks for `/api/v1/auth/join` resolving department+role from the invite document. The existing join-team allows the invitee to pick their own department, and role defaults to staff.

2. Adapt the existing endpoints: add a new admin-protected `POST /api/v1/auth/invite` endpoint that creates a department-scoped invite doc under `tenants/{tid}/invites/{code}`, and enhance the existing join-team flow to read department/role from the invite doc when present. Also expose the legacy `/api/auth/invite`.

Given the ambiguity, I should clarify with the user how to map the spec's endpoint names to the existing codebase. But the user said "Continue if you have next steps, or stop and ask for clarification if you are unsure how to proceed." 

Let me first explore more to understand the existing structure fully before deciding:
- backend/app/services/tenant_registration.py — join_team, verify_invite, register_tenant, DEPARTMENT_LABELS
- backend/app/routes/ — what other route files exist, and how they're mounted (e.g., admin.py, users.py)
- backend/app/services/users.py — upsert_user_doc
- Is there an existing team management frontend? Search public/ for settings or team pages.
- Check main.py for how routes are mounted, and whether there's a legacy /api/auth alias.
- Look at existing role constants in config.py.
- Check the middleware auth (resolve_user_context).

Let me do a batch of reads/searches.





**Tool: read**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\services\\tenant_registration.py"
}
```

**Output:**
```
<path>C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\services\tenant_registration.py</path>
<type>file</type>
<content>
1: # ============================================================================
2: # FILE: tenant_registration.py
3: # PATH: backend/app/services/tenant_registration.py
4: # PURPOSE: Self-service tenant registration + team-member onboarding for the
5: #          beta portal (betasms.aviasafesystems.com).
6: #
7: #   register_tenant():   creates a slugified tenant_id, provisions the primary
8: #                        administrator (AIRLINE_ADMIN / safety), initialises the
9: #                        operational profile under tenants/{tid}/profile/operational
10: #                        and issues a unique 6-char team invite code.
11: #   join_team():         self-registers a department postholder under an existing
12: #                        tenant via its invite code (or a ?tenant= tenant id).
13: #   resolve_tenant():    public lookup used by /join.html to render the dynamic
14: #                        department dropdown (and by /join-team).
15: #
16: # Errors are raised as exceptions for the route layer to map to HTTP statuses:
17: #   PermissionError -> 403   (beta access key mismatch)
18: #   ValueError      -> 422   (validation failures)
19: #   LookupError     -> 404   (unknown tenant / invite code)
20: #   RuntimeError    -> 500   (persistence failures)
21: # ============================================================================
22: 
23: import re
24: import secrets
25: import string
26: from datetime import datetime, timezone
27: from typing import Any, Dict, Optional, Tuple
28: 
29: from loguru import logger
30: from firebase_admin import auth as firebase_auth
31: 
32: from app.core.config import settings
33: from app.firebase import get_db, get_auth
34: from app.models.tenant_profile import OperationalScope
35: from app.services.audit_service import log_audit, request_context
36: from app.services.users import upsert_user_doc
37: 
38: # Classifications a self-registering organization may select. Regulators and
39: # ground-handling providers are not exposed on the public form.
40: REGISTRATION_SCOPES = (
41:     OperationalScope.AIRLINE_FIXED_WING,
42:     OperationalScope.AIRLINE_ROTARY,
43:     OperationalScope.AMO,
44:     OperationalScope.AERODROME,
45: )
46: 
47: # Human-readable operational category labels for the operational profile.
48: CATEGORY_LABELS = {
49:     OperationalScope.AIRLINE_FIXED_WING: "Fixed-Wing Airline",
50:     OperationalScope.AIRLINE_ROTARY: "Rotary-Wing / Helicopter Operator",
51:     OperationalScope.AMO: "Part-145 Maintenance Organization",
52:     OperationalScope.AERODROME: "Certified Airport / Aerodrome",
53:     OperationalScope.GROUND_HANDLING: "Ground Handling Services",
54:     OperationalScope.REGULATOR: "CAAN Directorates",
55: }
56: 
57: # Department code -> display label + the custom claim value assigned to a
58: # joining postholder. Labels align with the values the frontend already
59: # understands (getDepartmentLabel / getRoleDestination in public/js/firebase.js).
60: DEPARTMENT_LABELS = {
61:     "safety": "Safety",
62:     "flight_ops": "Flight Operations",
63:     "camo": "CAMO",
64:     "maintenance_145": "Part-145",
65:     "qa": "QA",
66:     "airside_ops": "Airside Operations",
67:     "arff": "ARFF (Rescue & Firefighting)",
68:     "ground_ops": "Ground Operations",
69: }
70: 
71: MIN_PASSWORD_LENGTH = 8
72: 
73: # Unambiguous 6-char alphabet for team invite codes (no 0/O or 1/I).
74: INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
75: INVITE_CODE_LENGTH = 6
76: 
77: _NON_SLUG_CHARS = re.compile(r"[^a-z0-9]+")
78: _REPEATED_HYPHENS = re.compile(r"-{2,}")
79: 
80: # Blocklist of disposable / temporary email providers. Registrations using
81: # these domains are rejected outright — self-service accounts must use a real
82: # corporate / organizational mailbox. The list is intentionally modest but
83: # covers the best-known throwaway providers; subdomains (e.g.
84: # mailinator.com aliases) are matched via a suffix check.
85: DISPOSABLE_EMAIL_DOMAINS = frozenset({
86:     "mailinator.com",
87:     "tempmail.com",
88:     "tempmail.net",
89:     "temp-mail.org",
90:     "temp-mail.io",
91:     "guerrillamail.com",
92:     "guerrillamail.net",
93:     "guerrillamail.org",
94:     "guerrillamail.biz",
95:     "guerrillamail.info",
96:     "grr.la",
97:     "10minutemail.com",
98:     "10minutemail.net",
99:     "yopmail.com",
100:     "yopmail.fr",
101:     "yopmail.net",
102:     "yopmail.org",
103:     "throwawaymail.com",
104:     "throwaway.email",
105:     "maildrop.cc",
106:     "getnada.com",
107:     "33mail.com",
108:     "trashmail.com",
109:     "mailnesia.com",
110:     "spamgourmet.com",
111:     "disposablemail.com",
112:     "mailtemp.net",
113: })
114: 
115: # Admin / developer email allowlist. These addresses bypass the corporate-email
116: # restriction (disposable AND consumer webmail domains) completely so the owner
117: # and any listed personal test addresses can self-register a tenant even when
118: # their mailbox uses a consumer provider.
119: ADMIN_EMAIL_ALLOWLIST = frozenset({
120:     "ghanshyamacharya@outlook.com",
121:     # Add any additional personal test addresses if needed
122: })
123: 
124: # Consumer webmail providers. Self-service registration targets corporate /
125: # organizational mailboxes, so these domains (and their subdomains) are treated
126: # as non-corporate and rejected unless the address is on ADMIN_EMAIL_ALLOWLIST.
127: CONSUMER_WEBMAIL_DOMAINS = frozenset({
128:     "gmail.com", "googlemail.com",
129:     "yahoo.com", "yahoo.co.uk", "ymail.com",
130:     "outlook.com", "hotmail.com", "live.com", "msn.com",
131:     "icloud.com", "me.com", "mac.com",
132:     "aol.com",
133:     "protonmail.com", "proton.me",
134:     "zoho.com",
135:     "mail.com", "gmx.com", "gmx.net",
136: })
137: 
138: # User-facing rejection message (mirrored in the frontend validation).
139: DISPOSABLE_EMAIL_MESSAGE = "Please provide a valid corporate or organizational email address."
140: 
141: 
142: class DisposableEmailError(ValueError):
143:     """Raised when a registration uses a disposable / temporary email domain.
144: 
145:     Subclasses ValueError so it can share the route-layer validation flow, but
146:     the auth routes map it to a 400 (not the generic 422) per the anti-spam
147:     contract. Catch it BEFORE the broad ValueError clause.
148:     """
149: 
150: 
151: def email_domain(email: str) -> str:
152:     """Return the lower-cased domain portion of an email address."""
153:     addr = str(email or "").strip().lower()
154:     return addr.rsplit("@", 1)[1] if "@" in addr else addr
155: 
156: 
157: def is_disposable_email(email: str) -> bool:
158:     """True when the email domain (or a subdomain of it) is on the blocklist."""
159:     domain = email_domain(email)
160:     if not domain:
161:         return False
162:     if domain in DISPOSABLE_EMAIL_DOMAINS:
163:         return True
164:     for blocked in DISPOSABLE_EMAIL_DOMAINS:
165:         if domain.endswith("." + blocked):
166:             return True
167:     return False
168: 
169: 
170: def is_admin_allowlisted(email: str) -> bool:
171:     """True when the email is on the admin/dev allowlist (bypasses the
172:     corporate-email restriction entirely)."""
173:     return str(email or "").strip().lower() in ADMIN_EMAIL_ALLOWLIST
174: 
175: 
176: def is_consumer_webmail(email: str) -> bool:
177:     """True when the email uses a consumer webmail provider (or a subdomain of
178:     one) rather than a corporate / organizational mailbox."""
179:     domain = email_domain(email)
180:     if not domain:
181:         return False
182:     if domain in CONSUMER_WEBMAIL_DOMAINS:
183:         return True
184:     for blocked in CONSUMER_WEBMAIL_DOMAINS:
185:         if domain.endswith("." + blocked):
186:             return True
187:     return False
188: 
189: 
190: def validate_corporate_email(email: str) -> None:
191:     """Reject disposable / consumer-webmail domains on self-service
192:     registration, unless the address is on the admin/dev allowlist."""
193:     if is_admin_allowlisted(email):
194:         return
195:     if is_disposable_email(email) or is_consumer_webmail(email):
196:         raise DisposableEmailError(DISPOSABLE_EMAIL_MESSAGE)
197: 
198: 
199: def slugify_organization(name: str) -> str:
200:     """Turn an organization name into a clean lowercase tenant slug."""
201:     slug = _NON_SLUG_CHARS.sub("-", str(name or "").strip().lower())
202:     slug = _REPEATED_HYPHENS.sub("-", slug).strip("-")
203:     return slug or "organization"
204: 
205: 
206: def _invite_code_taken(db: Any, code: str) -> bool:
207:     try:
208:         docs = (
209:             db.collection(settings.FIREBASE_COLLECTION_TENANTS)
210:             .where("team_invite_code", "==", code)
211:             .limit(1)
212:             .get()
213:         )
214:         return len(docs) > 0
215:     except Exception as e:
216:         logger.warning(f"Invite-code uniqueness check failed: {e}")
217:         return False
218: 
219: 
220: def generate_invite_code(db: Any) -> str:
221:     """Return a unique 6-character alphanumeric team invite code."""
222:     for _ in range(25):
223:         code = "".join(secrets.choice(INVITE_ALPHABET) for _ in range(INVITE_CODE_LENGTH))
224:         if not _invite_code_taken(db, code):
225:             return code
226:     raise RuntimeError("Unable to generate a unique team invite code")
227: 
228: 
229: def _unique_tenant_id(db: Any, organization_name: str) -> str:
230:     """Slugify the organization name and guarantee Firestore-document uniqueness."""
231:     base = slugify_organization(organization_name)
232:     candidate = base
233:     suffix = 2
234:     while True:
235:         ref = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(candidate)
236:         try:
237:             exists = ref.get().exists
238:         except Exception as e:
239:             logger.warning(f"Tenant-id existence check failed for {candidate}: {e}")
240:             exists = False
241:         if not exists:
242:             return candidate
243:         candidate = f"{base}-{suffix}"
244:         suffix += 1
245:         if suffix > 1000:  # pragma: no cover - defensive only
246:             raise RuntimeError("Unable to allocate a unique tenant id")
247: 
248: 
249: class DuplicateEmailError(ValueError):
250:     """Raised when the joining/registering email already exists in Firebase Auth."""
251: 
252: 
253: def _validate_password(password: str) -> None:
254:     if not password or len(password) < MIN_PASSWORD_LENGTH:
255:         raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
256:     if not re.search(r"[A-Z]", password):
257:         raise ValueError("Password must contain at least one uppercase letter")
258:     if not re.search(r"\d", password):
259:         raise ValueError("Password must contain at least one digit")
260: 
261: 
262: def _create_user(auth: Any, *, email: str, password: str, display_name: str) -> Any:
263:     """Create a Firebase Auth user, surfacing duplicate emails as an error."""
264:     try:
265:         return auth.create_user(
266:             email=email,
267:             password=password,
268:             display_name=display_name,
269:             email_verified=False,
270:         )
271:     except Exception as e:
272:         duplicate = isinstance(e, firebase_auth.EmailAlreadyExistsError) or (
273:             "email already" in str(e).lower() or "already in use" in str(e).lower()
274:         )
275:         if duplicate:
276:             raise DuplicateEmailError("An account with this email address already exists")
277:         raise RuntimeError(str(e))
278: 
279: 
280: def register_tenant(
281:     *,
282:     organization_name: str,
283:     classification: str,
284:     admin_full_name: str,
285:     admin_title: str,
286:     email: str,
287:     password: str,
288:     beta_access_key: Optional[str] = None,
289:     request=None,
290: ) -> Dict[str, Any]:
291:     """Provision a brand-new self-service tenant + primary administrator."""
292:     _validate_password(password)
293:     validate_corporate_email(email)
294: 
295:     try:
296:         scope = OperationalScope(classification)
297:     except ValueError:
298:         raise ValueError(
299:             "classification must be one of: "
300:             + ", ".join(s.value for s in REGISTRATION_SCOPES)
301:         )
302:     if scope not in REGISTRATION_SCOPES:
303:         raise ValueError(
304:             "classification must be one of: "
305:             + ", ".join(s.value for s in REGISTRATION_SCOPES)
306:         )
307: 
308:     is_beta_env = (settings.ENVIRONMENT or "").strip().lower() in ("beta", "staging", "development")
309:     provided_key = (beta_access_key or "").strip()
310:     if is_beta_env:
311:         # Beta sandbox: the access key is optional; a provided key must match.
312:         if provided_key and provided_key != settings.BETA_ACCESS_KEY:
313:             raise PermissionError("Invalid beta access key")
314:     else:
315:         # Production gate: self-service registration is by invitation only — a
316:         # valid enterprise access code (admin-issued invite key) is mandatory.
317:         # Without it the public form can never provision a tenant.
318:         if provided_key != settings.BETA_ACCESS_KEY:
319:             raise PermissionError(
320:                 "Invalid or missing beta access key. Self-service registration on the "
321:                 "production portal is by invitation only — enter the enterprise access "
322:                 "code provided by AviaSAFE, or contact info@aviasafesystems.com to "
323:                 "request access."
324:             )
325: 
326:     db = get_db()
327:     auth = get_auth()
328:     now = datetime.now(timezone.utc)
329:     tid = _unique_tenant_id(db, organization_name)
330: 
331:     user = _create_user(
332:         auth,
333:         email=email,
334:         password=password,
335:         display_name=admin_full_name,
336:     )
337:     auth.set_custom_user_claims(
338:         user.uid,
339:         {"role": "AIRLINE_ADMIN", "tenant_id": tid, "department": "safety"},
340:     )
341: 
342:     operates_flights = scope.operates_flights
343:     applicable_departments = list(scope.departments)
344:     invite_code = generate_invite_code(db)
345: 
346:     tenant_ref = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tid)
347:     sandbox_tags = {}
348:     if is_beta_env:
349:         # Beta sandbox marker: self-service tenants created on the beta portal
350:         # are flagged for periodic cleanup / evaluation.
351:         sandbox_tags = {"is_beta_sandbox": True, "auto_expire_days": 30}
352:     tenant_ref.set(
353:         {
354:             "tenant_id": tid,
355:             "name": organization_name,
356:             "tenant_type": scope.value,
357:             "classification": scope.value,
358:             "operates_flights": operates_flights,
359:             "applicable_departments": applicable_departments,
360:             "team_invite_code": invite_code,
361:             "active": True,
362:             "status": "Active",
363:             "safety_manager": {
364:                 "email": email,
365:                 "name": admin_full_name,
366:                 "title": admin_title,
367:                 "uid": user.uid,
368:             },
369:             "config": {"survey_rate_limit": settings.SURVEY_RATE_LIMIT},
370:             "created_at": now,
371:             "updated_at": now,
372:             **sandbox_tags,
373:         }
374:     )
375: 
376:     tenant_ref.collection("profile").document("operational").set(
377:         {
378:             "tenant_id": tid,
379:             "slug": tid,
380:             "tenant_name": organization_name,
381:             "email": email,
382:             "category": CATEGORY_LABELS.get(scope, scope.value),
383:             "scope": scope.value,
384:             "tenant_type": scope.value,
385:             "operates_flights": operates_flights,
386:             "applicable_departments": applicable_departments,
387:             "created_at": now,
388:         }
389:     )
390: 
391:     upsert_user_doc(
392:         user.uid,
393:         {
394:             "uid": user.uid,
395:             "email": email,
396:             "display_name": admin_full_name,
397:             "role": "AIRLINE_ADMIN",
398:             "tenant_id": tid,
399:             "department": "safety",
400:             "created_at": now,
401:             "updated_at": now,
402:         },
403:     )
404: 
405:     ip, request_id = request_context(request)
406:     log_audit(
407:         action="TENANT_REGISTERED",
408:         user=email,
409:         tenant_id=tid,
410:         target_type="tenant",
411:         target_id=tid,
412:         ip=ip,
413:         request_id=request_id,
414:         metadata={
415:             "tenant_name": organization_name,
416:             "classification": scope.value,
417:             "operates_flights": operates_flights,
418:         },
419:     )
420: 
421:     logger.info(
422:         f"Self-service tenant registered: {organization_name} -> {tid} "
423:         f"({scope.value}) admin={email}"
424:     )
425: 
426:     return {
427:         "tenant_id": tid,
428:         "tenant_name": organization_name,
429:         "classification": scope.value,
430:         "operates_flights": operates_flights,
431:         "applicable_departments": applicable_departments,
432:         "team_invite_code": invite_code,
433:         "admin_email": email,
434:         "created_at": now,
435:     }
436: 
437: 
438: def resolve_tenant(
439:     db: Any,
440:     invite_code: Optional[str] = None,
441:     tenant_id: Optional[str] = None,
442: ) -> Tuple[str, Dict[str, Any]]:
443:     """Locate a tenant doc by invite code or tenant id.
444: 
445:     Returns (tenant_id, tenant_doc). Raises LookupError when not found and
446:     ValueError when neither locator was supplied.
447:     """
448:     if tenant_id:
449:         tid = tenant_id.strip()
450:         snap = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tid).get()
451:         if not snap.exists:
452:             raise LookupError(f"Unknown tenant: {tid}")
453:         data = snap.to_dict() or {}
454:         if invite_code and invite_code.strip().upper() != str(data.get("team_invite_code") or "").upper():
455:             raise LookupError(f"Invite code does not match tenant {tid}")
456:         return tid, data
457: 
458:     if invite_code:
459:         code = invite_code.strip().upper()
460:         docs = (
461:             db.collection(settings.FIREBASE_COLLECTION_TENANTS)
462:             .where("team_invite_code", "==", code)
463:             .limit(1)
464:             .get()
465:         )
466:         for snap in docs:
467:             return snap.id, snap.to_dict() or {}
468:         raise LookupError(f"No tenant matches invite code: {code}")
469: 
470:     raise ValueError("An invite code or tenant id is required")
471: 
472: 
473: def verify_invite(db: Any, code: Optional[str]) -> Dict[str, Any]:
474:     """Real-time invite-code verification for /join.html.
475: 
476:     Resolves the tenant by invite code and confirms it is active. Returns a
477:     minimal public payload (no internal fields). Raises:
478:       ValueError  -> caller supplied no / blank code
479:       LookupError -> code unknown, or tenant is inactive/expired
480:     """
481:     if not code or not code.strip():
482:         raise ValueError("An invite code is required")
483:     tid, tenant_doc = resolve_tenant(db, code.strip(), None)
484: 
485:     active = tenant_doc.get("active")
486:     status = str(tenant_doc.get("status") or "").lower()
487:     if active is False or status == "inactive":
488:         raise LookupError("Invalid or expired invite code")
489: 
490:     return {
491:         "valid": True,
492:         "organization_name": tenant_doc.get("name") or tid,
493:         "tenant_id": tid,
494:         "category": tenant_doc.get("tenant_type") or tenant_doc.get("classification"),
495:     }
496: 
497: 
498: def join_team(
499:     *,
500:     invite_code: Optional[str] = None,
501:     tenant_id: Optional[str] = None,
502:     full_name: str,
503:     email: str,
504:     password: str,
505:     department: str,
506:     operational_role: Optional[str] = None,
507:     request=None,
508: ) -> Dict[str, Any]:
509:     """Self-register a department postholder under an existing tenant.
510: 
511:     Invitees are provisioned with the least-privilege 'USER' tier scoped to the
512:     tenant_id — they can never self-elevate to AIRLINE_ADMIN / tenant_admin;
513:     that requires a Safety Manager action in the admin console.
514:     """
515:     _validate_password(password)
516:     validate_corporate_email(email)
517: 
518:     db = get_db()
519:     auth = get_auth()
520:     now = datetime.now(timezone.utc)
521: 
522:     try:
523:         tid, tenant_doc = resolve_tenant(db, invite_code, tenant_id)
524:     except LookupError:
525:         raise
526:     except Exception as e:
527:         if isinstance(e, ValueError):
528:             raise
529:         raise LookupError(str(e))
530: 
531:     code = department.strip()
532:     allowed = tenant_doc.get("applicable_departments") or []
533:     if code not in allowed:
534:         raise ValueError(
535:             f"Department '{code}' is not applicable to tenant {tid}. "
536:             f"Allowed: {', '.join(allowed) or 'none'}"
537:         )
538: 
539:     label = DEPARTMENT_LABELS.get(code, code)
540: 
541:     user = _create_user(
542:         auth,
543:         email=email,
544:         password=password,
545:         display_name=full_name,
546:     )
547:     auth.set_custom_user_claims(
548:         user.uid,
549:         {"role": "USER", "tenant_id": tid, "department": label},
550:     )
551: 
552:     user_doc = {
553:         "uid": user.uid,
554:         "email": email,
555:         "display_name": full_name,
556:         "role": "USER",
557:         "tenant_id": tid,
558:         "department": label,
559:         "created_at": now,
560:         "updated_at": now,
561:     }
562:     if operational_role:
563:         user_doc["operational_role"] = operational_role.strip()[:100]
564:     upsert_user_doc(user.uid, user_doc)
565: 
566:     ip, request_id = request_context(request)
567:     log_audit(
568:         action="TEAM_MEMBER_JOINED",
569:         user=email,
570:         tenant_id=tid,
571:         target_type="tenant",
572:         target_id=tid,
573:         ip=ip,
574:         request_id=request_id,
575:         metadata={"department": code, "department_label": label},
576:     )
577: 
578:     logger.info(f"Team member joined tenant {tid}: {email} -> {label}")
579: 
580:     return {
581:         "tenant_id": tid,
582:         "tenant_name": tenant_doc.get("name") or tid,
583:         "classification": tenant_doc.get("tenant_type") or tenant_doc.get("classification"),
584:         "department": code,
585:         "department_label": label,
586:         "admin_email": email,
587:         "created_at": now,
588:     }

(End of file - total 588 lines)
</content>
```

**Tool: glob**

**Input:**
```json
{
  "pattern": "backend/app/routes/*.py"
}
```

**Output:**
```
C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\hazards.py
C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\state_risk.py
C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\contact.py
C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\dashboard.py
C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\__init__.py
C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\verification.py
C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\tenants.py
C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\surveys.py
C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\auth.py
C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\admin.py
C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\can_cap.py
C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\copilot.py
C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\feedback.py
C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\flight_diversions.py
C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\reporting.py
C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\regulators.py
C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\reports.py
```

**Tool: glob**

**Input:**
```json
{
  "pattern": "public/settings/**"
}
```

**Output:**
```
No files found
```

**Tool: read**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\services\\users.py"
}
```

**Output:**
```
<path>C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\services\users.py</path>
<type>file</type>
<content>
1: # ============================================================================
2: # FILE: users.py
3: # PATH: backend/app/services/users.py
4: # PURPOSE: Mirror Firebase Auth users into a Firestore `users` collection so
5: #          tenant-scoped queries are cheap and indexable. The collection is
6: #          backfilled from Auth, maintained on register/claims updates, and
7: #          consumed by GET /api/v1/tenants/{tenantId}/users.
8: # ============================================================================
9: 
10: from datetime import datetime, timezone
11: from typing import Any, Dict, List, Optional
12: 
13: from loguru import logger
14: 
15: from app.core.config import settings
16: from app.firebase import get_db, get_auth
17: 
18: 
19: def _parse_ms_timestamp(value: Any) -> Optional[datetime]:
20:     """Convert a Firebase Auth ms-epoch (int) or ISO string into a datetime."""
21:     if value is None:
22:         return None
23:     if isinstance(value, str):
24:         try:
25:             return datetime.fromisoformat(value.replace("Z", "+00:00"))
26:         except ValueError:
27:             try:
28:                 return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
29:             except (ValueError, OSError):
30:                 return None
31:     if isinstance(value, (int, float)):
32:         try:
33:             return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
34:         except (ValueError, OSError):
35:             return None
36:     return None
37: 
38: 
39: def user_doc_from_auth_record(record: Any) -> Dict[str, Any]:
40:     """Map a firebase_admin.auth.UserRecord to the Firestore users/{uid} shape."""
41:     claims = record.custom_claims or {}
42:     meta = getattr(record, "user_metadata", None)
43:     created_at = _parse_ms_timestamp(getattr(meta, "creation_timestamp", None))
44:     last_login = (
45:         getattr(meta, "last_sign_in_at", None)
46:         or getattr(meta, "last_sign_in_timestamp", None)
47:     )
48:     last_login = _parse_ms_timestamp(last_login)
49:     return {
50:         "uid": record.uid,
51:         "email": record.email,
52:         "display_name": getattr(record, "display_name", None),
53:         "role": claims.get("role") or "USER",
54:         "tenant_id": claims.get("tenant_id"),
55:         "department": claims.get("department") or "",
56:         "is_developer": bool(claims.get("is_developer")),
57:         "created_at": created_at,
58:         "last_login": last_login,
59:         "updated_at": datetime.now(timezone.utc),
60:     }
61: 
62: 
63: def upsert_user_doc(uid: str, data: Dict[str, Any]) -> None:
64:     """Best-effort write/merge of a user doc. Never breaks the caller."""
65:     try:
66:         get_db().collection(settings.FIREBASE_COLLECTION_USERS).document(uid).set(
67:             data, merge=True
68:         )
69:     except Exception as e:
70:         logger.warning(f"Failed to upsert user doc {uid}: {e}")
71: 
72: 
73: def backfill_users_from_auth(max_pages: Optional[int] = None) -> int:
74:     """Paginate Firebase Auth and upsert every user into the users collection.
75: 
76:     Returns the number of user docs written. `max_pages` limits the scan (for
77:     sanity checks on large directories); by default all users are synced.
78:     """
79:     auth = get_auth()
80:     written = 0
81:     page_token = None
82:     pages = 0
83:     while True:
84:         page = auth.list_users(max_results=1000, page_token=page_token)
85:         for record in page.users:
86:             upsert_user_doc(record.uid, user_doc_from_auth_record(record))
87:             written += 1
88:         pages += 1
89:         page_token = page.next_page_token
90:         if not page_token or (max_pages and pages >= max_pages):
91:             break
92:     logger.info(f"User backfill complete: {written} users synced")
93:     return written
94: 
95: 
96: def list_tenant_users(tenant_id: str) -> List[Dict[str, Any]]:
97:     """Query the users collection for all users assigned to a tenant."""
98:     snapshots = (
99:         get_db()
100:         .collection(settings.FIREBASE_COLLECTION_USERS)
101:         .where("tenant_id", "==", tenant_id)
102:         .get()
103:     )
104:     results = []
105:     for snap in snapshots:
106:         data = snap.to_dict() or {}
107:         results.append(
108:             {
109:                 "uid": data.get("uid") or snap.id,
110:                 "email": data.get("email"),
111:                 "role": data.get("role"),
112:                 "department": data.get("department") or "",
113:                 "createdAt": data.get("created_at").isoformat() if data.get("created_at") else None,
114:                 "lastLogin": data.get("last_login").isoformat() if data.get("last_login") else None,
115:             }
116:         )
117:     results.sort(key=lambda u: (u["createdAt"] or "", u["email"] or ""))
118:     return results
119: 
120: 
121: def get_user_department(uid: Optional[str] = None, email: Optional[str] = None) -> str:
122:     """Resolve a user's department from the mirrored users collection.
123: 
124:     Checks by uid first, then falls back to an email match. Returns an empty
125:     string when the user cannot be found or has no department assigned.
126:     """
127:     try:
128:         db = get_db()
129:         if uid:
130:             snap = db.collection(settings.FIREBASE_COLLECTION_USERS).document(uid).get()
131:             if snap.exists:
132:                 return (snap.to_dict() or {}).get("department") or ""
133:         if email:
134:             docs = (
135:                 db.collection(settings.FIREBASE_COLLECTION_USERS)
136:                 .where("email", "==", email)
137:                 .limit(1)
138:                 .get()
139:             )
140:             for d in docs:
141:                 return (d.to_dict() or {}).get("department") or ""
142:     except Exception as e:
143:         logger.warning(f"Failed to resolve department for uid={uid} email={email}: {e}")
144:     return ""

(End of file - total 144 lines)
</content>
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 43.3s)

_Thinking:_

Now I understand the current architecture:

- Roles currently: `AIRLINE_ADMIN`, `USER` (plus ROLE_DEFAULT, ROLE_DEFAULT_REGISTRATION in config).
- The spec uses: `SUPER_ADMIN`, `TENANT_ADMIN`, `DEPT_ADMIN`, `SAFETY_OFFICER`, `STAFF`/`EMPLOYEE`.
- The spec wants a protected `POST /api/v1/auth/invite` endpoint that creates a department-scoped invite document, and a `/api/v1/auth/join` endpoint that reads role+department from the invite.

This is a significant divergence between the spec's naming and the existing codebase. The existing code uses `AIRLINE_ADMIN` for the tenant admin and `USER` for members. The existing join flow is `/join-team` which lets the invitee self-select department and always assigns role USER.

I need to decide how to proceed. Options:

A) Implement exactly per spec: create `auth_service.py`, add `/invite` and `/join` endpoints, introduce new role constants (DEPT_ADMIN, etc.), keep existing endpoints working. This creates parallel systems but satisfies the spec.

B) Map the spec onto the existing flow: add a protected invite endpoint (`/api/v1/auth/invite` + legacy `/api/auth/invite`) creating department-scoped invite docs, and extend the existing `/join-team` to consume them (role/department from invite doc when present). Keep existing role names but add DEPT_ADMIN etc.

The spec is explicit about endpoints and role names. But the existing codebase has different conventions. This is a real ambiguity — the user should decide whether to follow the spec's new naming exactly or map onto existing conventions (AIRLINE_ADMIN = TENANT_ADMIN, USER = STAFF, plus new DEPT_ADMIN/SAFETY_OFFICER roles).

Given the instruction "Continue if you have next steps, or stop and ask for clarification if you are unsure how to proceed," I think this is a case where clarification is warranted because:
1. The spec's endpoint names (/api/v1/auth/invite, /api/v1/auth/join) don't exist; existing are /join-team, /verify-invite.
2. The role names conflict: spec wants TENANT_ADMIN/DEPT_ADMIN/SAFETY_OFFICER/STAFF; existing uses AIRLINE_ADMIN/USER, with frontend getRoleDestination in firebase.js.
3. There's no team management view — need to create it (spec says public/settings/team.html "or team management modal"). Need to decide where to put it.

However, I should be careful — the user might prefer I just make sensible decisions. But the role-name mismatch is a big deal affecting frontend role handling, navigation, etc. Getting this wrong would be costly. Let me ask a focused clarification question with recommended options.

Let me also quickly check how roles are used in the frontend (firebase.js getRoleDestination) and whether there's a user management endpoint (GET /api/v1/tenants/{tenantId}/users) and admin.py content to understand where team management would live. Let me gather a bit more before asking, so my options are well-informed.

Let me read admin.py, main.py route mounting, firebase.js role handling, and config.py roles.

Let me check the existing role handling, admin routes, and how routes are mounted before deciding the mapping

**Tool: read**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\routes\\admin.py"
}
```

**Output:**
```
<path>C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\admin.py</path>
<type>file</type>
<content>
1: # ============================================================================
2: # FILE: admin.py
3: # PATH: backend/app/routes/admin.py
4: # VERSION: 2.0.0
5: # DATE CREATED: 2026-07-03
6: # DATE REVISED: 2026-07-27
7: # PURPOSE: Admin and Safety Manager endpoints for system configuration.
8: # AUTHOR: Ghanshyam Acharya
9: # CODE OWNER: AviaSafeSystems
10: # ============================================================================
11: 
12: import secrets
13: from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
14: from pydantic import BaseModel, Field
15: from typing import Dict, Any, Optional, List
16: from loguru import logger
17: from datetime import datetime, timezone
18: 
19: from app.core.config import settings
20: from app.firebase import get_auth, get_db, verify_firebase_token
21: from app.middleware.auth import get_current_user, get_safety_manager, get_admin_user
22: from app.services.risk_matrix import (
23:     get_risk_matrix_config,
24:     set_risk_matrix_config,
25:     THRESHOLDS_DEFAULT,
26: )
27: from app.services.users import upsert_user_doc, user_doc_from_auth_record
28: from app.services.audit_service import log_audit, request_context
29: 
30: router = APIRouter()
31: 
32: 
33: def _verify_admin_setup(setup_key: str) -> None:
34:     """Second factor for admin provisioning endpoints.
35: 
36:     The setup key is a defense-in-depth secret loaded from the environment. It
37:     never grants access by itself — callers must also present a SUPER_ADMIN
38:     Firebase ID token (enforced via the `get_admin_user` dependency).
39:     """
40:     if not settings.SETUP_SECRET:
41:         raise HTTPException(
42:             status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
43:             detail="Admin setup is not configured on this server",
44:         )
45:     if not setup_key or not secrets.compare_digest(setup_key, settings.SETUP_SECRET):
46:         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid setup key")
47: 
48: 
49: def verify_task_auth(request: Request) -> Dict[str, Any]:
50:     """Authenticate the internal scheduled-task endpoints.
51: 
52:     Accepts either a shared `X-Task-Key` header matching TASK_API_KEY (used by
53:     Cloud Scheduler) or a SUPER_ADMIN Firebase ID token in the Authorization
54:     header. Returns the acting user context.
55:     """
56:     header_key = request.headers.get("X-Task-Key")
57:     if header_key and settings.TASK_API_KEY and secrets.compare_digest(header_key, settings.TASK_API_KEY):
58:         return {"uid": "system", "email": "system", "role": "SUPER_ADMIN", "tenant_id": None}
59: 
60:     auth_header = request.headers.get("Authorization", "")
61:     if auth_header.startswith("Bearer "):
62:         token = auth_header[len("Bearer "):]
63:         decoded = verify_firebase_token(token)
64:         if decoded and decoded.get("role") == "SUPER_ADMIN":
65:             return {
66:                 "uid": decoded.get("uid", "system"),
67:                 "email": decoded.get("email", "system"),
68:                 "role": "SUPER_ADMIN",
69:                 "tenant_id": decoded.get("tenant_id"),
70:             }
71: 
72:     raise HTTPException(
73:         status_code=status.HTTP_403_FORBIDDEN,
74:         detail="Task authentication required (X-Task-Key header or SUPER_ADMIN token)",
75:     )
76: 
77: 
78: class RiskMatrixThresholds(BaseModel):
79:     low_max: int = Field(default=5, ge=1, le=25)
80:     medium_max: int = Field(default=9, ge=1, le=25)
81:     high_max: int = Field(default=15, ge=1, le=25)
82: 
83: 
84: class RiskMatrixConfig(BaseModel):
85:     thresholds: RiskMatrixThresholds
86:     updated_by: Optional[str] = None
87:     updated_at: Optional[str] = None
88: 
89: 
90: @router.get("/risk-matrix")
91: async def get_risk_matrix(
92:     user: Dict[str, Any] = Depends(get_safety_manager),
93: ):
94:     """Get the ICAO risk matrix configuration for the user's tenant.
95: 
96:     Defaults to ICAO-aligned thresholds if not yet configured.
97:     """
98:     tenant_id = user.get("tenant_id")
99:     if not tenant_id and user.get("role") in ["CAAN_SMD", "SUPER_ADMIN"]:
100:         tenant_id = "default"
101:     config = get_risk_matrix_config(tenant_id)
102:     return config
103: 
104: 
105: @router.put("/risk-matrix", status_code=status.HTTP_200_OK)
106: async def update_risk_matrix(
107:     config: RiskMatrixConfig,
108:     user: Dict[str, Any] = Depends(get_safety_manager),
109: ):
110:     """Update the ICAO risk matrix thresholds for the user's tenant.
111: 
112:     Thresholds define Low/Medium/High/Very High boundaries.
113:     All thresholds are inclusive max values for each level.
114:     Must satisfy: 1 <= low_max < medium_max < high_max <= 25.
115:     """
116:     t = config.thresholds
117:     if not (1 <= t.low_max < t.medium_max < t.high_max <= 25):
118:         raise HTTPException(
119:             status_code=400,
120:             detail="Thresholds must satisfy: 1 <= low_max < medium_max < high_max <= 25",
121:         )
122: 
123:     tenant_id = user.get("tenant_id")
124:     if not tenant_id and user.get("role") in ["CAAN_SMD", "SUPER_ADMIN"]:
125:         tenant_id = "default"
126: 
127:     now = datetime.now(timezone.utc).isoformat()
128:     data = {
129:         "thresholds": t.model_dump(),
130:         "updated_by": user["uid"],
131:         "updated_at": now,
132:     }
133:     set_risk_matrix_config(tenant_id, data, updated_by=user["uid"])
134:     logger.info(f"Risk matrix updated for tenant {tenant_id} by {user['uid']}")
135:     return data
136: 
137: 
138: class SetupClaimsRequest(BaseModel):
139:     setup_key: str
140:     users: List[dict]
141: 
142: 
143: @router.post("/setup-claims")
144: async def setup_test_user_claims(
145:     req: SetupClaimsRequest,
146:     user: Dict[str, Any] = Depends(get_admin_user),
147: ):
148:     """Set custom claims on users.
149: 
150:     Requires a SUPER_ADMIN Bearer token and the admin setup key (env).
151:     """
152:     _verify_admin_setup(req.setup_key)
153: 
154:     results = []
155:     auth = get_auth()
156:     for u in req.users:
157:         email = u.get("email")
158:         role = u.get("role", "USER")
159:         tenant_id = u.get("tenant_id")
160:         if not email:
161:             results.append({"email": email, "status": "error", "detail": "email required"})
162:             continue
163:         try:
164:             user_record = auth.get_user_by_email(email)
165:             claims = {"role": role}
166:             if tenant_id:
167:                 claims["tenant_id"] = tenant_id
168:             uid = user_record.uid
169:             auth.update_user(uid, custom_claims=claims)
170:             upsert_user_doc(uid, user_doc_from_auth_record(auth.get_user(uid)))
171:             results.append({"email": email, "uid": uid, "role": role, "tenant_id": tenant_id, "status": "ok"})
172:             logger.info(f"Claims set for {email}: role={role}, tenant_id={tenant_id}")
173:         except Exception as e:
174:             results.append({"email": email, "status": "error", "detail": str(e)})
175:             logger.error(f"Failed to set claims for {email}: {e}")
176: 
177:     return {"success": True, "results": results}
178: 
179: 
180: class AdminSetupRequest(BaseModel):
181:     setup_key: str
182: 
183: 
184: AIRLINES = [
185:     {"id": "buddha-air", "name": "Buddha Air", "icao": "BHA", "email": "buddhaair@buddhaair.com"},
186:     {"id": "nepal-airlines", "name": "Nepal Airlines", "icao": "NAL", "email": "info@nac.com.np"},
187:     {"id": "shree-airlines", "name": "Shree Airlines", "icao": "SHA", "email": "info@shreeairlines.com"},
188:     {"id": "sita-air", "name": "Sita Air", "icao": "STA", "email": "info@sitaair.com"},
189:     {"id": "summit-air", "name": "Summit Air", "icao": "SMT", "email": "info@summitair.com.np"},
190:     {"id": "tara-air", "name": "Tara Air", "icao": "TRA", "email": "info@taraair.com"},
191:     {"id": "yeti-airlines", "name": "Yeti Airlines", "icao": "YET", "email": "info@yetiairlines.com"},
192:     {"id": "makalu-air", "name": "Makalu Air", "icao": "MKU", "email": "info@makaluair.com"},
193:     {"id": "himalaya-airlines", "name": "Himalaya Airlines", "icao": "HIM", "email": "info@himalaya-airlines.com"},
194:     {"id": "air-dynasty", "name": "Air Dynasty Heli Services", "icao": "ADH", "email": "info@airdynasty.com"},
195:     {"id": "altitude-air", "name": "Altitude Air", "icao": "ALT", "email": "info@altitudeair.com.np"},
196:     {"id": "annapurna-heli", "name": "Annapurna Helicopter", "icao": "ANH", "email": "info@annapurnaheli.com"},
197:     {"id": "fishtail-air", "name": "Fishtail Air", "icao": "FTA", "email": "info@fishtailair.com"},
198:     {"id": "heli-everest", "name": "Heli Everest", "icao": "HLE", "email": "info@helieverest.com"},
199:     {"id": "kailash-helicopter", "name": "Kailash Helicopter Services", "icao": "KHS", "email": "info@kailashhelicopter.com"},
200:     {"id": "manang-air", "name": "Manang Air", "icao": "MNA", "email": "info@manangair.com"},
201:     {"id": "mountain-helicopters", "name": "Mountain Helicopters", "icao": "MTH", "email": "info@mountainhelicopters.com"},
202:     {"id": "mustang-helicopter", "name": "Mustang Helicopter", "icao": "MSH", "email": "info@mustanghelicopter.com"},
203:     {"id": "prabhu-helicopters", "name": "Prabhu Helicopters", "icao": "PRB", "email": "info@prabhuhelicopters.com"},
204:     {"id": "simrik-air", "name": "Simrik Air", "icao": "SMK", "email": "info@simrikair.com"},
205: ]
206: 
207: @router.post("/provision-airlines", status_code=status.HTTP_200_OK)
208: async def provision_20_airlines(
209:     req: AdminSetupRequest,
210:     user: Dict[str, Any] = Depends(get_admin_user),
211: ):
212:     """Batch-provision all 20 Nepali airlines: create Auth users, set claims, create Firestore tenants."""
213:     _verify_admin_setup(req.setup_key)
214: 
215:     if not settings.DEFAULT_PROVISION_PASSWORD:
216:         raise HTTPException(
217:             status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
218:             detail="DEFAULT_PROVISION_PASSWORD is not configured on this server",
219:         )
220: 
221:     auth = get_auth()
222:     db = get_db()
223:     results = []
224:     now = datetime.now(timezone.utc).isoformat()
225: 
226:     for a in AIRLINES:
227:         tid = a["id"]
228:         email = a["email"]
229:         name = a["name"]
230:         icao = a["icao"]
231:         record = {"tenant_id": tid, "email": email, "name": name, "status": "pending"}
232: 
233:         try:
234:             try:
235:                 user = auth.create_user(
236:                     email=email,
237:                     password=settings.DEFAULT_PROVISION_PASSWORD,
238:                     email_verified=True,
239:                     display_name=f"{name} Safety Manager",
240:                 )
241:                 record["action"] = "created"
242:             except Exception as create_err:
243:                 if "email already exists" in str(create_err).lower():
244:                     user = auth.get_user_by_email(email)
245:                     record["action"] = "existing"
246:                 else:
247:                     raise
248: 
249:             uid = user.uid
250:             auth.update_user(uid, custom_claims={"role": "AIRLINE_ADMIN", "tenant_id": tid})
251:             upsert_user_doc(uid, user_doc_from_auth_record(auth.get_user(uid)))
252: 
253:             tenant_ref = db.collection("tenants").document(tid)
254:             tenant_doc = tenant_ref.get()
255: 
256:             if not tenant_doc.exists:
257:                 tenant_ref.set({
258:                     "tenant_id": tid,
259:                     "name": name,
260:                     "icao": icao,
261:                     "country": "Nepal",
262:                     "active": True,
263:                     "safety_manager": {
264:                         "email": email,
265:                         "name": f"{name} Safety Manager",
266:                         "uid": uid,
267:                     },
268:                     "survey_config": {
269:                         "open": True,
270:                         "open_date": "2026-08-01",
271:                         "close_date": "2026-08-31",
272:                     },
273:                     "created_at": now,
274:                     "updated_at": now,
275:                 })
276:                 record["tenant"] = "created"
277:             else:
278:                 record["tenant"] = "exists"
279: 
280:             record["uid"] = uid
281:             record["status"] = "ok"
282:             logger.info(f"Provisioned {name} ({tid}) -> {email} / {uid}")
283: 
284:         except Exception as e:
285:             record["status"] = "error"
286:             record["detail"] = str(e)
287:             logger.error(f"Provision failed for {email}: {e}")
288: 
289:         results.append(record)
290: 
291:     summary = {
292:         "total": len(AIRLINES),
293:         "ok": sum(1 for r in results if r["status"] == "ok"),
294:         "skipped": sum(1 for r in results if r["status"] == "skipped"),
295:         "error": sum(1 for r in results if r["status"] == "error"),
296:     }
297: 
298:     return {"success": True, "summary": summary, "results": results}
299: 
300: 
301: @router.post("/fix-tenant-ids", status_code=status.HTTP_200_OK)
302: async def fix_tenant_id_mismatch(
303:     req: AdminSetupRequest,
304:     user: Dict[str, Any] = Depends(get_admin_user),
305: ):
306:     """Fix tenant_id mismatch: provisioned users use hyphens but seed data uses underscores."""
307:     _verify_admin_setup(req.setup_key)
308: 
309:     auth = get_auth()
310:     FIXES = {
311:         "buddhaair@buddhaair.com": "buddha_air",
312:         "info@sitaair.com": "sita_air",
313:         "info@summitair.com.np": "summit_air",
314:         "info@yetiairlines.com": "yeti_airlines",
315:         "info@airdynasty.com": "air_dynasty",
316:         "info@simrikair.com": "simrik_air",
317:     }
318:     results = []
319:     for email, correct_tid in FIXES.items():
320:         try:
321:             user = auth.get_user_by_email(email)
322:             existing = user.custom_claims or {}
323:             existing["tenant_id"] = correct_tid
324:             auth.update_user(user.uid, custom_claims=existing)
325:             results.append({"email": email, "tenant_id": correct_tid, "status": "ok"})
326:             logger.info(f"Fixed tenant_id for {email}: {correct_tid}")
327:         except Exception as e:
328:             results.append({"email": email, "status": "error", "detail": str(e)})
329:     return {"success": True, "results": results}
330: 
331: 
332: @router.post("/create-seed-users", status_code=status.HTTP_200_OK)
333: async def create_seed_users(
334:     req: AdminSetupRequest,
335:     user: Dict[str, Any] = Depends(get_admin_user),
336: ):
337:     """Create seed users in Firebase Auth (skips users that already exist)."""
338:     if settings.DISABLE_DESTRUCTIVE_ENDPOINTS:
339:         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint disabled")
340:     _verify_admin_setup(req.setup_key)
341:     from seed.users import create_all_users
342:     try:
343:         created = create_all_users(get_auth())
344:         return {"success": True, "created": len(created), "users": created}
345:     except Exception as e:
346:         logger.error(f"Create seed users failed: {e}")
347:         return {"success": False, "error": str(e)}
348: 
349: 
350: @router.post("/seed-demo-data", status_code=status.HTTP_200_OK)
351: async def seed_demo_data(
352:     req: AdminSetupRequest,
353:     user: Dict[str, Any] = Depends(get_admin_user),
354: ):
355:     """Run the demo data seeder against production Firestore."""
356:     if settings.DISABLE_DESTRUCTIVE_ENDPOINTS:
357:         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint disabled")
358:     _verify_admin_setup(req.setup_key)
359:     from seed.runner import run
360:     try:
361:         result = run(db=get_db(), auth=get_auth(), force=True)
362:         return {"success": True, "result": result}
363:     except Exception as e:
364:         logger.error(f"Seed failed: {e}")
365:         return {"success": False, "error": str(e)}
366: 
367: 
368: # ============================================================================
369: # Super-Admin web seeding panel (production-setup.html)
370: # ============================================================================
371: 
372: class RegulatorCreate(BaseModel):
373:     id: str
374:     name: str
375:     short_name: Optional[str] = None
376:     country: Optional[str] = None
377:     country_name: Optional[str] = None
378:     domain: Optional[str] = None
379:     operator_tenant_ids: Optional[List[str]] = None
380:     active: bool = True
381: 
382: 
383: class TenantCreate(BaseModel):
384:     tenant_id: str
385:     name: str
386:     icao: Optional[str] = None
387:     country: Optional[str] = "Nepal"
388:     active: bool = True
389:     regulator_id: Optional[str] = None
390:     safety_manager: Optional[Dict[str, Any]] = None
391:     survey_config: Optional[Dict[str, Any]] = None
392:     contact: Optional[Dict[str, Any]] = None
393:     contract: Optional[Dict[str, Any]] = None
394:     users: Optional[List[Dict[str, Any]]] = None
395:     status: Optional[str] = "active"
396: 
397: 
398: class TenantBulkRequest(BaseModel):
399:     setup_key: str
400:     records: Optional[List[TenantCreate]] = None
401:     csv: Optional[str] = None
402: 
403: 
404: class SeedDeployRequest(BaseModel):
405:     setup_key: str
406:     force: bool = False
407: 
408: 
409: class RegulatorSetupRequest(BaseModel):
410:     setup_key: str
411:     regulator: RegulatorCreate
412: 
413: 
414: class TenantSetupRequest(BaseModel):
415:     setup_key: str
416:     tenant: TenantCreate
417: 
418: 
419: @router.post("/regulators", status_code=status.HTTP_200_OK)
420: async def admin_create_regulator(
421:     req: RegulatorSetupRequest,
422:     user: Dict[str, Any] = Depends(get_admin_user),
423: ):
424:     """Create a State Regulator document (SUPER_ADMIN + setup key)."""
425:     _verify_admin_setup(req.setup_key)
426:     from app.services.production_seed import create_regulator
427:     try:
428:         doc = create_regulator(req.regulator.model_dump(), user)
429:         return {"success": True, "regulator": doc}
430:     except ValueError as e:
431:         raise HTTPException(status_code=409, detail=str(e))
432:     except Exception as e:
433:         logger.error(f"Create regulator failed: {e}")
434:         raise HTTPException(status_code=500, detail=str(e))
435: 
436: 
437: @router.get("/regulators", status_code=status.HTTP_200_OK)
438: async def admin_list_regulators(
439:     user: Dict[str, Any] = Depends(get_admin_user),
440: ):
441:     """List every State Regulator (SUPER_ADMIN)."""
442:     from app.services.production_seed import list_regulators_admin
443:     return {"success": True, "regulators": list_regulators_admin()}
444: 
445: 
446: @router.post("/tenants", status_code=status.HTTP_200_OK)
447: async def admin_create_tenant(
448:     req: TenantSetupRequest,
449:     user: Dict[str, Any] = Depends(get_admin_user),
450: ):
451:     """Create one operator tenant (SUPER_ADMIN + setup key).
452: 
453:     When `tenant.users` is provided the tenant is created together with its
454:     Firebase Auth users (AIRLINE_ADMIN etc.) and the generated passwords are
455:     returned exactly once (never persisted).
456:     """
457:     _verify_admin_setup(req.setup_key)
458:     data = req.tenant.model_dump()
459:     if data.get("users"):
460:         from app.services.tenant_credentials import create_tenant_with_credentials
461:         try:
462:             result = create_tenant_with_credentials(data, user)
463:             return {"success": True, **result}
464:         except ValueError as e:
465:             raise HTTPException(status_code=409, detail=str(e))
466:         except Exception as e:
467:             logger.error(f"Create tenant with credentials failed: {e}")
468:             raise HTTPException(status_code=500, detail=str(e))
469: 
470:     from app.services.production_seed import create_tenant
471:     try:
472:         doc = create_tenant(data, user)
473:         return {"success": True, "tenant": doc}
474:     except ValueError as e:
475:         raise HTTPException(status_code=409, detail=str(e))
476:     except Exception as e:
477:         logger.error(f"Create tenant failed: {e}")
478:         raise HTTPException(status_code=500, detail=str(e))
479: 
480: 
481: @router.post("/tenants/bulk", status_code=status.HTTP_200_OK)
482: async def admin_bulk_create_tenants(
483:     req: TenantBulkRequest,
484:     user: Dict[str, Any] = Depends(get_admin_user),
485: ):
486:     """Bulk-import tenants from a JSON list or CSV text (SUPER_ADMIN + setup key)."""
487:     _verify_admin_setup(req.setup_key)
488:     from app.services.production_seed import bulk_create_tenants
489: 
490:     records: List[Dict[str, Any]] = []
491:     if req.records:
492:         records = [r.model_dump() for r in req.records]
493:     elif req.csv:
494:         import csv as _csv
495:         import io
496:         reader = _csv.DictReader(io.StringIO(req.csv))
497:         for row in reader:
498:             rec = {k.strip(): (v or "").strip() for k, v in row.items() if k}
499:             if not rec.get("tenant_id") and rec.get("id"):
500:                 rec["tenant_id"] = rec.pop("id")
501:             if not rec.get("tenant_id"):
502:                 continue
503:             records.append(rec)
504:     else:
505:         raise HTTPException(status_code=400, detail="Provide 'records' (JSON) or 'csv' text")
506: 
507:     if not records:
508:         raise HTTPException(status_code=400, detail="No valid tenant records provided")
509: 
510:     try:
511:         result = bulk_create_tenants(records, user)
512:         return {"success": True, **result}
513:     except Exception as e:
514:         logger.error(f"Bulk tenant import failed: {e}")
515:         raise HTTPException(status_code=500, detail=str(e))
516: 
517: 
518: @router.get("/tenants", status_code=status.HTTP_200_OK)
519: async def admin_list_tenants(
520:     user: Dict[str, Any] = Depends(get_admin_user),
521: ):
522:     """List all operator tenants with per-subcollection counts (SUPER_ADMIN)."""
523:     from app.services.production_seed import list_tenants_admin
524:     return {"success": True, "tenants": list_tenants_admin()}
525: 
526: 
527: @router.get("/seed/preview", status_code=status.HTTP_200_OK)
528: async def admin_seed_preview(
529:     user: Dict[str, Any] = Depends(get_admin_user),
530: ):
531:     """Preview the CAAN demo seed plan against the current database (SUPER_ADMIN)."""
532:     from app.services.production_seed import preview_seed
533:     try:
534:         plan = preview_seed(actor=user)
535:         return {"success": True, **plan}
536:     except Exception as e:
537:         logger.error(f"Seed preview failed: {e}")
538:         raise HTTPException(status_code=500, detail=str(e))
539: 
540: 
541: @router.post("/seed/deploy", status_code=status.HTTP_200_OK)
542: async def admin_seed_deploy(
543:     req: SeedDeployRequest,
544:     user: Dict[str, Any] = Depends(get_admin_user),
545: ):
546:     """Deploy the CAAN demo seed plan (SUPER_ADMIN + setup key).
547: 
548:     Writes the regulator, tags the operator tenants, and seeds surveys +
549:     hazards + reports. Runs against the backend's configured database
550:     (beta -> sms-db-beta, production -> sms-db).
551:     """
552:     _verify_admin_setup(req.setup_key)
553:     from app.services import production_seed
554:     try:
555:         result = production_seed.deploy_seed(force=req.force, actor=user)
556:         return {"success": True, "result": result}
557:     except Exception as e:
558:         logger.error(f"Seed deploy failed: {e}")
559:         production_seed._audit("SEED_DEPLOY", user, "caan", f"Deploy failed: {str(e)}", result="error")
560:         raise HTTPException(status_code=500, detail=str(e))
561: 
562: 
563: @router.get("/seed/logs", status_code=status.HTTP_200_OK)
564: async def admin_seed_logs(
565:     limit: int = Query(50, ge=1, le=200),
566:     user: Dict[str, Any] = Depends(get_admin_user),
567: ):
568:     """Recent seeding/admin audit log entries (SUPER_ADMIN)."""
569:     from app.services.production_seed import list_audit_logs
570:     return {"success": True, "logs": list_audit_logs(limit=limit)}
571: 
572: 
573: # ============================================================================
574: # Scheduled tasks (internal; Cloud Scheduler / task runners)
575: # ============================================================================
576: 
577: class CheckOverdueRequest(BaseModel):
578:     tenant_id: Optional[str] = None
579: 
580: 
581: @router.post("/tasks/check-overdue", status_code=status.HTTP_200_OK)
582: async def admin_check_overdue(
583:     req: CheckOverdueRequest,
584:     request: Request,
585: ):
586:     """Run the overdue/escalation scan across all tenants (or one tenant).
587: 
588:     Intended to be invoked daily by Cloud Scheduler with the X-Task-Key header
589:     (TASK_API_KEY) or a SUPER_ADMIN token. Escalates past-due CANs to
590:     "Escalated" and past-due CAPs to "Overdue", logging every change.
591:     """
592:     verify_task_auth(request)
593:     from app.services.escalation_service import check_all_overdue
594:     try:
595:         result = check_all_overdue(tenant_id=req.tenant_id or None)
596:         return {"success": True, "result": result}
597:     except Exception as e:
598:         logger.error(f"Overdue check failed: {e}")
599:         raise HTTPException(status_code=500, detail=f"Overdue check failed: {str(e)}")
600: 
601: 
602: # ============================================================================
603: # Tenant credentials management (tenant-credentials.html)
604: # ============================================================================
605: 
606: class CheckEmailRequest(BaseModel):
607:     setup_key: str
608:     email: str
609: 
610: 
611: class TenantIdSetupRequest(BaseModel):
612:     setup_key: str
613:     tenant_id: str
614: 
615: 
616: @router.post("/tenants/check-email", status_code=status.HTTP_200_OK)
617: async def admin_check_email(
618:     req: CheckEmailRequest,
619:     user: Dict[str, Any] = Depends(get_admin_user),
620: ):
621:     """Check whether an email is already registered in Firebase Auth (SUPER_ADMIN + setup key)."""
622:     _verify_admin_setup(req.setup_key)
623:     from app.services.tenant_credentials import check_email_available
624:     try:
625:         return {"success": True, **check_email_available(req.email)}
626:     except ValueError as e:
627:         raise HTTPException(status_code=400, detail=str(e))
628:     except Exception as e:
629:         logger.error(f"Email availability check failed: {e}")
630:         raise HTTPException(status_code=500, detail=str(e))
631: 
632: 
633: @router.get("/tenants/{tenant_id}/credentials", status_code=status.HTTP_200_OK)
634: async def admin_get_tenant_credentials(
635:     tenant_id: str,
636:     setup_key: str = Query("", description="Admin setup key (SETUP_SECRET)"),
637:     user: Dict[str, Any] = Depends(get_admin_user),
638: ):
639:     """Get a tenant's stored credential metadata (SUPER_ADMIN + setup key).
640: 
641:     Never returns passwords — those are generated, applied to Firebase Auth,
642:     surfaced once, and never persisted.
643:     """
644:     _verify_admin_setup(setup_key)
645:     from app.services.tenant_credentials import get_tenant_credentials
646:     try:
647:         return {"success": True, "credentials": get_tenant_credentials(tenant_id)}
648:     except ValueError as e:
649:         raise HTTPException(status_code=404, detail=str(e))
650:     except Exception as e:
651:         logger.error(f"Get tenant credentials failed: {e}")
652:         raise HTTPException(status_code=500, detail=str(e))
653: 
654: 
655: @router.post("/tenants/{tenant_id}/reset-password", status_code=status.HTTP_200_OK)
656: async def admin_reset_tenant_password(
657:     tenant_id: str,
658:     req: AdminSetupRequest,
659:     user: Dict[str, Any] = Depends(get_admin_user),
660: ):
661:     """Reset a tenant's admin password (SUPER_ADMIN + setup key).
662: 
663:     The new password is returned exactly once and is never stored.
664:     """
665:     _verify_admin_setup(req.setup_key)
666:     from app.services.tenant_credentials import reset_admin_password
667:     try:
668:         return {"success": True, **reset_admin_password(tenant_id, user)}
669:     except ValueError as e:
670:         raise HTTPException(status_code=404, detail=str(e))
671:     except Exception as e:
672:         logger.error(f"Reset tenant password failed: {e}")
673:         raise HTTPException(status_code=500, detail=str(e))
674: 
675: 
676: @router.post("/tenants/{tenant_id}/send-welcome", status_code=status.HTTP_200_OK)
677: async def admin_send_tenant_welcome(
678:     tenant_id: str,
679:     req: AdminSetupRequest,
680:     user: Dict[str, Any] = Depends(get_admin_user),
681: ):
682:     """Set a fresh temporary password and email it to the tenant admin.
683: 
684:     Requires an email provider (EMAIL_PROVIDER=smtp|sendgrid). With the default
685:     'none' provider the message is rendered, logged, and returned as a preview.
686:     """
687:     _verify_admin_setup(req.setup_key)
688:     from app.services.tenant_credentials import send_welcome_email_for_tenant
689:     try:
690:         return {"success": True, **send_welcome_email_for_tenant(tenant_id, user)}
691:     except ValueError as e:
692:         raise HTTPException(status_code=404, detail=str(e))
693:     except Exception as e:
694:         logger.error(f"Send welcome email failed: {e}")
695:         raise HTTPException(status_code=500, detail=str(e))
696: 
697: 
698: # ============================================================================
699: # Tenant lifecycle status + demo-data seeding (production-setup.html)
700: # ============================================================================
701: 
702: class TenantStatusRequest(BaseModel):
703:     setup_key: str
704:     status: Optional[str] = None
705:     contract_start_date: Optional[str] = None
706:     contract_end_date: Optional[str] = None
707:     payment_status: Optional[str] = None
708: 
709: 
710: class DemoDataRequest(BaseModel):
711:     setup_key: str
712:     action: str = "seed"
713:     all: bool = True
714:     tenant_ids: Optional[List[str]] = None
715:     kinds: List[str] = ["vsr", "mor", "can", "cap"]
716: 
717: 
718: @router.post("/tenants/{tenant_id}/status", status_code=status.HTTP_200_OK)
719: async def admin_update_tenant_status(
720:     tenant_id: str,
721:     req: TenantStatusRequest,
722:     user: Dict[str, Any] = Depends(get_admin_user),
723: ):
724:     """Update a tenant's lifecycle status (Trial/Active/Inactive).
725: 
726:     `status` may be set explicitly or derived from the contract dates and
727:     payment status. Requires a SUPER_ADMIN token + admin setup key.
728:     """
729:     _verify_admin_setup(req.setup_key)
730:     from app.services.admin_data_service import update_tenant_status
731:     try:
732:         doc = update_tenant_status(
733:             tenant_id,
734:             user,
735:             status=req.status,
736:             contract_start_date=req.contract_start_date,
737:             contract_end_date=req.contract_end_date,
738:             payment_status=req.payment_status,
739:         )
740:         return {"success": True, "tenant": doc}
741:     except ValueError as e:
742:         msg = str(e)
743:         raise HTTPException(
744:             status_code=404 if "not found" in msg else 400,
745:             detail=msg,
746:         )
747:     except Exception as e:
748:         logger.error(f"Update tenant status failed ({tenant_id}): {e}")
749:         raise HTTPException(status_code=500, detail=str(e))
750: 
751: 
752: @router.post("/demo-data", status_code=status.HTTP_200_OK)
753: async def admin_demo_data(
754:     req: DemoDataRequest,
755:     user: Dict[str, Any] = Depends(get_admin_user),
756: ):
757:     """Seed or unseed dummy operational data (VSR/MOR/CAN/CAP).
758: 
759:     Targets one tenant (tenant_ids) or every tenant (all=True). Unseed only
760:     removes documents created by this seeder (marked admin-demo-1).
761:     """
762:     _verify_admin_setup(req.setup_key)
763:     from app.services.admin_data_service import (
764:         demo_data_scope,
765:         seed_tenant_demo_data,
766:         unseed_tenant_demo_data,
767:     )
768: 
769:     if req.action not in ("seed", "unseed"):
770:         raise HTTPException(status_code=400, detail="action must be 'seed' or 'unseed'")
771: 
772:     tenant_ids = demo_data_scope(req.tenant_ids, all_tenants=req.all)
773:     if not tenant_ids:
774:         raise HTTPException(
775:             status_code=400,
776:             detail="No tenants to target — create tenants first or pass tenant_ids",
777:         )
778: 
779:     fn = seed_tenant_demo_data if req.action == "seed" else unseed_tenant_demo_data
780:     results = []
781:     for tid in tenant_ids:
782:         try:
783:             results.append(fn(tid, req.kinds, user))
784:         except ValueError as e:
785:             results.append({"tenant_id": tid, "error": str(e)})
786:         except Exception as e:
787:             logger.error(f"Demo data {req.action} failed for {tid}: {e}")
788:             results.append({"tenant_id": tid, "error": str(e)})
789: 
790:     return {
791:         "success": True,
792:         "action": req.action,
793:         "kinds": req.kinds,
794:         "results": results,
795:     }
796: 
797: 
798: @router.get("/feedback")
799: async def list_feedback(
800:     limit: int = Query(default=50, ge=1, le=200),
801:     status_filter: Optional[str] = Query(default=None, alias="status"),
802:     user: Dict[str, Any] = Depends(get_current_user),
803: ):
804:     """List in-product feedback submissions for review.
805: 
806:     Restricted to CROSS-TENANT (SUPER_ADMIN / CAAN_SMD) roles. Returns the most
807:     recent feedback first, with the submitter's email, role, tenant, page
808:     context, optional 1-5 rating, and message body.
809:     """
810:     if user.get("role") not in settings.CROSS_TENANT_ROLES:
811:         raise HTTPException(
812:             status_code=status.HTTP_403_FORBIDDEN,
813:             detail="SUPER_ADMIN or CAAN_SMD role required to review feedback",
814:         )
815: 
816:     try:
817:         db = get_db()
818:         query = db.collection("feedback")
819:         if status_filter:
820:             query = query.where("status", "==", status_filter)
821:         docs = sorted(
822:             query.limit(limit).stream(),
823:             key=lambda d: (d.to_dict() or {}).get("created_at"),
824:             reverse=True,
825:         )
826:     except Exception as e:
827:         logger.error(f"Failed to list feedback for {user.get('email')}: {e}")
828:         raise HTTPException(
829:             status_code=status.HTTP_502_BAD_GATEWAY,
830:             detail="Could not retrieve feedback at this time.",
831:         )
832: 
833:     items = []
834:     for d in docs:
835:         x = d.to_dict() or {}
836:         ts = x.get("created_at")
837:         items.append(
838:             {
839:                 "id": d.id,
840:                 "uid": x.get("uid"),
841:                 "email": x.get("email"),
842:                 "role": x.get("role"),
843:                 "tenant_id": x.get("tenant_id"),
844:                 "subject": x.get("subject"),
845:                 "message": x.get("message"),
846:                 "rating": x.get("rating"),
847:                 "page": x.get("page"),
848:                 "created_at": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
849:                 "status": x.get("status", "new"),
850:             }
851:         )
852: 
853:     return {"feedback": items, "count": len(items)}
854: 
855: 
856: # ============================================================================
857: # Developer / SuperAdmin tenant governance (admin/admin-tenants.html)
858: # ============================================================================
859: # Governance statuses control whether a tenant's users can authenticate. They
860: # live on the tenant document's `status` field (ACTIVE / SUSPENDED /
861: # PENDING_REVIEW); `get_current_user` in middleware/auth.py rejects users whose
862: # tenant is SUSPENDED with HTTP 403. The access gate is SUPER_ADMIN role OR the
863: # developer email allowlist (defense in depth — never rely on role alone).
864: 
865: GOVERNANCE_STATUSES = {"ACTIVE", "SUSPENDED", "PENDING_REVIEW"}
866: DEVELOPER_EMAIL_ALLOWLIST = {"ghanshyamacharya@outlook.com"}
867: 
868: 
869: async def get_developer_user(
870:     user: Dict[str, Any] = Depends(get_current_user),
871: ) -> Dict[str, Any]:
872:     """Gate for tenant governance endpoints: SUPER_ADMIN role or developer email."""
873:     if user.get("role") in settings.SUPER_ADMIN_ROLES:
874:         return user
875:     if (user.get("email") or "").strip().lower() in DEVELOPER_EMAIL_ALLOWLIST:
876:         return user
877:     raise HTTPException(
878:         status_code=status.HTTP_403_FORBIDDEN,
879:         detail="SUPER_ADMIN or developer access required",
880:     )
881: 
882: 
883: class TenantGovernanceStatusRequest(BaseModel):
884:     status: str
885: 
886: 
887: def _governance_row(snap: Any) -> Dict[str, Any]:
888:     """Normalize one tenant document into the governance list row shape."""
889:     x = snap.to_dict() or {}
890:     raw_status = str(x.get("status") or "ACTIVE").strip().upper()
891:     if raw_status not in GOVERNANCE_STATUSES:
892:         raw_status = "ACTIVE"
893:     created_at = x.get("created_at")
894:     return {
895:         "tenant_id": x.get("tenant_id") or snap.id,
896:         "name": x.get("name") or x.get("tenant_name") or snap.id,
897:         "classification": x.get("classification") or x.get("tenant_type") or "",
898:         "admin_email": (x.get("safety_manager") or {}).get("email") or "",
899:         "status": raw_status,
900:         "created_at": (
901:             created_at.isoformat() if hasattr(created_at, "isoformat") else (str(created_at) if created_at else None)
902:         ),
903:         "is_beta_sandbox": bool(x.get("is_beta_sandbox", False)),
904:     }
905: 
906: 
907: @router.get("/tenants/governance", status_code=status.HTTP_200_OK)
908: async def admin_list_tenant_governance(
909:     user: Dict[str, Any] = Depends(get_developer_user),
910: ):
911:     """List every tenant for governance review (SUPER_ADMIN / developer).
912: 
913:     Returns a clean summary: tenant_id, name, classification, admin_email,
914:     status (default ACTIVE when unset), created_at and is_beta_sandbox.
915:     """
916:     try:
917:         docs = get_db().collection(settings.FIREBASE_COLLECTION_TENANTS).get()
918:     except Exception as e:
919:         logger.error(f"Failed to list tenant governance for {user.get('email')}: {e}")
920:         raise HTTPException(
921:             status_code=status.HTTP_502_BAD_GATEWAY,
922:             detail="Could not retrieve tenants at this time.",
923:         )
924: 
925:     rows = [_governance_row(d) for d in docs]
926:     rows.sort(key=lambda r: (r["name"] or "").lower())
927:     return {"tenants": rows, "count": len(rows)}
928: 
929: 
930: @router.patch("/tenants/{tenant_id}/status", status_code=status.HTTP_200_OK)
931: async def admin_update_tenant_governance_status(
932:     tenant_id: str,
933:     req: TenantGovernanceStatusRequest,
934:     request: Request,
935:     user: Dict[str, Any] = Depends(get_developer_user),
936: ):
937:     """Set a tenant's governance status (ACTIVE / SUSPENDED / PENDING_REVIEW).
938: 
939:     Users belonging to a SUSPENDED tenant are blocked at authentication
940:     (middleware/auth.py -> get_current_user) with HTTP 403.
941:     """
942:     new_status = (req.status or "").strip().upper()
943:     if new_status not in GOVERNANCE_STATUSES:
944:         raise HTTPException(
945:             status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
946:             detail=f"status must be one of: {sorted(GOVERNANCE_STATUSES)}",
947:         )
948: 
949:     db = get_db()
950:     ref = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tenant_id)
951:     try:
952:         doc = ref.get()
953:     except Exception as e:
954:         logger.error(f"Failed to read tenant {tenant_id}: {e}")
955:         raise HTTPException(
956:             status_code=status.HTTP_502_BAD_GATEWAY,
957:             detail="Could not read the tenant at this time.",
958:         )
959:     if doc is None or not doc.exists:
960:         raise HTTPException(
961:             status_code=status.HTTP_404_NOT_FOUND,
962:             detail=f"Tenant '{tenant_id}' not found",
963:         )
964: 
965:     now = datetime.now(timezone.utc).isoformat()
966:     updates = {
967:         "status": new_status,
968:         "active": new_status == "ACTIVE",
969:         "status_updated_at": now,
970:         "status_updated_by": user.get("uid"),
971:         "updated_at": now,
972:     }
973:     try:
974:         ref.update(updates)
975:     except Exception as e:
976:         logger.error(f"Failed to update tenant {tenant_id} status: {e}")
977:         raise HTTPException(
978:             status_code=status.HTTP_502_BAD_GATEWAY,
979:             detail="Could not update the tenant status at this time.",
980:         )
981: 
982:     ip, request_id = request_context(request)
983:     log_audit(
984:         action="TENANT_GOVERNANCE_STATUS_UPDATED",
985:         user=user.get("email"),
986:         tenant_id=tenant_id,
987:         target_type="tenant",
988:         target_id=tenant_id,
989:         ip=ip,
990:         request_id=request_id,
991:         metadata={"status": new_status, "by_uid": user.get("uid")},
992:     )
993:     logger.info(f"Tenant {tenant_id} governance status -> {new_status} by {user.get('email')}")
994: 
995:     return {
996:         "success": True,
997:         "tenant": {
998:             **{"tenant_id": tenant_id},
999:             **_governance_row(doc),
1000:             "status": new_status,
1001:         },
1002:     }

(End of file - total 1002 lines)
</content>
```

**Tool: read**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\core\\config.py"
}
```

**Output:**
```
<path>C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\core\config.py</path>
<type>file</type>
<content>
1: from pathlib import Path
2: from dotenv import load_dotenv
3: 
4: from pydantic_settings import BaseSettings
5: from typing import List, Optional
6: from enum import Enum
7: 
8: # Ensure .env is loaded into os.environ regardless of pydantic-settings path resolution
9: _env_path = Path(__file__).resolve().parent.parent.parent / ".env"
10: if _env_path.exists():
11:     load_dotenv(_env_path, override=False)
12: 
13: 
14: class AuthRole(str, Enum):
15:     AIRLINE_ADMIN = "AIRLINE_ADMIN"
16:     CAAN_SMD = "CAAN_SMD"
17:     SUPER_ADMIN = "SUPER_ADMIN"
18:     USER = "USER"
19: 
20: 
21: class Settings(BaseSettings):
22:     # ── API ──
23:     API_VERSION: str = "1.0.0"
24:     API_PREFIX_AUTH: str = "/api/v1/auth"
25:     API_PREFIX_REPORTS: str = "/api/v1/reports"
26:     API_PREFIX_DASHBOARD: str = "/api/v1/dashboard"
27:     API_PREFIX_ADMIN: str = "/api/v1/admin"
28:     API_PREFIX_HAZARDS: str = "/api/v1/hazards"
29:     API_PREFIX_CAN_CAP: str = "/api/v1/cans"
30:     API_PREFIX_VERIFICATION: str = "/api/v1/verification"
31:     API_PREFIX_REPORTING: str = "/api/v1/reporting"
32:     API_PREFIX_FLIGHT_DIVERSIONS: str = "/api/v1/flight-diversions"
33:     API_PREFIX_STATE_RISK: str = "/api/v1/state-risk"
34:     API_PREFIX_SURVEYS: str = "/api/v1/surveys"
35:     API_PREFIX_TENANTS: str = "/api/v1/tenants"
36:     API_PREFIX_REGULATORS: str = "/api/v1/regulators"
37:     API_PREFIX_CONTACT: str = "/api/v1/contact"
38:     API_PREFIX_FEEDBACK: str = "/api/v1/feedback"
39:     API_PREFIX_COPILOT: str = "/api/v1/copilot"
40:     API_PREFIX_AUTH_LEGACY: str = "/api/auth"
41:     API_PREFIX_REPORTS_LEGACY: str = "/api/reports"
42:     API_PREFIX_DASHBOARD_LEGACY: str = "/api/dashboard"
43:     API_PREFIX_ADMIN_LEGACY: str = "/api/admin"
44:     API_PREFIX_HAZARDS_LEGACY: str = "/api/hazards"
45:     API_PREFIX_CAN_CAP_LEGACY: str = "/api/cans"
46:     API_PREFIX_VERIFICATION_LEGACY: str = "/api/verification"
47:     API_PREFIX_REPORTING_LEGACY: str = "/api/reporting"
48:     API_PREFIX_FLIGHT_DIVERSIONS_LEGACY: str = "/api/flight-diversions"
49:     API_PREFIX_STATE_RISK_LEGACY: str = "/api/state-risk"
50:     API_PREFIX_SURVEYS_LEGACY: str = "/api/surveys"
51:     API_PREFIX_TENANTS_LEGACY: str = "/api/tenants"
52:     DEBUG: bool = False
53:     # Deployment environment: "production" (default), "beta", "staging",
54:     # "development". Drives self-service registration gating (production
55:     # requires the enterprise access key / admin invite code) and beta sandbox
56:     # tagging (is_beta_sandbox + auto_expire_days on self-service tenants).
57:     ENVIRONMENT: str = "production"
58: 
59:     # ── CORS ──
60:     ALLOWED_ORIGINS: str = "https://sms.aviasafesystems.com,https://betasms.aviasafesystems.com,https://aerosafety-sms-prod.web.app,https://aerosafety-sms-beta.web.app,https://sms-beta.web.app,http://localhost:3000,http://localhost:8000,http://localhost:5000,http://127.0.0.1:5500"
61: 
62:     # ── Firebase ──
63:     FIREBASE_PROJECT_ID: Optional[str] = None
64:     FIREBASE_PRIVATE_KEY: Optional[str] = None
65:     FIREBASE_CLIENT_EMAIL: Optional[str] = None
66:     FIREBASE_DATABASE_ID: Optional[str] = None
67:     # Public Firebase Web API key used by the server-side login endpoint
68:     # (app/services/login_service.py) to verify credentials against the
69:     # Identity Toolkit REST API. It is the same public key shipped in
70:     # public/js/firebase.js — not a secret — but is configurable here for
71:     # non-default projects.
72:     FIREBASE_WEB_API_KEY: str = "AIzaSyCdCtUuyOcUIoCBEaiWGbhp6_XwZKHsicc"
73:     FIREBASE_COLLECTION_TENANTS: str = "tenants"
74:     FIREBASE_COLLECTION_REPORTS: str = "reports"
75:     FIREBASE_COLLECTION_METADATA: str = "metadata"
76:     FIREBASE_COLLECTION_USERS: str = "users"
77:     FIREBASE_COLLECTION_REGULATORS: str = "regulators"
78:     FIREBASE_COLLECTION_AUDIT_LOGS: str = "audit_logs"
79:     FIREBASE_DOCUMENT_INFO: str = "info"
80:     FIREBASE_TOKEN_URI: str = "https://oauth2.googleapis.com/token"
81: 
82:     # ── JWT ──
83:     JWT_ALGORITHM: str = "RS256"
84:     JWT_EXPIRES_IN: int = 3600
85: 
86:     # ── AI / Gemini ──
87:     AI_MODEL: str = "gemini-2.0-pro-exp-02-05"
88:     AI_PROMPT_VERSION: str = "2.0"
89:     AI_NARRATIVE_TRUNCATE: int = 5000
90:     AI_API_KEY: Optional[str] = None
91:     GEMINI_API_KEY: Optional[str] = None
92: 
93:     # ── AI / Groq Copilot ──
94:     # Groq API key for the Safety & Compliance Copilot chat assistant. When
95:     # unset the chat endpoint degrades to a helpful offline response (200).
96:     GROQ_API_KEY: Optional[str] = None
97:     GROQ_MODEL: str = "openai/gpt-oss-120b"
98:     GROQ_MAX_TOKENS: int = 900
99:     GROQ_TEMPERATURE: float = 0.4
100: 
101:     # ── Repository / Pagination ──
102:     REPO_CACHE_TTL_SECONDS: int = 60
103:     REPO_DEFAULT_PAGE_SIZE: int = 20
104:     REPO_MAX_PAGE_SIZE: int = 100
105:     REPO_QUERY_LIMIT: int = 5000
106: 
107:     # ── Dashboard defaults ──
108:     DASHBOARD_DEFAULT_DAYS: int = 90
109:     DASHBOARD_TREND_DAYS: int = 180
110:     DASHBOARD_RECENT_PAGE_SIZE: int = 10
111:     DASHBOARD_ADMIN_USAGE_DAYS: int = 30
112:     DASHBOARD_ADMIN_SYSTEM_DAYS: int = 7
113:     DASHBOARD_ADMIN_TENANT_DAYS: int = 30
114: 
115:     # ── Roles ──
116:     ROLE_DEFAULT: str = "USER"
117:     ROLE_DEFAULT_REGISTRATION: str = "AIRLINE_ADMIN"
118:     CROSS_TENANT_ROLES: List[str] = ["CAAN_SMD", "SUPER_ADMIN"]
119:     SUPER_ADMIN_ROLES: List[str] = ["SUPER_ADMIN"]
120: 
121:     # ── Upstash Redis (enabled when REDIS_URL is non-empty) ──
122:     REDIS_URL: str = ""
123:     REDIS_ENABLED: bool = True
124: 
125:     # ── Rate limiting ──
126:     RATE_LIMIT_PER_MINUTE: int = 60
127:     # Per-tenant daily survey submission cap (configurable per deployment).
128:     SURVEY_RATE_LIMIT: int = 5
129: 
130:     # ── Admin security (env-only; RC-1) ──
131:     # Setup key used as a second factor on admin provisioning endpoints. Never
132:     # hardcoded; must be provided via the environment. Access is never granted
133:     # by the key alone — a SUPER_ADMIN Firebase ID token is always required.
134:     SETUP_SECRET: Optional[str] = None
135:     # Shared secret for internal scheduled tasks (e.g. the Cloud Scheduler job
136:     # that runs the overdue/escalation check). Sent as the X-Task-Key header.
137:     TASK_API_KEY: Optional[str] = None
138:     # Password used by /provision-airlines. No hardcoded fallback.
139:     DEFAULT_PROVISION_PASSWORD: Optional[str] = None
140:     # Password used by the seed data pipeline (backend/seed). No hardcoded fallback.
141:     DEFAULT_SEED_PASSWORD: Optional[str] = None
142:     # When True (default), data-destructive endpoints (/seed-demo-data,
143:     # /create-seed-users) return 404. Disable only in non-production environments.
144:     DISABLE_DESTRUCTIVE_ENDPOINTS: bool = True
145: 
146:     # ── Self-service onboarding ──
147:     # Access key required for public tenant registration on the beta portal.
148:     # A blank / missing field on the form falls back to this default; a
149:     # provided key must match exactly.
150:     BETA_ACCESS_KEY: str = "AVIASAFE-BETA-2026"
151: 
152:     # ── Tenant credentials / welcome email ──
153:     # Provider: none (log + preview only), smtp, or sendgrid.
154:     EMAIL_PROVIDER: str = "none"
155:     EMAIL_FROM: Optional[str] = None
156:     EMAIL_FROM_NAME: str = "AviaSAFE SMS Team"
157:     APP_LOGIN_URL: str = "https://sms.aviasafesystems.com"
158:     APP_SUPPORT_EMAIL: str = "info@aviasafesystems.com"
159:     SENDGRID_API_KEY: Optional[str] = None
160:     SMTP_HOST: Optional[str] = None
161:     SMTP_PORT: int = 587
162:     SMTP_USER: Optional[str] = None
163:     SMTP_PASS: Optional[str] = None
164: 
165:     # ── Gmail REST API dispatcher (registration intake acknowledgments) ──
166:     # Dedicated Gmail channel used by app/services/gmail_dispatcher.py to send
167:     # self-service registration acknowledgments over HTTPS (port 443) via the
168:     # Gmail REST API with an OAuth2 refresh-token flow. Leave
169:     # GMAIL_CLIENT_ID / GMAIL_REFRESH_TOKEN empty to skip delivery (the
170:     # acknowledgment is logged only and the provisioned tenant record is never
171:     # rolled back).
172:     GMAIL_CLIENT_ID: Optional[str] = None
173:     GMAIL_CLIENT_SECRET: Optional[str] = None
174:     GMAIL_REFRESH_TOKEN: Optional[str] = None
175:     GMAIL_SENDER_EMAIL: Optional[str] = None
176:     GMAIL_NOTIFICATION_BCC: Optional[str] = None
177: 
178:     # ── Contact form / Sender.net ──
179:     # Sender.net REST API v2. The key must be set via the environment (Render
180:     # dashboard); never commit the key to the repository.
181:     SENDER_API_KEY: Optional[str] = None
182:     # Email the contact form submissions are associated with.
183:     SENDER_FROM_EMAIL: str = "info@aviasafesystems.com"
184:     # Optional Sender list/group id to add contacts to. Empty = account default.
185:     SENDER_LIST_ID: Optional[str] = None
186:     SENDER_API_BASE_URL: str = "https://api.sender.net/v2"
187: 
188:     # ── Server ──
189:     HOST: str = "0.0.0.0"
190:     PORT: int = 8000
191:     WORKERS: int = 1
192: 
193:     model_config = {"env_file": "backend/.env", "env_file_encoding": "utf-8", "case_sensitive": True, "extra": "ignore"}
194: 
195: 
196: settings = Settings()

(End of file - total 196 lines)
</content>
```

**Tool: grep**

**Input:**
```json
{
  "include": "*.js",
  "path": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public",
  "pattern": "getRoleDestination|AIRLINE_ADMIN|TENANT_ADMIN|DEPT_ADMIN|SAFETY_OFFICER|role ===|user.role"
}
```

**Output:**
```
Found 19 matches
C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\js\admin-credentials.js:
  Line 29:     var ROLES = ['AIRLINE_ADMIN', 'AIRLINE_SAFETY', 'AIRLINE_INSPECTOR', 'VIEWER'];

  Line 169:             ROLES.map(function (r) { return '<option value="' + r + '"' + (r === 'AIRLINE_ADMIN' ? ' selected' : '') + '>' + r + '</option>'; }).join('') +


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\admin\app.js:
  Line 44:             if (claims.role === 'SUPER_ADMIN') {


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\js\dashboard.js:
  Line 15:     if (user.role === 'CAAN_SMD') return 'State Aviation Safety Oversight';

  Line 16:     if (user.department === 'CAMO' || user.role === 'CAMO') return 'CAMO Department';

  Line 17:     if (user.department === 'Part-145' || user.role === '145') return 'Part-145 Maintenance Department';

  Line 18:     if (user.department === 'Flight Operations' || user.role === 'ops') return 'Flight Operations Department';

  Line 19:     return 'Corporate Safety Department'; // Default for safety / AIRLINE_ADMIN

  Line 56:     if (role !== 'AIRLINE_ADMIN' && role !== 'CAAN_SMD' && role !== 'SUPER_ADMIN') {


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\js\firebase.js:
  Line 495:     if (role === 'CAAN_SMD') return 'State Aviation Safety Oversight';

  Line 496:     if (role === 'AIRLINE_ADMIN') return 'Corporate Safety Department';

  Line 508: function getRoleDestination(user) {

  Line 509:     var role = (user && user.role) || 'USER';

  Line 510:     if (role === 'SUPER_ADMIN') return '/admin/production-setup.html';

  Line 511:     if (role === 'CAAN_SMD') return '/caan.html';

  Line 512:     if (role === 'USER') {

  Line 522:     window.location.href = getRoleDestination(user);


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\js\admin.js:
  Line 23:         if (user.role !== 'SUPER_ADMIN') {


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\js\shell.js:
  Line 39:     // A nav item may specify `roles: ['AIRLINE_ADMIN', ...]` to be shown

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 16.6s)

_Thinking:_

Now I have a clear picture. The codebase has these roles: `AIRLINE_ADMIN`, `CAAN_SMD`, `SUPER_ADMIN`, `USER`. There's no `TENANT_ADMIN`, `DEPT_ADMIN`, `SAFETY_OFFICER`, `STAFF`. The frontend has `getRoleDestination` handling SUPER_ADMIN, CAAN_SMD, USER, and AIRLINE_ADMIN.

The spec's role hierarchy:
- SUPER_ADMIN (exists)
- TENANT_ADMIN (Safety Manager) — maps to existing AIRLINE_ADMIN
- DEPT_ADMIN (HOD) — new
- SAFETY_OFFICER — new
- STAFF / EMPLOYEE — maps to existing USER

The spec endpoints: `POST /api/v1/auth/invite` + legacy `/api/auth/invite`, and `/api/v1/auth/join`. Existing: `/join-team` (self-register, invitee picks department, role=USER), `/verify-invite`.

There's no team management view. I need to decide where to add it — there's `public/admin/` folder (admin.js, app.js), `public/settings/` doesn't exist. The existing admin console is for SUPER_ADMIN. There's a `GET /api/v1/tenants/{tenantId}/users` endpoint (per users.py docstring). Let me check tenants.py for that endpoint. Actually the docstring says "consumed by GET /api/v1/tenants/{tenantId}/users" — let me check the tenants route.

This is a big ambiguity. The spec uses different endpoint names and role names than the existing codebase. I should ask the user how to proceed with mapping. But I want to minimize friction — let me propose a concrete mapping and ask for confirmation. The key decisions:

1. **Role naming**: Introduce new roles per spec (TENANT_ADMIN, DEPT_ADMIN, SAFETY_OFFICER, STAFF) and treat AIRLINE_ADMIN as TENANT_ADMIN alias? Or keep existing role names (AIRLINE_ADMIN, USER) and add DEPT_ADMIN + SAFETY_OFFICER? 

The spec explicitly lists the role hierarchy, and item 1 says "Ensure user records in Firestore contain: uid, email, tenant_id, role, department, status." It wants specific role names. Given the spec is authoritative, I'd introduce the new role names but map AIRLINE_ADMIN → TENANT_ADMIN for backward compat. Actually, safest: support BOTH. Recognize AIRLINE_ADMIN as equivalent to TENANT_ADMIN in permission checks (tenant admin capabilities), and use new names going forward. But claims use "role" string. The frontend getRoleDestination only checks specific strings; I'd need to add TENANT_ADMIN etc.

2. **Endpoints**: The spec wants `POST /api/v1/auth/invite` and `/api/auth/invite`. These are new admin endpoints. Should I also keep `/join-team`? The spec wants `/api/v1/auth/join` — but existing join.html uses `/join-team`. I'd add the invite endpoint (new) and enhance the join flow. Should I create a new `/join` endpoint or adapt `/join-team`? The spec says "When resolving invite code in /api/v1/auth/join: Read the assigned department and role directly from the valid invite document." I could implement the logic in the existing `/join-team` endpoint (and/or add a `/join` alias). 

Given the complexity, I think it's best to ask the user a focused clarifying question. But the user gave a "Continue if you have next steps, or stop and ask for clarification if you are unsure how to proceed." 

I've done enough exploration to be sure this needs clarification on the naming/mapping. But let me minimize: I'll ask 2 questions max:
- Q1: How to map roles (new names per spec vs existing AIRLINE_ADMIN/USER + new roles)?
- Q2: Endpoint strategy — add new `/invite` + `/join` endpoints per spec, or extend existing `/join-team`?

Actually, let me reconsider. The spec is quite explicit. Perhaps the user wants me to implement exactly as specified, creating the new endpoints and roles, while keeping backward compatibility. The risk of just proceeding: frontend role handling could break for existing users (AIRLINE_ADMIN users would lose admin access if the frontend/backend switches to TENANT_ADMIN only). 

I think the responsible move is to ask ONE consolidated clarifying question about mapping, with a recommended option, since this materially affects the design. Let me also check the tenants.py users endpoint and the middleware auth.py to understand get_current_user and role checks, plus how main.py mounts routers (legacy aliases), so my question and subsequent implementation are well-grounded. Let me read those in parallel.

Let me check the users list endpoint, auth middleware, and route mounting before finalizing the approach

**Tool: grep**

**Input:**
```json
{
  "include": "*.py",
  "path": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend",
  "pattern": "/users|list_tenant_users|get_current_user|get_safety_manager|resolve_user_context"
}
```

**Output:**
```
Found 100 matches (more matches available)
C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\scripts\backfill_users.py:
  Line 49: from app.services.users import backfill_users_from_auth, list_tenant_users

  Line 55:     users = list_tenant_users(tid)


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\scripts\purge_legacy_accounts.py:
  Line 4: sms-db-beta Firebase Auth + Firestore /users.

  Line 13:   - Firestore /users documents whose id matches ^(sm|ae|mgr)-

  Line 62:     print(f"Firestore /users docs: {len(fs_docs)}")


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\middleware\auth.py:
  Line 47: def resolve_user_context(email: str, role: str, tenant_id: Optional[str]) -> Dict[str, Any]:

  Line 94: async def get_current_user(

  Line 112:     resolved = resolve_user_context(email, role, tenant_id)

  Line 133:     user: Dict[str, Any] = Depends(get_current_user)

  Line 144:     user: Dict[str, Any] = Depends(get_current_user)

  Line 155:     user: Dict[str, Any] = Depends(get_current_user)

  Line 165: async def get_safety_manager(

  Line 166:     user: Dict[str, Any] = Depends(get_current_user)

  Line 204:     user: Dict[str, Any] = Depends(get_current_user)

  Line 220:     user: Dict[str, Any] = Depends(get_current_user)


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\services\gmail_dispatcher.py:
  Line 13: #               POST https://gmail.googleapis.com/gmail/v1/users/me/messages/send

  Line 45: GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\feedback.py:
  Line 19: from app.middleware.auth import get_current_user

  Line 45:     user: Dict[str, Any] = Depends(get_current_user),


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\copilot.py:
  Line 21: from app.middleware.auth import get_current_user

  Line 51:     user: Dict[str, Any] = Depends(get_current_user),


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\dashboard.py:
  Line 18: from app.middleware.auth import get_current_user, get_tenant_user, get_caan_user, get_admin_user

  Line 171:     user: Dict[str, Any] = Depends(get_current_user),


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\can_cap.py:
  Line 10: from app.middleware.auth import get_current_user, get_tenant_user, get_safety_manager, get_responsible_manager, get_department_scope

  Line 23:     user: Dict[str, Any] = Depends(get_safety_manager),

  Line 53:     user: Dict[str, Any] = Depends(get_current_user),

  Line 84:     user: Dict[str, Any] = Depends(get_current_user),

  Line 101:     user: Dict[str, Any] = Depends(get_current_user),

  Line 131:     user: Dict[str, Any] = Depends(get_current_user),

  Line 145:     user: Dict[str, Any] = Depends(get_safety_manager),

  Line 161:     user: Dict[str, Any] = Depends(get_safety_manager),

  Line 216:     user: Dict[str, Any] = Depends(get_current_user),

  Line 227:     user: Dict[str, Any] = Depends(get_current_user),

  Line 258:     user: Dict[str, Any] = Depends(get_safety_manager),


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\tests\test_admin_credentials.py:
  Line 13: from app.middleware.auth import get_admin_user, get_current_user

  Line 186:     app.dependency_overrides.pop(get_current_user, None)

  Line 330:     app.dependency_overrides[get_current_user] = lambda: _admin_user(role="AIRLINE_ADMIN")


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\tests\test_admin_feedback.py:
  Line 12: from app.middleware.auth import get_current_user

  Line 82:     app.dependency_overrides[get_current_user] = lambda: user or _user()

  Line 87:     app.dependency_overrides.pop(get_current_user, None)


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\flight_diversions.py:
  Line 9: from app.middleware.auth import get_current_user, get_tenant_user, get_safety_manager, get_admin_user

  Line 101:     user: Dict[str, Any] = Depends(get_current_user),

  Line 121:     user: Dict[str, Any] = Depends(get_current_user),

  Line 131:     user: Dict[str, Any] = Depends(get_current_user),

  Line 183:     user: Dict[str, Any] = Depends(get_safety_manager),

  Line 198:     user: Dict[str, Any] = Depends(get_safety_manager),


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\tests\test_admin_seed.py:
  Line 13: from app.middleware.auth import get_admin_user, get_current_user

  Line 346:     # No override -> real get_current_user -> 401/403

  Line 353:     # Override the *underlying* get_current_user so get_admin_user's real check

  Line 355:     app.dependency_overrides[get_current_user] = lambda: _admin_user(role="AIRLINE_ADMIN")

  Line 359:         app.dependency_overrides.pop(get_current_user, None)


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\admin.py:
  Line 21: from app.middleware.auth import get_current_user, get_safety_manager, get_admin_user

  Line 92:     user: Dict[str, Any] = Depends(get_safety_manager),

  Line 108:     user: Dict[str, Any] = Depends(get_safety_manager),

  Line 802:     user: Dict[str, Any] = Depends(get_current_user),

  Line 861: # PENDING_REVIEW); `get_current_user` in middleware/auth.py rejects users whose

  Line 870:     user: Dict[str, Any] = Depends(get_current_user),

  Line 940:     (middleware/auth.py -> get_current_user) with HTTP 403.


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\tests\test_admin_tenants.py:
  Line 6: belonging to a SUSPENDED tenant is rejected by get_current_user with HTTP 403.

  Line 17: from app.middleware.auth import get_current_user, SUSPENDED_TENANT_DETAIL

  Line 104:     app.dependency_overrides[get_current_user] = lambda: user or _user()

  Line 109:     app.dependency_overrides.pop(get_current_user, None)

  Line 270:         asyncio.run(get_current_user(_Creds("token")))

  Line 279:     user = asyncio.run(get_current_user(_Creds("token")))

  Line 289:     user = asyncio.run(get_current_user(_Creds("token")))

  Line 304:     user = asyncio.run(get_current_user(_Creds("token")))


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\hazards.py:
  Line 19: from app.middleware.auth import get_current_user, get_tenant_user, get_safety_manager

  Line 68:     user: Dict[str, Any] = Depends(get_current_user),

  Line 98:     user: Dict[str, Any] = Depends(get_current_user),

  Line 108:     user: Dict[str, Any] = Depends(get_current_user),

  Line 203:     user: Dict[str, Any] = Depends(get_current_user),


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\auth.py:
  Line 27: from app.middleware.auth import resolve_user_context

  Line 131:     resolved = resolve_user_context(decoded_token.get('email', ''), role, tenant_id)


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\reports.py:
  Line 19: from app.middleware.auth import get_current_user, get_tenant_user, get_safety_manager

  Line 167:     user: Dict[str, Any] = Depends(get_current_user),

  Line 185:     user: Dict[str, Any] = Depends(get_current_user),

  Line 203:     user: Dict[str, Any] = Depends(get_safety_manager),


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\reporting.py:
  Line 8: from app.middleware.auth import get_current_user, get_tenant_user

  Line 51:     user: Dict[str, Any] = Depends(get_current_user),

  Line 97:     user: Dict[str, Any] = Depends(get_current_user),

  Line 140:     user: Dict[str, Any] = Depends(get_current_user),

  Line 166:     user: Dict[str, Any] = Depends(get_current_user),

  Line 207:     user: Dict[str, Any] = Depends(get_current_user),

  Line 253:     user: Dict[str, Any] = Depends(get_current_user),

  Line 296:     user: Dict[str, Any] = Depends(get_current_user),

  Line 322:     user: Dict[str, Any] = Depends(get_current_user),


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\services\users.py:
  Line 3: # PATH: backend/app/services/users.py

  Line 7: #          consumed by GET /api/v1/tenants/{tenantId}/users.

  Line 96: def list_tenant_users(tenant_id: str) -> List[Dict[str, Any]]:


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\tests\test_dashboard_risk_trends.py:
  Line 18: from app.middleware.auth import get_current_user

  Line 50:     app.dependency_overrides[get_current_user] = lambda: user

  Line 54:     app.dependency_overrides.pop(get_current_user, None)


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\surveys.py:
  Line 20: from app.middleware.auth import get_current_user

  Line 48:     return await get_current_user(credentials)


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\tests\test_feedback.py:
  Line 14: from app.middleware.auth import get_current_user

  Line 28:     app.dependency_overrides[get_current_user] = lambda: user

  Line 32:     app.dependency_overrides.pop(get_current_user, None)


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\verification.py:
  Line 7: from app.middleware.auth import get_current_user, get_tenant_user, get_safety_manager, get_accountable_executive

  Line 26:     user: Dict[str, Any] = Depends(get_safety_manager),

  Line 41:     user: Dict[str, Any] = Depends(get_current_user),


(Results truncated. Consider using a more specific path or pattern.)
```

**Tool: read**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\middleware\\auth.py"
}
```

**Output:**
```
<path>C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\middleware\auth.py</path>
<type>file</type>
<content>
1: # ============================================================================
2: # FILE: auth.py
3: # PATH: backend/app/middleware/auth.py
4: # VERSION: 1.0.0
5: # DATE CREATED: 2026-07-03
6: # DATE REVISED: 2026-07-03
7: # PURPOSE: Authentication middleware for FastAPI routes.
8: #          Verifies Firebase ID tokens and extracts user claims.
9: # AUTHOR: Ghanshyam Acharya
10: # CODE OWNER: AviaSafeSystems
11: # ============================================================================
12: 
13: from fastapi import HTTPException, Security, Depends
14: from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
15: from typing import Dict, Any, Optional
16: from loguru import logger
17: 
18: from app.core.config import settings
19: from app.firebase import verify_firebase_token, get_db
20: 
21: security = HTTPBearer()
22: 
23: 
24: def _lookup_tenant_by_email(email: str) -> Optional[Dict[str, Any]]:
25:     """Search all tenant documents for a safety_manager with matching email.
26: 
27:     This is a fallback when Firebase Auth custom claims are not available
28:     in the ID token (known Firebase propagation issue).
29:     """
30:     try:
31:         db = get_db()
32:         tenants = db.collection(settings.FIREBASE_COLLECTION_TENANTS).get()
33:         for t in tenants:
34:             td = t.to_dict()
35:             if not td:
36:                 continue
37:             sm = td.get("safety_manager")
38:             if sm and sm.get("email") == email:
39:                 return {"tenant_id": td.get("tenant_id") or t.id, "role": "AIRLINE_ADMIN"}
40:             # Also check for CAAN_SMD emails in a separate config
41:         return None
42:     except Exception as e:
43:         logger.warning(f"Tenant lookup failed for {email}: {e}")
44:         return None
45: 
46: 
47: def resolve_user_context(email: str, role: str, tenant_id: Optional[str]) -> Dict[str, Any]:
48:     """Normalize tenant_id and fall back to a Firestore email lookup when the
49:     ID token carries no custom claims (e.g. freshly-linked Google sign-ins)."""
50:     if tenant_id:
51:         normalized = tenant_id.replace('_', '-')
52:         if normalized != tenant_id:
53:             logger.info(f"Normalized tenant_id for {email}: '{tenant_id}' -> '{normalized}'")
54:             tenant_id = normalized
55: 
56:     if role == settings.ROLE_DEFAULT and not tenant_id and email:
57:         tenant_info = _lookup_tenant_by_email(email)
58:         if tenant_info:
59:             role = tenant_info["role"]
60:             tenant_id = tenant_info["tenant_id"]
61:             logger.info(f"Claims resolved via Firestore fallback for {email}: role={role}, tenant={tenant_id}")
62: 
63:     return {"role": role, "tenant_id": tenant_id}
64: 
65: 
66: SUSPENDED_TENANT_DETAIL = (
67:     "This organization account is currently inactive or suspended. "
68:     "Please contact support@aviasafesystems.com."
69: )
70: 
71: 
72: def _tenant_is_suspended(tenant_id: str) -> bool:
73:     """True when the tenant document's governance status is SUSPENDED.
74: 
75:     Fail-open by design: a missing doc, missing status or a database error
76:     must never lock a user out of the platform — only an explicit
77:     ``status == "SUSPENDED"`` blocks access.
78:     """
79:     try:
80:         db = get_db()
81:         doc = (
82:             db.collection(settings.FIREBASE_COLLECTION_TENANTS)
83:             .document(tenant_id)
84:             .get()
85:         )
86:         if doc is None or not doc.exists:
87:             return False
88:         return (doc.to_dict() or {}).get("status") == "SUSPENDED"
89:     except Exception as e:
90:         logger.warning(f"Tenant status check failed for {tenant_id}: {e}")
91:         return False
92: 
93: 
94: async def get_current_user(
95:     credentials: HTTPAuthorizationCredentials = Security(security)
96: ) -> Dict[str, Any]:
97:     token = credentials.credentials
98:     decoded_token = verify_firebase_token(token)
99: 
100:     if not decoded_token:
101:         raise HTTPException(
102:             status_code=401,
103:             detail="Invalid authentication credentials",
104:             headers={"WWW-Authenticate": "Bearer"},
105:         )
106: 
107:     email = decoded_token.get('email', '')
108:     role = decoded_token.get('role', settings.ROLE_DEFAULT)
109:     tenant_id = decoded_token.get('tenant_id')
110:     department = decoded_token.get('department') or None
111: 
112:     resolved = resolve_user_context(email, role, tenant_id)
113:     role = resolved["role"]
114:     tenant_id = resolved["tenant_id"]
115: 
116:     if tenant_id and role not in settings.CROSS_TENANT_ROLES and _tenant_is_suspended(tenant_id):
117:         logger.warning(f"Suspended tenant access denied for {email} (tenant={tenant_id})")
118:         raise HTTPException(status_code=403, detail=SUSPENDED_TENANT_DETAIL)
119: 
120:     logger.info(f"Authenticated user {email}: role={role}, tenant_id={tenant_id}")
121: 
122:     return {
123:         "uid": decoded_token['uid'],
124:         "email": email,
125:         "role": role,
126:         "tenant_id": tenant_id,
127:         "department": department,
128:         "claims": {"role": role, "tenant_id": tenant_id, "department": department},
129:     }
130: 
131: 
132: async def get_tenant_user(
133:     user: Dict[str, Any] = Depends(get_current_user)
134: ) -> Dict[str, Any]:
135:     if not user.get('tenant_id'):
136:         raise HTTPException(
137:             status_code=403,
138:             detail="User does not have tenant access"
139:         )
140:     return user
141: 
142: 
143: async def get_caan_user(
144:     user: Dict[str, Any] = Depends(get_current_user)
145: ) -> Dict[str, Any]:
146:     if user.get('role') not in settings.CROSS_TENANT_ROLES:
147:         raise HTTPException(
148:             status_code=403,
149:             detail="CAAN_SMD role required"
150:         )
151:     return user
152: 
153: 
154: async def get_admin_user(
155:     user: Dict[str, Any] = Depends(get_current_user)
156: ) -> Dict[str, Any]:
157:     if user.get('role') not in settings.SUPER_ADMIN_ROLES:
158:         raise HTTPException(
159:             status_code=403,
160:             detail="SUPER_ADMIN role required"
161:         )
162:     return user
163: 
164: 
165: async def get_safety_manager(
166:     user: Dict[str, Any] = Depends(get_current_user)
167: ) -> Dict[str, Any]:
168:     if user.get('role') not in settings.CROSS_TENANT_ROLES and user.get('role') != "AIRLINE_ADMIN":
169:         raise HTTPException(
170:             status_code=403,
171:             detail="Safety Manager or CAAN_SMD role required"
172:         )
173:     if user.get('role') == "AIRLINE_ADMIN" and not user.get('tenant_id'):
174:         raise HTTPException(
175:             status_code=403,
176:             detail="Tenant access required for AIRLINE_ADMIN"
177:         )
178:     return user
179: 
180: 
181: # Department accounts (email prefix) -> the single department they are scoped to.
182: # Used to restrict 145 / CAMO users to only their own department's CANs & CAPs.
183: DEPARTMENT_SCOPE_PREFIXES = {
184:     "145": "Part-145",
185:     "camo": "CAMO",
186: }
187: 
188: 
189: def get_department_scope(user: Dict[str, Any]) -> Optional[str]:
190:     """Return the department a user is restricted to based on their email prefix.
191: 
192:     Emails starting with ``145`` or ``camo`` belong to the Part-145 / CAMO
193:     departments and should only ever see CANs and CAPs for that department.
194:     Returns ``None`` for all other users (no restriction).
195:     """
196:     email = (user.get("email") or "").lower()
197:     for prefix, department in DEPARTMENT_SCOPE_PREFIXES.items():
198:         if email.startswith(prefix):
199:             return department
200:     return None
201: 
202: 
203: async def get_responsible_manager(
204:     user: Dict[str, Any] = Depends(get_current_user)
205: ) -> Dict[str, Any]:
206:     if user.get('role') not in settings.CROSS_TENANT_ROLES and user.get('role') not in ("AIRLINE_ADMIN", "USER"):
207:         raise HTTPException(
208:             status_code=403,
209:             detail="Responsible Manager, AIRLINE_ADMIN, or CAAN_SMD role required"
210:         )
211:     if not user.get('tenant_id') and user.get('role') not in settings.CROSS_TENANT_ROLES:
212:         raise HTTPException(
213:             status_code=403,
214:             detail="Tenant access required"
215:         )
216:     return user
217: 
218: 
219: async def get_accountable_executive(
220:     user: Dict[str, Any] = Depends(get_current_user)
221: ) -> Dict[str, Any]:
222:     if user.get('role') not in settings.CROSS_TENANT_ROLES and user.get('role') != "AIRLINE_ADMIN":
223:         raise HTTPException(
224:             status_code=403,
225:             detail="Accountable Executive, AIRLINE_ADMIN, or CAAN_SMD role required"
226:         )
227:     if user.get('role') == "AIRLINE_ADMIN" and not user.get('tenant_id'):
228:         raise HTTPException(
229:             status_code=403,
230:             detail="Tenant access required for AIRLINE_ADMIN"
231:         )
232:     return user

(End of file - total 232 lines)
</content>
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 246.9s)

_Thinking:_

Now I have a complete picture. The codebase's existing roles and structure differ significantly from the spec. The spec wants:

Roles: SUPER_ADMIN, TENANT_ADMIN, DEPT_ADMIN, SAFETY_OFFICER, STAFF/EMPLOYEE.

Existing: AIRLINE_ADMIN (=tenant admin/safety manager), CAAN_SMD, SUPER_ADMIN, USER.

The spec's endpoint names: `POST /api/v1/auth/invite` (+ legacy `/api/auth/invite`), `POST /api/v1/auth/join`.

Existing: `/join-team`, `/verify-invite`, `/tenant-lookup`, `/register-tenant`.

There's no `auth_service.py` — invite/join logic is in `tenant_registration.py`. No `settings/team.html`.

Given this divergence, this is a case where I should ask the user for clarification on the mapping before implementing a large feature. The instruction says "Continue if you have next steps, or stop and ask for clarification if you are unsure how to proceed."

I am genuinely unsure how to map the spec onto the existing codebase without risking breaking existing behavior (e.g., AIRLINE_ADMIN users, the join.html frontend flow, getRoleDestination routing, get_safety_manager checks). Let me ask a concise clarifying question with a recommended option.

Options for the key question (role + endpoint mapping):
1. **Additive with backward compatibility (Recommended)**: Introduce new role constants (TENANT_ADMIN, DEPT_ADMIN, SAFETY_OFFICER, STAFF) alongside existing ones. Treat AIRLINE_ADMIN as an alias for TENANT_ADMIN everywhere a tenant-admin check happens (get_safety_manager, etc.), and USER as STAFF. Add new protected `POST /api/v1/auth/invite` (admin-scoped, creates department-scoped invite docs under `tenants/{tid}/invites/`) + legacy `/api/auth/invite`. Extend the existing `/join-team` flow to resolve department+role from the invite doc when present (keep invitee-self-select as fallback for legacy tenant-level codes), and also add `/api/v1/auth/join` alias. Frontend: create `public/settings/team.html` team management page wired into the shell nav for TENANT_ADMIN + DEPT_ADMIN.
2. Follow spec literally: replace roles/endpoints wholesale (risky — breaks existing AIRLINE_ADMIN flows and join.html).
3. Minimal: only implement backend invite + join-team enhancement + tests, skip frontend page (since no team page exists).

I'll ask one question with these options. Actually, I could ask 2 questions: one on role/endpoint mapping, one on frontend placement (new settings/team.html vs modal in dashboard). Let me combine into a single question set with 2 questions. But keep it tight.

Actually, let me reconsider whether to ask at all. The user has been directing large features and expects execution. The previous rounds (Gmail, SRM) the user accepted the mapping decision I made (for frontend files). In the SRM round, I asked about the missing files and the user picked Option 1 (map to real pages). So asking a focused mapping question is consistent with the established workflow and the user's last message explicitly invites it ("stop and ask for clarification if you are unsure how to proceed").

I'll ask a focused question.

The spec describes endpoints, roles, and a team page that don't exist yet in this codebase. Current state:

- **Roles today**: `AIRLINE_ADMIN` (tenant admin), `USER`, `CAAN_SMD`, `SUPER_ADMIN` — no `TENANT_ADMIN`/`DEPT_ADMIN`/`SAFETY_OFFICER`/`STAFF`.
- **Invite flow today**: public self-service only — `/join-team` lets an invitee pick their own department and always becomes `USER`; there's no authenticated admin `invite` endpoint and no `auth_service.py` (logic lives in `tenant_registration.py`).
- **No team-management page** exists (`public/settings/` is empty); `getRoleDestination`/`get_safety_manager` key off `AIRLINE_ADMIN`/`USER`.

Before I implement, I need to confirm the mapping so I don't break the existing `AIRLINE_ADMIN`/`USER` flows.

**Tool: question**

**Input:**
```json
{
  "questions": [
    {
      "question": "How should I map the spec's roles/endpoints onto the existing codebase (which uses AIRLINE_ADMIN and USER)?",
      "header": "Role/endpoint mapping",
      "options": [
        {
          "label": "Additive + backward compatible (Recommended)",
          "description": "Add DEPT_ADMIN/SAFETY_OFFICER/STAFF + TENANT_ADMIN as new role constants; treat AIRLINE_ADMIN==TENANT_ADMIN and USER==STAFF in existing checks. Add new authenticated POST /api/v1/auth/invite (+ /api/auth/invite legacy) that writes department-scoped invite docs; extend the existing /join-team flow to read department+role from the invite doc when present (keep legacy behavior as fallback). Add /api/v1/auth/join as an alias."
        },
        {
          "label": "Follow spec literally",
          "description": "Replace AIRLINE_ADMIN->TENANT_ADMIN and USER->STAFF everywhere, add /invite and /join as brand-new endpoints, and retire the /join-team self-select flow. Higher risk: breaks existing provisioned users, join.html, and role-based guards."
        },
        {
          "label": "Backend only",
          "description": "Implement invite endpoint + join-team enhancement + RBAC enforcement + tests only; skip the team-management UI for now."
        }
      ]
    },
    {
      "question": "Where should the team-management view live for TENANT_ADMIN and DEPT_ADMIN?",
      "header": "Team UI location",
      "options": [
        {
          "label": "New public/settings/team.html (Recommended)",
          "description": "Create a dedicated team page as the spec names it, wired into the existing shell nav so both TENANT_ADMIN and DEPT_ADMIN can reach it (role-aware rendering)."
        },
        {
          "label": "Modal in existing dashboard",
          "description": "Add a team-management modal to the existing Safety dashboard instead of a new page."
        }
      ]
    }
  ]
}
```

**Output:**
```
User has answered your questions: "How should I map the spec's roles/endpoints onto the existing codebase (which uses AIRLINE_ADMIN and USER)?"="Proceed with Option 1: Additive + backward compatible.

1. Role Model:
   - Define role constants: AIRLINE_ADMIN, TENANT_ADMIN (alias for AIRLINE_ADMIN), DEPT_ADMIN, SAFETY_OFFICER, USER, STAFF (alias for USER), CAAN_SMD, SUPER_ADMIN.
   - Update role checking utilities so existing AIRLINE_ADMIN/USER checks recognize the new equivalents.

2. Invites & Registration:
   - Implement authenticated POST /api/v1/auth/invite (+ /api/auth/invite alias) writing department-scoped invite documents.
   - Extend the /join-team endpoint to extract department + role from the invite document when available, falling back gracefully to existing behavior.
   - Alias /api/v1/auth/join to the join handler.

3. Team UI:
   - Add the team management view under public/settings/team.html (or embed as a scoped modal accessible to AIRLINE_ADMIN / TENANT_ADMIN and DEPT_ADMIN), applying department locks for DEPT_ADMIN.", "Where should the team-management view live for TENANT_ADMIN and DEPT_ADMIN?"="Proceed with Option 1: New public/settings/team.html.

Create the dedicated team management page under public/settings/team.html, wired into the existing shell navigation with role-aware rendering for both TENANT_ADMIN and DEPT_ADMIN.". You can now continue with the user's answers in mind.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 18.0s)

_Thinking:_

The user chose Option 1 for both. Now let me plan the implementation.

Let me first look at a few more things:
1. How main.py mounts routers (legacy aliases) so I can add `/api/v1/auth/join` alias and `/api/auth/invite` legacy.
2. The existing `test_auth.py` and how tests mock Firestore/Auth to follow the pattern.
3. The shell navigation (public/js/shell.js) to wire the team page.
4. Existing user listing endpoint (GET /api/v1/tenants/{tenantId}/users) — where is it? Let me check tenants.py.

Let me set up todos and read these files in parallel.

Let me check:
- backend/app/main.py
- backend/tests/test_auth.py (mocking pattern)
- backend/app/routes/tenants.py (users endpoint)
- public/js/shell.js (nav)
- public/dashboard.html or similar to see the shell usage
- public/js/firebase.js getRoleDestination (lines ~490-525)

Let me read these.

Now let me set up the task plan and gather the remaining context



**Tool: todowrite**

**Input:**
```json
{
  "todos": [
    {
      "content": "Add role constants/aliases (TENANT_ADMIN, DEPT_ADMIN, SAFETY_OFFICER, STAFF) to config.py + update role-checking middleware (get_safety_manager, get_responsible_manager, resolve_user_context) to recognize equivalents",
      "priority": "high",
      "status": "pending"
    },
    {
      "content": "Implement authenticated POST /api/v1/auth/invite + /api/auth/invite legacy in routes/auth.py writing department-scoped invite docs under tenants/{tid}/invites/{code}",
      "priority": "high",
      "status": "pending"
    },
    {
      "content": "Extend /join-team (+ add /api/v1/auth/join alias) to read department+role from invite doc when present, fall back to legacy self-select behavior",
      "priority": "high",
      "status": "pending"
    },
    {
      "content": "Create GET /api/v1/tenants/{tenantId}/users endpoint honoring DEPT_ADMIN department scoping (filter to caller's department)",
      "priority": "high",
      "status": "pending"
    },
    {
      "content": "Create public/settings/team.html + team.js with role-aware rendering (DEPT_ADMIN locks department+STAFF role; TENANT_ADMIN full controls)",
      "priority": "high",
      "status": "pending"
    },
    {
      "content": "Wire team page into shell navigation with role-aware visibility",
      "priority": "medium",
      "status": "pending"
    },
    {
      "content": "Write backend/tests/test_dept_admin_rbac.py covering all spec scenarios (invite grants, 403 cross-dept, 403 escalation, join binding dept+role)",
      "priority": "high",
      "status": "pending"
    },
    {
      "content": "Run full pytest + frontend integrity checks (check-inline-scripts, node --check, frontend suites)",
      "priority": "high",
      "status": "pending"
    },
    {
      "content": "Commit, sync feat branch, push both branches, verify backend /health + Firebase hosting deploy",
      "priority": "high",
      "status": "pending"
    }
  ]
}
```

**Output:**
```
[
  {
    "content": "Add role constants/aliases (TENANT_ADMIN, DEPT_ADMIN, SAFETY_OFFICER, STAFF) to config.py + update role-checking middleware (get_safety_manager, get_responsible_manager, resolve_user_context) to recognize equivalents",
    "status": "pending",
    "priority": "high"
  },
  {
    "content": "Implement authenticated POST /api/v1/auth/invite + /api/auth/invite legacy in routes/auth.py writing department-scoped invite docs under tenants/{tid}/invites/{code}",
    "status": "pending",
    "priority": "high"
  },
  {
    "content": "Extend /join-team (+ add /api/v1/auth/join alias) to read department+role from invite doc when present, fall back to legacy self-select behavior",
    "status": "pending",
    "priority": "high"
  },
  {
    "content": "Create GET /api/v1/tenants/{tenantId}/users endpoint honoring DEPT_ADMIN department scoping (filter to caller's department)",
    "status": "pending",
    "priority": "high"
  },
  {
    "content": "Create public/settings/team.html + team.js with role-aware rendering (DEPT_ADMIN locks department+STAFF role; TENANT_ADMIN full controls)",
    "status": "pending",
    "priority": "high"
  },
  {
    "content": "Wire team page into shell navigation with role-aware visibility",
    "status": "pending",
    "priority": "medium"
  },
  {
    "content": "Write backend/tests/test_dept_admin_rbac.py covering all spec scenarios (invite grants, 403 cross-dept, 403 escalation, join binding dept+role)",
    "status": "pending",
    "priority": "high"
  },
  {
    "content": "Run full pytest + frontend integrity checks (check-inline-scripts, node --check, frontend suites)",
    "status": "pending",
    "priority": "high"
  },
  {
    "content": "Commit, sync feat branch, push both branches, verify backend /health + Firebase hosting deploy",
    "status": "pending",
    "priority": "high"
  }
]
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 13.1s)





**Tool: read**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\main.py"
}
```

**Output:**
```
<path>C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\main.py</path>
<type>file</type>
<content>
1: from contextlib import asynccontextmanager
2: from datetime import datetime, timezone
3: from fastapi import FastAPI, Request
4: from fastapi.responses import JSONResponse
5: from fastapi.middleware.cors import CORSMiddleware
6: from fastapi.exceptions import RequestValidationError
7: from starlette.exceptions import HTTPException as StarletteHTTPException
8: from loguru import logger
9: 
10: from app.core.config import settings
11: from app.core.logging import setup_logging, RequestLoggingMiddleware
12: from app.core.metrics import router as metrics_router
13: from app.core.security import SecurityHeadersMiddleware, RateLimitMiddleware
14: from app.core.cors import ManualCORSMiddleware
15: from app.firebase import initialize_firebase, is_firebase_ready
16: from app.routes import reports, dashboard, auth, admin, hazards, can_cap, verification, reporting, flight_diversions, state_risk, surveys, tenants, regulators, contact, feedback, copilot
17: 
18: setup_logging()
19: 
20: # The application's own hosting frontends are always valid CORS origins. They are
21: # merged into whatever ALLOWED_ORIGINS is configured with so a stale or partial
22: # environment variable can never break the browser -> API calls (CORS preflight).
23: CANONICAL_ALLOWED_ORIGINS = (
24:     "https://sms.aviasafesystems.com",
25:     "https://betasms.aviasafesystems.com",
26:     "https://aerosafety-sms-prod.web.app",
27:     "https://aerosafety-sms-beta.web.app",
28:     "https://sms-beta.web.app",
29:     "https://demo.aviasafesystems.com",
30:     # Public survey frontends (multi-tenant subdomains / portals)
31:     "https://smssurvey.gsacharya.com",
32:     "https://sms.nac.com.np",
33:     "https://ssp.caanepal.gov.np",
34:     # Local development / static file servers
35:     "http://localhost:5000",
36:     "http://localhost:8000",
37:     "http://127.0.0.1:5500",
38: )
39: 
40: 
41: def _allowed_origins() -> list[str]:
42:     configured = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
43:     for origin in CANONICAL_ALLOWED_ORIGINS:
44:         if origin not in configured:
45:             configured.append(origin)
46:     return configured
47: 
48: 
49: @asynccontextmanager
50: async def lifespan(app: FastAPI):
51:     try:
52:         initialize_firebase()
53:     except Exception as e:
54:         logger.warning(f"Firebase initialization failed at startup: {e}. Lazy init will retry on first request.")
55:     yield
56: 
57: 
58: app = FastAPI(
59:     title="AviaSAFE SMS API",
60:     description="Safety Climate Measurement System - ICAO Annex 19 Compliant",
61:     version=settings.API_VERSION,
62:     debug=settings.DEBUG,
63:     lifespan=lifespan,
64: )
65: 
66: app.add_middleware(
67:     CORSMiddleware,
68:     allow_origins=_allowed_origins(),
69:     allow_credentials=True,
70:     allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
71:     allow_headers=[
72:         "Authorization",
73:         "Content-Type",
74:         "X-Firebase-AppCheck",
75:         "X-Requested-With",
76:         "Accept",
77:         "Origin",
78:         "X-Tenant-Id",
79:         "X-User-Department",
80:         "X-Task-Key",
81:         "X-Request-ID",
82:     ],
83:     expose_headers=[
84:         "Retry-After",
85:         "X-RateLimit-Limit",
86:         "X-RateLimit-Remaining",
87:         "X-RateLimit-Reset",
88:     ],
89: )
90: 
91: # Guarantees Access-Control-Allow-Origin on actual (non-preflight) responses.
92: # See app/core/cors.py for why this is needed in addition to CORSMiddleware.
93: app.add_middleware(ManualCORSMiddleware)
94: 
95: app.add_middleware(SecurityHeadersMiddleware)
96: app.add_middleware(RateLimitMiddleware)
97: app.add_middleware(RequestLoggingMiddleware)
98: 
99: 
100: def _req_id(request: Request) -> str:
101:     return getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID", "")
102: 
103: 
104: def _cors_headers(request: Request) -> dict:
105:     """Mirror ManualCORSMiddleware so error responses stay CORS-visible.
106: 
107:     Without this, an unhandled exception returns a 500 with no
108:     Access-Control-Allow-Origin, and the browser hides the body behind a
109:     generic "Network error" instead of surfacing the real message.
110:     """
111:     try:
112:         from app.core.cors import _allowed_origins, ALLOWED_HEADERS
113:         origin = request.headers.get("origin")
114:         if origin and origin in _allowed_origins():
115:             return {
116:                 "Access-Control-Allow-Origin": origin,
117:                 "Access-Control-Allow-Credentials": "true",
118:                 "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
119:                 "Access-Control-Allow-Headers": ALLOWED_HEADERS,
120:                 "Access-Control-Expose-Headers": (
121:                     "Retry-After, X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset"
122:                 ),
123:                 "Vary": "Origin",
124:             }
125:     except Exception:
126:         pass
127:     return {}
128: 
129: 
130: def _error_body(
131:     request: Request,
132:     status_code: int,
133:     message: str,
134:     detail=None,
135:     errors=None,
136: ) -> dict:
137:     """Structured error envelope.
138: 
139:     The primary `error` object carries the machine-readable contract
140:     (code / message / timestamp / requestId). Legacy top-level fields
141:     (`success`, `detail`, `errors`, `request_id`) are preserved so existing
142:     frontend clients keep parsing error messages unchanged.
143:     """
144:     request_id = _req_id(request)
145:     return {
146:         "error": {
147:             "code": status_code,
148:             "message": message,
149:             "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
150:             "requestId": request_id,
151:         },
152:         "success": False,
153:         "detail": detail if detail is not None else message,
154:         "errors": errors,
155:         "request_id": request_id,
156:     }
157: 
158: 
159: @app.exception_handler(StarletteHTTPException)
160: async def http_exception_handler(request: Request, exc: StarletteHTTPException):
161:     detail = exc.detail
162:     errors = None
163:     if isinstance(detail, dict):
164:         message = detail.get("message") or "Request failed"
165:         errors = detail.get("errors")
166:     else:
167:         message = detail if isinstance(detail, str) else str(detail)
168:     request_id = _req_id(request)
169:     logger.error(f"HTTP {exc.status_code} for {request.method} {request.url.path} (request_id={request_id}): {message}")
170:     return JSONResponse(
171:         status_code=exc.status_code,
172:         headers={**_cors_headers(request), **(exc.headers or {})},
173:         content=_error_body(request, exc.status_code, message, detail=message, errors=errors),
174:     )
175: 
176: 
177: @app.exception_handler(RequestValidationError)
178: async def validation_exception_handler(request: Request, exc: RequestValidationError):
179:     errors = []
180:     for err in exc.errors():
181:         errors.append({
182:             "field": " -> ".join(str(loc) for loc in err.get("loc", [])),
183:             "message": err.get("msg", str(err)),
184:         })
185:     request_id = _req_id(request)
186:     logger.error(f"Validation error for {request.method} {request.url.path} (request_id={request_id}): {errors}")
187:     return JSONResponse(
188:         status_code=422,
189:         headers=_cors_headers(request),
190:         content=_error_body(
191:             request,
192:             422,
193:             "Validation error",
194:             detail=str(exc),
195:             errors=errors,
196:         ),
197:     )
198: 
199: 
200: @app.exception_handler(Exception)
201: async def unhandled_exception_handler(request: Request, exc: Exception):
202:     request_id = _req_id(request)
203:     logger.error(f"Unhandled exception (request_id={request_id}): {exc}")
204:     logger.exception("Unhandled exception traceback:")
205:     return JSONResponse(
206:         status_code=500,
207:         headers=_cors_headers(request),
208:         content=_error_body(
209:             request,
210:             500,
211:             "Internal server error",
212:             detail=str(exc) if settings.DEBUG else None,
213:         ),
214:     )
215: 
216: app.include_router(auth.router, prefix=settings.API_PREFIX_AUTH, tags=["Authentication"])
217: app.include_router(reports.router, prefix=settings.API_PREFIX_REPORTS, tags=["Reports"])
218: app.include_router(dashboard.router, prefix=settings.API_PREFIX_DASHBOARD, tags=["Dashboard"])
219: app.include_router(admin.router, prefix=settings.API_PREFIX_ADMIN, tags=["Admin"])
220: app.include_router(hazards.router, prefix=settings.API_PREFIX_HAZARDS, tags=["Hazards"])
221: app.include_router(can_cap.router, prefix=settings.API_PREFIX_CAN_CAP, tags=["CAN/CAP"])
222: 
223: app.include_router(auth.router, prefix=settings.API_PREFIX_AUTH_LEGACY, tags=["Authentication (Legacy)"], include_in_schema=False)
224: app.include_router(reports.router, prefix=settings.API_PREFIX_REPORTS_LEGACY, tags=["Reports (Legacy)"], include_in_schema=False)
225: app.include_router(dashboard.router, prefix=settings.API_PREFIX_DASHBOARD_LEGACY, tags=["Dashboard (Legacy)"], include_in_schema=False)
226: app.include_router(admin.router, prefix=settings.API_PREFIX_ADMIN_LEGACY, tags=["Admin (Legacy)"], include_in_schema=False)
227: app.include_router(hazards.router, prefix=settings.API_PREFIX_HAZARDS_LEGACY, tags=["Hazards (Legacy)"], include_in_schema=False)
228: app.include_router(can_cap.router, prefix=settings.API_PREFIX_CAN_CAP_LEGACY, tags=["CAN/CAP (Legacy)"], include_in_schema=False)
229: 
230: app.include_router(verification.router, prefix=settings.API_PREFIX_VERIFICATION, tags=["Verification & Closure"])
231: app.include_router(verification.router, prefix=settings.API_PREFIX_VERIFICATION_LEGACY, tags=["Verification & Closure (Legacy)"], include_in_schema=False)
232: 
233: app.include_router(reporting.router, prefix=settings.API_PREFIX_REPORTING, tags=["Reporting"])
234: app.include_router(reporting.router, prefix=settings.API_PREFIX_REPORTING_LEGACY, tags=["Reporting (Legacy)"], include_in_schema=False)
235: 
236: app.include_router(flight_diversions.router, prefix=settings.API_PREFIX_FLIGHT_DIVERSIONS, tags=["Flight Diversions"])
237: app.include_router(flight_diversions.router, prefix=settings.API_PREFIX_FLIGHT_DIVERSIONS_LEGACY, tags=["Flight Diversions (Legacy)"], include_in_schema=False)
238: 
239: app.include_router(state_risk.router, prefix=settings.API_PREFIX_STATE_RISK, tags=["State Risk Register"])
240: app.include_router(state_risk.router, prefix=settings.API_PREFIX_STATE_RISK_LEGACY, tags=["State Risk Register (Legacy)"], include_in_schema=False)
241: 
242: app.include_router(surveys.router, prefix=settings.API_PREFIX_SURVEYS, tags=["Surveys"])
243: app.include_router(surveys.router, prefix=settings.API_PREFIX_SURVEYS_LEGACY, tags=["Surveys (Legacy)"], include_in_schema=False)
244: 
245: app.include_router(tenants.router, prefix=settings.API_PREFIX_TENANTS, tags=["Tenants"])
246: app.include_router(tenants.router, prefix=settings.API_PREFIX_TENANTS_LEGACY, tags=["Tenants (Legacy)"], include_in_schema=False)
247: 
248: app.include_router(regulators.router, prefix=settings.API_PREFIX_REGULATORS, tags=["Regulators"])
249: 
250: app.include_router(contact.router, prefix=settings.API_PREFIX_CONTACT, tags=["Contact"])
251: 
252: app.include_router(feedback.router, prefix=settings.API_PREFIX_FEEDBACK, tags=["Feedback"])
253: app.include_router(copilot.router, prefix=settings.API_PREFIX_COPILOT, tags=["Copilot"])
254: 
255: app.include_router(metrics_router, prefix="", tags=["Metrics"])
256: 
257: @app.api_route("/", methods=["GET", "HEAD"])
258: async def root():
259:     return {
260:         "message": "AviaSAFE SMS API is running",
261:         "version": settings.API_VERSION,
262:         "status": "operational"
263:     }
264: 
265: @app.get("/health")
266: async def health_check():
267:     return {
268:         "status": "healthy",
269:         "firebase": "connected" if is_firebase_ready() else "unavailable",
270:         "service": "AviaSAFE SMS API",
271:         "version": settings.API_VERSION,
272:     }
273: 
274: @app.get("/live")
275: async def liveness_probe():
276:     return {"status": "alive"}
277: 
278: @app.get("/ready")
279: async def readiness_probe():
280:     fb = is_firebase_ready()
281:     return {
282:         "status": "ready" if fb else "not_ready",
283:         "firebase": "connected" if fb else "unavailable",
284:     }

(End of file - total 284 lines)
</content>
```

**Tool: grep**

**Input:**
```json
{
  "include": "*.py",
  "path": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\routes\\tenants.py",
  "pattern": "users|list_tenant_users|def |router\\."
}
```

**Output:**
```
Found 100 matches (more matches available)
C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\feedback.py:
  Line 34: def _envelope(data: Any) -> Dict[str, Any]:

  Line 42: @router.post("", status_code=status.HTTP_201_CREATED)

  Line 43: async def submit_feedback(


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\contact.py:
  Line 34: def _envelope(data: Any) -> Dict[str, Any]:

  Line 42: def _split_name(name: str):

  Line 52: def _send_to_sender(payload: Dict[str, Any]) -> Dict[str, Any]:

  Line 93: @router.post("", status_code=status.HTTP_200_OK)

  Line 94: async def submit_contact_form(message: ContactMessage):


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\dashboard.py:
  Line 25: def _envelope(data: Any) -> Dict[str, Any]:

  Line 33: def _empty_kpis():

  Line 42: def _empty_ai_kpis():

  Line 50: def _empty_org_kpis():

  Line 63: @router.get("/overview")

  Line 64: async def get_dashboard_overview(

  Line 87: def _safe_airline(method_name: str, svc: DashboardService, **kwargs):

  Line 96: @router.get("/recent")

  Line 97: async def get_recent_reports(

  Line 112: @router.get("/risk")

  Line 113: async def get_risk_distribution(

  Line 122: @router.get("/trends")

  Line 123: async def get_monthly_trends(

  Line 132: @router.get("/risk-trends")

  Line 133: async def get_ssp_risk_trends(

  Line 147: @router.get("/hazards")

  Line 148: async def get_hazard_frequency(

  Line 157: @router.get("/actions")

  Line 158: async def get_actions_summary(

  Line 167: @router.get("/master-register")

  Line 168: async def get_master_register(

  Line 193: @router.get("/airline/sms-maturity")

  Line 194: async def get_airline_sms_maturity(

  Line 228: @router.get("/caan/overview")

  Line 229: async def get_caan_overview(

  Line 238: @router.get("/caan/trends")

  Line 239: async def get_caan_trends(

  Line 248: @router.get("/caan/risk")

  Line 249: async def get_caan_risk(

  Line 258: @router.get("/caan/hazards")

  Line 259: async def get_caan_hazards(

  Line 268: @router.get("/caan/survey-maturity")

  Line 269: async def get_caan_survey_maturity(

  Line 278: @router.get("/caan/state")

  Line 279: async def get_caan_state(

  Line 289: @router.get("/caan/sms-maturity-assessment")

  Line 290: async def get_caan_sms_maturity_assessment(

  Line 305: @router.get("/caan/benchmark")

  Line 306: async def get_caan_benchmark(

  Line 320: @router.get("/admin/system")

  Line 321: async def get_admin_system(

  Line 329: @router.get("/admin/tenants")

  Line 330: async def get_admin_tenants(

  Line 338: @router.get("/admin/usage")

  Line 339: async def get_admin_usage(


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\flight_diversions.py:
  Line 31: def _auto_create_hazard_from_diversion(stored: dict, user: dict):

  Line 83: @router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)

  Line 84: async def create_diversion(

  Line 95: @router.get("/", response_model=List[dict])

  Line 96: async def list_diversions(

  Line 119: @router.get("/stats", response_model=DiversionStats)

  Line 120: async def get_diversion_stats(

  Line 128: @router.get("/{diversion_id}", response_model=dict)

  Line 129: async def get_diversion(

  Line 141: @router.patch("/{diversion_id}", response_model=dict)

  Line 142: async def update_diversion(

  Line 156: @router.delete("/{diversion_id}", status_code=status.HTTP_204_NO_CONTENT)

  Line 157: async def delete_diversion(

  Line 179: @router.post("/{diversion_id}/link-hazard", response_model=dict)

  Line 180: async def link_diversion_to_hazard(

  Line 195: @router.delete("/{diversion_id}/link-hazard", response_model=dict)

  Line 196: async def unlink_diversion_from_hazard(

  Line 210: def _to_diversion_response(data: dict) -> dict:


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\hazards.py:
  Line 27: @router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)

  Line 28: async def create_hazard(

  Line 59: @router.get("/", response_model=List[HazardListItem])

  Line 60: async def list_hazards(

  Line 96: @router.get("/stats", response_model=dict)

  Line 97: async def get_hazard_stats(

  Line 105: @router.get("/{hazard_id}", response_model=dict)

  Line 106: async def get_hazard(

  Line 118: @router.put("/{hazard_id}", response_model=dict)

  Line 119: async def update_hazard(

  Line 140: @router.patch("/{hazard_id}/status", response_model=dict)

  Line 141: async def update_hazard_status(

  Line 154: @router.patch("/{hazard_id}/assign", response_model=dict)

  Line 155: async def assign_hazard(

  Line 174: def _severity_inputs(data: dict) -> dict:

  Line 186: def _barrier_lists(barriers: Any) -> dict:

  Line 198: @router.post("/{hazard_id}/sram/calculate", response_model=dict)

  Line 199: async def calculate_sram(

  Line 232: @router.put("/{hazard_id}/sram/save", response_model=dict)

  Line 233: async def save_sram(

  Line 349: def _normalize_source(value):

  Line 355: def _normalize_taxonomy(value, occurrence_category=None):

  Line 378: def _normalize_priority(value):

  Line 384: def _to_hazard_response(data: dict) -> dict:

  Line 426: def _to_list_item(data: dict) -> dict:


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\can_cap.py:
  Line 19: @router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)

  Line 20: async def issue_can(

  Line 44: @router.get("/", response_model=List[CANListItem])

  Line 45: async def list_cans(


(Results truncated. Consider using a more specific path or pattern.)
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 17.3s)

_Thinking:_

The tenants.py grep returned a lot of noise. Let me directly read tenants.py to find the users endpoint. Also read test_auth.py to follow the mocking pattern, and the shell.js for nav wiring. Let me do these in parallel.

**Tool: read**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\routes\\tenants.py"
}
```

**Output:**
```
<path>C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\tenants.py</path>
<type>file</type>
<content>
1: # ============================================================================
2: # FILE: tenants.py
3: # PATH: backend/app/routes/tenants.py
4: # PURPOSE: Per-tenant configuration endpoints. Phase 1 exposes the survey rate
5: #          limit control (tenants/{tid}/config). Phase 3 extends the same PUT
6: #          contract with survey instructions and adds an auth-optional GET.
7: # ============================================================================
8: 
9: from datetime import datetime
10: from typing import Any, Dict, Optional
11: 
12: from fastapi import APIRouter, Depends, HTTPException, Request, status
13: from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
14: from pydantic import BaseModel, Field
15: from loguru import logger
16: 
17: from app.core.config import settings
18: from app.firebase import get_db
19: from app.middleware.auth import get_current_user
20: from app.services.audit_service import log_audit, request_context
21: from app.services.tenant_service import (
22:     SURVEY_RATE_LIMIT_OPTIONS,
23:     save_tenant_config,
24: )
25: from app.services.users import list_tenant_users
26: 
27: router = APIRouter()
28: 
29: optional_bearer = HTTPBearer(auto_error=False)
30: 
31: 
32: async def get_optional_user(
33:     credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer),
34: ) -> Optional[Dict[str, Any]]:
35:     """Return the authenticated user when a Bearer token is supplied.
36: 
37:     Public pages (e.g. the survey) must be able to read tenant config without
38:     a login. A supplied but invalid token is still rejected with 401.
39:     """
40:     if credentials is None:
41:         return None
42:     return await get_current_user(credentials)
43: 
44: SURVEY_MANAGER_ROLES = ("AIRLINE_ADMIN", "safety")
45: 
46: 
47: def _envelope(data: Any) -> Dict[str, Any]:
48:     return {
49:         "status": "success",
50:         "timestamp": datetime.now(),
51:         "data": data,
52:     }
53: 
54: 
55: class TenantConfigUpdate(BaseModel):
56:     survey_rate_limit: Optional[int] = Field(None, description="Max daily survey submissions for this tenant")
57:     survey_instructions: Optional[str] = Field(None, description="Optional instructions shown at the top of the survey")
58:     survey_open_date: Optional[str] = Field(None, description="Survey start date (ISO string / YYYY-MM-DD)")
59:     survey_close_date: Optional[str] = Field(None, description="Survey expiry date (ISO string / YYYY-MM-DD)")
60:     is_survey_active: Optional[bool] = Field(None, description="Manual override to open/close the tenant survey")
61: 
62: 
63: def _require_tenant_admin(user: Dict[str, Any], tenant_id: str) -> None:
64:     """Only the Safety Manager (AIRLINE_ADMIN / safety) of the target tenant
65:     may update its config. SUPER_ADMIN / CAAN_SMD cannot edit tenant settings."""
66:     if user.get("role") not in SURVEY_MANAGER_ROLES:
67:         raise HTTPException(
68:             status_code=status.HTTP_403_FORBIDDEN,
69:             detail="Only the Safety Manager of this tenant can update its config",
70:         )
71:     if user.get("tenant_id") != tenant_id:
72:         raise HTTPException(
73:             status_code=status.HTTP_403_FORBIDDEN,
74:             detail="tenantId does not match the authenticated user's tenant",
75:         )
76: 
77: 
78: def _require_tenant_viewer(user: Dict[str, Any], tenant_id: str) -> None:
79:     """Phase 2: AIRLINE_ADMIN of the tenant or SUPER_ADMIN may list users."""
80:     if user.get("role") == "SUPER_ADMIN":
81:         return
82:     if user.get("role") != "AIRLINE_ADMIN":
83:         raise HTTPException(
84:             status_code=status.HTTP_403_FORBIDDEN,
85:             detail="Only the AIRLINE_ADMIN of this tenant or SUPER_ADMIN can view users",
86:         )
87:     if user.get("tenant_id") != tenant_id:
88:         raise HTTPException(
89:             status_code=status.HTTP_403_FORBIDDEN,
90:             detail="tenantId does not match the authenticated user's tenant",
91:         )
92: 
93: 
94: @router.get("/{tenant_id}/config", status_code=status.HTTP_200_OK)
95: async def get_tenant_config(
96:     tenant_id: str,
97:     request: Request,
98:     user: Optional[Dict[str, Any]] = Depends(get_optional_user),
99: ):
100:     """Read per-tenant configuration (survey rate limit, survey instructions).
101: 
102:     Authentication is optional: the public survey page calls this to render the
103:     airline's instructions at the top of the survey. Returns 404 for unknown
104:     tenants. The config map is returned as stored (missing fields omitted).
105:     """
106:     tenant_id = tenant_id.strip()
107:     db = get_db()
108:     tenant_ref = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tenant_id)
109:     try:
110:         tenant_snap = tenant_ref.get()
111:     except Exception as e:
112:         logger.warning(f"Tenant config lookup failed for {tenant_id}: {e}")
113:         raise HTTPException(status_code=500, detail="Tenant storage unavailable")
114:     if not tenant_snap.exists:
115:         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown tenant: {tenant_id}")
116: 
117:     tenant_data = tenant_snap.to_dict() or {}
118:     config = tenant_data.get("config") or {}
119:     survey_config = dict(tenant_data.get("surveyConfig") or {})
120:     # Fall back to the canonical config map so dates/active set via PUT are
121:     # exposed to the public survey page even before the camelCase mirror exists.
122:     if "survey_open_date" in config and "openDate" not in survey_config:
123:         survey_config["openDate"] = config["survey_open_date"]
124:     if "survey_close_date" in config and "closeDate" not in survey_config:
125:         survey_config["closeDate"] = config["survey_close_date"]
126:     if "is_survey_active" in config and "isActive" not in survey_config:
127:         survey_config["isActive"] = config["is_survey_active"]
128:     for camel, snake in (
129:         ("openDate", "open_date"),
130:         ("closeDate", "close_date"),
131:         ("isActive", "is_active"),
132:     ):
133:         if camel in survey_config and snake not in survey_config:
134:             survey_config[snake] = survey_config[camel]
135:     return _envelope({
136:         "tenant_id": tenant_id,
137:         "name": tenant_data.get("name"),
138:         "config": config,
139:         "surveyConfig": survey_config,
140:     })
141: 
142: 
143: @router.get("/{tenant_id}/users", status_code=status.HTTP_200_OK)
144: async def list_users(
145:     tenant_id: str,
146:     user: Dict[str, Any] = Depends(get_current_user),
147: ):
148:     """List the authorized users for a tenant (view-only).
149: 
150:     AIRLINE_ADMIN of the target tenant or SUPER_ADMIN. Returns uid, email, role,
151:     createdAt and lastLogin (when available) from the mirrored users collection.
152:     """
153:     tenant_id = tenant_id.strip()
154:     _require_tenant_viewer(user, tenant_id)
155:     try:
156:         users = list_tenant_users(tenant_id)
157:     except Exception as e:
158:         logger.warning(f"Failed to list users for tenant {tenant_id}: {e}")
159:         raise HTTPException(status_code=500, detail="Failed to list tenant users")
160:     return _envelope({"tenant_id": tenant_id, "users": users})
161: 
162: 
163: @router.put("/{tenant_id}/config", status_code=status.HTTP_200_OK)
164: async def update_tenant_config(
165:     tenant_id: str,
166:     config: TenantConfigUpdate,
167:     request: Request,
168:     user: Dict[str, Any] = Depends(get_current_user),
169: ):
170:     """Update per-tenant survey management configuration.
171: 
172:     Accepts the survey activation dates, the manual open/close override, the
173:     daily respondent rate limit and the survey instructions. Only the Safety
174:     Manager (AIRLINE_ADMIN / safety role) of the target tenant may edit it.
175:     """
176:     tenant_id = tenant_id.strip()
177:     _require_tenant_admin(user, tenant_id)
178:     if config.survey_rate_limit is not None and config.survey_rate_limit not in SURVEY_RATE_LIMIT_OPTIONS:
179:         raise HTTPException(
180:             status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
181:             detail=f"survey_rate_limit must be one of {', '.join(str(o) for o in SURVEY_RATE_LIMIT_OPTIONS)}",
182:         )
183: 
184:     db = get_db()
185:     tenant_ref = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tenant_id)
186:     try:
187:         tenant_snap = tenant_ref.get()
188:     except Exception as e:
189:         logger.warning(f"Tenant config lookup failed for {tenant_id}: {e}")
190:         raise HTTPException(status_code=500, detail="Tenant storage unavailable")
191:     if not tenant_snap.exists:
192:         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown tenant: {tenant_id}")
193: 
194:     tenant_data = tenant_snap.to_dict() or {}
195:     existing_config = tenant_data.get("config") or {}
196:     existing_survey_config = tenant_data.get("surveyConfig") or {}
197: 
198:     fields = config.model_dump()
199:     try:
200:         updated, survey_config = save_tenant_config(
201:             tenant_id,
202:             fields,
203:             existing_config,
204:             existing_survey_config,
205:         )
206:     except ValueError as e:
207:         raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
208:     except RuntimeError as e:
209:         raise HTTPException(status_code=500, detail=str(e))
210: 
211:     ip, request_id = request_context(request)
212:     log_audit(
213:         action="TENANT_CONFIG_UPDATED",
214:         user=user.get("email") or user.get("uid"),
215:         tenant_id=tenant_id,
216:         target_type="tenant",
217:         target_id=tenant_id,
218:         ip=ip,
219:         request_id=request_id,
220:         metadata={
221:             "survey_rate_limit": updated.get("survey_rate_limit"),
222:             "survey_open_date": updated.get("survey_open_date"),
223:             "survey_close_date": updated.get("survey_close_date"),
224:             "is_survey_active": updated.get("is_survey_active"),
225:         },
226:     )
227: 
228:     return _envelope({
229:         "tenant_id": tenant_id,
230:         "config": updated,
231:         "surveyConfig": survey_config,
232:     })

(End of file - total 232 lines)
</content>
```

**Tool: read**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\tests\\test_auth.py",
  "limit": 200
}
```

**Output:**
```
<path>C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\tests\test_auth.py</path>
<type>file</type>
<content>
1: """Self-service onboarding safeguards: real-time invite verification and
2: duplicate-account protection (2026-08).
3: 
4: Covers:
5:   * GET  /api/v1/auth/verify-invite  (valid / invalid / inactive / blank code,
6:     case-insensitive resolution, public payload shape)
7:   * POST /api/v1/auth/join-team      (duplicate email -> 409, least-privilege
8:     USER claims, operational_role capture, strong-password rules)
9: 
10: Invite verification deliberately reveals nothing when a code is unknown or
11: inactive: it returns {valid: false, error} with 404 / 400.
12: """
13: 
14: from fastapi.testclient import TestClient
15: 
16: from app.main import app
17: from app.core.config import settings
18: 
19: 
20: # ============================================================================
21: # Fake Firebase storage + auth for the endpoint tests
22: # ============================================================================
23: 
24: class _Doc:
25:     def __init__(self, data, exists=True, id=None):
26:         self._data = data or {}
27:         self.exists = exists
28:         self.id = id
29: 
30:     def get(self, field, default=None):
31:         if field is None:
32:             return self._data
33:         return self._data.get(field, default)
34: 
35:     def to_dict(self):
36:         return self._data
37: 
38: 
39: class _TenantQuery:
40:     def __init__(self, db):
41:         self._db = db
42:         self._filters = []
43: 
44:     def where(self, field, op, value):
45:         self._filters.append((field, op, value))
46:         return self
47: 
48:     def limit(self, n):
49:         return self
50: 
51:     def get(self):
52:         rows = []
53:         for tid, data in self._db.tenants.items():
54:             doc = dict(data or {})
55:             doc.setdefault("tenant_id", tid)
56:             ok = True
57:             for field, op, value in self._filters:
58:                 if op == "==" and doc.get(field) != value:
59:                     ok = False
60:             if ok:
61:                 rows.append(_Doc(doc, exists=True, id=tid))
62:         return rows
63: 
64: 
65: class _TenantRef:
66:     def __init__(self, db, tid):
67:         self._db = db
68:         self._tid = tid
69: 
70:     def get(self):
71:         if self._tid not in self._db.tenants:
72:             return _Doc(None, exists=False, id=self._tid)
73:         return _Doc(dict(self._db.tenants[self._tid]), exists=True, id=self._tid)
74: 
75: 
76: class _TenantsColl:
77:     def __init__(self, db):
78:         self._db = db
79: 
80:     def document(self, tid):
81:         return _TenantRef(self._db, tid)
82: 
83:     def where(self, field, op, value):
84:         return _TenantQuery(self._db).where(field, op, value)
85: 
86: 
87: class _UserRef:
88:     def __init__(self, db, uid):
89:         self._db = db
90:         self._uid = uid
91: 
92:     def set(self, data, merge=False):
93:         if merge and self._uid in self._db.users:
94:             merged = dict(self._db.users[self._uid])
95:             merged.update(dict(data))
96:             data = merged
97:         self._db.users[self._uid] = dict(data)
98: 
99:     def get(self):
100:         if self._uid not in self._db.users:
101:             return _Doc(None, exists=False)
102:         return _Doc(dict(self._db.users[self._uid]), exists=True)
103: 
104: 
105: class _UsersColl:
106:     def __init__(self, db):
107:         self._db = db
108: 
109:     def document(self, uid):
110:         return _UserRef(self._db, uid)
111: 
112: 
113: class _AuditColl:
114:     def __init__(self, db):
115:         self._db = db
116: 
117:     def add(self, entry):
118:         self._db.audit.append(dict(entry))
119:         return type("Ref", (), {"id": f"audit-{len(self._db.audit)}"})()
120: 
121: 
122: class _FakeDB:
123:     def __init__(self):
124:         self.tenants = {}
125:         self.users = {}
126:         self.audit = []
127: 
128:     def collection(self, name):
129:         if name == "tenants":
130:             return _TenantsColl(self)
131:         if name == "users":
132:             return _UsersColl(self)
133:         if name == "audit_logs":
134:             return _AuditColl(self)
135:         raise AssertionError(f"unexpected collection {name}")
136: 
137: 
138: class _FakeAuth:
139:     def __init__(self):
140:         self.records = {}
141:         self.claims = {}
142: 
143:     def create_user(self, **kw):
144:         uid = f"uid-{len(self.records) + 1}"
145:         self.records[uid] = dict(kw)
146:         return type("U", (), {"uid": uid, "email": kw.get("email")})()
147: 
148:     def set_custom_user_claims(self, uid, claims):
149:         self.claims[uid] = dict(claims)
150: 
151: 
152: def _patch(monkeypatch, db, auth=None):
153:     monkeypatch.setattr("app.firebase.get_db", lambda: db)
154:     monkeypatch.setattr("app.routes.auth.get_db", lambda: db)
155:     monkeypatch.setattr("app.services.tenant_registration.get_db", lambda: db)
156:     monkeypatch.setattr("app.services.users.get_db", lambda: db)
157:     monkeypatch.setattr("app.services.audit_service.get_db", lambda: db)
158:     if auth is not None:
159:         monkeypatch.setattr("app.firebase.get_auth", lambda: auth)
160:         monkeypatch.setattr("app.services.tenant_registration.get_auth", lambda: auth)
161: 
162: 
163: def _seed_tenant(db, tid="yeti-airlines", name="Yeti Airlines",
164:                  classification="AIRLINE_FIXED_WING",
165:                  departments=None, invite_code="ABC123", active=True, status=None):
166:     db.tenants[tid] = {
167:         "tenant_id": tid,
168:         "name": name,
169:         "tenant_type": classification,
170:         "classification": classification,
171:         "applicable_departments": departments or ["safety", "flight_ops", "camo", "qa"],
172:         "team_invite_code": invite_code,
173:         "active": active,
174:     }
175:     if status is not None:
176:         db.tenants[tid]["status"] = status
177:     return db.tenants[tid]
178: 
179: 
180: def _join_body(tid="yeti-airlines", department="flight_ops", invite_code="ABC123",
181:                operational_role="safety_officer", **overrides):
182:     body = {
183:         "invite_code": invite_code,
184:         "full_name": "Rajesh Thapa",
185:         "email": "ops@yetiairlines.com",
186:         "password": "Ops-2026-Password",
187:         "confirm_password": "Ops-2026-Password",
188:         "department": department,
189:         "operational_role": operational_role,
190:     }
191:     body.update(overrides)
192:     if tid:
193:         body["tenant_id"] = tid
194:     return body
195: 
196: 
197: # ============================================================================
198: # GET /api/v1/auth/verify-invite
199: # ============================================================================
200: 

(Showing lines 1-200 of 351. Use offset=201 to continue.)
</content>
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 25.2s)

_Thinking:_

Now let me read the rest of test_auth.py to see the join tests pattern, plus the shell.js for nav, and firebase.js role handling. Let me read these in parallel.

**Tool: read**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\tests\\test_auth.py",
  "offset": 200
}
```

**Output:**
```
<path>C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\tests\test_auth.py</path>
<type>file</type>
<content>
200: 
201: def test_verify_invite_valid_code(monkeypatch):
202:     db = _FakeDB()
203:     _patch(monkeypatch, db, _FakeAuth())
204:     _seed_tenant(db, invite_code="ABC123")
205: 
206:     resp = TestClient(app).get("/api/v1/auth/verify-invite?code=ABC123")
207:     assert resp.status_code == 200
208:     body = resp.json()
209:     assert body["valid"] is True
210:     assert body["organization_name"] == "Yeti Airlines"
211:     assert body["tenant_id"] == "yeti-airlines"
212:     assert body["category"] == "AIRLINE_FIXED_WING"
213: 
214: 
215: def test_verify_invite_is_case_insensitive(monkeypatch):
216:     db = _FakeDB()
217:     _patch(monkeypatch, db, _FakeAuth())
218:     _seed_tenant(db, invite_code="ABC123")
219: 
220:     resp = TestClient(app).get("/api/v1/auth/verify-invite?code=abc123")
221:     assert resp.status_code == 200
222:     assert resp.json()["valid"] is True
223: 
224: 
225: def test_verify_invite_invalid_code(monkeypatch):
226:     _patch(monkeypatch, _FakeDB(), _FakeAuth())
227:     resp = TestClient(app).get("/api/v1/auth/verify-invite?code=ZZZZZZ")
228:     assert resp.status_code == 404
229:     body = resp.json()
230:     assert body["valid"] is False
231:     assert body["error"] == "Invalid or expired invite code"
232: 
233: 
234: def test_verify_invite_blank_code(monkeypatch):
235:     _patch(monkeypatch, _FakeDB(), _FakeAuth())
236:     resp = TestClient(app).get("/api/v1/auth/verify-invite")
237:     assert resp.status_code == 400
238:     assert resp.json()["valid"] is False
239: 
240: 
241: def test_verify_invite_inactive_tenant_rejected(monkeypatch):
242:     db = _FakeDB()
243:     _patch(monkeypatch, db, _FakeAuth())
244:     _seed_tenant(db, invite_code="OFF000", active=False)
245: 
246:     resp = TestClient(app).get("/api/v1/auth/verify-invite?code=OFF000")
247:     assert resp.status_code == 404
248:     body = resp.json()
249:     assert body["valid"] is False
250:     assert body["error"] == "Invalid or expired invite code"
251: 
252: 
253: def test_verify_invite_suspended_status_rejected(monkeypatch):
254:     db = _FakeDB()
255:     _patch(monkeypatch, db, _FakeAuth())
256:     _seed_tenant(db, invite_code="SUS000", status="inactive")
257: 
258:     resp = TestClient(app).get("/api/v1/auth/verify-invite?code=SUS000")
259:     assert resp.status_code == 404
260:     assert resp.json()["valid"] is False
261: 
262: 
263: # ============================================================================
264: # POST /api/v1/auth/join-team — duplicate accounts & least privilege
265: # ============================================================================
266: 
267: def test_join_team_duplicate_email_returns_409(monkeypatch):
268:     db = _FakeDB()
269:     auth = _FakeAuth()
270:     _patch(monkeypatch, db, auth)
271:     _seed_tenant(db)
272: 
273:     def _fail_duplicate(**kw):
274:         if kw.get("email") == "ops@yetiairlines.com":
275:             raise ValueError("The email address is already in use by another account.")
276:         return type("U", (), {"uid": "u-x", "email": kw.get("email")})()
277: 
278:     monkeypatch.setattr(auth, "create_user", _fail_duplicate)
279: 
280:     resp = TestClient(app).post("/api/v1/auth/join-team", json=_join_body())
281:     assert resp.status_code == 409
282:     assert "already exists" in resp.json()["detail"]
283:     assert not auth.claims
284: 
285: 
286: def test_join_team_duplicate_email_never_creates_user_doc(monkeypatch):
287:     db = _FakeDB()
288:     auth = _FakeAuth()
289:     _patch(monkeypatch, db, auth)
290:     _seed_tenant(db)
291: 
292:     def _fail_duplicate(**kw):
293:         raise ValueError("Email already in use")
294: 
295:     monkeypatch.setattr(auth, "create_user", _fail_duplicate)
296: 
297:     resp = TestClient(app).post("/api/v1/auth/join-team", json=_join_body())
298:     assert resp.status_code == 409
299:     assert not db.users
300: 
301: 
302: def test_join_team_stores_operational_role(monkeypatch):
303:     db = _FakeDB()
304:     auth = _FakeAuth()
305:     _patch(monkeypatch, db, auth)
306:     _seed_tenant(db)
307: 
308:     resp = TestClient(app).post(
309:         "/api/v1/auth/join-team",
310:         json=_join_body(operational_role="Licensed Aircraft Engineer (AME)", email="145@yetiairlines.com"),
311:     )
312:     assert resp.status_code == 200, resp.text
313:     uid = list(auth.claims)[0]
314:     assert auth.claims[uid] == {
315:         "role": "USER",
316:         "tenant_id": "yeti-airlines",
317:         "department": "Flight Operations",
318:     }
319:     user_doc = list(db.users.values())[0]
320:     assert user_doc["operational_role"] == "Licensed Aircraft Engineer (AME)"
321:     assert user_doc["role"] == "USER"
322: 
323: 
324: def test_join_team_weak_password_rejected(monkeypatch):
325:     db = _FakeDB()
326:     auth = _FakeAuth()
327:     _patch(monkeypatch, db, auth)
328:     _seed_tenant(db)
329: 
330:     for weak in ("alllowercase123", "NOUPPERCASE", "Short1x"):
331:         resp = TestClient(app).post(
332:             "/api/v1/auth/join-team",
333:             json=_join_body(password=weak, confirm_password=weak, email=f"{weak}@yetiairlines.com"),
334:         )
335:         assert resp.status_code == 422, weak
336:         detail = resp.json()["detail"]
337:         assert "uppercase" in detail or "digit" in detail or "at least" in detail, weak
338:     assert not auth.claims
339: 
340: 
341: def test_join_team_password_with_uppercase_and_digit_accepted(monkeypatch):
342:     db = _FakeDB()
343:     auth = _FakeAuth()
344:     _patch(monkeypatch, db, auth)
345:     _seed_tenant(db)
346: 
347:     resp = TestClient(app).post(
348:         "/api/v1/auth/join-team",
349:         json=_join_body(password="SafeOps2026x", confirm_password="SafeOps2026x"),
350:     )
351:     assert resp.status_code == 200, resp.text

(End of file - total 351 lines)
</content>
```

**Tool: read**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\js\\shell.js"
}
```

**Output:**
```
<path>C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\js\shell.js</path>
<type>file</type>
<content>
1: /* ============================================================================
2:    FILE: shell.js
3:    PATH: public/js/shell.js
4:    VERSION: 1.0.0
5:    PURPOSE: Shared dashboard shell. Renders the fixed left sidebar navigation,
6:             the top header (brand + tenant info + user + logout), a hero showing
7:             the tenant title + department subtitle, a clean single-line footer,
8:             and scroll-spy active states. Used by all tenant dashboards and the
9:             CAAN dashboard.
10:    AUTHOR: AviaSAFE Systems
11:    ============================================================================ */
12: 
13: (function (global) {
14:     'use strict';
15: 
16:     // Shell configuration is supplied by each page BEFORE this script loads:
17:     //   window.SHELL_CONFIG = {
18:     //     brand: 'AviaSAFE',
19:     //     roleLabel: 'Airline Safety Manager',     // shown under brand in sidebar
20:     //     tenantTitle: 'SITA AIR',                 // optional (tenant scope)
21:     //     tenantMeta: 'ICAO: STA · Nepal',         // optional additional info
22:     //     heroSubtitle: 'Corporate Safety Dept',   // optional hero subtitle override
23:     //                                                (defaults to department label)
24:     //     nav: [ { id: 'overview', label: 'Overview', icon: 'fa-gauge-high' }, ... ],
25:     //     links: [ { href, label }, ... ]          // optional footer links
26:     //   }
27:     //
28:     // Pages may set SHELL_CONFIG either before or after this script runs (in a
29:     // script that executes before DOMContentLoaded). We re-read it at init time
30:     // so the sidebar/header always reflect the latest config.
31:     let cfg = global.SHELL_CONFIG || { nav: [] };
32: 
33:     function refreshCfg() {
34:         if (global.SHELL_CONFIG) cfg = global.SHELL_CONFIG;
35:         return cfg;
36:     }
37: 
38:     // Hide/show sidebar items that declare a restricted set of roles.
39:     // A nav item may specify `roles: ['AIRLINE_ADMIN', ...]` to be shown
40:     // only to users whose role is in that list.
41:     function applyNavVisibility(role) {
42:         document.querySelectorAll('.sidebar-nav li[data-roles]').forEach(function (li) {
43:             const allowed = (li.dataset.roles || '').split(',').filter(function (r) { return r; });
44:             li.style.display = allowed.indexOf(role) !== -1 ? '' : 'none';
45:         });
46:     }
47: 
48:     function buildSidebar() {
49:         const aside = document.createElement('aside');
50:         aside.className = 'shell-sidebar';
51:         aside.id = 'shellSidebar';
52: 
53:         const brand = document.createElement('div');
54:         brand.className = 'sidebar-brand';
55:         brand.innerHTML = '<i class="fas fa-shield-alt"></i><span>' +
56:             (cfg.brand || 'AviaSAFE') + '</span>';
57:         aside.appendChild(brand);
58: 
59:         if (cfg.roleLabel) {
60:             const role = document.createElement('div');
61:             role.className = 'sidebar-role';
62:             role.textContent = cfg.roleLabel;
63:             aside.appendChild(role);
64:         }
65: 
66:         const navWrap = document.createElement('nav');
67:         navWrap.className = 'sidebar-nav';
68:         const ul = document.createElement('ul');
69:         (cfg.nav || []).forEach(function (item) {
70:             const li = document.createElement('li');
71:             if (Array.isArray(item.roles) && item.roles.length) {
72:                 li.dataset.roles = item.roles.join(',');
73:             }
74:             const a = document.createElement('a');
75:             if (item.href) {
76:                 a.href = item.href;
77:             } else {
78:                 a.href = '#' + item.id;
79:                 a.dataset.target = item.id;
80:             }
81:             a.innerHTML = '<i class="fas ' + (item.icon || 'fa-circle') + '"></i>' +
82:                 '<span>' + item.label + '</span>';
83:             li.appendChild(a);
84:             ul.appendChild(li);
85:         });
86:         navWrap.appendChild(ul);
87:         aside.appendChild(navWrap);
88: 
89:         const foot = document.createElement('div');
90:         foot.className = 'sidebar-footer';
91:         foot.textContent = 'ICAO Annex 19 · Doc 9859 · Doc 10159';
92:         aside.appendChild(foot);
93: 
94:         return aside;
95:     }
96: 
97:     function buildHeader() {
98:         const header = document.createElement('header');
99:         header.className = 'shell-header';
100:         header.id = 'shellHeader';
101: 
102:         const brand = document.createElement('div');
103:         brand.className = 'shell-brand';
104:         brand.innerHTML = '<i class="fas fa-shield-alt"></i><span>Avia' +
105:             '<span style="color:#34a853;">SAFE</span>system</span>';
106:         header.appendChild(brand);
107: 
108:         if (cfg.tenantTitle) {
109:             const tenant = document.createElement('div');
110:             tenant.className = 'shell-tenant';
111:             tenant.innerHTML = '<div class="tenant-name">' + cfg.tenantTitle + '</div>' +
112:                 (cfg.tenantMeta ? '<div class="tenant-meta">' + cfg.tenantMeta + '</div>' : '');
113:             header.appendChild(tenant);
114:         }
115: 
116:         const actions = document.createElement('div');
117:         actions.className = 'shell-actions';
118:         const user = document.createElement('span');
119:         user.className = 'shell-user';
120:         user.id = 'shellUser';
121:         user.textContent = '—';
122:         actions.appendChild(user);
123:         const logout = document.createElement('button');
124:         logout.className = 'btn-logout';
125:         logout.id = 'shellLogoutBtn';
126:         logout.innerHTML = '<i class="fas fa-sign-out-alt"></i> Logout';
127:         logout.addEventListener('click', function () {
128:             if (typeof firebase !== 'undefined' && firebase.auth) {
129:                 firebase.auth().signOut().then(function () {
130:                     window.location.href = '/login.html';
131:                 });
132:             } else {
133:                 window.location.href = '/login.html';
134:             }
135:         });
136:         actions.appendChild(logout);
137:         header.appendChild(actions);
138: 
139:         return header;
140:     }
141: 
142:     // Uniform top section: centered tenant name (title) + department label
143:     // (mapped from the signed-in user's role / custom claims).
144:     function buildHero() {
145:         const hero = document.createElement('section');
146:         hero.className = 'shell-hero';
147:         hero.id = 'shellHero';
148:         const title = document.createElement('h1');
149:         title.className = 'shell-hero-title';
150:         title.id = 'shellHeroTitle';
151:         title.textContent = cfg.tenantTitle || cfg.roleLabel || (cfg.brand || 'AviaSAFE');
152:         const user = document.createElement('div');
153:         user.className = 'shell-hero-user';
154:         user.id = 'shellHeroUser';
155:         user.textContent = cfg.heroSubtitle || '—';
156:         hero.appendChild(title);
157:         hero.appendChild(user);
158:         return hero;
159:     }
160: 
161:     // Clean single-line footer. The user's email and department live in the
162:     // header; the floating "Send Feedback" widget is injected separately by
163:     // feedback.js and stays untouched.
164:     function buildFooter() {
165:         const footer = document.createElement('footer');
166:         footer.className = 'dashboard-footer text-center';
167:         footer.id = 'shellFooter';
168: 
169:         const links = document.createElement('div');
170:         links.style.fontSize = '0.875rem';
171:         links.style.marginBottom = '0.25rem';
172:         links.innerHTML =
173:             '<a href="/privacy.html" style="color: var(--color-text-muted); text-decoration: none;">Privacy Policy</a>' +
174:             '<span style="margin: 0 0.5rem; color: var(--color-gray-400);">|</span>' +
175:             '<a href="/terms.html" style="color: var(--color-text-muted); text-decoration: none;">Terms of Service</a>';
176:         footer.appendChild(links);
177: 
178:         const p = document.createElement('p');
179:         p.className = 'mb-0 text-muted';
180:         p.style.fontSize = '0.875rem';
181:         p.style.fontWeight = '500';
182:         p.style.marginTop = '0.25rem';
183:         p.innerHTML = 'A Project by <strong>Ghanshyam Acharya</strong>';
184:         footer.appendChild(p);
185: 
186:         const cr = document.createElement('p');
187:         cr.className = 'mb-0 text-muted';
188:         cr.style.fontSize = '0.75rem';
189:         cr.style.opacity = '0.7';
190:         cr.style.marginTop = '0.25rem';
191:         cr.textContent = '\u00A9 2026 AviaSAFE Systems. Engineered for ICAO Annex 19 (3rd Ed.), Doc 9859 & Doc 10159 Compliance.';
192:         footer.appendChild(cr);
193:         return footer;
194:     }
195: 
196:     function applyTenantToSurveyLinks(tenantId) {
197:         if (!tenantId) return;
198:         document.querySelectorAll('a[href*="/survey"]').forEach(function (a) {
199:             const href = a.getAttribute('href') || '';
200:             if (href.indexOf('/survey') === -1) return;
201:             if (href.indexOf('tenant=') !== -1) return;
202:             const sep = href.indexOf('?') === -1 ? '?' : '&';
203:             a.setAttribute('href', href + sep + 'tenant=' + encodeURIComponent(tenantId));
204:         });
205:     }
206: 
207:     function attachScrollSpy() {
208:         const links = document.querySelectorAll('.sidebar-nav li a');
209:         const navWrap = document.querySelector('.sidebar-nav');
210:         const targets = (cfg.nav || [])
211:             .map(function (n) { return document.getElementById(n.id); })
212:             .filter(Boolean);
213: 
214:         function onScroll() {
215:             const pos = window.scrollY + 120;
216:             let current = null;
217:             targets.forEach(function (el) {
218:                 if (el.offsetParent === null) return;
219:                 if (el.offsetTop <= pos) current = el.id;
220:             });
221:             if (!current && targets.length) current = targets[0].id;
222:             if (navWrap) {
223:                 // Dim every section except the one currently in view.
224:                 if (current) navWrap.classList.add('has-active');
225:                 else navWrap.classList.remove('has-active');
226:             }
227:             links.forEach(function (a) {
228:                 if (a.dataset.target === current) a.classList.add('active');
229:                 else a.classList.remove('active');
230:             });
231:         }
232: 
233:         links.forEach(function (a) {
234:             a.addEventListener('click', function (e) {
235:                 const el = document.getElementById(a.dataset.target);
236:                 if (el) {
237:                     e.preventDefault();
238:                     el.scrollIntoView({ behavior: 'smooth', block: 'start' });
239:                 }
240:             });
241:         });
242: 
243:         window.addEventListener('scroll', onScroll, { passive: true });
244:         onScroll();
245:     }
246: 
247:     function loadInterFont() {
248:         if (document.querySelector('link[href*="Inter"]')) return;
249:         const link = document.createElement('link');
250:         link.href = 'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap';
251:         link.rel = 'stylesheet';
252:         document.head.appendChild(link);
253:     }
254: 
255:     function initShell() {
256:         if (document.getElementById('shellSidebar')) return;
257:         loadInterFont();
258:         const shell = document.querySelector('.app-shell');
259:         if (!shell) return;
260: 
261:         // Re-read SHELL_CONFIG in case it was assigned after this script loaded.
262:         refreshCfg();
263: 
264:         const sidebar = buildSidebar();
265:         const main = document.createElement('div');
266:         main.className = 'shell-main';
267: 
268:         // Wrap existing children into .shell-content
269:         const content = document.createElement('div');
270:         content.className = 'shell-content';
271:         while (shell.firstChild) content.appendChild(shell.firstChild);
272:         main.appendChild(buildHeader());
273:         main.appendChild(buildHero());
274:         main.appendChild(content);
275:         main.appendChild(buildFooter());
276:         shell.appendChild(sidebar);
277:         shell.appendChild(main);
278: 
279:         attachScrollSpy();
280: 
281:         // Populate user email (top-right header) + department (hero subtitle)
282:         // once auth is ready.
283:         if (typeof firebase !== 'undefined' && firebase.auth) {
284:             firebase.auth().onAuthStateChanged(function (user) {
285:                 const el = document.getElementById('shellUser');
286:                 if (el) el.textContent = user ? user.email : '—';
287:                 const heroUser = document.getElementById('shellHeroUser');
288:                 if (heroUser) heroUser.textContent = '—';
289:                 if (user && user.getIdTokenResult) {
290:                     user.getIdTokenResult(true).then(function (tokenResult) {
291:                         const claims = (tokenResult && tokenResult.claims) || {};
292:                         applyNavVisibility(claims.role || 'USER');
293:                         if (claims.tenant_id) applyTenantToSurveyLinks(claims.tenant_id);
294:                         if (heroUser && typeof getDepartmentLabel === 'function') {
295:                             heroUser.textContent = cfg.heroSubtitle || getDepartmentLabel(claims) || '—';
296:                         }
297:                     }).catch(function () {
298:                         if (heroUser) heroUser.textContent = '—';
299:                     });
300:                 } else {
301:                     applyNavVisibility('USER');
302:                 }
303:             });
304:         }
305:     }
306: 
307:     // Allow pages to update the header tenant info after auth resolves.
308:     global.updateShellTenant = function (title, meta) {
309:         cfg.tenantTitle = title || cfg.tenantTitle;
310:         cfg.tenantMeta = meta || cfg.tenantMeta;
311:         const tenantEl = document.querySelector('.shell-tenant');
312:         if (tenantEl) {
313:             const nameEl = tenantEl.querySelector('.tenant-name');
314:             const metaEl = tenantEl.querySelector('.tenant-meta');
315:             if (nameEl) nameEl.textContent = title || '';
316:             if (metaEl) metaEl.textContent = meta || '';
317:         }
318:         const heroTitle = document.getElementById('shellHeroTitle');
319:         if (heroTitle) heroTitle.textContent = cfg.tenantTitle || cfg.roleLabel || '';
320:     };
321: 
322:     if (document.readyState === 'loading') {
323:         document.addEventListener('DOMContentLoaded', initShell);
324:     } else {
325:         initShell();
326:     }
327: })(window);

(End of file - total 327 lines)
</content>
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 40.2s)

_Thinking:_

Now I have enough context. Let me look at the firebase.js role destination and department label functions to understand what I need to update, and the dashboard.html to see shell config usage. Let me read the relevant part of firebase.js.





**Tool: read**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\js\\firebase.js",
  "offset": 470,
  "limit": 70
}
```

**Output:**
```
<path>C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\js\firebase.js</path>
<type>file</type>
<content>
470:                     });
471:                 } catch (error) {
472:                     settle(null);
473:                 }
474:             });
475:         } catch (error) {
476:             settle(null);
477:             return;
478:         }
479:         setTimeout(function() {
480:             settle(null);
481:         }, 8000);
482:     });
483: }
484: 
485: // ============================================================================
486: // DEPARTMENT LABEL — maps a user's role + custom claims to the department name
487: // shown in the central header banner (hero subtitle, below the tenant title).
488: // The user's email stays visible ONLY in the top-right header menu next to the
489: // Logout button; it is never displayed in the hero.
490: // ============================================================================
491: 
492: function getDepartmentLabel(claims) {
493:     var role = (claims && claims.role) || 'USER';
494:     var dept = (claims && claims.department) || '';
495:     if (role === 'CAAN_SMD') return 'State Aviation Safety Oversight';
496:     if (role === 'AIRLINE_ADMIN') return 'Corporate Safety Department';
497:     if (dept === 'CAMO') return 'CAMO Department';
498:     if (dept === 'Part-145') return 'Part-145 Maintenance Department';
499:     if (dept === 'Flight Operations') return 'Flight Operations Department';
500:     return dept || '';
501: }
502: window.getDepartmentLabel = getDepartmentLabel;
503: 
504: // ============================================================================
505: // ROLE-BASED ROUTING — where should a signed-in user land after login?
506: // ============================================================================
507: 
508: function getRoleDestination(user) {
509:     var role = (user && user.role) || 'USER';
510:     if (role === 'SUPER_ADMIN') return '/admin/production-setup.html';
511:     if (role === 'CAAN_SMD') return '/caan.html';
512:     if (role === 'USER') {
513:         var claims = (user && (user.claims || {})) || {};
514:         var department = claims.department || (user && user.department) || '';
515:         if (department) return '/dashboard/responsible-manager.html';
516:         return '/safety.html';
517:     }
518:     return '/safety.html';
519: }
520: 
521: function redirectByRole(user) {
522:     window.location.href = getRoleDestination(user);
523: }
524: 
525: console.log('📦 firebase.js loaded');

(End of file - total 525 lines)
</content>
```

**Tool: glob**

**Input:**
```json
{
  "pattern": "public/dashboard*.html"
}
```

**Output:**
```
No files found
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 20.9s)

_Thinking:_

Let me find where the shell nav is configured and where dashboards live, plus the safety dashboard. Let me look for pages that define SHELL_CONFIG.

**Tool: grep**

**Input:**
```json
{
  "include": "*.html",
  "path": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public",
  "pattern": "SHELL_CONFIG"
}
```

**Output:**
```
Found 9 matches
C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\caan.html:
  Line 210: window.SHELL_CONFIG = {


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\caan-state-risk.html:
  Line 228: window.SHELL_CONFIG = {

  Line 266:     window.SHELL_CONFIG.roleLabel = `${short} · Safety Management Division`;


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\administration.html:
  Line 190: window.SHELL_CONFIG = {


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\dashboard\caan-sms-maturity.html:
  Line 190: window.SHELL_CONFIG = {


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\dashboard\index.html:
  Line 292: window.SHELL_CONFIG = {


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\top-hazards.html:
  Line 98: window.SHELL_CONFIG = {


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\safety.html:
  Line 443: window.SHELL_CONFIG = {


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\risk-trends.html:
  Line 102: window.SHELL_CONFIG = {

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 29.4s)

**Tool: read**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\safety.html",
  "limit": 120,
  "offset": 440
}
```

**Output:**
```
<path>C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\safety.html</path>
<type>file</type>
<content>
440:     <script src="/js/department_resolver.js"></script>
441: <script>
442: window.DEFAULT_DASHBOARD_VIEW = 'key-indicators-section';
443: window.SHELL_CONFIG = {
444:     brand: 'AviaSAFE',
445:     roleLabel: 'Operator Safety Dashboard',
446:     nav: [
447:         { href: '/safety.html', label: 'Key Indicators', icon: 'fa-chart-simple' },
448:         { href: '/dashboard/index.html', label: 'SMS Maturity', icon: 'fa-heart-pulse' },
449:         { href: '/risk-trends.html', label: 'Risk & Trends', icon: 'fa-chart-bar' },
450:         { href: '/top-hazards.html', label: 'Top Hazards', icon: 'fa-triangle-exclamation' },
451:         { href: '/administration.html', label: 'Administration', icon: 'fa-user-gear', roles: ['AIRLINE_ADMIN', 'safety'] },
452:     ],
453: };
454: </script>
455: <script src="/js/api/client.js"></script>
456: <script src="/js/shell.js"></script>
457: <script src="/js/dashboard-nav.js"></script>
458: <script src="/js/api/dashboard.js"></script>
459: <script src="/js/dashboard-utils.js"></script>
460: <script src="/js/report.js"></script>
461: <script src="/js/hazards.js"></script>
462: <script src="/js/can_cap.js"></script>
463: <script src="/js/verification.js"></script>
464: <script src="/js/reports.js"></script>
465: <script src="/js/flight_diversions.js"></script>
466: <script src="/js/feedback.js"></script>
467: <script src="/js/dashboard.js"></script>
468: 
469: <script>
470: initFeedbackWidget();
471: </script>
472: 
473: </body>
474: </html>

(End of file - total 474 lines)
</content>
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 19.5s)

_Thinking:_

Now let me look at the administration.html which is the admin console for AIRLINE_ADMIN — maybe there's already a user management section there. Let me read its relevant part to understand the structure and whether I should add the team management link there too.





**Tool: read**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\administration.html",
  "limit": 120,
  "offset": 180
}
```

**Output:**
```
<path>C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\administration.html</path>
<type>file</type>
<content>
180:                 </div>
181:             </div>
182:         </div>
183: 
184:         </div>
185: 
186:     </div>
187: </div>
188: 
189: <script>
190: window.SHELL_CONFIG = {
191:     brand: 'AviaSAFE',
192:     roleLabel: 'Operator Safety Dashboard',
193:     nav: [
194:         { href: '/safety.html', label: 'Key Indicators', icon: 'fa-chart-simple' },
195:         { href: '/dashboard/index.html', label: 'SMS Maturity', icon: 'fa-heart-pulse' },
196:         { href: '/risk-trends.html', label: 'Risk & Trends', icon: 'fa-chart-bar' },
197:         { href: '/top-hazards.html', label: 'Top Hazards', icon: 'fa-triangle-exclamation' },
198:         { href: '/administration.html', label: 'Administration', icon: 'fa-user-gear', roles: ['AIRLINE_ADMIN', 'safety'] },
199:     ],
200: };
201: </script>
202: <script src="/js/api/client.js"></script>
203: <script src="/js/shell.js"></script>
204: <script src="/js/dashboard-nav.js"></script>
205: <script src="/js/dashboard-utils.js"></script>
206: <script src="/js/report.js"></script>
207: <script src="https://cdn.jsdelivr.net/npm/qrcode@1.5.3/build/qrcode.min.js"></script>
208: <script>
209: function isAdministrationAllowed(session) {
210:     if (!session) return false;
211:     const email = (session.email || '').toLowerCase();
212:     // Safety Managers: any tenant, identified by a 'safety' email prefix.
213:     if (email.startsWith('safety')) return true;
214:     // Super-admin / airline-admin escape hatch.
215:     if (session.role === 'SUPER_ADMIN') return true;
216:     if (session.role === 'AIRLINE_ADMIN' || session.role === 'safety') return true;
217:     return false;
218: }
219: 
220: function showAdministrationAccessDenied() {
221:     const pageContent = document.getElementById('pageContent');
222:     if (!pageContent) return;
223:     pageContent.innerHTML = `
224:         <div style="text-align:center;padding:3rem;">
225:             <i class="fas fa-lock" style="font-size:2.5rem;color:#dc3545;"></i>
226:             <h2 style="color:#dc3545;margin-top:1rem;">Access Denied</h2>
227:             <p style="color:#64748b;">The Administration section is available to Safety Managers only.</p>
228:             <a href="/safety.html" class="btn btn-outline btn-sm" style="margin-top:1rem;"><i class="fas fa-arrow-left"></i> Back to Dashboard</a>
229:         </div>`;
230:     pageContent.style.display = 'block';
231: }
232: 
233: document.addEventListener('DOMContentLoaded', async () => {
234:     try {
235:         await waitForFirebase();
236:         const session = await getCurrentUser();
237:         if (!session) { window.location.href = '/login.html'; return; }
238: 
239:         if (!isAdministrationAllowed(session)) {
240:             showAdministrationAccessDenied();
241:             return;
242:         }
243: 
244:         // Reveal the page first so a later data-load failure can never leave a
245:         // blank white screen.
246:         const pageContent = document.getElementById('pageContent');
247:         if (pageContent) pageContent.style.display = 'block';
248: 
249:         if (typeof window.updateShellTenant === 'function') {
250:             const tenantName = session.tenantId ? session.tenantId.toUpperCase() : 'Safety Overview';
251:             window.updateShellTenant(tenantName, 'Administration · Safety Manager');
252:         }
253: 
254:         try { await loadRiskMatrixConfig(); } catch (e) { console.error('Risk matrix load failed:', e); }
255:         try { setupRiskMatrixForm(); } catch (e) { console.error('Risk matrix setup failed:', e); }
256:         try { await loadSurveyManagement(session); } catch (e) { console.error('Survey load failed:', e); }
257:         try { setupSurveyManagementForm(session); } catch (e) { console.error('Survey setup failed:', e); }
258:         try { generateSurveyQrCode(session); } catch (e) { console.error('QR generation failed:', e); }
259:     } catch (err) {
260:         console.error('Administration init failed:', err);
261:         const pageContent = document.getElementById('pageContent');
262:         if (pageContent) {
263:             pageContent.innerHTML = '<div style="text-align:center;padding:3rem;color:#dc3545;"><i class="fas fa-exclamation-circle"></i> Failed to initialise the Administration page. Please reload.</div>';
264:             pageContent.style.display = 'block';
265:         }
266:     }
267: });
268: 
269: async function loadRiskMatrixConfig() {
270:     try {
271:         const config = await getRiskMatrix();
272:         if (config && config.thresholds) {
273:             document.getElementById('rmLowMax').value = config.thresholds.low_max || 5;
274:             document.getElementById('rmMediumMax').value = config.thresholds.medium_max || 9;
275:             document.getElementById('rmHighMax').value = config.thresholds.high_max || 15;
276:         }
277:     } catch {
278:         // Use defaults
279:     }
280:     syncRiskMatrixThresholds();
281:     renderRiskMatrixPreview();
282: }
283: 
284: function riskMatrixThresholdsFromInputs() {
285:     return {
286:         lowMax: parseInt(document.getElementById('rmLowMax').value, 10) || 5,
287:         mediumMax: parseInt(document.getElementById('rmMediumMax').value, 10) || 9,
288:         highMax: parseInt(document.getElementById('rmHighMax').value, 10) || 15,
289:     };
290: }
291: 
292: function syncRiskMatrixThresholds() {
293:     const t = riskMatrixThresholdsFromInputs();
294:     if (t.lowMax >= t.mediumMax || t.mediumMax >= t.highMax) return;
295:     if (typeof ICAO_THRESHOLDS !== 'undefined') {
296:         ICAO_THRESHOLDS.lowMax = t.lowMax;
297:         ICAO_THRESHOLDS.mediumMax = t.mediumMax;
298:         ICAO_THRESHOLDS.highMax = t.highMax;
299:     }

(Showing lines 180-299 of 531. Use offset=300 to continue.)
</content>
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 17.6s)

_Thinking:_

I now have enough context. Let me check `getCurrentUser` in firebase.js to understand session shape, and how API client works (public/js/api/client.js) for adding an invite call. Let me read the relevant part of firebase.js for getCurrentUser, and client.js.

**Tool: grep**

**Input:**
```json
{
  "include": "*.js",
  "path": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\js",
  "pattern": "function getCurrentUser|async function getCurrentUser|function waitForFirebase"
}
```

**Output:**
```
Found 3 matches
C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\js\dashboard.js:
  Line 22: function waitForFirebase() {


C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\js\firebase.js:
  Line 417: function waitForFirebase() {

  Line 436: async function getCurrentUser() {

```

**Tool: read**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\js\\api\\client.js"
}
```

**Output:**
```
<path>C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\js\api\client.js</path>
<type>file</type>
<content>
1: const ApiClient = {
2:     _baseUrl: () => (window.APP_CONFIG && window.APP_CONFIG.apiBaseUrl) || 'https://aviasafe-unified-platform.onrender.com',
3: 
4:     _waitForFirebase: () => {
5:         return new Promise(resolve => {
6:             if (typeof firebase !== 'undefined' && firebase.auth) {
7:                 resolve();
8:                 return;
9:             }
10:             const check = setInterval(() => {
11:                 if (typeof firebase !== 'undefined' && firebase.auth) {
12:                     clearInterval(check);
13:                     resolve();
14:                 }
15:             }, 30);
16:             setTimeout(() => {
17:                 clearInterval(check);
18:                 resolve();
19:             }, 8000);
20:         });
21:     },
22: 
23:     _tokenRedirecting: false,
24: 
25:     _getToken: async () => {
26:         await ApiClient._waitForFirebase();
27:         const session = await getCurrentUser();
28:         if (!session) {
29:             if (!ApiClient._tokenRedirecting) {
30:                 ApiClient._tokenRedirecting = true;
31:                 window.location.href = '/login.html';
32:             }
33:             return null;
34:         }
35:         const user = firebase.auth().currentUser;
36:         if (!user) {
37:             if (!ApiClient._tokenRedirecting) {
38:                 ApiClient._tokenRedirecting = true;
39:                 window.location.href = '/login.html';
40:             }
41:             return null;
42:         }
43:         try {
44:             return await user.getIdToken();
45:         } catch {
46:             window.location.href = '/login.html';
47:             return null;
48:         }
49:     },
50: 
51:     _getTenantId: async () => {
52:         try {
53:             // Prefer the active tenant slug resolved from the subdomain / demo
54:             // context (single source of truth), then fall back to the session
55:             // tenant claim for signed-in users whose subdomain is absent.
56:             if (typeof TenantResolver !== 'undefined' && TenantResolver.getCurrentTenant) {
57:                 const active = TenantResolver.getCurrentTenant();
58:                 if (active) return active;
59:             }
60:             const session = await getCurrentUser();
61:             return (session && session.tenantId) || null;
62:         } catch {
63:             return null;
64:         }
65:     },
66: 
67:     _getUserDepartment: async () => {
68:         try {
69:             const session = await getCurrentUser();
70:             const email = (session && session.email) || '';
71:             if (email && typeof resolveDepartmentFromEmail === 'function') {
72:                 let tenantId = null;
73:                 if (typeof TenantResolver !== 'undefined' && TenantResolver.getCurrentTenant) {
74:                     tenantId = TenantResolver.getCurrentTenant();
75:                 }
76:                 if (!tenantId && session) tenantId = session.tenantId || null;
77:                 return resolveDepartmentFromEmail(email, tenantId);
78:             }
79:             return null;
80:         } catch {
81:             return null;
82:         }
83:     },
84: 
85:     _request: async (method, path, body) => {
86:         const token = await ApiClient._getToken();
87:         if (!token) return null;
88:         const [tenantId, department] = await Promise.all([
89:             ApiClient._getTenantId(),
90:             ApiClient._getUserDepartment(),
91:         ]);
92: 
93:         const url = `${ApiClient._baseUrl()}${path}`;
94:         const opts = {
95:             method,
96:             headers: {
97:                 'Content-Type': 'application/json',
98:                 'Authorization': `Bearer ${token}`,
99:                 ...(tenantId ? { 'X-Tenant-Id': tenantId } : {}),
100:                 ...(department ? { 'X-User-Department': department } : {}),
101:             },
102:         };
103:         if (body && method !== 'GET') {
104:             opts.body = JSON.stringify(body);
105:         }
106: 
107:         let response;
108:         let lastErr;
109:         // Retry on transient network failures (connection reset / cold-start on
110:         // the free Render tier). GET requests are idempotent so retrying is safe.
111:         const maxAttempts = method === 'GET' ? 3 : 1;
112:         for (let attempt = 1; attempt <= maxAttempts; attempt++) {
113:             try {
114:                 response = await fetch(url, opts);
115:                 lastErr = null;
116:                 break;
117:             } catch (err) {
118:                 lastErr = err;
119:                 console.warn(`[ApiClient] network attempt ${attempt}/${maxAttempts} failed for ${method} ${path}: ${err.message}`);
120:                 if (attempt < maxAttempts) {
121:                     await new Promise(r => setTimeout(r, 800 * attempt));
122:                 }
123:             }
124:         }
125:         if (lastErr) {
126:             const detail = `Network error while reaching the API (${method} ${path}): ${lastErr.message}`;
127:             console.error('[ApiClient]', detail);
128:             throw new Error('Network error. Please check your connection and try again.');
129:         }
130: 
131:         if (response.status === 401) {
132:             console.error(`[ApiClient] Authorization failed (401) for ${method} ${path}`);
133:             window.location.href = '/login.html';
134:             return null;
135:         }
136: 
137:         if (!response.ok) {
138:             const err = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
139:             const detail = err.detail || `Request failed: ${response.status}`;
140:             console.error(`[ApiClient] ${method} ${path} failed (${response.status}):`, detail);
141:             throw new Error(detail);
142:         }
143: 
144:         const json = await response.json();
145:         return json.data !== undefined ? json.data : json;
146:     },
147: 
148:     get: (path) => ApiClient._request('GET', path),
149:     post: (path, body) => ApiClient._request('POST', path, body),
150:     put: (path, body) => ApiClient._request('PUT', path, body),
151:     patch: (path, body) => ApiClient._request('PATCH', path, body),
152:     del: (path) => ApiClient._request('DELETE', path),
153: };
154: 
155: // ── Global Safety Copilot widget (auto-loaded on every authenticated page) ──
156: // client.js is included on all dashboard pages, so wiring the widget here gives
157: // a single global include point. Guarded against double-injection.
158: (function injectCopilotWidget() {
159:     if (window.__CopilotWidgetInjected) return;
160:     window.__CopilotWidgetInjected = true;
161:     try {
162:         const link = document.createElement('link');
163:         link.rel = 'stylesheet';
164:         link.href = '/css/copilot-widget.css';
165:         (document.head || document.body).appendChild(link);
166: 
167:         const script = document.createElement('script');
168:         script.src = '/js/components/copilot-widget.js';
169:         script.async = true;
170:         (document.head || document.body).appendChild(script);
171:     } catch (e) {
172:         console.error('[CopilotWidget] failed to load:', e);
173:     }
174: })();

(End of file - total 174 lines)
</content>
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 18.6s)

_Thinking:_

Now let me read the `getCurrentUser` function in firebase.js and the firebase.js header to understand the session shape (claims including department).

**Tool: read**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\js\\firebase.js",
  "limit": 55,
  "offset": 415
}
```

**Output:**
```
<path>C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\js\firebase.js</path>
<type>file</type>
<content>
415: // ============================================================================
416: 
417: function waitForFirebase() {
418:     return new Promise(function(resolve) {
419:         if (typeof firebase !== 'undefined' && firebase.auth) {
420:             resolve();
421:             return;
422:         }
423:         var check = setInterval(function() {
424:             if (typeof firebase !== 'undefined' && firebase.auth) {
425:                 clearInterval(check);
426:                 resolve();
427:             }
428:         }, 30);
429:         setTimeout(function() {
430:             clearInterval(check);
431:             resolve();
432:         }, 10000);
433:     });
434: }
435: 
436: async function getCurrentUser() {
437:     await waitForFirebase();
438:     return new Promise(function(resolve) {
439:         var settled = false;
440:         var unsubscribe = null;
441:         var settle = function(value) {
442:             if (settled) return;
443:             settled = true;
444:             if (unsubscribe) {
445:                 try { unsubscribe(); } catch (e) { /* ignore */ }
446:             }
447:             resolve(value);
448:         };
449:         try {
450:             if (typeof firebase === 'undefined' || !firebase.auth) {
451:                 settle(null);
452:                 return;
453:             }
454:             unsubscribe = firebase.auth().onAuthStateChanged(async function(user) {
455:                 if (settled) return;
456:                 if (!user) return; // not signed in — let the timeout settle(null)
457:                 try {
458:                     // Forced refresh can stall on App Check / reCAPTCHA or a
459:                     // cold network. Never block here: `settle` is guarded by a
460:                     // hard timeout below so the page can never hang on the
461:                     // "Checking ... access" gate.
462:                     var tokenResult = await user.getIdTokenResult(true);
463:                     var claims = (tokenResult && tokenResult.claims) || {};
464:                     settle({
465:                         uid: user.uid,
466:                         email: user.email,
467:                         role: claims.role || 'USER',
468:                         tenantId: claims.tenant_id || null,
469:                         claims: claims

(Showing lines 415-469 of 525. Use offset=470 to continue.)
</content>
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 75.8s)

_Thinking:_

I have enough context now. Let me implement.

## Backend plan

### 1. config.py — role constants
Add:
```python
ROLE_TENANT_ADMIN = "TENANT_ADMIN"
ROLE_DEPT_ADMIN = "DEPT_ADMIN"
ROLE_SAFETY_OFFICER = "SAFETY_OFFICER"
ROLE_STAFF = "STAFF"
```
Also add `TENANT_ADMIN_ROLES` = ["AIRLINE_ADMIN", "TENANT_ADMIN"] and `ADMIN_ROLES` maybe. Keep it simple. Add a `ROLE_ALIASES` mapping: AIRLINE_ADMIN→TENANT_ADMIN, USER→STAFF, and inverse. Actually the user chose "Update role checking utilities so existing AIRLINE_ADMIN/USER checks recognize the new equivalents." So:

- `get_safety_manager` currently checks `role != "AIRLINE_ADMIN"`. Change to allow TENANT_ADMIN too. Simplest: define settings.TENANT_ADMIN_ROLES = ("AIRLINE_ADMIN", "TENANT_ADMIN") and use `user.get("role") in settings.TENANT_ADMIN_ROLES`.
- `get_responsible_manager` checks roles in ("AIRLINE_ADMIN", "USER"). Update to include TENANT_ADMIN, SAFETY_OFFICER, STAFF.
- tenants.py `SURVEY_MANAGER_ROLES` and `_require_tenant_viewer`/`_require_tenant_admin` — update to recognize TENANT_ADMIN.
- `resolve_user_context` — the fallback only for `role == settings.ROLE_DEFAULT` (USER). Keep. Maybe also treat STAFF == USER for fallback.
- admin.py uses SUPER_ADMIN only — fine.
- dashboard.js frontend getDepartmentLabel + getRoleDestination — add TENANT_ADMIN, DEPT_ADMIN, SAFETY_OFFICER, STAFF handling.

### 2. Auth service for invites — create `backend/app/services/invites.py` (since auth_service.py doesn't exist and tenant_registration.py holds invite logic). Actually the spec says "Update POST /api/v1/auth/invite (and /api/auth/invite)" in routes/auth.py & services/auth_service.py. Since auth_service.py doesn't exist, I'll create `backend/app/services/invites.py` as the service module (better name) and reference it from routes/auth.py. Or create auth_service.py per spec. The user's Option 1 said "Implement authenticated POST /api/v1/auth/invite (+ /api/auth/invite alias) writing department-scoped invite documents." and "Extend the /join-team endpoint... Alias /api/v1/auth/join to the join handler."

I'll create `backend/app/services/invites.py` with:
- Role constants:
  - `TENANT_ADMIN_ASSIGNABLE_ROLES = {"DEPT_ADMIN", "SAFETY_OFFICER", "STAFF"}`
  - `DEPT_ADMIN_ASSIGNABLE_ROLES = {"STAFF"}`
- `create_invite(*, caller, department, role, request=None)`:
  - validates caller role
  - For TENANT_ADMIN: department must be in tenant's applicable_departments; role in TENANT_ADMIN_ASSIGNABLE_ROLES
  - For DEPT_ADMIN: target department must equal caller's department (compare normalized); role must be STAFF. Reject with PermissionError → 403.
  - For SUPER_ADMIN: allow like TENANT_ADMIN (super admin global) — spec focuses on TENANT_ADMIN/DEPT_ADMIN, but SUPER_ADMIN is global; allow full.
  - Generate unique code; write to `tenants/{tid}/invites/{code}` with {code, tenant_id, department, department_label, role, created_by, created_at, status: "ACTIVE"}.
  - Also handle SAFETY_OFFICER assignable? Spec: TENANT_ADMIN can assign roles ["DEPT_ADMIN", "SAFETY_OFFICER", "STAFF"]. Yes.
- `resolve_invite_doc(db, code)` — look up invite doc across tenants? Since invites are under tenants/{tid}/invites/{code}, to resolve by code we need a query on subcollection which Firestore doesn't support across collections easily. Better to store invites in a top-level collection `invites` keyed by code, OR store code→(tid, dept, role) mapping. The spec says "Persist the invite document with: { code, tenant_id, department, role, created_by, created_at, status: ACTIVE }". It doesn't specify where. To make resolution by code easy (join only has the code), a top-level `invites/{code}` collection is cleanest. But the spec earlier said "under tenants/{tid}/invites/"? Actually the spec doesn't specify location. My earlier message to the user proposed "writing department-scoped invite documents" and my todo says "under tenants/{tid}/invites/{code}". 

Hmm, but joining requires resolving by code alone. Firestore subcollection query `collectionGroup("invites").where("code","==",code)` works with collection group queries but requires index. The mock test DB would need to support collectionGroup. Alternatively, top-level `invites` collection with doc id = code. That's simplest and resolvable. But then the tenant's invites aren't scoped under the tenant doc.

Compromise: Store invite docs in top-level `invites/{code}` collection (resolvable by code, simple). This matches "Persist the invite document with: { code, tenant_id, department, role, ... }". I'll go with top-level `invites` collection. Let me adjust the todo wording mentally.

Actually wait — I told the user "writing department-scoped invite documents" in the question, and they approved. "Department-scoped" refers to the invite carrying a department field (scoping the invitee to a department), not necessarily a subcollection. A top-level invites collection with department+tenant_id fields satisfies "department-scoped". I'll use top-level `invites` collection for resolvability. I'll document this.

For tests, the mock `_FakeDB.collection` must handle "invites". I'll write the new test file with its own fakes.

### 3. routes/auth.py additions:
- `InviteRequest(BaseModel)`: department: str, role: str (default STAFF). Maybe allow `tenant_id`? Caller's tenant is authoritative; no need. Keep department + role.
- `POST /invite` (async) with `Depends(get_current_user)`:
  - caller must have role in (TENANT_ADMIN, AIRLINE_ADMIN, DEPT_ADMIN, SUPER_ADMIN). Others → 403.
  - call `create_invite`.
  - return {success, code, tenant_id, department, role, created_at}.
- `GET /invites`? Not in spec but useful for team page to list active invites. Actually the team page needs to show invites. The spec frontend part only mentions team list + invite form. But showing existing invite codes is important for sharing. I'll add `GET /invites` (list caller-scoped invites) and maybe `POST /invites/{code}/revoke`. Keep scope tight: add GET /invites for listing; skip revoke to keep scope minimal (spec doesn't ask). Actually a revoke is natural, but I'll keep minimal per spec. Hmm — but a team page that generates invite codes but can't list them is not useful. I'll add GET /invites (list) too. Let me include it; it's low-risk and needed by the UI.

- `JoinTeamRequest` already exists. Modify `join_team_endpoint` and the `join_team` service to read invite doc:
  - In `join_team` service (tenant_registration.py): before department validation, try resolve invite doc by code. If found and ACTIVE:
    - validate email not duplicate (already handled in _create_user)
    - department = invite.department (validate it's in tenant's applicable_departments)
    - role = invite.role (STAFF, DEPT_ADMIN, SAFETY_OFFICER)
    - bind user claims + user_doc with that role and department.
    - if invite not found and code still matches tenant's team_invite_code → legacy path (self-select department, role USER/STAFF).
  - Return department/role in result.

- Add `@router.post("/join")` alias that calls the same handler. But note rate limit decorators — applying two decorators to one function? The cleanest: define the handler once, then create a second endpoint that reuses it. Actually FastAPI path operation decorators stack: I can stack `@router.post("/join-team")` and `@router.post("/join")` on the same function; both routes register. And `@rate_limit("join_team")` applies to both. Yes, stacking decorators works. But the route is also mounted under legacy /api/auth. So `/api/auth/join` would work too (spec asked /api/auth/invite alias — that works via the same router mount for /invite).

Wait: the spec says POST /api/v1/auth/invite AND /api/auth/invite. Since auth.router is mounted at both API_PREFIX_AUTH and API_PREFIX_AUTH_LEGACY, adding `@router.post("/invite")` gives both /api/v1/auth/invite and /api/auth/invite automatically. Good. Same for /join → /api/v1/auth/join and /api/auth/join.

- Also update `verify_invite_endpoint` to also check the invite doc (department/role invites) so join.html shows org name. Spec item 2 only mentions /join. But verify-invite currently checks tenant's team_invite_code. For department-scoped invites, verify-invite should also accept them. I'll extend `verify_invite` service to check the invites collection first, falling back to tenant code. This keeps join.html working for department-scoped codes.

### 4. users listing endpoint with DEPT_ADMIN scoping
Modify `tenants.py`:
- `_require_tenant_viewer` → allow TENANT_ADMIN/AIRLINE_ADMIN/DEPT_ADMIN + SUPER_ADMIN. For DEPT_ADMIN, require tenant match AND filter users to caller's department.
- In `list_users` endpoint, if caller is DEPT_ADMIN, filter users to their department. Need department normalized to code vs label. Users store `department` as label (e.g., "Flight Operations") per join_team. DEPT_ADMIN claims department — what format? When joining via invite, we set department to label (consistent with existing join_team which sets `department: label`). For DEPT_ADMIN created via invite, department = label too. So filtering by label works if we compare labels. But the invite doc stores department as code (e.g., "flight_ops") and label. The user's claim department is set to label (matching existing convention where claims["department"] = label). Hmm, let me keep consistent: claims department = label (like join_team does). The DEPT_ADMIN's department claim = their label. So filter users where `user.department == caller_department_label`. I'll add a `department` query param to `list_tenant_users` for optional filtering, or filter in-memory in the route. In-memory filter is simplest: `[u for u in users if u["department"] == dept_label]`.

But wait — the caller's `department` claim for DEPT_ADMIN: set by join via invite to label. Good. However, what about existing AIRLINE_ADMIN? They have department "safety" label "Safety"? AIRLINE_ADMIN created via register_tenant has claims department "safety" (code) not label! Look at register_tenant: claims `{"role": "AIRLINE_ADMIN", "tenant_id": tid, "department": "safety"}` — that's the code, not label. But join_team sets claims department = label. Inconsistent. For DEPT_ADMIN we control creation via invite → label. For scoping comparisons I should normalize. Let me store department as the CODE in claims for new invites? Hmm, existing join_team sets label in claims and user_doc. The user_doc department is also label. The frontend getDepartmentLabel handles label formats like 'CAMO', 'Part-145', 'Flight Operations'. So label is the convention used by frontend.

Decision: For invite-based joins, store department as label (consistent with join_team). For DEPT_ADMIN scoping, compare normalized labels. To be robust, I'll add a helper that maps code→label and label→code using DEPARTMENT_LABELS, and compare both. I'll write `normalize_department` in invites.py: returns the canonical label given either a code or a label.

For the users list filter, DEPT_ADMIN's department claim (label) is compared against each user's department field (label). Both labels → direct equality. Good.

### 5. Frontend
Create `public/settings/team.html` + `public/js/team.js` (or inline). Use shell.js pattern. Need role-aware rendering:
- On load, get current user session (getCurrentUser), role = claims.role.
- For DEPT_ADMIN: 
  - fetch users via ApiClient.get(`/api/v1/tenants/{tenantId}/users`) — backend already filters for DEPT_ADMIN, but frontend also filters client-side to be safe.
  - Invite form: department selector locked to caller's department (read-only), role locked to STAFF.
- For TENANT_ADMIN/AIRLINE_ADMIN:
  - show all users, department dropdown with applicable departments, role dropdown with DEPT_ADMIN/SAFETY_OFFICER/STAFF.
- Invite submission: ApiClient.post('/api/v1/auth/invite', {department, role}) → show generated code + copy button.
- Show existing invites: ApiClient.get('/api/v1/auth/invites').

Wait — role aliases: backend stores role as STAFF etc. but frontend displays labels. Need mapping: DEPT_ADMIN → "Department Admin (HOD)", SAFETY_OFFICER → "Safety Officer", STAFF → "Staff / Employee". Also handle legacy AIRLINE_ADMIN → "Safety Manager (Tenant Admin)".

I need to update:
- `public/js/firebase.js`: getRoleDestination to route TENANT_ADMIN→safety.html, DEPT_ADMIN→safety.html (or team.html?), SAFETY_OFFICER→safety.html, STAFF→safety.html/responsible-manager. Add to getDepartmentLabel: TENANT_ADMIN → 'Corporate Safety Department', DEPT_ADMIN → dept label, SAFETY_OFFICER → dept label.
- Shell nav in safety.html/administration.html: add Team link with roles ['AIRLINE_ADMIN','TENANT_ADMIN','DEPT_ADMIN'].
- The nav `data-roles` matching uses exact role string. TENANT_ADMIN/DEPT_ADMIN roles will be new claims. Fine.

Also the `isAdministrationAllowed` in administration.html checks role === 'AIRLINE_ADMIN' or 'safety'. TENANT_ADMIN would be denied. I should update it to allow TENANT_ADMIN too (and maybe DEPT_ADMIN? Administration is survey mgmt + risk matrix — safety manager territory. I'll allow TENANT_ADMIN/AIRLINE_ADMIN; not DEPT_ADMIN). Update to recognize TENANT_ADMIN.

### 6. Tests
Create `backend/tests/test_dept_admin_rbac.py` using the fake-db pattern. Tests:
1. TENANT_ADMIN can invite DEPT_ADMIN to any department (200, invite doc persisted with role DEPT_ADMIN, department).
2. TENANT_ADMIN can invite STAFF to any department.
3. DEPT_ADMIN can invite STAFF to their own department (200).
4. DEPT_ADMIN inviting to another department → 403.
5. DEPT_ADMIN attempting to assign DEPT_ADMIN or TENANT_ADMIN role → 403.
6. Join with department-scoped invite binds department + role (e.g., STAFF invite → user role STAFF, department label; DEPT_ADMIN invite → role DEPT_ADMIN).
7. Maybe: USER (staff) cannot invite → 403.
8. SUPER_ADMIN can invite (bonus).
9. Legacy code path still works (join-team without dept-scoped invite falls back).

The mock DB must support:
- `tenants` collection (document get, where on team_invite_code)
- `invites` collection (document by code: set/get; where queries for tenant listing + uniqueness check)
- `users` collection (document set/get, where on tenant_id for list)
- `audit_logs`

The invite uniqueness check `_invite_code_taken` in tenant_registration queries tenants by team_invite_code. For invite codes in the invites collection, generate_invite_code only checks tenants collection. I'll create a separate code generator in invites.py that checks both tenants' team_invite_code and the invites collection.

Let me check how tests fake `get_current_user`. The invite endpoint uses `Depends(get_current_user)`. In tests, I'll override the dependency: `app.dependency_overrides[get_current_user] = lambda: {...}`. That's the pattern used elsewhere (test_admin_credentials etc.).

But note: auth.py imports `get_current_user`? Currently auth.py imports `resolve_user_context` only. I'll add `get_current_user` import. Tests can override `app.middleware.auth.get_current_user` via dependency_overrides on the function object — but FastAPI dependency override keys on the function passed to Depends. If I import the same function object, `app.dependency_overrides[get_current_user]` works. Yes since it's the same object imported from app.middleware.auth.

Now, the join endpoint also needs to work with the invite doc resolution. The `join_team` service uses `resolve_tenant(db, invite_code, tenant_id)` which looks up tenant by team_invite_code. For department-scoped invites, the invite code is in the invites collection, NOT in the tenant's team_invite_code. So `resolve_tenant` by code would fail. I need to modify `join_team` to first check the invites collection for the code; if found, resolve tenant from invite.tenant_id.

Let me design `invites.py`:

```python
ROLE_STAFF = "STAFF"
ROLE_DEPT_ADMIN = "DEPT_ADMIN"
ROLE_SAFETY_OFFICER = "SAFETY_OFFICER"
ROLE_TENANT_ADMIN = "TENANT_ADMIN"

TENANT_ADMIN_ASSIGNABLE = frozenset({ROLE_DEPT_ADMIN, ROLE_SAFETY_OFFICER, ROLE_STAFF})
DEPT_ADMIN_ASSIGNABLE = frozenset({ROLE_STAFF})

ROLE_LABELS = {
    "TENANT_ADMIN": "Safety Manager (Tenant Admin)",
    "DEPT_ADMIN": "Department Admin (HOD)",
    "SAFETY_OFFICER": "Safety Officer",
    "STAFF": "Staff / Employee",
}

def normalize_department(value):  # code or label -> label
    if not value: return ""
    for code, label in DEPARTMENT_LABELS.items():
        if value.strip().lower() == code.strip().lower() or value.strip().lower() == label.strip().lower():
            return label
    return value.strip()

def invite_code_taken(db, code):
    # check invites collection + tenants team_invite_code
    ...

def generate_invite_code(db):
    ...

def create_invite(*, caller, department, role, request=None):
    # caller: {role, tenant_id, department, uid, email}
    # returns dict
    role = (role or "").strip().upper()
    dept = normalize_department(department)
    db = get_db()
    tid = caller.get("tenant_id")
    if not tid:
        raise PermissionError("...")
    # tenant check
    tenant_ref = db.collection("tenants").document(tid)
    tenant = tenant_ref.get()
    if not tenant.exists: raise LookupError
    td = tenant.to_dict() or {}
    applicable = td.get("applicable_departments") or []
    caller_role = caller.get("role")
    if caller_role in ("SUPER_ADMIN", "TENANT_ADMIN", "AIRLINE_ADMIN"):
        if dept not in applicable:
            raise ValueError(f"Department ... not applicable")
        if role not in TENANT_ADMIN_ASSIGNABLE:
            raise PermissionError(f"Cannot assign role {role}")
    elif caller_role == "DEPT_ADMIN":
        caller_dept = normalize_department(caller.get("department"))
        if dept != caller_dept:
            raise PermissionError("DEPT_ADMIN may only invite members of their own department")
        if role not in DEPT_ADMIN_ASSIGNABLE:
            raise PermissionError("DEPT_ADMIN may only assign the STAFF role")
    else:
        raise PermissionError("...")  # 403
    code = generate_invite_code(db)
    now = datetime.now(timezone.utc)
    doc = {code, tenant_id, department: dept, role, created_by: caller.get("uid") or caller.get("email"), created_at, status: "ACTIVE"}
    db.collection("invites").document(code).set(doc)
    audit...
    return {...}
```

Department applicability: `applicable_departments` holds codes (e.g., "flight_ops"). `dept` is label after normalize. So comparing `dept` (label) against codes in applicable fails. I need to compare code. Let me keep `dept_code` and `dept_label`. Normalize to code: I should convert the requested department to its code if it's a label. Let me add `department_to_code(value)`:

```python
def department_to_code(value):
    v = (value or "").strip().lower()
    for code, label in DEPARTMENT_LABELS.items():
        if v == code or v == label.lower():
            return code
    return v  # assume already a code
```

Then validate code in applicable. And label = DEPARTMENT_LABELS.get(code, code). Store department = code in the invite doc? The spec says department field. For join, we need to set claims department = label (frontend convention). I'll store `department` = code (canonical) and `department_label` = label in the invite doc. For DEPT_ADMIN comparison: caller's department claim is a label (from their own join). Compare normalized label: `department_to_code(caller.department) == dept_code`. Good.

For join: 
```python
def join_team(...):
    ...
    db = get_db()
    # try department-scoped invite first
    invited = None
    if invite_code:
        invited = resolve_invite(db, invite_code)  # returns doc or None
    if invited:
        tid = invited["tenant_id"]
        tenant_doc = resolve_tenant(db, None, tid)  # by id
        code = invited["department"]
        label = invited.get("department_label") or DEPARTMENT_LABELS.get(code, code)
        role = invited["role"]
        # if invite not ACTIVE -> LookupError
    else:
        tid, tenant_doc = resolve_tenant(db, invite_code, tenant_id)
        code = department.strip()  # from body
        # validate code in applicable
        label = DEPARTMENT_LABELS.get(code, code)
        role = settings.ROLE_DEFAULT  # USER
    ...
    claims = {"role": role, "tenant_id": tid, "department": label}
    user_doc role = role
    return with department, department_label, role
```

Also mark invite used? Spec doesn't require consumption; keep ACTIVE for reuse (or set status USED). I'll leave ACTIVE (no revocation flow), but that means same code reusable. Acceptable for now.

Also need `resolve_invite` in invites.py:
```python
def resolve_invite(db, code):
    if not code: return None
    snap = db.collection("invites").document(code.upper()).get()
    if snap.exists:
        return snap.to_dict() or {}
    return None
```

And `verify_invite` in tenant_registration: extend to check invites first:
```python
def verify_invite(db, code):
    if not code or not code.strip(): raise ValueError
    code = code.strip().upper()
    invite = resolve_invite(db, code)
    if invite:
        tid = invite.get("tenant_id")
        tenant_doc = resolve_tenant(db, None, tid)[1]  # careful signature
        # active check tenant
        ...
        return {valid, organization_name, tenant_id, category, department, department_label, role}
    # fallback legacy
    tid, tenant_doc = resolve_tenant(db, code, None)
    ...
```

Hmm resolve_tenant signature is `resolve_tenant(db, invite_code, tenant_id)`. For invite path, call `resolve_tenant(db, None, tid)`.

Now the route-level for invite endpoint: I'll add to auth.py:

```python
class InviteRequest(BaseModel):
    department: str = Field(..., min_length=1)
    role: str = Field(default="STAFF", max_length=50)

class InviteListResponse... # not needed, return dicts

@router.post("/invite")
@rate_limit("invite")
async def invite_endpoint(request, body: InviteRequest, user: dict = Depends(get_current_user)):
    try:
        result = create_invite(caller=user, department=body.department, role=body.role, request=request)
    except PermissionError as e: 403
    except ValueError as e: 422
    except LookupError as e: 404
    except RuntimeError as e: 500
    return {"success": True, **result}

@router.get("/invites")
async def list_invites_endpoint(user=Depends(get_current_user)):
    # list invites for caller's tenant (SUPER_ADMIN/TENANT_ADMIN all; DEPT_ADMIN own dept)
    ...
```

Rate limit: add "invite": (20, 3600) to rate_limit config.

For listing invites, I need a query on invites by tenant_id. Mock DB needs `.where("tenant_id","==",tid)`. Fine.

Frontend role labels + routing updates.

Let me now check the rate_limit.py to add the invite bucket.

Also need to handle the `get_current_user` import in auth.py — it's currently imported? Line 27 imports only resolve_user_context. I'll add get_current_user import.

Now, one more consideration: `create_invite` needs `caller.get("department")` for DEPT_ADMIN. get_current_user returns `department` from claims (decoded_token.get('department')). Good.

Let me also check: does `resolve_user_context` need updating for role fallback? The fallback triggers when role == ROLE_DEFAULT (USER) and no tenant_id → looks up tenant by email and sets AIRLINE_ADMIN. For new roles, keep as is. But should treat STAFF same as USER? If a STAFF user's token lacks tenant_id... edge case, skip. I'll leave resolve_user_context as is except maybe none. Actually I'll leave it.

Now let me check middleware `get_safety_manager` and `get_responsible_manager` updates:
- get_safety_manager: allow TENANT_ADMIN as tenant admin. Change `user.get('role') != "AIRLINE_ADMIN"` to `user.get('role') not in settings.TENANT_ADMIN_ROLES`. Add settings.TENANT_ADMIN_ROLES = ("AIRLINE_ADMIN", "TENANT_ADMIN").
- get_responsible_manager: allow roles in ("AIRLINE_ADMIN","TENANT_ADMIN","SAFETY_OFFICER","USER","STAFF").

tenants.py:
- SURVEY_MANAGER_ROLES add TENANT_ADMIN.
- _require_tenant_viewer: allow AIRLINE_ADMIN, TENANT_ADMIN, DEPT_ADMIN (with dept filter), SUPER_ADMIN.
- _require_tenant_admin: allow AIRLINE_ADMIN, TENANT_ADMIN.

Let me also add role helpers in config for clarity:
```python
ROLE_TENANT_ADMIN = "TENANT_ADMIN"
ROLE_DEPT_ADMIN = "DEPT_ADMIN"
ROLE_SAFETY_OFFICER = "SAFETY_OFFICER"
ROLE_STAFF = "STAFF"
TENANT_ADMIN_ROLES: List[str] = ["AIRLINE_ADMIN", "TENANT_ADMIN"]
DEPT_ADMIN_ROLES: List[str] = ["DEPT_ADMIN"]
STAFF_ROLES: List[str] = ["USER", "STAFF"]
```

Now, let me also check `AuthRole` enum — it's used somewhere? grep showed only definition. I'll add the new roles to the enum too for completeness.

Let me start implementing. First config.py.

Let me also check the frontend test suites to make sure I don't break them. The frontend tests: dashboard.test.js, input-guard.test.js, tenant-context.test.js. They may reference firebase.js? Probably not heavily. I'll run them after.

Now, let me write the code. Start with config.py edits.

Let me implement step by step.

Edit 1: config.py — add roles.

I have enough context. Let me start implementing. First, role constants in config.py

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\core\\config.py",
  "oldString": "class AuthRole(str, Enum):\n    AIRLINE_ADMIN = \"AIRLINE_ADMIN\"\n    CAAN_SMD = \"CAAN_SMD\"\n    SUPER_ADMIN = \"SUPER_ADMIN\"\n    USER = \"USER\"",
  "newString": "class AuthRole(str, Enum):\n    # Legacy tenant-admin role (kept for backward compatibility).\n    AIRLINE_ADMIN = \"AIRLINE_ADMIN\"\n    # Canonical tenant admin (Safety Manager); AIRLINE_ADMIN is its legacy alias.\n    TENANT_ADMIN = \"TENANT_ADMIN\"\n    # Department-scoped administrator (Head of Department).\n    DEPT_ADMIN = \"DEPT_ADMIN\"\n    # Operational safety review role (cross-department review within tenant).\n    SAFETY_OFFICER = \"SAFETY_OFFICER\"\n    # Legacy least-privilege member role.\n    USER = \"USER\"\n    # Canonical least-privilege member role; USER is its legacy alias.\n    STAFF = \"STAFF\"\n    CAAN_SMD = \"CAAN_SMD\"\n    SUPER_ADMIN = \"SUPER_ADMIN\""
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 10.6s)

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\core\\config.py",
  "newString": "# ── Roles ──\n    ROLE_DEFAULT: str = \"USER\"\n    ROLE_DEFAULT_REGISTRATION: str = \"AIRLINE_ADMIN\"\n    CROSS_TENANT_ROLES: List[str] = [\"CAAN_SMD\", \"SUPER_ADMIN\"]\n    SUPER_ADMIN_ROLES: List[str] = [\"SUPER_ADMIN\"]\n    # Canonical role constants for the delegated admin hierarchy.\n    ROLE_TENANT_ADMIN: str = \"TENANT_ADMIN\"\n    ROLE_DEPT_ADMIN: str = \"DEPT_ADMIN\"\n    ROLE_SAFETY_OFFICER: str = \"SAFETY_OFFICER\"\n    ROLE_STAFF: str = \"STAFF\"\n    # Role-alias groups so existing AIRLINE_ADMIN/USER checks recognize the new\n    # canonical names (TENANT_ADMIN == AIRLINE_ADMIN, STAFF == USER).\n    TENANT_ADMIN_ROLES: List[str] = [\"AIRLINE_ADMIN\", \"TENANT_ADMIN\"]\n    DEPT_ADMIN_ROLES: List[str] = [\"DEPT_ADMIN\"]\n    SAFETY_OFFICER_ROLES: List[str] = [\"SAFETY_OFFICER\"]\n    STAFF_ROLES: List[str] = [\"USER\", \"STAFF\"]\n    # Roles permitted to act across the whole tenant (tenant admins + cross-tenant).\n    TENANT_WIDE_ROLES: List[str] = [\"AIRLINE_ADMIN\", \"TENANT_ADMIN\", \"CAAN_SMD\", \"SUPER_ADMIN\"]",
  "oldString": "# ── Roles ──\n    ROLE_DEFAULT: str = \"USER\"\n    ROLE_DEFAULT_REGISTRATION: str = \"AIRLINE_ADMIN\"\n    CROSS_TENANT_ROLES: List[str] = [\"CAAN_SMD\", \"SUPER_ADMIN\"]\n    SUPER_ADMIN_ROLES: List[str] = [\"SUPER_ADMIN\"]"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 27.8s)

_Thinking:_

Now update middleware/auth.py to recognize the new role equivalents.

Now update the role-checking middleware



**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\middleware\\auth.py",
  "newString": "async def get_safety_manager(\n    user: Dict[str, Any] = Depends(get_current_user)\n) -> Dict[str, Any]:\n    if user.get('role') not in settings.CROSS_TENANT_ROLES and user.get('role') not in settings.TENANT_ADMIN_ROLES:\n        raise HTTPException(\n            status_code=403,\n            detail=\"Safety Manager or CAAN_SMD role required\"\n        )\n    if user.get('role') in settings.TENANT_ADMIN_ROLES and not user.get('tenant_id'):\n        raise HTTPException(\n            status_code=403,\n            detail=\"Tenant access required for Safety Manager\"\n        )\n    return user",
  "oldString": "async def get_safety_manager(\n    user: Dict[str, Any] = Depends(get_current_user)\n) -> Dict[str, Any]:\n    if user.get('role') not in settings.CROSS_TENANT_ROLES and user.get('role') != \"AIRLINE_ADMIN\":\n        raise HTTPException(\n            status_code=403,\n            detail=\"Safety Manager or CAAN_SMD role required\"\n        )\n    if user.get('role') == \"AIRLINE_ADMIN\" and not user.get('tenant_id'):\n        raise HTTPException(\n            status_code=403,\n            detail=\"Tenant access required for AIRLINE_ADMIN\"\n        )\n    return user"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 23.0s)

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\middleware\\auth.py",
  "newString": "async def get_responsible_manager(\n    user: Dict[str, Any] = Depends(get_current_user)\n) -> Dict[str, Any]:\n    allowed = (\n        settings.CROSS_TENANT_ROLES\n        + settings.TENANT_ADMIN_ROLES\n        + settings.SAFETY_OFFICER_ROLES\n        + settings.STAFF_ROLES\n    )\n    if user.get('role') not in allowed:\n        raise HTTPException(\n            status_code=403,\n            detail=\"Responsible Manager, Safety Manager, or CAAN_SMD role required\"\n        )\n    if not user.get('tenant_id') and user.get('role') not in settings.CROSS_TENANT_ROLES:\n        raise HTTPException(\n            status_code=403,\n            detail=\"Tenant access required\"\n        )\n    return user",
  "oldString": "async def get_responsible_manager(\n    user: Dict[str, Any] = Depends(get_current_user)\n) -> Dict[str, Any]:\n    if user.get('role') not in settings.CROSS_TENANT_ROLES and user.get('role') not in (\"AIRLINE_ADMIN\", \"USER\"):\n        raise HTTPException(\n            status_code=403,\n            detail=\"Responsible Manager, AIRLINE_ADMIN, or CAAN_SMD role required\"\n        )\n    if not user.get('tenant_id') and user.get('role') not in settings.CROSS_TENANT_ROLES:\n        raise HTTPException(\n            status_code=403,\n            detail=\"Tenant access required\"\n        )\n    return user"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 10.9s)

_Thinking:_

Now update tenants.py to recognize TENANT_ADMIN and DEPT_ADMIN for user listing. Let me update `SURVEY_MANAGER_ROLES`, `_require_tenant_admin`, `_require_tenant_viewer`, and the `list_users` endpoint to filter for DEPT_ADMIN.

Now update the tenant users endpoint for DEPT_ADMIN scoping

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\routes\\tenants.py",
  "newString": "SURVEY_MANAGER_ROLES = (\"AIRLINE_ADMIN\", \"TENANT_ADMIN\", \"safety\")",
  "oldString": "SURVEY_MANAGER_ROLES = (\"AIRLINE_ADMIN\", \"safety\")"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 54.7s)





**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\routes\\tenants.py",
  "newString": "def _require_tenant_admin(user: Dict[str, Any], tenant_id: str) -> None:\n    \"\"\"Only the Safety Manager (AIRLINE_ADMIN / TENANT_ADMIN / safety) of the\n    target tenant may update its config. SUPER_ADMIN / CAAN_SMD cannot edit\n    tenant settings.\"\"\"\n    if user.get(\"role\") not in SURVEY_MANAGER_ROLES:\n        raise HTTPException(\n            status_code=status.HTTP_403_FORBIDDEN,\n            detail=\"Only the Safety Manager of this tenant can update its config\",\n        )\n    if user.get(\"tenant_id\") != tenant_id:\n        raise HTTPException(\n            status_code=status.HTTP_403_FORBIDDEN,\n            detail=\"tenantId does not match the authenticated user's tenant\",\n        )\n\n\ndef _require_tenant_viewer(user: Dict[str, Any], tenant_id: str) -> None:\n    \"\"\"AIRLINE_ADMIN / TENANT_ADMIN / DEPT_ADMIN of the tenant or SUPER_ADMIN\n    may list users. DEPT_ADMIN is additionally restricted to their own\n    department (enforced in the list endpoint).\"\"\"\n    if user.get(\"role\") == \"SUPER_ADMIN\":\n        return\n    if user.get(\"role\") not in (\"AIRLINE_ADMIN\", \"TENANT_ADMIN\", \"DEPT_ADMIN\"):\n        raise HTTPException(\n            status_code=status.HTTP_403_FORBIDDEN,\n            detail=\"Only the Safety Manager or Department Admin of this tenant or SUPER_ADMIN can view users\",\n        )\n    if user.get(\"tenant_id\") != tenant_id:\n        raise HTTPException(\n            status_code=status.HTTP_403_FORBIDDEN,\n            detail=\"tenantId does not match the authenticated user's tenant\",\n        )",
  "oldString": "def _require_tenant_admin(user: Dict[str, Any], tenant_id: str) -> None:\n    \"\"\"Only the Safety Manager (AIRLINE_ADMIN / safety) of the target tenant\n    may update its config. SUPER_ADMIN / CAAN_SMD cannot edit tenant settings.\"\"\"\n    if user.get(\"role\") not in SURVEY_MANAGER_ROLES:\n        raise HTTPException(\n            status_code=status.HTTP_403_FORBIDDEN,\n            detail=\"Only the Safety Manager of this tenant can update its config\",\n        )\n    if user.get(\"tenant_id\") != tenant_id:\n        raise HTTPException(\n            status_code=status.HTTP_403_FORBIDDEN,\n            detail=\"tenantId does not match the authenticated user's tenant\",\n        )\n\n\ndef _require_tenant_viewer(user: Dict[str, Any], tenant_id: str) -> None:\n    \"\"\"Phase 2: AIRLINE_ADMIN of the tenant or SUPER_ADMIN may list users.\"\"\"\n    if user.get(\"role\") == \"SUPER_ADMIN\":\n        return\n    if user.get(\"role\") != \"AIRLINE_ADMIN\":\n        raise HTTPException(\n            status_code=status.HTTP_403_FORBIDDEN,\n            detail=\"Only the AIRLINE_ADMIN of this tenant or SUPER_ADMIN can view users\",\n        )\n    if user.get(\"tenant_id\") != tenant_id:\n        raise HTTPException(\n            status_code=status.HTTP_403_FORBIDDEN,\n            detail=\"tenantId does not match the authenticated user's tenant\",\n        )"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 19.0s)

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\routes\\tenants.py",
  "newString": "tenant_id = tenant_id.strip()\n    _require_tenant_viewer(user, tenant_id)\n    try:\n        users = list_tenant_users(tenant_id)\n    except Exception as e:\n        logger.warning(f\"Failed to list users for tenant {tenant_id}: {e}\")\n        raise HTTPException(status_code=500, detail=\"Failed to list tenant users\")\n    # DEPT_ADMIN sees only their own department's members.\n    if user.get(\"role\") == \"DEPT_ADMIN\":\n        from app.services.invites import department_to_code\n        caller_code = department_to_code(user.get(\"department\"))\n        users = [\n            u for u in users\n            if department_to_code(u.get(\"department\")) == caller_code\n        ]\n    return _envelope({\"tenant_id\": tenant_id, \"users\": users})",
  "oldString": "tenant_id = tenant_id.strip()\n    _require_tenant_viewer(user, tenant_id)\n    try:\n        users = list_tenant_users(tenant_id)\n    except Exception as e:\n        logger.warning(f\"Failed to list users for tenant {tenant_id}: {e}\")\n        raise HTTPException(status_code=500, detail=\"Failed to list tenant users\")\n    return _envelope({\"tenant_id\": tenant_id, \"users\": users})"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 44.4s)

_Thinking:_

Now create the invites service module. Let me write `backend/app/services/invites.py`.

Key functions:
- Role constants and labels
- `department_to_code`, `normalize_department`, `department_label`
- `generate_invite_code` (checks invites + tenants team_invite_code)
- `create_invite`
- `resolve_invite`
- `list_invites` (by tenant + optional dept code)

Let me write it.

Now create the invites service module

**Tool: write**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\services\\invites.py",
  "content": "# ============================================================================\n# FILE: invites.py\n# PATH: backend/app/services/invites.py\n# PURPOSE: Department-scoped team invites for the delegated admin hierarchy.\n#\n#   create_invite():   authenticated admin issues a department-scoped invite\n#                      document keyed by its 6-char code in the top-level\n#                      `invites` collection. RBAC:\n#                        - TENANT_ADMIN / AIRLINE_ADMIN / SUPER_ADMIN may invite\n#                          into ANY applicable department with roles\n#                          DEPT_ADMIN / SAFETY_OFFICER / STAFF.\n#                        - DEPT_ADMIN may only invite STAFF into their OWN\n#                          department (cross-department or privilege escalation\n#                          is rejected with PermissionError -> 403).\n#   resolve_invite():  lookup an invite document by code (used by the public\n#                      join flow to bind department + role).\n#   list_invites():    tenant-scoped invite listing for the team page.\n#\n# Errors are raised as exceptions for the route layer to map to HTTP statuses:\n#   PermissionError -> 403   (RBAC violation / privilege escalation)\n#   ValueError      -> 422   (invalid department / role payload)\n#   LookupError     -> 404   (unknown tenant)\n#   RuntimeError    -> 500   (persistence failures)\n# ============================================================================\n\nimport secrets\nfrom datetime import datetime, timezone\nfrom typing import Any, Dict, List, Optional\n\nfrom loguru import logger\n\nfrom app.core.config import settings\nfrom app.firebase import get_db\nfrom app.services.audit_service import log_audit, request_context\nfrom app.services.tenant_registration import (\n    DEPARTMENT_LABELS,\n    INVITE_ALPHABET,\n    INVITE_CODE_LENGTH,\n)\n\n# Canonical roles + assignable-role matrix for the delegated admin hierarchy.\nROLE_TENANT_ADMIN = settings.ROLE_TENANT_ADMIN\nROLE_DEPT_ADMIN = settings.ROLE_DEPT_ADMIN\nROLE_SAFETY_OFFICER = settings.ROLE_SAFETY_OFFICER\nROLE_STAFF = settings.ROLE_STAFF\n\n# Roles a tenant admin (or SUPER_ADMIN) may assign via invite.\nTENANT_ADMIN_ASSIGNABLE_ROLES = frozenset(\n    {ROLE_DEPT_ADMIN, ROLE_SAFETY_OFFICER, ROLE_STAFF}\n)\n# Roles a department admin (HOD) may assign via invite.\nDEPT_ADMIN_ASSIGNABLE_ROLES = frozenset({ROLE_STAFF})\n\n# Roles that may issue invites at all.\nINVITER_ROLES = frozenset(\n    {\"SUPER_ADMIN\"} | set(settings.TENANT_ADMIN_ROLES) | set(settings.DEPT_ADMIN_ROLES)\n)\n\n# Human-readable role labels for the team-management UI.\nROLE_LABELS = {\n    \"SUPER_ADMIN\": \"Global Administrator\",\n    \"TENANT_ADMIN\": \"Safety Manager (Tenant Admin)\",\n    \"AIRLINE_ADMIN\": \"Safety Manager (Tenant Admin)\",\n    \"DEPT_ADMIN\": \"Department Admin (HOD)\",\n    \"SAFETY_OFFICER\": \"Safety Officer\",\n    \"STAFF\": \"Staff / Employee\",\n    \"USER\": \"Staff / Employee\",\n    \"CAAN_SMD\": \"State Safety Regulator\",\n}\n\n\ndef department_label(code_or_label: str) -> str:\n    \"\"\"Return the canonical display label for a department code or label.\"\"\"\n    return DEPARTMENT_LABELS.get((code_or_label or \"\").strip(), code_or_label or \"\")\n\n\ndef department_to_code(value: Optional[str]) -> str:\n    \"\"\"Normalize a department code or display label to its canonical code.\"\"\"\n    v = (value or \"\").strip().lower()\n    for code, label in DEPARTMENT_LABELS.items():\n        if v == code.lower() or v == label.lower():\n            return code\n    return v or \"\"\n\n\ndef _invite_code_taken(db: Any, code: str) -> bool:\n    \"\"\"True when the code is already used by a tenant's team invite or an\n    admin-issued department-scoped invite.\"\"\"\n    try:\n        docs = (\n            db.collection(settings.FIREBASE_COLLECTION_TENANTS)\n            .where(\"team_invite_code\", \"==\", code)\n            .limit(1)\n            .get()\n        )\n        if len(docs) > 0:\n            return True\n        snap = db.collection(\"invites\").document(code).get()\n        return snap is not None and getattr(snap, \"exists\", False)\n    except Exception as e:\n        logger.warning(f\"Invite-code uniqueness check failed: {e}\")\n        return False\n\n\ndef generate_invite_code(db: Any) -> str:\n    \"\"\"Return a unique 6-character department-scoped invite code.\"\"\"\n    for _ in range(25):\n        code = \"\".join(secrets.choice(INVITE_ALPHABET) for _ in range(INVITE_CODE_LENGTH))\n        if not _invite_code_taken(db, code):\n            return code\n    raise RuntimeError(\"Unable to generate a unique invite code\")\n\n\ndef resolve_invite(db: Any, code: Optional[str]) -> Optional[Dict[str, Any]]:\n    \"\"\"Look up a department-scoped invite document by its code.\n\n    Returns None when the code is unknown. Callers decide whether to fall back\n    to the legacy tenant-level team invite code.\n    \"\"\"\n    if not code or not code.strip():\n        return None\n    try:\n        snap = db.collection(\"invites\").document(code.strip().upper()).get()\n    except Exception as e:\n        logger.warning(f\"Invite lookup failed for code {code}: {e}\")\n        return None\n    if snap is None or not getattr(snap, \"exists\", False):\n        return None\n    return snap.to_dict() or {}\n\n\ndef create_invite(\n    *,\n    caller: Dict[str, Any],\n    department: str,\n    role: str,\n    request=None,\n) -> Dict[str, Any]:\n    \"\"\"Issue a department-scoped invite under the caller's tenant.\n\n    RBAC (enforced strictly):\n      - TENANT_ADMIN / AIRLINE_ADMIN / SUPER_ADMIN: any applicable department,\n        assignable roles DEPT_ADMIN / SAFETY_OFFICER / STAFF.\n      - DEPT_ADMIN: target department MUST equal the caller's department and\n        the role MUST be STAFF (no cross-department invites, no escalation).\n    \"\"\"\n    db = get_db()\n    tid = caller.get(\"tenant_id\")\n    if not tid:\n        raise PermissionError(\"An authenticated tenant is required to issue invites\")\n\n    caller_role = caller.get(\"role\")\n    if caller_role not in INVITER_ROLES:\n        raise PermissionError(\"You do not have permission to issue team invites\")\n\n    role = (role or \"\").strip().upper()\n    dept_code = department_to_code(department)\n    dept_label = department_label(dept_code)\n\n    tenant_ref = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tid)\n    try:\n        tenant_snap = tenant_ref.get()\n    except Exception as e:\n        logger.warning(f\"Tenant lookup failed for invite ({tid}): {e}\")\n        raise RuntimeError(\"Tenant storage unavailable\")\n    if tenant_snap is None or not getattr(tenant_snap, \"exists\", False):\n        raise LookupError(f\"Unknown tenant: {tid}\")\n    tenant_doc = tenant_snap.to_dict() or {}\n    applicable = tenant_doc.get(\"applicable_departments\") or []\n\n    if caller_role in (\"SUPER_ADMIN\",) or caller_role in settings.TENANT_ADMIN_ROLES:\n        if dept_code not in applicable:\n            raise ValueError(\n                f\"Department '{dept_code}' is not applicable to tenant {tid}. \"\n                f\"Allowed: {', '.join(applicable) or 'none'}\"\n            )\n        if role not in TENANT_ADMIN_ASSIGNABLE_ROLES:\n            raise PermissionError(\n                f\"Role '{role}' cannot be assigned by a Safety Manager. \"\n                f\"Assignable: {', '.join(sorted(TENANT_ADMIN_ASSIGNABLE_ROLES))}\"\n            )\n    elif caller_role in settings.DEPT_ADMIN_ROLES:\n        caller_code = department_to_code(caller.get(\"department\"))\n        if caller_code != dept_code:\n            raise PermissionError(\n                \"Department Admins may only invite members into their own department\"\n            )\n        if role not in DEPT_ADMIN_ASSIGNABLE_ROLES:\n            raise PermissionError(\n                f\"Role '{role}' cannot be assigned by a Department Admin. \"\n                f\"Assignable: {', '.join(sorted(DEPT_ADMIN_ASSIGNABLE_ROLES))}\"\n            )\n    else:  # pragma: no cover - guarded by INVITER_ROLES above\n        raise PermissionError(\"You do not have permission to issue team invites\")\n\n    if dept_code not in applicable:\n        raise ValueError(\n            f\"Department '{dept_code}' is not applicable to tenant {tid}. \"\n            f\"Allowed: {', '.join(applicable) or 'none'}\"\n        )\n\n    code = generate_invite_code(db)\n    now = datetime.now(timezone.utc)\n    doc = {\n        \"code\": code,\n        \"tenant_id\": tid,\n        \"department\": dept_code,\n        \"department_label\": dept_label,\n        \"role\": role,\n        \"created_by\": caller.get(\"uid\") or caller.get(\"email\"),\n        \"created_by_email\": caller.get(\"email\"),\n        \"created_at\": now,\n        \"status\": \"ACTIVE\",\n    }\n    try:\n        db.collection(\"invites\").document(code).set(doc)\n    except Exception as e:\n        logger.error(f\"Failed to persist invite {code} for tenant {tid}: {e}\")\n        raise RuntimeError(\"Failed to persist the invite\")\n\n    ip, request_id = request_context(request)\n    log_audit(\n        action=\"TEAM_INVITE_CREATED\",\n        user=caller.get(\"email\"),\n        tenant_id=tid,\n        target_type=\"invite\",\n        target_id=code,\n        ip=ip,\n        request_id=request_id,\n        metadata={\"department\": dept_code, \"role\": role},\n    )\n\n    logger.info(\n        f\"Team invite issued for tenant {tid}: code={code} dept={dept_code} \"\n        f\"role={role} by={caller.get('email')}\"\n    )\n\n    return {\n        \"code\": code,\n        \"tenant_id\": tid,\n        \"department\": dept_code,\n        \"department_label\": dept_label,\n        \"role\": role,\n        \"status\": \"ACTIVE\",\n        \"created_at\": now,\n    }\n\n\ndef list_invites(\n    *,\n    caller: Dict[str, Any],\n) -> List[Dict[str, Any]]:\n    \"\"\"List department-scoped invites for the caller's tenant.\n\n    DEPT_ADMIN sees only their own department's invites; tenant admins and\n    SUPER_ADMIN see every invite for the tenant.\n    \"\"\"\n    tid = caller.get(\"tenant_id\")\n    if not tid:\n        raise PermissionError(\"An authenticated tenant is required to list invites\")\n    db = get_db()\n    try:\n        snapshots = (\n            db.collection(\"invites\").where(\"tenant_id\", \"==\", tid).get()\n        )\n    except Exception as e:\n        logger.warning(f\"Failed to list invites for tenant {tid}: {e}\")\n        raise RuntimeError(\"Failed to list invites\")\n\n    caller_code = None\n    if caller.get(\"role\") in settings.DEPT_ADMIN_ROLES:\n        caller_code = department_to_code(caller.get(\"department\"))\n\n    rows = []\n    for snap in snapshots:\n        data = snap.to_dict() or {}\n        dept = data.get(\"department\") or department_to_code(data.get(\"department_label\"))\n        if caller_code and department_to_code(dept) != caller_code:\n            continue\n        rows.append(\n            {\n                \"code\": data.get(\"code\") or snap.id,\n                \"tenant_id\": data.get(\"tenant_id\"),\n                \"department\": dept,\n                \"department_label\": department_label(dept),\n                \"role\": data.get(\"role\"),\n                \"role_label\": ROLE_LABELS.get(data.get(\"role\"), data.get(\"role\")),\n                \"created_by\": data.get(\"created_by_email\") or data.get(\"created_by\"),\n                \"status\": data.get(\"status\", \"ACTIVE\"),\n                \"created_at\": (\n                    data.get(\"created_at\").isoformat()\n                    if hasattr(data.get(\"created_at\"), \"isoformat\")\n                    else data.get(\"created_at\")\n                ),\n            }\n        )\n    rows.sort(key=lambda r: (r[\"created_at\"] or \"\", r[\"code\"] or \"\"))\n    return rows"
}
```

**Output:**
```
Wrote file successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 43.5s)

_Thinking:_

Now update `tenant_registration.py`:
1. `join_team` — resolve dept-scoped invite first, then bind department + role.
2. `verify_invite` — also accept dept-scoped invites.

Let me update `verify_invite` first.

Now extend the join/verify flows in tenant_registration.py to consume

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\services\\tenant_registration.py",
  "newString": "def verify_invite(db: Any, code: Optional[str]) -> Dict[str, Any]:\n    \"\"\"Real-time invite-code verification for /join.html.\n\n    Resolves the tenant by invite code and confirms it is active. Accepts both\n    legacy tenant-level team invite codes and admin-issued department-scoped\n    invites (returning the assigned department + role). Returns a minimal\n    public payload (no internal fields). Raises:\n      ValueError  -> caller supplied no / blank code\n      LookupError -> code unknown, or tenant is inactive/expired\n    \"\"\"\n    if not code or not code.strip():\n        raise ValueError(\"An invite code is required\")\n\n    from app.services.invites import resolve_invite, department_label\n\n    raw = code.strip()\n    invite = resolve_invite(db, raw)\n    if invite:\n        tid = invite.get(\"tenant_id\")\n        if not tid:\n            raise LookupError(\"Invalid or expired invite code\")\n        tid, tenant_doc = resolve_tenant(db, None, tid)\n        active = tenant_doc.get(\"active\")\n        status = str(tenant_doc.get(\"status\") or \"\").lower()\n        if active is False or status == \"inactive\":\n            raise LookupError(\"Invalid or expired invite code\")\n        dept = invite.get(\"department\")\n        return {\n            \"valid\": True,\n            \"organization_name\": tenant_doc.get(\"name\") or tid,\n            \"tenant_id\": tid,\n            \"category\": tenant_doc.get(\"tenant_type\") or tenant_doc.get(\"classification\"),\n            \"department\": dept,\n            \"department_label\": department_label(dept),\n            \"role\": invite.get(\"role\", settings.ROLE_DEFAULT),\n        }\n\n    tid, tenant_doc = resolve_tenant(db, raw, None)\n\n    active = tenant_doc.get(\"active\")\n    status = str(tenant_doc.get(\"status\") or \"\").lower()\n    if active is False or status == \"inactive\":\n        raise LookupError(\"Invalid or expired invite code\")\n\n    return {\n        \"valid\": True,\n        \"organization_name\": tenant_doc.get(\"name\") or tid,\n        \"tenant_id\": tid,\n        \"category\": tenant_doc.get(\"tenant_type\") or tenant_doc.get(\"classification\"),\n    }",
  "oldString": "def verify_invite(db: Any, code: Optional[str]) -> Dict[str, Any]:\n    \"\"\"Real-time invite-code verification for /join.html.\n\n    Resolves the tenant by invite code and confirms it is active. Returns a\n    minimal public payload (no internal fields). Raises:\n      ValueError  -> caller supplied no / blank code\n      LookupError -> code unknown, or tenant is inactive/expired\n    \"\"\"\n    if not code or not code.strip():\n        raise ValueError(\"An invite code is required\")\n    tid, tenant_doc = resolve_tenant(db, code.strip(), None)\n\n    active = tenant_doc.get(\"active\")\n    status = str(tenant_doc.get(\"status\") or \"\").lower()\n    if active is False or status == \"inactive\":\n        raise LookupError(\"Invalid or expired invite code\")\n\n    return {\n        \"valid\": True,\n        \"organization_name\": tenant_doc.get(\"name\") or tid,\n        \"tenant_id\": tid,\n        \"category\": tenant_doc.get(\"tenant_type\") or tenant_doc.get(\"classification\"),\n    }"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 24.7s)

Now update `join_team` to bind department + role from the invite document

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\services\\tenant_registration.py",
  "newString": "_validate_password(password)\n    validate_corporate_email(email)\n\n    db = get_db()\n    auth = get_auth()\n    now = datetime.now(timezone.utc)\n\n    # Admin-issued department-scoped invites bind BOTH the department and the\n    # role directly from the invite document. Legacy tenant-level invite codes\n    # fall back to the previous behavior (invitee self-selects the department\n    # and is provisioned with the least-privilege role).\n    from app.services.invites import resolve_invite, department_label\n\n    assigned_role = settings.ROLE_DEFAULT\n    department_code: Optional[str] = None\n\n    if invite_code and invite_code.strip():\n        invite = resolve_invite(db, invite_code.strip())\n        if invite:\n            if str(invite.get(\"status\") or \"ACTIVE\").strip().upper() != \"ACTIVE\":\n                raise LookupError(\"Invalid or expired invite code\")\n            tid = invite.get(\"tenant_id\")\n            if not tid:\n                raise LookupError(\"Invalid or expired invite code\")\n            try:\n                tid, tenant_doc = resolve_tenant(db, None, tid)\n            except LookupError:\n                raise\n            department_code = invite.get(\"department\") or department.strip()\n            assigned_role = str(invite.get(\"role\") or settings.ROLE_DEFAULT).upper()\n\n    if department_code is None:\n        try:\n            tid, tenant_doc = resolve_tenant(db, invite_code, tenant_id)\n        except LookupError:\n            raise\n        except Exception as e:\n            if isinstance(e, ValueError):\n                raise\n            raise LookupError(str(e))\n        department_code = department.strip()\n\n    code = department_code\n    allowed = tenant_doc.get(\"applicable_departments\") or []\n    if code not in allowed:\n        raise ValueError(\n            f\"Department '{code}' is not applicable to tenant {tid}. \"\n            f\"Allowed: {', '.join(allowed) or 'none'}\"\n        )\n\n    label = DEPARTMENT_LABELS.get(code, code)\n\n    user = _create_user(\n        auth,\n        email=email,\n        password=password,\n        display_name=full_name,\n    )\n    auth.set_custom_user_claims(\n        user.uid,\n        {\"role\": assigned_role, \"tenant_id\": tid, \"department\": label},\n    )\n\n    user_doc = {\n        \"uid\": user.uid,\n        \"email\": email,\n        \"display_name\": full_name,\n        \"role\": assigned_role,\n        \"tenant_id\": tid,\n        \"department\": label,\n        \"status\": \"ACTIVE\",\n        \"created_at\": now,\n        \"updated_at\": now,\n    }\n    if operational_role:\n        user_doc[\"operational_role\"] = operational_role.strip()[:100]\n    upsert_user_doc(user.uid, user_doc)\n\n    ip, request_id = request_context(request)\n    log_audit(\n        action=\"TEAM_MEMBER_JOINED\",\n        user=email,\n        tenant_id=tid,\n        target_type=\"tenant\",\n        target_id=tid,\n        ip=ip,\n        request_id=request_id,\n        metadata={\n            \"department\": code,\n            \"department_label\": label,\n            \"role\": assigned_role,\n            \"invite_scoped\": department_code is not None,\n        },\n    )\n\n    logger.info(\n        f\"Team member joined tenant {tid}: {email} -> {label} ({assigned_role})\"\n    )\n\n    return {\n        \"tenant_id\": tid,\n        \"tenant_name\": tenant_doc.get(\"name\") or tid,\n        \"classification\": tenant_doc.get(\"tenant_type\") or tenant_doc.get(\"classification\"),\n        \"department\": code,\n        \"department_label\": label,\n        \"role\": assigned_role,\n        \"admin_email\": email,\n        \"created_at\": now,\n    }",
  "oldString": "_validate_password(password)\n    validate_corporate_email(email)\n\n    db = get_db()\n    auth = get_auth()\n    now = datetime.now(timezone.utc)\n\n    try:\n        tid, tenant_doc = resolve_tenant(db, invite_code, tenant_id)\n    except LookupError:\n        raise\n    except Exception as e:\n        if isinstance(e, ValueError):\n            raise\n        raise LookupError(str(e))\n\n    code = department.strip()\n    allowed = tenant_doc.get(\"applicable_departments\") or []\n    if code not in allowed:\n        raise ValueError(\n            f\"Department '{code}' is not applicable to tenant {tid}. \"\n            f\"Allowed: {', '.join(allowed) or 'none'}\"\n        )\n\n    label = DEPARTMENT_LABELS.get(code, code)\n\n    user = _create_user(\n        auth,\n        email=email,\n        password=password,\n        display_name=full_name,\n    )\n    auth.set_custom_user_claims(\n        user.uid,\n        {\"role\": \"USER\", \"tenant_id\": tid, \"department\": label},\n    )\n\n    user_doc = {\n        \"uid\": user.uid,\n        \"email\": email,\n        \"display_name\": full_name,\n        \"role\": \"USER\",\n        \"tenant_id\": tid,\n        \"department\": label,\n        \"created_at\": now,\n        \"updated_at\": now,\n    }\n    if operational_role:\n        user_doc[\"operational_role\"] = operational_role.strip()[:100]\n    upsert_user_doc(user.uid, user_doc)\n\n    ip, request_id = request_context(request)\n    log_audit(\n        action=\"TEAM_MEMBER_JOINED\",\n        user=email,\n        tenant_id=tid,\n        target_type=\"tenant\",\n        target_id=tid,\n        ip=ip,\n        request_id=request_id,\n        metadata={\"department\": code, \"department_label\": label},\n    )\n\n    logger.info(f\"Team member joined tenant {tid}: {email} -> {label}\")\n\n    return {\n        \"tenant_id\": tid,\n        \"tenant_name\": tenant_doc.get(\"name\") or tid,\n        \"classification\": tenant_doc.get(\"tenant_type\") or tenant_doc.get(\"classification\"),\n        \"department\": code,\n        \"department_label\": label,\n        \"admin_email\": email,\n        \"created_at\": now,\n    }"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 29.9s)

_Thinking:_

Now add the invite endpoint, invites listing, and `/join` alias to routes/auth.py. Let me add:

1. Import `create_invite`, `list_invites` from invites service.
2. Import `get_current_user` from middleware.
3. `InviteRequest` model.
4. `POST /invite` endpoint with rate limit.
5. `GET /invites` endpoint.
6. Add `/join` alias by stacking decorators on `join_team_endpoint`.

Let me add the rate limit bucket first.

Add the rate-limit bucket for invite issuance

**Tool: read**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\middleware\\rate_limit.py",
  "limit": 40,
  "offset": 40
}
```

**Output:**
```
<path>C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\middleware\rate_limit.py</path>
<type>file</type>
<content>
40:             _redis_client = None
41:     return _redis_client
42: 
43: 
44: RATE_LIMITS = {
45:     "vsr_submit":    (50,  86400),   # 50/day  (beta)
46:     "survey_submit": (settings.SURVEY_RATE_LIMIT, 86400),   # per-day, configurable (SURVEY_RATE_LIMIT)
47:     "mor_submit":    (20,  86400),   # 20/day  (beta)
48:     "dashboard":     (500, 3600),    # 500/hour (beta)
49:     "auth_attempts": (200, 3600),    # 200/hour (beta; safety net for shared login attempts)
50:     "register_tenant": (5, 3600),    # 5/hour per IP (self-service tenant registration)
51:     "join_team":     (30, 3600),     # 30/hour per IP (team-member onboarding)
52:     "register":      (10, 3600),     # 10/hour per IP (legacy /api/v1/auth/register)
53:     "copilot":       (120, 3600),    # 120/hour (beta; AI chat assistant per tenant)
54: }
55: 
56: # Strict sliding-window limits enforced with Redis sorted sets (each request is
57: # logged with its timestamp and the window slides with real time, so a burst at
58: # the end of one hour can never leak into the next). These override the
59: # fixed-window buckets above for the same limit types.
60: #
61: #   login_failures: 5 failed login attempts / 15 minutes / IP
62: #   register_tenant: 5 registration attempts / hour / IP
63: #   verify_invite: 10 invite-verification attempts / hour / IP
64: #   copilot_guest: 10 guest copilot queries / minute / IP (primary protection
65: #                  for the public chat endpoint in privacy modes where App
66: #                  Check tokens are unavailable)
67: SLIDING_WINDOW_LIMITS = {
68:     "login_failures": (5, 900),
69:     "register_tenant": (5, 3600),
70:     "verify_invite": (10, 3600),
71:     "copilot_guest": (10, 60),
72: }
73: 
74: 
75: def _now_ms() -> int:
76:     return int(time.time() * 1000)
77: 
78: 
79: def _sliding_key(limit_type: str, ip: str) -> str:

(Showing lines 40-79 of 374. Use offset=80 to continue.)
</content>
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 12.0s)

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\middleware\\rate_limit.py",
  "newString": "\"join_team\":     (30, 3600),     # 30/hour per IP (team-member onboarding)\n    \"invite\":        (20, 3600),     # 20/hour per IP (admin invite issuance)\n    \"register\":      (10, 3600),     # 10/hour per IP (legacy /api/v1/auth/register)",
  "oldString": "\"join_team\":     (30, 3600),     # 30/hour per IP (team-member onboarding)\n    \"register\":      (10, 3600),     # 10/hour per IP (legacy /api/v1/auth/register)"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 12.2s)

_Thinking:_

Now add the invite endpoints to routes/auth.py. Let me update the imports and add the endpoints. I'll add after the join-team endpoint (before tenant-lookup) or after register-tenant. I'll add the InviteRequest model near the other models and the endpoints after the register endpoint area. Let me place them after the `verify_invite_endpoint` / before `JoinTeamRequest`. Actually cleanest to add the invite endpoints near the join-team section.

Let me edit imports first.

Now wire the invite endpoints into routes/auth.py

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\routes\\auth.py",
  "newString": "from app.middleware.auth import resolve_user_context, get_current_user\nfrom app.middleware.app_check import verify_app_check\nfrom app.models.tenant_profile import OperationalScope\nfrom app.services.audit_service import log_audit, request_context\nfrom app.services.users import upsert_user_doc\nfrom app.services import login_service\nfrom app.services.invites import create_invite, list_invites\nfrom app.services.gmail_dispatcher import send_registration_acknowledgment",
  "oldString": "from app.middleware.auth import resolve_user_context\nfrom app.middleware.app_check import verify_app_check\nfrom app.models.tenant_profile import OperationalScope\nfrom app.services.audit_service import log_audit, request_context\nfrom app.services.users import upsert_user_doc\nfrom app.services import login_service\nfrom app.services.gmail_dispatcher import send_registration_acknowledgment"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 14.5s)

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\routes\\auth.py",
  "newString": "class JoinTeamRequest(BaseModel):\n    invite_code: Optional[str] = None\n    tenant_id: Optional[str] = None\n    full_name: str = Field(..., min_length=1)\n    email: EmailStr\n    password: str\n    confirm_password: str\n    department: str = Field(..., min_length=1)\n    operational_role: Optional[str] = Field(None, max_length=100)\n\n\nclass InviteRequest(BaseModel):\n    department: str = Field(..., min_length=1, description=\"Target department code or label\")\n    role: str = Field(default=\"STAFF\", max_length=50, description=\"Role to assign on join\")\n\n\n@router.post(\"/invite\")\n@rate_limit(\"invite\")\nasync def invite_endpoint(\n    request: Request,\n    body: InviteRequest,\n    user: dict = Depends(get_current_user),\n):\n    \"\"\"Issue a department-scoped team invite (TENANT_ADMIN / DEPT_ADMIN).\n\n    Role-aware enforcement:\n      - TENANT_ADMIN / AIRLINE_ADMIN / SUPER_ADMIN: invite into any applicable\n        department with DEPT_ADMIN / SAFETY_OFFICER / STAFF.\n      - DEPT_ADMIN: target department must equal the caller's department and\n        only the STAFF role may be assigned (403 otherwise).\n    \"\"\"\n    try:\n        result = create_invite(\n            caller=user,\n            department=body.department,\n            role=body.role,\n            request=request,\n        )\n    except PermissionError as e:\n        raise HTTPException(status_code=403, detail=str(e))\n    except ValueError as e:\n        raise HTTPException(status_code=422, detail=str(e))\n    except LookupError as e:\n        raise HTTPException(status_code=404, detail=str(e))\n    except RuntimeError as e:\n        raise HTTPException(status_code=500, detail=str(e))\n    return {\"success\": True, **result}\n\n\n@router.get(\"/invites\")\nasync def invite_list_endpoint(\n    user: dict = Depends(get_current_user),\n):\n    \"\"\"List department-scoped invites for the caller's tenant.\n\n    TENANT_ADMIN / SUPER_ADMIN see every invite for the tenant; DEPT_ADMIN sees\n    only their own department's invites.\n    \"\"\"\n    try:\n        rows = list_invites(caller=user)\n    except PermissionError as e:\n        raise HTTPException(status_code=403, detail=str(e))\n    except RuntimeError as e:\n        raise HTTPException(status_code=500, detail=str(e))\n    return {\"success\": True, \"invites\": rows}\n\n\n@router.post(\"/join-team\")\n@router.post(\"/join\")\n@rate_limit(\"join_team\")\nasync def join_team_endpoint(\n    request: Request,\n    body: JoinTeamRequest,\n    _app_check: None = Depends(verify_app_check),\n):\n    \"\"\"Self-register a department postholder under an existing tenant.\n\n    When the invite code is an admin-issued department-scoped invite the\n    assigned department and role are read directly from the invite document.\n    Legacy tenant-level team invite codes keep the previous behavior (invitee\n    self-selects the department and is provisioned with the least-privilege\n    role). Available at both /api/v1/auth/join-team and /api/v1/auth/join.\n    \"\"\"",
  "oldString": "class JoinTeamRequest(BaseModel):\n    invite_code: Optional[str] = None\n    tenant_id: Optional[str] = None\n    full_name: str = Field(..., min_length=1)\n    email: EmailStr\n    password: str\n    confirm_password: str\n    department: str = Field(..., min_length=1)\n    operational_role: Optional[str] = Field(None, max_length=100)\n\n\n@router.post(\"/join-team\")\n@rate_limit(\"join_team\")\nasync def join_team_endpoint(\n    request: Request,\n    body: JoinTeamRequest,\n    _app_check: None = Depends(verify_app_check),\n):\n    \"\"\"Self-register a department postholder under an existing tenant.\"\"\""
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 48.9s)

_Thinking:_

Wait, there's an issue: the `@router.post("/invite")` and `@router.get("/invites")` endpoints are added with `Depends(get_current_user)`. But `get_current_user` uses `Security(HTTPBearer())`. In the TestClient, tests will override the dependency, so fine.

However, the invite endpoint is mounted at both /api/v1/auth and /api/auth prefixes. Good.

Now let me verify there are no issues with the stacked decorators: `@router.post("/join-team")` then `@router.post("/join")` then `@rate_limit("join_team")` then async def. Decorator order: the route decorators stack correctly. Both register the same function.

Now, one concern: rate limit decorator wraps the function with `@rate_limit("join_team")` — when both route decorators reference the wrapped function, both endpoints get rate limiting. Good.

Now, `get_current_user` import: auth.py previously imported only resolve_user_context. Now importing get_current_user from app.middleware.auth. That's fine.

But wait — there's a subtle issue. The test `_patch` in test_auth.py monkeypatches `app.routes.auth.get_db` etc. The invite endpoint calls `create_invite` which calls `get_db` from `app.firebase` — monkeypatched. Good. `list_invites` also uses get_db. Good.

Now let me run the existing auth tests to ensure nothing broke before proceeding to frontend. But first, let me double check there could be circular imports: `invites.py` imports from `tenant_registration.py` (DEPARTMENT_LABELS, INVITE_ALPHABET, INVITE_CODE_LENGTH). And `tenant_registration.py` imports from `app.services.invites` inside functions (lazy import). Good, no cycle at module load. `auth.py` imports `create_invite, list_invites` from invites at module load; invites imports tenant_registration at module load; tenant_registration doesn't import invites at module load (lazy). Good.

Now run the existing tests quickly to confirm nothing broke. Let me run the auth tests.

Let me run the existing auth tests to confirm nothing broke before moving

**Tool: bash**

**Input:**
```json
{
  "command": "python -m pytest tests/test_auth.py tests/test_self_service_registration.py tests/test_anti_spam_guardrails.py -q 2>&1 | Select-Object -Last 6",
  "timeout": 300000,
  "workdir": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend"
}
```

**Output:**
```
..\..\..\AppData\Local\Programs\Python\Python313\Lib\site-packages\reportlab\lib\rl_safe_eval.py:11
  C:\Users\CEO-LAPTOP\AppData\Local\Programs\Python\Python313\Lib\site-packages\reportlab\lib\rl_safe_eval.py:11: DeprecationWarning: ast.NameConstant is deprecated and will be removed in Python 3.14; use ast.Constant instead
    haveNameConstant = hasattr(ast,'NameConstant')

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
66 passed, 1 warning in 9.61s

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 20.9s)

_Thinking:_

Existing auth tests still pass (66). Now write the new RBAC tests. Let me model the test file on test_auth.py's fake DB pattern, but extend it to support:
- `invites` collection with document set/get and where queries.
- users collection with where on tenant_id for list_tenant_users.
- get_current_user dependency override.
- auth create_user/set_custom_user_claims.

I also need to monkeypatch `app.middleware.auth.get_db` for tenant suspension checks in get_current_user? Actually tests override get_current_user via dependency_overrides, so the real get_current_user never runs. Good.

But careful: `app.dependency_overrides[get_current_user]` — get_current_user imported into auth.py is the same object. Overriding by that function object works.

Let me check the auth endpoints I'll test:
1. POST /api/v1/auth/invite (with overridden get_current_user).
2. POST /api/v1/auth/join (alias) + join-team.

For the join tests with a dept-scoped invite: seed tenant + create an invite doc in `invites` collection with role STAFF/DEPT_ADMIN, then POST /join-team with that invite_code and some department in the body (should be overridden by invite). Check claims role + department label + user doc.

Also test DEPT_ADMIN scoping of GET /api/v1/tenants/{tenantId}/users? The spec's test list doesn't explicitly require it but it's part of frontend requirement 3. I'll add a test for the users listing filter too — good value.

Let me design the fake DB. I'll write a comprehensive fake:

```python
class _Doc:
    def __init__(self, data, exists=True, id=None):
        self._data = data or {}
        self.exists = exists
        self.id = id
    def get(self, field, default=None):
        if field is None: return self._data
        return self._data.get(field, default)
    def to_dict(self): return self._data

class _CollQuery:
    def __init__(self, db, name):
        self._db = db
        self._name = name
        self._filters = []
    def where(self, field, op, value):
        self._filters.append((field, op, value)); return self
    def limit(self, n): return self
    def get(self):
        rows = []
        for key, data in self._db.colls.get(self._name, {}).items():
            doc = dict(data or {})
            doc.setdefault("id", key)
            ok = True
            for field, op, value in self._filters:
                if op == "==" and doc.get(field) != value:
                    ok = False
            if ok: rows.append(_Doc(doc, exists=True, id=key))
        return rows
    def stream(self): return self.get()

class _CollRef:
    def __init__(self, db, name, key):
        self._db = db; self._name = name; self._key = key
    def get(self):
        data = self._db.colls.get(self._name, {}).get(self._key)
        if data is None: return _Doc(None, exists=False, id=self._key)
        return _Doc(dict(data), exists=True, id=self._key)
    def set(self, data, merge=False):
        store = self._db.colls.setdefault(self._name, {})
        if merge and self._key in store:
            merged = dict(store[self._key]); merged.update(dict(data)); data = merged
        store[self._key] = dict(data)
    def update(self, data):
        store = self._db.colls.setdefault(self._name, {})
        merged = dict(store.get(self._key) or {}); merged.update(dict(data)); store[self._key] = merged

class _Coll:
    def __init__(self, db, name):
        self._db = db; self._name = name
    def document(self, key): return _CollRef(self._db, self._name, key)
    def where(self, field, op, value): return _CollQuery(self._db, self._name).where(field, op, value)

class _FakeDB:
    def __init__(self):
        self.colls = {"tenants": {}, "users": {}, "invites": {}, "audit_logs": {}}
        self.audit = self.colls["audit_logs"]
    def collection(self, name):
        if name not in self.colls: raise AssertionError(f"unexpected collection {name}")
        return _Coll(self, name)
```

Wait, but test_auth.py used `db.tenants` attribute-style dict. For my new test file, I'll use the colls approach with helpers `db.tenants` proxies. Simpler: keep `.tenants`, `.users`, `.invites`, `.audit` attributes AND collection() that maps. Let me do:

```python
class _FakeDB:
    def __init__(self):
        self.tenants = {}
        self.users = {}
        self.invites = {}
        self.audit = []
    def _store(self, name):
        return {"tenants": self.tenants, "users": self.users, "invites": self.invites, "audit_logs": self.audit}[name]
    def collection(self, name):
        return _Coll(self, name)
```

And _Coll query iterates `self._db._store(name).items()`.

For audit_logs collection, the service does `db.collection("audit_logs").add(entry)`. So _Coll needs an `add` method. Let me add `add(self, data)` appending to the list.

Let me handle: for "audit_logs", _CollQuery.get() iterates a list not a dict. Let me make `_store` return the list for audit_logs and handle both dict and list in query. Simpler: make audit a dict keyed by incrementing id.

Actually let me look at how audit_service.log_audit writes. Let me check audit_service to be safe — it might use `.add()`.

Existing tests pass. Let me check the audit service write pattern before writing the RBAC tests

**Tool: read**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\services\\audit_service.py"
}
```

**Output:**
```
<path>C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\services\audit_service.py</path>
<type>file</type>
<content>
1: from datetime import datetime, timezone
2: from typing import Any, Dict, Optional, Tuple
3: from loguru import logger
4: 
5: from app.firebase import get_db
6: 
7: AUDIT_COLLECTION = "audit_logs"
8: 
9: 
10: def request_context(request) -> Tuple[Optional[str], Optional[str]]:
11:     """Return (client_ip, request_id) from a FastAPI Request."""
12:     if request is None:
13:         return None, None
14:     client = getattr(request, "client", None)
15:     ip = client.host if client else None
16:     request_id = getattr(request.state, "request_id", None)
17:     if not request_id:
18:         request_id = request.headers.get("X-Request-ID")
19:     return ip, request_id or None
20: 
21: 
22: def log_audit(
23:     *,
24:     action: str,
25:     user: Optional[str] = None,
26:     tenant_id: Optional[str] = None,
27:     target_type: Optional[str] = None,
28:     target_id: Optional[str] = None,
29:     ip: Optional[str] = None,
30:     request_id: Optional[str] = None,
31:     metadata: Optional[Dict[str, Any]] = None,
32: ) -> None:
33:     """Append an entry to the Firestore `audit_logs` collection.
34: 
35:     Failures to persist an audit entry must never break the business request,
36:     so the write is best-effort and only logged as a warning.
37:     """
38:     try:
39:         db = get_db()
40:         entry = {
41:             "action": action,
42:             "user": user,
43:             "tenant_id": tenant_id,
44:             "target_type": target_type,
45:             "target_id": target_id,
46:             "ip": ip,
47:             "request_id": request_id,
48:             "metadata": metadata or {},
49:             "timestamp": datetime.now(timezone.utc),
50:         }
51:         db.collection(AUDIT_COLLECTION).add(entry)
52:     except Exception as e:
53:         logger.warning(f"Audit log write failed for action={action}: {e}")

(End of file - total 53 lines)
</content>
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 51.1s)

_Thinking:_

Good — audit uses `.add(entry)`. Now write the RBAC test file. I'll create a fake DB that handles tenants, users, invites, audit_logs collections with `document`, `where`, `limit`, `get`, `set`, `add`.

Now let me write test_dept_admin_rbac.py.

Tests to cover:
1. TENANT_ADMIN can invite DEPT_ADMIN to any department → 200, invite doc persisted with role DEPT_ADMIN + department.
2. TENANT_ADMIN can invite STAFF (any dept) → 200.
3. DEPT_ADMIN can invite STAFF to their own department → 200.
4. DEPT_ADMIN inviting to another department → 403.
5. DEPT_ADMIN attempting to assign TENANT_ADMIN → 403. And DEPT_ADMIN role → 403.
6. Registration with department-scoped invite binds correct department + role (STAFF invite → role STAFF, department label; DEPT_ADMIN invite → role DEPT_ADMIN).
7. Legacy code path (tenant team_invite_code, no dept-scoped invite) → role USER (fallback) — existing tests cover, but add one to confirm fallback still works with the new code.
8. STAFF (USER role) cannot invite → 403.
9. Legacy alias `/api/auth/invite` also works (legacy mount) — optional. And `/api/v1/auth/join` alias works.
10. DEPT_ADMIN users listing filtered (GET /api/v1/tenants/{tid}/users) — DEPT_ADMIN sees only their dept members; TENANT_ADMIN sees all.
11. verify-invite returns department/role for scoped invites.

I need to override get_current_user for invite + invites + users endpoints. For join endpoints, they're public (no auth), so no override needed.

The override: `app.dependency_overrides[get_current_user] = lambda: caller`. And cleanup.

Let me now also confirm: the invite endpoint uses `user: dict = Depends(get_current_user)`. get_current_user is imported into auth.py from app.middleware.auth. Overriding `app.middleware.auth.get_current_user` function object — since it's the same object, dependency_overrides key matches. Tests elsewhere do `app.dependency_overrides[get_current_user] = lambda: ...` after importing from app.middleware.auth. Good.

For the users endpoint in tenants.py, it also uses get_current_user imported from app.middleware.auth. Same object. Good.

Let me write the test file now.

One thing about `create_invite`: it calls `department_to_code(department)`. For a request with department "Flight Operations" it returns "flight_ops". For "flight_ops" returns "flight_ops". Then validates `dept_code in applicable` (applicable are codes). Good.

For DEPT_ADMIN caller, `caller.get("department")` — I'll set to the label "Flight Operations" (as stored in claims for dept-admin via join). department_to_code converts to "flight_ops". The target dept code must match. Good.

For the join with scoped invite: `resolve_invite` returns doc with `department` = code "flight_ops", `role` = "STAFF". join_team sets department_code = invite.get("department") = "flight_ops". Validates code in applicable. label = DEPARTMENT_LABELS["flight_ops"] = "Flight Operations". Claims role = STAFF, department = "Flight Operations". user_doc role STAFF, department "Flight Operations", status "ACTIVE". 

Note I added `"status": "ACTIVE"` to the user_doc in join_team. The spec item 1 says user records should contain status. Good.

For the invite doc, `created_at` is a datetime; `list_invites` handles isoformat. In the test, invite doc set via fake stores the datetime fine.

Let me also think about the `verify_invite` test: GET /api/v1/auth/verify-invite?code=DEXX11 where invite doc exists. It resolves invite → returns department + role. But note: `resolve_tenant(db, None, tid)` — with tenant_id given, it checks the tenant doc exists and optionally matches invite code (skipped since invite_code None). Good.

Now `_patch` for join: monkeypatch get_db in app.firebase, app.routes.auth, app.services.tenant_registration, app.services.users, app.services.audit_service, and also app.services.invites (create_invite/list_invites use get_db from app.firebase which is patched; but list_invites uses get_db directly from app.firebase import — patched). Actually invites.py imports `from app.firebase import get_db`. monkeypatch.setattr("app.firebase.get_db", ...) replaces the source, so all `from app.firebase import get_db` already-bound references? No! `from app.firebase import get_db` binds the function object at import time in each module. monkeypatch.setattr("app.firebase.get_db", lambda: db) replaces the attribute on the app.firebase module, but modules that did `from app.firebase import get_db` still reference the ORIGINAL function object, not the patched attribute.

That's why test_auth._patch patches each consumer module explicitly:
```
monkeypatch.setattr("app.routes.auth.get_db", lambda: db)
monkeypatch.setattr("app.services.tenant_registration.get_db", lambda: db)
monkeypatch.setattr("app.services.users.get_db", lambda: db)
monkeypatch.setattr("app.services.audit_service.get_db", lambda: db)
```

So I must also patch `app.services.invites.get_db` since it did `from app.firebase import get_db`. And for the tenants route users endpoint, get_db is used in list_tenant_users (patched via app.services.users.get_db). Good.

I'll add `monkeypatch.setattr("app.services.invites.get_db", lambda: db)`.

Also auth get_auth for create_user in join. Patch app.firebase.get_auth + app.services.tenant_registration.get_auth.

Now, one concern: `resolve_user_context` and `get_current_user` are NOT overridden for join — join is public. Good.

For the invite endpoint test, `create_invite` calls `request_context(request)` — the TestClient provides a real request. Fine.

Let me write the file.

Also add a test that the invite endpoint rejects a non-inviter (USER/STAFF) with 403 — covered by create_invite raising PermissionError.

Let me write comprehensive but focused tests.

For users listing test: need list_tenant_users to query users where tenant_id == tid. My fake query iterates the users store, filters. Good. And `_envelope` wraps in data. The DEPT_ADMIN filter uses department_to_code on u.get("department") (label) — works.

Note: list_tenant_users returns keys uid,email,role,department,createdAt,lastLogin. Good.

Let me write the test file.

Now write the RBAC test suite

**Tool: write**

**Input:**
```json
{
  "content": "\"\"\"Departmental Admin (HOD) delegation — invite RBAC + department-scoped join.\n\nCovers (2026-08):\n  * POST /api/v1/auth/invite  — TENANT_ADMIN may invite DEPT_ADMIN/SAFETY_OFFICER/\n    STAFF into any applicable department; DEPT_ADMIN may only invite STAFF into\n    their own department (cross-department and escalation -> 403).\n  * POST /api/v1/auth/join (alias of /join-team) — a department-scoped invite\n    binds the invitee's department AND role directly from the invite document.\n  * GET  /api/v1/tenants/{tenantId}/users — DEPT_ADMIN sees only their own\n    department's members; TENANT_ADMIN sees everyone.\n  * GET  /api/v1/auth/verify-invite — returns department + role for scoped invites.\n\"\"\"\n\nfrom fastapi.testclient import TestClient\n\nfrom app.main import app\nfrom app.middleware.auth import get_current_user\n\n\n# ============================================================================\n# Fake Firebase storage + auth\n# ============================================================================\n\nclass _Doc:\n    def __init__(self, data, exists=True, id=None):\n        self._data = data or {}\n        self.exists = exists\n        self.id = id\n\n    def get(self, field, default=None):\n        if field is None:\n            return self._data\n        return self._data.get(field, default)\n\n    def to_dict(self):\n        return self._data\n\n\nclass _CollQuery:\n    def __init__(self, db, name):\n        self._db = db\n        self._name = name\n        self._filters = []\n\n    def where(self, field, op, value):\n        self._filters.append((field, op, value))\n        return self\n\n    def limit(self, n):\n        return self\n\n    def get(self):\n        return self._run()\n\n    def stream(self):\n        return self._run()\n\n    def _run(self):\n        store = self._db._store(self._name)\n        if isinstance(store, list):\n            rows = []\n            for i, data in enumerate(store):\n                doc = dict(data or {})\n                doc.setdefault(\"id\", str(i))\n                ok = True\n                for field, op, value in self._filters:\n                    if op == \"==\" and doc.get(field) != value:\n                        ok = False\n                if ok:\n                    rows.append(_Doc(doc, exists=True, id=doc[\"id\"]))\n            return rows\n        rows = []\n        for key, data in store.items():\n            doc = dict(data or {})\n            doc.setdefault(\"id\", key)\n            ok = True\n            for field, op, value in self._filters:\n                if op == \"==\" and doc.get(field) != value:\n                    ok = False\n            if ok:\n                rows.append(_Doc(doc, exists=True, id=key))\n        return rows\n\n\nclass _CollRef:\n    def __init__(self, db, name, key):\n        self._db = db\n        self._name = name\n        self._key = key\n\n    def get(self):\n        store = self._db._store(self._name)\n        data = store.get(self._key) if isinstance(store, dict) else None\n        if data is None:\n            return _Doc(None, exists=False, id=self._key)\n        return _Doc(dict(data), exists=True, id=self._key)\n\n    def set(self, data, merge=False):\n        store = self._db._store(self._name)\n        if not isinstance(store, dict):\n            raise AssertionError(f\"cannot set document in non-dict collection {self._name}\")\n        if merge and self._key in store:\n            merged = dict(store[self._key])\n            merged.update(dict(data))\n            data = merged\n        store[self._key] = dict(data)\n\n    def update(self, data):\n        store = self._db._store(self._name)\n        merged = dict(store.get(self._key) or {}) if isinstance(store, dict) else {}\n        merged.update(dict(data))\n        if isinstance(store, dict):\n            store[self._key] = merged\n\n\nclass _Coll:\n    def __init__(self, db, name):\n        self._db = db\n        self._name = name\n\n    def document(self, key):\n        return _CollRef(self._db, self._name, key)\n\n    def where(self, field, op, value):\n        return _CollQuery(self._db, self._name).where(field, op, value)\n\n    def add(self, entry):\n        self._db._store(self._name).append(dict(entry))\n        return type(\"Ref\", (), {\"id\": f\"{self._name}-{len(self._db._store(self._name))}\"})()\n\n\nclass _FakeDB:\n    def __init__(self):\n        self.tenants = {}\n        self.users = {}\n        self.invites = {}\n        self.audit = []\n\n    def _store(self, name):\n        return {\n            \"tenants\": self.tenants,\n            \"users\": self.users,\n            \"invites\": self.invites,\n            \"audit_logs\": self.audit,\n        }[name]\n\n    def collection(self, name):\n        if name not in (\"tenants\", \"users\", \"invites\", \"audit_logs\"):\n            raise AssertionError(f\"unexpected collection {name}\")\n        return _Coll(self, name)\n\n\nclass _FakeAuth:\n    def __init__(self):\n        self.records = {}\n        self.claims = {}\n\n    def create_user(self, **kw):\n        uid = f\"uid-{len(self.records) + 1}\"\n        self.records[uid] = dict(kw)\n        return type(\"U\", (), {\"uid\": uid, \"email\": kw.get(\"email\")})()\n\n    def set_custom_user_claims(self, uid, claims):\n        self.claims[uid] = dict(claims)\n\n\ndef _patch(monkeypatch, db, auth=None):\n    monkeypatch.setattr(\"app.firebase.get_db\", lambda: db)\n    monkeypatch.setattr(\"app.routes.auth.get_db\", lambda: db)\n    monkeypatch.setattr(\"app.services.tenant_registration.get_db\", lambda: db)\n    monkeypatch.setattr(\"app.services.users.get_db\", lambda: db)\n    monkeypatch.setattr(\"app.services.audit_service.get_db\", lambda: db)\n    monkeypatch.setattr(\"app.services.invites.get_db\", lambda: db)\n    if auth is not None:\n        monkeypatch.setattr(\"app.firebase.get_auth\", lambda: auth)\n        monkeypatch.setattr(\"app.services.tenant_registration.get_auth\", lambda: auth)\n\n\ndef _seed_tenant(db, tid=\"yeti-airlines\", name=\"Yeti Airlines\",\n                 departments=None, invite_code=\"ABC123\", active=True):\n    db.tenants[tid] = {\n        \"tenant_id\": tid,\n        \"name\": name,\n        \"tenant_type\": \"AIRLINE_FIXED_WING\",\n        \"classification\": \"AIRLINE_FIXED_WING\",\n        \"applicable_departments\": departments or [\"safety\", \"flight_ops\", \"camo\", \"qa\"],\n        \"team_invite_code\": invite_code,\n        \"active\": active,\n    }\n\n\ndef _seed_scoped_invite(db, code=\"HOD123\", tid=\"yeti-airlines\",\n                        department=\"flight_ops\", role=\"STAFF\", status=\"ACTIVE\"):\n    db.invites[code] = {\n        \"code\": code,\n        \"tenant_id\": tid,\n        \"department\": department,\n        \"department_label\": \"Flight Operations\" if department == \"flight_ops\" else department,\n        \"role\": role,\n        \"created_by\": \"sm@yeti-airlines.com\",\n        \"created_at\": \"2026-08-01T00:00:00Z\",\n        \"status\": status,\n    }\n\n\ndef _as_role(role, tid=\"yeti-airlines\", department=None):\n    return {\n        \"uid\": f\"uid-{role.lower()}\",\n        \"email\": f\"{role.lower()}@example.com\",\n        \"role\": role,\n        \"tenant_id\": tid,\n        \"department\": department,\n        \"claims\": {\"role\": role, \"tenant_id\": tid, \"department\": department},\n    }\n\n\ndef _override_user(user):\n    app.dependency_overrides[get_current_user] = lambda: user\n\n\ndef _clear_override():\n    app.dependency_overrides.pop(get_current_user, None)\n\n\n# ============================================================================\n# Invite RBAC\n# ============================================================================\n\ndef test_tenant_admin_invites_dept_admin_any_department(monkeypatch):\n    db = _FakeDB()\n    _patch(monkeypatch, db, _FakeAuth())\n    _seed_tenant(db)\n    _override_user(_as_role(\"TENANT_ADMIN\", department=\"safety\"))\n    try:\n        resp = TestClient(app).post(\"/api/v1/auth/invite\",\n                                    json={\"department\": \"camo\", \"role\": \"DEPT_ADMIN\"})\n    finally:\n        _clear_override()\n    assert resp.status_code == 200, resp.text\n    body = resp.json()\n    assert body[\"success\"] is True\n    assert body[\"role\"] == \"DEPT_ADMIN\"\n    assert body[\"department\"] == \"camo\"\n    code = body[\"code\"]\n    assert len(code) == 6\n    stored = db.invites[code]\n    assert stored[\"tenant_id\"] == \"yeti-airlines\"\n    assert stored[\"department\"] == \"camo\"\n    assert stored[\"role\"] == \"DEPT_ADMIN\"\n    assert stored[\"status\"] == \"ACTIVE\"\n    assert stored[\"created_by\"] == \"uid-tenant_admin\"\n\n\ndef test_tenant_admin_invites_staff_any_department(monkeypatch):\n    db = _FakeDB()\n    _patch(monkeypatch, db, _FakeAuth())\n    _seed_tenant(db)\n    _override_user(_as_role(\"TENANT_ADMIN\", department=\"safety\"))\n    try:\n        resp = TestClient(app).post(\"/api/v1/auth/invite\",\n                                    json={\"department\": \"qa\", \"role\": \"STAFF\"})\n    finally:\n        _clear_override()\n    assert resp.status_code == 200, resp.text\n    assert resp.json()[\"role\"] == \"STAFF\"\n\n\ndef test_legacy_airline_admin_can_invite_safety_officer(monkeypatch):\n    db = _FakeDB()\n    _patch(monkeypatch, db, _FakeAuth())\n    _seed_tenant(db)\n    _override_user(_as_role(\"AIRLINE_ADMIN\", department=\"safety\"))\n    try:\n        resp = TestClient(app).post(\"/api/v1/auth/invite\",\n                                    json={\"department\": \"flight_ops\", \"role\": \"SAFETY_OFFICER\"})\n    finally:\n        _clear_override()\n    assert resp.status_code == 200, resp.text\n    assert resp.json()[\"role\"] == \"SAFETY_OFFICER\"\n\n\ndef test_legacy_auth_invite_alias_works(monkeypatch):\n    db = _FakeDB()\n    _patch(monkeypatch, db, _FakeAuth())\n    _seed_tenant(db)\n    _override_user(_as_role(\"TENANT_ADMIN\", department=\"safety\"))\n    try:\n        resp = TestClient(app).post(\"/api/auth/invite\",\n                                    json={\"department\": \"camo\", \"role\": \"STAFF\"})\n    finally:\n        _clear_override()\n    assert resp.status_code == 200, resp.text\n\n\ndef test_dept_admin_invites_staff_own_department(monkeypatch):\n    db = _FakeDB()\n    _patch(monkeypatch, db, _FakeAuth())\n    _seed_tenant(db)\n    _override_user(_as_role(\"DEPT_ADMIN\", department=\"Flight Operations\"))\n    try:\n        resp = TestClient(app).post(\"/api/v1/auth/invite\",\n                                    json={\"department\": \"flight_ops\", \"role\": \"STAFF\"})\n    finally:\n        _clear_override()\n    assert resp.status_code == 200, resp.text\n    body = resp.json()\n    assert body[\"role\"] == \"STAFF\"\n    assert body[\"department\"] == \"flight_ops\"\n\n\ndef test_dept_admin_cross_department_invite_returns_403(monkeypatch):\n    db = _FakeDB()\n    _patch(monkeypatch, db, _FakeAuth())\n    _seed_tenant(db)\n    _override_user(_as_role(\"DEPT_ADMIN\", department=\"Flight Operations\"))\n    try:\n        resp = TestClient(app).post(\"/api/v1/auth/invite\",\n                                    json={\"department\": \"camo\", \"role\": \"STAFF\"})\n    finally:\n        _clear_override()\n    assert resp.status_code == 403\n    assert \"own department\" in resp.json()[\"detail\"]\n    assert not db.invites\n\n\ndef test_dept_admin_cannot_assign_dept_admin_role(monkeypatch):\n    db = _FakeDB()\n    _patch(monkeypatch, db, _FakeAuth())\n    _seed_tenant(db)\n    _override_user(_as_role(\"DEPT_ADMIN\", department=\"Flight Operations\"))\n    try:\n        resp = TestClient(app).post(\"/api/v1/auth/invite\",\n                                    json={\"department\": \"flight_ops\", \"role\": \"DEPT_ADMIN\"})\n    finally:\n        _clear_override()\n    assert resp.status_code == 403\n    assert \"Department Admin\" in resp.json()[\"detail\"]\n    assert not db.invites\n\n\ndef test_dept_admin_cannot_assign_tenant_admin_role(monkeypatch):\n    db = _FakeDB()\n    _patch(monkeypatch, db, _FakeAuth())\n    _seed_tenant(db)\n    _override_user(_as_role(\"DEPT_ADMIN\", department=\"Flight Operations\"))\n    try:\n        resp = TestClient(app).post(\"/api/v1/auth/invite\",\n                                    json={\"department\": \"flight_ops\", \"role\": \"TENANT_ADMIN\"})\n    finally:\n        _clear_override()\n    assert resp.status_code == 403\n    assert not db.invites\n\n\ndef test_staff_cannot_invite(monkeypatch):\n    db = _FakeDB()\n    _patch(monkeypatch, db, _FakeAuth())\n    _seed_tenant(db)\n    _override_user(_as_role(\"STAFF\", department=\"Flight Operations\"))\n    try:\n        resp = TestClient(app).post(\"/api/v1/auth/invite\",\n                                    json={\"department\": \"flight_ops\", \"role\": \"STAFF\"})\n    finally:\n        _clear_override()\n    assert resp.status_code == 403\n    assert not db.invites\n\n\ndef test_tenant_admin_cannot_invite_to_inapplicable_department(monkeypatch):\n    db = _FakeDB()\n    _patch(monkeypatch, db, _FakeAuth())\n    _seed_tenant(db, departments=[\"safety\", \"flight_ops\"])\n    _override_user(_as_role(\"TENANT_ADMIN\", department=\"safety\"))\n    try:\n        resp = TestClient(app).post(\"/api/v1/auth/invite\",\n                                    json={\"department\": \"arff\", \"role\": \"STAFF\"})\n    finally:\n        _clear_override()\n    assert resp.status_code == 422\n    assert not db.invites\n\n\n# ============================================================================\n# Join binds department + role from the scoped invite\n# ============================================================================\n\ndef _join_body(invite_code=\"HOD123\", department=\"flight_ops\", **overrides):\n    body = {\n        \"invite_code\": invite_code,\n        \"full_name\": \"Ramesh Gurung\",\n        \"email\": \"ramesh@yetiairlines.com\",\n        \"password\": \"Join-2026-Pass\",\n        \"confirm_password\": \"Join-2026-Pass\",\n        \"department\": department,\n    }\n    body.update(overrides)\n    return body\n\n\ndef test_join_with_scoped_invite_binds_department_and_staff_role(monkeypatch):\n    db = _FakeDB()\n    auth = _FakeAuth()\n    _patch(monkeypatch, db, auth)\n    _seed_tenant(db)\n    _seed_scoped_invite(db, code=\"HOD123\", department=\"camo\", role=\"STAFF\")\n\n    resp = TestClient(app).post(\n        \"/api/v1/auth/join-team\",\n        json=_join_body(invite_code=\"HOD123\", department=\"flight_ops\"),\n    )\n    assert resp.status_code == 200, resp.text\n    body = resp.json()\n    assert body[\"department\"] == \"camo\"\n    assert body[\"department_label\"] == \"CAMO\"\n    assert body[\"role\"] == \"STAFF\"\n\n    uid = list(auth.claims)[0]\n    assert auth.claims[uid] == {\n        \"role\": \"STAFF\",\n        \"tenant_id\": \"yeti-airlines\",\n        \"department\": \"CAMO\",\n    }\n    user_doc = list(db.users.values())[0]\n    assert user_doc[\"role\"] == \"STAFF\"\n    assert user_doc[\"department\"] == \"CAMO\"\n    assert user_doc[\"status\"] == \"ACTIVE\"\n\n\ndef test_join_alias_endpoint_binds_dept_admin_role(monkeypatch):\n    db = _FakeDB()\n    auth = _FakeAuth()\n    _patch(monkeypatch, db, auth)\n    _seed_tenant(db)\n    _seed_scoped_invite(db, code=\"HOD456\", department=\"qa\", role=\"DEPT_ADMIN\")\n\n    resp = TestClient(app).post(\n        \"/api/v1/auth/join\",\n        json=_join_body(invite_code=\"HOD456\", department=\"flight_ops\",\n                        email=\"hodqa@yetiairlines.com\"),\n    )\n    assert resp.status_code == 200, resp.text\n    body = resp.json()\n    assert body[\"department\"] == \"qa\"\n    assert body[\"role\"] == \"DEPT_ADMIN\"\n    uid = list(auth.claims)[0]\n    assert auth.claims[uid][\"role\"] == \"DEPT_ADMIN\"\n    assert auth.claims[uid][\"department\"] == \"QA\"\n\n\ndef test_join_inactive_scoped_invite_rejected(monkeypatch):\n    db = _FakeDB()\n    auth = _FakeAuth()\n    _patch(monkeypatch, db, auth)\n    _seed_tenant(db)\n    _seed_scoped_invite(db, code=\"DEAD00\", department=\"camo\", role=\"STAFF\", status=\"USED\")\n\n    resp = TestClient(app).post(\n        \"/api/v1/auth/join-team\",\n        json=_join_body(invite_code=\"DEAD00\"),\n    )\n    assert resp.status_code == 404\n    assert not auth.claims\n    assert not db.users\n\n\ndef test_join_legacy_tenant_code_still_defaults_to_least_privilege(monkeypatch):\n    db = _FakeDB()\n    auth = _FakeAuth()\n    _patch(monkeypatch, db, auth)\n    _seed_tenant(db, invite_code=\"ABC123\")\n\n    resp = TestClient(app).post(\n        \"/api/v1/auth/join-team\",\n        json=_join_body(invite_code=\"ABC123\", department=\"flight_ops\"),\n    )\n    assert resp.status_code == 200, resp.text\n    uid = list(auth.claims)[0]\n    assert auth.claims[uid][\"role\"] == \"USER\"\n    assert auth.claims[uid][\"department\"] == \"Flight Operations\"\n\n\ndef test_verify_invite_returns_scoped_department_and_role(monkeypatch):\n    db = _FakeDB()\n    _patch(monkeypatch, db, _FakeAuth())\n    _seed_tenant(db)\n    _seed_scoped_invite(db, code=\"HOD999\", department=\"flight_ops\", role=\"SAFETY_OFFICER\")\n\n    resp = TestClient(app).get(\"/api/v1/auth/verify-invite?code=HOD999\")\n    assert resp.status_code == 200, resp.text\n    body = resp.json()\n    assert body[\"valid\"] is True\n    assert body[\"tenant_id\"] == \"yeti-airlines\"\n    assert body[\"department\"] == \"flight_ops\"\n    assert body[\"department_label\"] == \"Flight Operations\"\n    assert body[\"role\"] == \"SAFETY_OFFICER\"\n\n\n# ============================================================================\n# Department-scoped team listing\n# ============================================================================\n\ndef _seed_users(db):\n    db.users[\"u-sm\"] = {\n        \"uid\": \"u-sm\", \"email\": \"sm@yeti.com\", \"role\": \"AIRLINE_ADMIN\",\n        \"tenant_id\": \"yeti-airlines\", \"department\": \"Safety\",\n    }\n    db.users[\"u-hod\"] = {\n        \"uid\": \"u-hod\", \"email\": \"hodops@yeti.com\", \"role\": \"DEPT_ADMIN\",\n        \"tenant_id\": \"yeti-airlines\", \"department\": \"Flight Operations\",\n    }\n    db.users[\"u-eng\"] = {\n        \"uid\": \"u-eng\", \"email\": \"eng@yeti.com\", \"role\": \"STAFF\",\n        \"tenant_id\": \"yeti-airlines\", \"department\": \"Flight Operations\",\n    }\n    db.users[\"u-camo\"] = {\n        \"uid\": \"u-camo\", \"email\": \"camo@yeti.com\", \"role\": \"STAFF\",\n        \"tenant_id\": \"yeti-airlines\", \"department\": \"CAMO\",\n    }\n\n\ndef test_dept_admin_users_list_is_scoped_to_own_department(monkeypatch):\n    db = _FakeDB()\n    _patch(monkeypatch, db, _FakeAuth())\n    _seed_tenant(db)\n    _seed_users(db)\n    _override_user(_as_role(\"DEPT_ADMIN\", department=\"Flight Operations\"))\n    try:\n        resp = TestClient(app).get(\"/api/v1/tenants/yeti-airlines/users\")\n    finally:\n        _clear_override()\n    assert resp.status_code == 200, resp.text\n    users = resp.json()[\"data\"][\"users\"]\n    emails = [u[\"email\"] for u in users]\n    assert \"hodops@yeti.com\" in emails\n    assert \"eng@yeti.com\" in emails\n    assert \"camo@yeti.com\" not in emails\n    assert \"sm@yeti.com\" not in emails\n\n\ndef test_tenant_admin_users_list_shows_all_departments(monkeypatch):\n    db = _FakeDB()\n    _patch(monkeypatch, db, _FakeAuth())\n    _seed_tenant(db)\n    _seed_users(db)\n    _override_user(_as_role(\"TENANT_ADMIN\", department=\"safety\"))\n    try:\n        resp = TestClient(app).get(\"/api/v1/tenants/yeti-airlines/users\")\n    finally:\n        _clear_override()\n    assert resp.status_code == 200, resp.text\n    users = resp.json()[\"data\"][\"users\"]\n    assert len(users) == 4\n",
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\tests\\test_dept_admin_rbac.py"
}
```

**Output:**
```
Wrote file successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 22.0s)

**Tool: bash**

**Input:**
```json
{
  "command": "python -m pytest tests/test_dept_admin_rbac.py -q 2>&1 | Select-Object -Last 15",
  "timeout": 300000,
  "workdir": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend"
}
```

**Output:**
```
[31;1mC:\Users\CEO-LAPTOP\AppData\Local\Programs\Python\Python313\Lib\site-packages\requests\__init__.py:113: RequestsDependencyWarning: urllib3 (2.5.0) or chardet (7.4.3)/charset_normalizer (3.4.3) doesn't match a supported version![0m
[31;1m  warnings.warn([0m
.................                                                        [100%]
============================== warnings summary ===============================
..\..\..\AppData\Local\Programs\Python\Python313\Lib\site-packages\reportlab\lib\rl_safe_eval.py:11
  C:\Users\CEO-LAPTOP\AppData\Local\Programs\Python\Python313\Lib\site-packages\reportlab\lib\rl_safe_eval.py:11: DeprecationWarning: ast.NameConstant is deprecated and will be removed in Python 3.14; use ast.Constant instead
    haveNameConstant = hasattr(ast,'NameConstant')

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
17 passed, 1 warning in 0.28s

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 50.1s)

_Thinking:_

All 17 RBAC tests pass. Now let me run the full backend test suite to make sure nothing else broke (e.g., other tests relying on get_safety_manager role checks or users listing).

All 17 RBAC tests pass. Run the full backend suite

**Tool: bash**

**Input:**
```json
{
  "command": "python -m pytest -q 2>&1 | Select-Object -Last 5",
  "timeout": 600000,
  "workdir": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend"
}
```

**Output:**
```
  C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\backend\app\routes\copilot.py:59: PydanticDeprecatedSince20: The `dict` method is deprecated; use `model_dump` instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.11/migration/
    history = [item.dict() for item in (payload.history or [])]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
464 passed, 4 warnings in 31.14s

```

---

## Assistant (Build · DeepSeek V4 Flash Free · 20.2s)

_Thinking:_

464 passed (447 previous + 17 new). Backend done.

Now update the todos and move to the frontend. Let me mark backend tasks complete.

Frontend tasks:
1. Create `public/settings/team.html` + `public/js/team.js`.
2. Wire into shell nav (safety.html, administration.html) with roles including TENANT_ADMIN/DEPT_ADMIN.
3. Update firebase.js getRoleDestination + getDepartmentLabel to handle new roles.
4. Update administration.html isAdministrationAllowed to recognize TENANT_ADMIN.

Let me first look at how a typical page is structured (e.g., risk-trends.html top) to mimic the app-shell markup and script includes. Let me read the top of risk-trends.html or top-hazards.html.

Full backend green (464 = 447 + 17). Now the frontend. Let me check a page template structure

**Tool: read**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\top-hazards.html",
  "limit": 120
}
```

**Output:**
```
<path>C:\Users\CEO-LAPTOP\Projects\betasms-aviasafe\public\top-hazards.html</path>
<type>file</type>
<content>
1: <!DOCTYPE html>
2: <html lang="en">
3: <head>
4:     <meta charset="UTF-8">
5:     <meta name="viewport" content="width=device-width, initial-scale=1.0">
6:     <title>Top Hazards — AviaSAFE</title>
7:     <link rel="preconnect" href="https://fonts.googleapis.com">
8:     <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
9:     <link href="https://fonts.googleapis.com/css2?family=Inter:opsz@14..32&display=swap" rel="stylesheet">
10:     <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
11:     <link rel="stylesheet" href="/css/shell.css">
12:     <link rel="stylesheet" href="/css/variables.css">
13:     <link rel="stylesheet" href="/styles/global.css">
14:     <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
15:     <script src="js/chart-theme.js"></script>
16:     <style>
17:         *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
18:         body { font-family: 'Inter', system-ui, -apple-system, sans-serif; background: #f1f5f9; color: #0b2a42; min-height: 100vh; }
19:         #pageContent { display: none; }
20:         .page-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; margin-bottom: 1.5rem; }
21:         .page-header h2 { margin: 0; color: #0b2a42; }
22:         .section-title { font-size: 1.25rem; font-weight: 600; color: #0b2a42; margin: 1.5rem 0 1rem; display: flex; align-items: center; gap: 0.5rem; }
23:         .section-title:first-of-type { margin-top: 0; }
24:         .filter-bar { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.5rem; background: #fff; padding: 0.75rem 1.25rem; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
25:         .filter-bar label { font-size: 0.85rem; font-weight: 500; color: #0b2a42; }
26:         .filter-bar select { padding: 0.4rem 0.75rem; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 0.85rem; background: #fff; cursor: pointer; }
27:         .btn-refresh { margin-left: auto; background: #1a6b8a; color: #fff; border: none; padding: 0.4rem 1rem; border-radius: 6px; cursor: pointer; font-size: 0.85rem; font-weight: 500; transition: background 0.15s; }
28:         .btn-refresh:hover { background: #0b2a42; }
29:         .chart-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-bottom: 1.5rem; }
30:         @media (max-width: 860px) { .chart-grid { grid-template-columns: 1fr; } }
31:         .chart-card { background: #fff; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); padding: 1.25rem; }
32:         .chart-card h3 { font-size: 0.85rem; font-weight: 600; color: #0b2a42; margin-bottom: 1rem; }
33:         .chart-wrapper { position: relative; height: 260px; }
34:         .chart-full { grid-column: 1 / -1; }
35:         .chart-full .chart-wrapper { height: 280px; }
36:         .state-container { position: relative; min-height: 100px; }
37:         .state-loading::before { content: ''; position: absolute; inset: 0; background: rgba(255,255,255,0.7); display: flex; align-items: center; justify-content: center; z-index: 1; }
38:         .state-loading::after { content: 'Loading...'; position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: #64748b; font-size: 0.9rem; z-index: 2; }
39:         .state-empty, .state-error { display: flex; align-items: center; justify-content: center; padding: 3rem 1rem; }
40:         .state-empty .empty-msg, .state-error .error-msg { font-size: 0.9rem; color: #64748b; }
41:         .state-error .error-msg { color: #dc3545; }
42:         .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 0.75rem; }
43:         .stat-card { background: #fff; padding: 0.9rem; border-radius: 8px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
44:         .stat-card .num { font-size: 1.5rem; font-weight: 700; color: #0b2a42; }
45:         .stat-card .lbl { font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.3px; margin-top: 0.25rem; }
46:     </style>
47: 
48:     <link rel="stylesheet" href="css/theme.css">
49:     </head>
50: <body>
51: 
52: <div class="app-shell">
53:     <div id="pageContent">
54: 
55:         <div id="top-hazards-section" class="dashboard-view" data-dashboard-view>
56: 
57:         <div class="page-header">
58:             <h2><i class="fas fa-triangle-exclamation"></i> Top Hazards</h2>
59:             <a href="/safety.html" class="btn btn-outline btn-sm"><i class="fas fa-arrow-left"></i> Back to Dashboard</a>
60:         </div>
61: 
62:         <div class="filter-bar">
63:             <label for="daysFilter"><i class="fas fa-calendar-alt"></i> Period:</label>
64:             <select id="daysFilter">
65:                 <option value="30">Last 30 Days</option>
66:                 <option value="60" selected>Last 60 Days</option>
67:                 <option value="90">Last 90 Days</option>
68:                 <option value="180">Last 180 Days</option>
69:                 <option value="365">Last 365 Days</option>
70:             </select>
71:             <button id="refreshBtn" class="btn-refresh"><i class="fas fa-rotate"></i> Refresh</button>
72:         </div>
73: 
74:         <div class="section-title"><i class="fas fa-book"></i> Master Hazard Register Summary</div>
75:         <div class="chart-card">
76:             <div id="hazardStatsGrid" class="stats-grid"></div>
77:         </div>
78: 
79:         <div class="section-title"><i class="fas fa-triangle-exclamation"></i> Hazard Occurrence Frequency</div>
80:         <div class="chart-grid">
81:             <div class="chart-card chart-full">
82:                 <h3>Hazard Occurrence Frequency <a href="/hazards/index.html" class="btn btn-primary btn-sm" style="float:right;font-size:0.8rem;font-weight:500;"><i class="fas fa-external-link-alt"></i> Master Hazard Register</a></h3>
83:                 <div id="hazardChart" class="chart-wrapper state-container">
84:                     <canvas id="hazardChartCanvas"></canvas>
85:                 </div>
86:             </div>
87:         </div>
88: 
89:         </div>
90: 
91:     </div>
92: </div>
93: 
94: <script src="https://www.gstatic.com/firebasejs/9.22.0/firebase-app-compat.js"></script>
95: <script src="https://www.gstatic.com/firebasejs/9.22.0/firebase-auth-compat.js"></script>
96: <script src="/js/firebase.js"></script>
97: <script>
98: window.SHELL_CONFIG = {
99:     brand: 'AviaSAFE',
100:     roleLabel: 'Operator Safety Dashboard',
101:     nav: [
102:         { href: '/safety.html', label: 'Key Indicators', icon: 'fa-chart-simple' },
103:         { href: '/dashboard/index.html', label: 'SMS Maturity', icon: 'fa-heart-pulse' },
104:         { href: '/risk-trends.html', label: 'Risk & Trends', icon: 'fa-chart-bar' },
105:         { href: '/top-hazards.html', label: 'Top Hazards', icon: 'fa-triangle-exclamation' },
106:         { href: '/administration.html', label: 'Administration', icon: 'fa-user-gear', roles: ['AIRLINE_ADMIN'] },
107:     ],
108: };
109: </script>
110: <script src="/js/api/client.js"></script>
111: <script src="/js/shell.js"></script>
112: <script src="/js/dashboard-nav.js"></script>
113: <script src="/js/api/dashboard.js"></script>
114: <script src="/js/dashboard-utils.js"></script>
115: <script src="/js/hazards.js"></script>
116: <script>
117: let chartInstances = {};
118: let currentDays = 90;
119: 
120: function safeArray(data) {

(Showing lines 1-120 of 279. Use offset=121 to continue.)
</content>
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 33.1s)

_Thinking:_

I have the page structure. Now create `public/settings/team.html` and `public/js/team.js`.

For the team page, I need:
- app-shell wrapper with pageContent
- shell config with nav including a Team link (roles TENANT_ADMIN, AIRLINE_ADMIN, DEPT_ADMIN)
- firebase.js, client.js, shell.js, team.js
- role-aware logic in team.js:
  - DEPT_ADMIN: lock department select (read-only showing caller's dept), lock role to STAFF
  - TENANT_ADMIN/AIRLINE_ADMIN: department dropdown of applicable departments, role dropdown DEPT_ADMIN/SAFETY_OFFICER/STAFF
- fetch users list (GET /api/v1/tenants/{tenantId}/users), fetch invites (GET /api/v1/auth/invites)
- invite form posts POST /api/v1/auth/invite {department, role}, shows the generated code with a copy button.

For applicable departments: need to fetch tenant config? The tenant-lookup endpoint is public but requires invite code or tenant id: GET /api/v1/auth/tenant-lookup?tenant_id=... It's public (no auth). Returns applicable_departments. But it's under rate_limit "auth_attempts". Alternatively, I can derive from users or just use the invite endpoint's validation. Simpler: fetch via /api/v1/auth/tenant-lookup?tenant_id=<tid> to populate departments. That returns codes + labels. Good.

Also need role labels. I'll define a JS map mirroring ROLE_LABELS.

The team.js should also render role label and department label for each user.

Now regarding auth for these GET endpoints: client.js attaches Bearer token. tenant-lookup is public though; but client.js works fine for it (it just includes the token). Actually client.js `_getToken` redirects to login if no session. On this page there's a session. Fine.

Let me also decide nav: add Team link to safety.html, administration.html, top-hazards.html, risk-trends.html, dashboard/index.html, caan-sms-maturity.html? Minimal: add to safety.html and administration.html nav, roles ['AIRLINE_ADMIN','TENANT_ADMIN','DEPT_ADMIN']. The user asked "wired into the existing shell navigation". Adding to the primary tenant dashboard pages (safety.html + administration.html) is reasonable. I'll add to safety.html, administration.html, top-hazards.html, risk-trends.html (the common tenant pages). Actually to keep scope tight but useful, add to safety.html + administration.html (the pages where admins land and manage). Let me add to safety.html and administration.html.

Wait — but TENANT_ADMIN users land on safety.html (getRoleDestination → /safety.html for non-SUPER_ADMIN/non-CAAN). DEPT_ADMIN too. So safety.html nav should show Team for them. And administration.html is restricted to safety managers; DEPT_ADMIN can't access administration. The nav on administration.html is shown to whoever is on that page (admins). I'll add Team link to safety.html with roles including TENANT_ADMIN/AIRLINE_ADMIN/DEPT_ADMIN.

Let me update the role handling in firebase.js:
- getDepartmentLabel: add TENANT_ADMIN → 'Corporate Safety Department'; DEPT_ADMIN/SAFETY_OFFICER/STAFF → department-based.
- getRoleDestination: TENANT_ADMIN/DEPT_ADMIN/SAFETY_OFFICER/STAFF → '/safety.html'. Currently default returns '/safety.html' anyway, and USER with department goes to responsible-manager. STAFF with department should go to responsible-manager too? Existing USER with department → responsible-manager. STAFF is the canonical alias of USER, so mirror: if role in (USER, STAFF) and department → responsible-manager; else safety.html.

Let me update:
```js
function getRoleDestination(user) {
    var role = (user && user.role) || 'USER';
    if (role === 'SUPER_ADMIN') return '/admin/production-setup.html';
    if (role === 'CAAN_SMD') return '/caan.html';
    if (role === 'USER' || role === 'STAFF') {
        var claims = (user && (user.claims || {})) || {};
        var department = claims.department || (user && user.department) || '';
        if (department) return '/dashboard/responsible-manager.html';
        return '/safety.html';
    }
    return '/safety.html';
}
```

getDepartmentLabel:
```js
function getDepartmentLabel(claims) {
    var role = (claims && claims.role) || 'USER';
    var dept = (claims && claims.department) || '';
    if (role === 'CAAN_SMD') return 'State Aviation Safety Oversight';
    if (role === 'AIRLINE_ADMIN' || role === 'TENANT_ADMIN') return 'Corporate Safety Department';
    if (dept === 'CAMO') return 'CAMO Department';
    if (dept === 'Part-145') return 'Part-145 Maintenance Department';
    if (dept === 'Flight Operations') return 'Flight Operations Department';
    return dept || '';
}
```

Now, the shell nav `applyNavVisibility` uses `claims.role` exact match against data-roles. So nav item roles: ['AIRLINE_ADMIN','TENANT_ADMIN','DEPT_ADMIN']. But for legacy AIRLINE_ADMIN users, role claim = AIRLINE_ADMIN. Good. For new TENANT_ADMIN/DEPT_ADMIN, exact matches. Good.

Also update the Administration nav item roles in safety.html/administration.html to include TENANT_ADMIN (since a TENANT_ADMIN should see Administration). Currently `roles: ['AIRLINE_ADMIN', 'safety']`. Add 'TENANT_ADMIN'. The 'safety' here refers to role 'safety' (lowercase), a legacy role value. Keep it.

And isAdministrationAllowed in administration.html: add TENANT_ADMIN. Also DEPT_ADMIN should NOT get Administration (it's safety-manager config), so don't add.

Now create team.js. Let me write the HTML page.

The team.js needs getCurrentUser + waitForFirebase from firebase.js. It uses ApiClient from client.js. I'll write it as an IIFE with global init.

Key functions in team.js:
- roleLabel(role) map
- departmentLabel(codeOrLabel)
- initTeamPage()
  - waitForFirebase, getCurrentUser
  - gate: role must be in TENANT_ADMIN/AIRLINE_ADMIN/DEPT_ADMIN/SUPER_ADMIN else show access denied
  - set up UI state (locked vs full)
  - load tenant info (tenant-lookup) → populate department dropdown
  - load users + invites
- submitInvite(e)
  - POST /api/v1/auth/invite {department, role}
  - display generated code + copy
- renderUsers, renderInvites

Let me write it. I'll make it robust and self-contained.

One consideration: the users endpoint returns users with `department` field as label (from user_doc). Also list_tenant_users sorts. The DEPT_ADMIN filter is applied server-side, but frontend will also filter defensively? Server is authoritative; frontend just renders. Fine.

Let me also expose a "copy code" button using navigator.clipboard.

Now the HTML page. Let me build it mirroring top-hazards structure but simpler.

Also, the page should handle the case where the caller's department claim is absent (e.g., legacy). For DEPT_ADMIN it will exist. For robustness, if role is DEPT_ADMIN and no department, show error.

Now write the files.

Also, must add Team nav link. Let me define nav in team.html itself too (so it has nav). Add Team link with roles.

Let me write team.html.

Now create the team management page and its controller

**Tool: write**

**Input:**
```json
{
  "content": "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n    <meta charset=\"UTF-8\">\n    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n    <title>Team Management — AviaSAFE</title>\n    <link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">\n    <link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>\n    <link href=\"https://fonts.googleapis.com/css2?family=Inter:opsz@14..32&display=swap\" rel=\"stylesheet\">\n    <link rel=\"stylesheet\" href=\"https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css\">\n    <link rel=\"stylesheet\" href=\"/css/shell.css\">\n    <link rel=\"stylesheet\" href=\"/css/variables.css\">\n    <link rel=\"stylesheet\" href=\"/styles/global.css\">\n    <style>\n        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }\n        body { font-family: 'Inter', system-ui, -apple-system, sans-serif; background: #f1f5f9; color: #0b2a42; min-height: 100vh; }\n        #pageContent { display: none; }\n        .page-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; margin-bottom: 1.5rem; }\n        .page-header h2 { margin: 0; color: #0b2a42; }\n        .grid-2 { display: grid; grid-template-columns: 1.1fr 1fr; gap: 1.5rem; }\n        @media (max-width: 960px) { .grid-2 { grid-template-columns: 1fr; } }\n        .card { background: #fff; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); padding: 1.5rem; }\n        .card h3 { font-size: 1rem; font-weight: 600; color: #0b2a42; margin-bottom: 1rem; display: flex; align-items: center; gap: 0.5rem; }\n        .card .hint { font-size: 0.8rem; color: #64748b; margin-top: 0.5rem; }\n        .form-row { margin-bottom: 1rem; }\n        .form-row label { display: block; font-size: 0.85rem; font-weight: 500; color: #0b2a42; margin-bottom: 0.35rem; }\n        .form-row select, .form-row input { width: 100%; padding: 0.55rem 0.75rem; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 0.9rem; background: #fff; color: #0b2a42; }\n        .form-row select:disabled, .form-row input:disabled { background: #f1f5f9; color: #475569; cursor: not-allowed; }\n        .btn-primary { background: #1a6b8a; color: #fff; border: none; padding: 0.55rem 1.25rem; border-radius: 6px; cursor: pointer; font-size: 0.9rem; font-weight: 500; transition: background 0.15s; }\n        .btn-primary:hover { background: #0b2a42; }\n        .btn-outline { background: #fff; color: #1a6b8a; border: 1px solid #cbd5e1; padding: 0.4rem 0.9rem; border-radius: 6px; cursor: pointer; font-size: 0.8rem; font-weight: 500; }\n        .btn-outline:hover { border-color: #1a6b8a; }\n        .btn-copy { margin-left: 0.5rem; font-size: 0.75rem; padding: 0.25rem 0.6rem; }\n        .role-badge { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 999px; font-size: 0.72rem; font-weight: 600; }\n        .role-admin { background: #dcfce7; color: #166534; }\n        .role-hod { background: #dbeafe; color: #1e40af; }\n        .role-officer { background: #fef9c3; color: #854d0e; }\n        .role-staff { background: #e2e8f0; color: #334155; }\n        .dept-tag { font-size: 0.75rem; color: #64748b; }\n        .table-wrap { overflow-x: auto; }\n        table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }\n        th, td { text-align: left; padding: 0.6rem 0.75rem; border-bottom: 1px solid #eef2f7; vertical-align: middle; }\n        th { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.4px; color: #64748b; font-weight: 600; }\n        tr:hover td { background: #f8fafc; }\n        .invite-code { font-family: 'Consolas', 'Menlo', monospace; font-weight: 700; letter-spacing: 1px; color: #0b2a42; }\n        .invite-result { display: none; margin-top: 1rem; padding: 0.9rem 1rem; border: 1px solid #bbf7d0; background: #f0fdf4; border-radius: 8px; }\n        .invite-result .code-big { font-size: 1.4rem; font-weight: 800; letter-spacing: 2px; color: #166534; font-family: 'Consolas', 'Menlo', monospace; }\n        .empty { text-align: center; padding: 2rem 1rem; color: #64748b; font-size: 0.85rem; }\n        .error-box, .denied-box { display: none; text-align: center; padding: 3rem 1rem; }\n        .error-box i, .denied-box i { font-size: 2.5rem; color: #dc3545; }\n        .denied-box h2 { color: #dc3545; margin-top: 1rem; }\n        .denied-box p { color: #64748b; margin-top: 0.5rem; }\n        .denied-box a { display: inline-block; margin-top: 1rem; }\n        .toast { position: fixed; bottom: 1.5rem; right: 1.5rem; background: #0b2a42; color: #fff; padding: 0.7rem 1.1rem; border-radius: 8px; font-size: 0.85rem; opacity: 0; transition: opacity 0.2s; pointer-events: none; z-index: 999; }\n        .toast.show { opacity: 1; }\n    </style>\n</head>\n<body>\n\n<div class=\"app-shell\">\n    <div id=\"pageContent\">\n\n        <div id=\"deniedBox\" class=\"denied-box\">\n            <i class=\"fas fa-lock\"></i>\n            <h2>Access Denied</h2>\n            <p>Team management is available to the Safety Manager (Tenant Admin) and Department Admins only.</p>\n            <a href=\"/safety.html\" class=\"btn btn-outline\"><i class=\"fas fa-arrow-left\"></i> Back to Dashboard</a>\n        </div>\n\n        <div id=\"errorBox\" class=\"error-box\">\n            <i class=\"fas fa-exclamation-circle\"></i>\n            <h2 style=\"margin-top:1rem;color:#dc3545;\">Failed to load Team Management</h2>\n            <p style=\"color:#64748b;margin-top:0.5rem;\" id=\"errorMsg\">Please reload the page.</p>\n        </div>\n\n        <div id=\"teamContent\" style=\"display:none;\">\n            <div class=\"page-header\">\n                <h2><i class=\"fas fa-users-gear\"></i> Team Management</h2>\n                <span id=\"scopeBadge\" class=\"dept-tag\"></span>\n            </div>\n\n            <div class=\"grid-2\">\n                <div class=\"card\">\n                    <h3><i class=\"fas fa-user-plus\"></i> Invite Team Member</h3>\n                    <form id=\"inviteForm\">\n                        <div class=\"form-row\">\n                            <label for=\"inviteDepartment\">Department</label>\n                            <select id=\"inviteDepartment\"></select>\n                        </div>\n                        <div class=\"form-row\">\n                            <label for=\"inviteRole\">Role</label>\n                            <select id=\"inviteRole\"></select>\n                        </div>\n                        <button type=\"submit\" class=\"btn-primary\"><i class=\"fas fa-paper-plane\"></i> Generate Invite Code</button>\n                        <p class=\"hint\">Share the generated invite code with your colleague — they enter it on the Join Team page to connect to your organization.</p>\n                    </form>\n                    <div id=\"inviteResult\" class=\"invite-result\">\n                        <div style=\"font-size:0.8rem;color:#166534;font-weight:600;\">Invite generated for\n                            <span id=\"inviteResultDept\"></span> · <span id=\"inviteResultRole\"></span></div>\n                        <div class=\"code-big\" id=\"inviteResultCode\">ABCDEF</div>\n                        <a href=\"/join.html\" class=\"btn btn-outline\" style=\"margin-top:0.75rem;display:inline-block;\">\n                            <i class=\"fas fa-arrow-up-right-from-square\"></i> Open Join Team Page</a>\n                    </div>\n                </div>\n\n                <div class=\"card\">\n                    <h3><i class=\"fas fa-ticket\"></i> Active Invites</h3>\n                    <div id=\"invitesList\">\n                        <div class=\"empty\">No active invites.</div>\n                    </div>\n                </div>\n            </div>\n\n            <div class=\"card\" style=\"margin-top:1.5rem;\">\n                <h3><i class=\"fas fa-address-book\"></i> Team Members</h3>\n                <div class=\"table-wrap\">\n                    <table>\n                        <thead>\n                        <tr>\n                            <th>Name</th>\n                            <th>Email</th>\n                            <th>Role</th>\n                            <th>Department</th>\n                        </tr>\n                        </thead>\n                        <tbody id=\"usersTableBody\">\n                        <tr><td colspan=\"4\" class=\"empty\">Loading team members…</td></tr>\n                        </tbody>\n                    </table>\n                </div>\n            </div>\n        </div>\n\n    </div>\n</div>\n\n<div id=\"toast\" class=\"toast\"></div>\n\n<script src=\"https://www.gstatic.com/firebasejs/9.22.0/firebase-app-compat.js\"></script>\n<script src=\"https://www.gstatic.com/firebasejs/9.22.0/firebase-auth-compat.js\"></script>\n<script src=\"/js/firebase.js\"></script>\n<script>\nwindow.SHELL_CONFIG = {\n    brand: 'AviaSAFE',\n    roleLabel: 'Operator Safety Dashboard',\n    nav: [\n        { href: '/safety.html', label: 'Key Indicators', icon: 'fa-chart-simple' },\n        { href: '/dashboard/index.html', label: 'SMS Maturity', icon: 'fa-heart-pulse' },\n        { href: '/risk-trends.html', label: 'Risk & Trends', icon: 'fa-chart-bar' },\n        { href: '/top-hazards.html', label: 'Top Hazards', icon: 'fa-triangle-exclamation' },\n        { href: '/settings/team.html', label: 'Team', icon: 'fa-users-gear', roles: ['AIRLINE_ADMIN', 'TENANT_ADMIN', 'DEPT_ADMIN'] },\n        { href: '/administration.html', label: 'Administration', icon: 'fa-user-gear', roles: ['AIRLINE_ADMIN', 'TENANT_ADMIN', 'safety'] },\n    ],\n};\n</script>\n<script src=\"/js/api/client.js\"></script>\n<script src=\"/js/shell.js\"></script>\n<script src=\"/js/team.js\"></script>\n\n<script>\ndocument.addEventListener('DOMContentLoaded', function () {\n    window.initTeamPage();\n});\n</script>\n\n</body>\n</html>\n",
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\settings\\team.html"
}
```

**Output:**
```
Wrote file successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 34.1s)

_Thinking:_

Now write team.js. I need to reference:
- getCurrentUser, waitForFirebase from firebase.js
- ApiClient from client.js
- updateShellTenant from shell.js

Logic:
- ROLE_MANAGER = ['AIRLINE_ADMIN','TENANT_ADMIN','DEPT_ADMIN','SUPER_ADMIN']
- ROLE_LABELS, DEPT mapping via tenant-lookup
- initTeamPage():
  - gate auth + role
  - populate department select: for TENANT_ADMIN fetch tenant-lookup; for DEPT_ADMIN locked to own dept
  - populate role select: DEPT_ADMIN → [STAFF]; TENANT_ADMIN → [DEPT_ADMIN, SAFETY_OFFICER, STAFF]
  - load users + invites
- On role switch maybe nothing.

The applicable departments endpoint: GET /api/v1/auth/tenant-lookup?tenant_id=<tid>. Response: {success, tenant_id, tenant_name, classification, operates_flights, applicable_departments:[{code,label}]}. It's public (rate limited). ApiClient.post/get works.

For DEPT_ADMIN, caller's department claim is a label like "Flight Operations". I need the code to display? I can show label directly. The invite payload should send the code or label — backend normalizes either. I'll send the label to be safe (department_to_code handles labels). Actually simplest: for DEPT_ADMIN, set the select with a single option using the caller's department label as both value+text. Backend normalizes label→code. Good.

For TENANT_ADMIN: populate with codes+labels from tenant-lookup. Value = code.

Role select options:
- TENANT_ADMIN/AIRLINE_ADMIN/SUPER_ADMIN: DEPT_ADMIN (Department Admin (HOD)), SAFETY_OFFICER (Safety Officer), STAFF (Staff / Employee)
- DEPT_ADMIN: STAFF only, disabled.

Users table: fetch GET /api/v1/tenants/{tenantId}/users → resp.data.users (envelope). Each: uid, email, role, department, createdAt, lastLogin. Note: no name field in list_tenant_users. The table has a Name column — I'll drop to email or show department? list_tenant_users doesn't include display_name. I'll adjust: show email as primary, and reuse the Name cell for "—" or display_name if present (it's not). Let me just merge name into email cell. Actually I'll render Name as the part before @? No. Better: change the table header to not include Name... but the HTML already written has Name. I'll fill Name with display_name if present else '' and Email with email. Since list_tenant_users doesn't include display_name, Name will be blank. Hmm. 

Let me instead update list_tenant_users in users.py to include display_name? That's a backend change but low-risk and improves the page. Actually simpler: I'll edit the table to have columns Email, Role, Department. But I already wrote the HTML. Let me just update users.py to include display_name in list_tenant_users — it's a mirror doc that includes display_name already. That's a clean improvement. But it also affects other consumers (none besides the admin users endpoint + backfill script). Safe.

Actually, let me keep it minimal and just render display_name if available. I'll edit the HTML to make first column "Email" second "Role" etc.? The header says Name, Email, Role, Department. I'll just update users.py list_tenant_users to include display_name and name the column via JS. Simpler: keep HTML, in JS render Name cell as u.display_name || '—'. And update users.py to add display_name.

Let me update users.py list_tenant_users to include display_name.

Role badge classes: map role→class. TENANT_ADMIN/AIRLINE_ADMIN → role-admin; DEPT_ADMIN → role-hod; SAFETY_OFFICER → role-officer; STAFF/USER → role-staff; SUPER_ADMIN/CAAN_SMD → role-admin.

Invites rendering: GET /api/v1/auth/invites → {success, invites:[...]} rows with code, department_label, role_label, created_by, status, created_at.

Copy: navigator.clipboard.writeText(code) with fallback.

Toast helper.

Scope badge: for TENANT_ADMIN "All departments"; DEPT_ADMIN "Department scope: <label>".

Now write team.js.

Also note the DEPT_ADMIN department claim from getCurrentUser is `claims.department`. For DEPT_ADMIN created via invite, claim department = label e.g. "Flight Operations". Good.

Edge: DEPT_ADMIN with no department claim — fallback to '' → department_to_code '' → invite would fail server-side with cross-dept 403. I'll show an error toast. Fine.

Let me write team.js.

**Tool: write**

**Input:**
```json
{
  "content": "/* ============================================================================\n   FILE: team.js\n   PATH: public/js/team.js\n   PURPOSE: Team Management page (public/settings/team.html). Role-aware for the\n            delegated admin hierarchy:\n              - TENANT_ADMIN / AIRLINE_ADMIN: full visibility, any applicable\n                department, assignable roles DEPT_ADMIN / SAFETY_OFFICER / STAFF.\n              - DEPT_ADMIN: department selector locked to the caller's own\n                department; role locked to STAFF / Employee.\n            Uses GET /api/v1/tenants/{tenantId}/users, GET /api/v1/auth/invites\n            and POST /api/v1/auth/invite via ApiClient.\n   AUTHOR: AviaSAFE Systems\n   ============================================================================ */\n\n(function (global) {\n    'use strict';\n\n    var INVITER_ROLES = ['SUPER_ADMIN', 'AIRLINE_ADMIN', 'TENANT_ADMIN', 'DEPT_ADMIN'];\n    var TENANT_WIDE_ROLES = ['SUPER_ADMIN', 'AIRLINE_ADMIN', 'TENANT_ADMIN'];\n\n    var ROLE_LABELS = {\n        SUPER_ADMIN: 'Global Administrator',\n        TENANT_ADMIN: 'Safety Manager (Tenant Admin)',\n        AIRLINE_ADMIN: 'Safety Manager (Tenant Admin)',\n        DEPT_ADMIN: 'Department Admin (HOD)',\n        SAFETY_OFFICER: 'Safety Officer',\n        STAFF: 'Staff / Employee',\n        USER: 'Staff / Employee',\n        CAAN_SMD: 'State Safety Regulator',\n    };\n\n    var ROLE_CLASSES = {\n        SUPER_ADMIN: 'role-admin',\n        TENANT_ADMIN: 'role-admin',\n        AIRLINE_ADMIN: 'role-admin',\n        DEPT_ADMIN: 'role-hod',\n        SAFETY_OFFICER: 'role-officer',\n        STAFF: 'role-staff',\n        USER: 'role-staff',\n        CAAN_SMD: 'role-admin',\n    };\n\n    function esc(value) {\n        return String(value == null ? '' : value)\n            .replace(/&/g, '&amp;')\n            .replace(/</g, '&lt;')\n            .replace(/>/g, '&gt;')\n            .replace(/\"/g, '&quot;');\n    }\n\n    function roleLabel(role) {\n        return ROLE_LABELS[role] || role || '—';\n    }\n\n    function roleBadge(role) {\n        var cls = ROLE_CLASSES[role] || 'role-staff';\n        return '<span class=\"role-badge ' + cls + '\">' + esc(roleLabel(role)) + '</span>';\n    }\n\n    function toast(message) {\n        var el = document.getElementById('toast');\n        if (!el) return;\n        el.textContent = message;\n        el.classList.add('show');\n        setTimeout(function () { el.classList.remove('show'); }, 2600);\n    }\n\n    function showPage() {\n        document.getElementById('teamContent').style.display = 'block';\n        document.getElementById('pageContent').style.display = 'block';\n    }\n\n    function showDenied() {\n        document.getElementById('deniedBox').style.display = 'block';\n        document.getElementById('pageContent').style.display = 'block';\n    }\n\n    function showError(message) {\n        document.getElementById('errorMsg').textContent = message;\n        document.getElementById('errorBox').style.display = 'block';\n        document.getElementById('pageContent').style.display = 'block';\n    }\n\n    function populateDepartmentSelect(session, departments) {\n        var select = document.getElementById('inviteDepartment');\n        select.innerHTML = '';\n        if (session.role === 'DEPT_ADMIN') {\n            var dept = (session.claims && session.claims.department) || session.department || '';\n            var opt = document.createElement('option');\n            opt.value = dept;\n            opt.textContent = dept || '—';\n            select.appendChild(opt);\n            select.disabled = true;\n            var badge = document.getElementById('scopeBadge');\n            if (badge) badge.textContent = 'Department scope: ' + (dept || '—');\n        } else {\n            var all = departments && departments.length\n                ? departments\n                : [{ code: 'safety', label: 'Safety' }];\n            all.forEach(function (d) {\n                var opt = document.createElement('option');\n                opt.value = d.code;\n                opt.textContent = d.label;\n                select.appendChild(opt);\n            });\n            select.disabled = false;\n            var badge = document.getElementById('scopeBadge');\n            if (badge) badge.textContent = 'Scope: all departments';\n        }\n    }\n\n    function populateRoleSelect(session) {\n        var select = document.getElementById('inviteRole');\n        select.innerHTML = '';\n        var options;\n        if (session.role === 'DEPT_ADMIN') {\n            options = [{ value: 'STAFF', label: 'Staff / Employee' }];\n            select.disabled = true;\n        } else {\n            options = [\n                { value: 'DEPT_ADMIN', label: 'Department Admin (HOD)' },\n                { value: 'SAFETY_OFFICER', label: 'Safety Officer' },\n                { value: 'STAFF', label: 'Staff / Employee' },\n            ];\n            select.disabled = false;\n        }\n        options.forEach(function (o) {\n            var opt = document.createElement('option');\n            opt.value = o.value;\n            opt.textContent = o.label;\n            select.appendChild(opt);\n        });\n    }\n\n    function renderUsers(users) {\n        var tbody = document.getElementById('usersTableBody');\n        if (!users || !users.length) {\n            tbody.innerHTML = '<tr><td colspan=\"4\" class=\"empty\">No team members found.</td></tr>';\n            return;\n        }\n        tbody.innerHTML = users.map(function (u) {\n            return '<tr>' +\n                '<td>' + esc(u.displayName || '—') + '</td>' +\n                '<td>' + esc(u.email || '—') + '</td>' +\n                '<td>' + roleBadge(u.role) + '</td>' +\n                '<td class=\"dept-tag\">' + esc(u.department || '—') + '</td>' +\n                '</tr>';\n        }).join('');\n    }\n\n    function renderInvites(invites) {\n        var wrap = document.getElementById('invitesList');\n        if (!invites || !invites.length) {\n            wrap.innerHTML = '<div class=\"empty\">No active invites.</div>';\n            return;\n        }\n        wrap.innerHTML = invites.map(function (inv) {\n            return '<div style=\"display:flex;justify-content:space-between;align-items:center;padding:0.55rem 0;border-bottom:1px solid #eef2f7;gap:0.75rem;\">' +\n                '<div>' +\n                '<span class=\"invite-code\">' + esc(inv.code) + '</span>' +\n                ' <span class=\"dept-tag\">' + esc(inv.department_label || inv.department || '') + ' · ' +\n                esc(inv.role_label || roleLabel(inv.role)) + '</span>' +\n                '</div>' +\n                '<button type=\"button\" class=\"btn-outline btn-copy\" data-code=\"' + esc(inv.code) + '\">' +\n                '<i class=\"fas fa-copy\"></i> Copy</button>' +\n                '</div>';\n        }).join('');\n        Array.prototype.forEach.call(wrap.querySelectorAll('[data-code]'), function (btn) {\n            btn.addEventListener('click', function () {\n                copyToClipboard(btn.getAttribute('data-code'));\n            });\n        });\n    }\n\n    function copyToClipboard(text) {\n        function fallback() {\n            var ta = document.createElement('textarea');\n            ta.value = text;\n            ta.style.position = 'fixed';\n            ta.style.opacity = '0';\n            document.body.appendChild(ta);\n            ta.select();\n            try { document.execCommand('copy'); } catch (e) { /* ignore */ }\n            document.body.removeChild(ta);\n            toast('Invite code copied');\n        }\n        if (navigator.clipboard && navigator.clipboard.writeText) {\n            navigator.clipboard.writeText(text).then(function () {\n                toast('Invite code copied');\n            }).catch(fallback);\n        } else {\n            fallback();\n        }\n    }\n\n    async function loadUsers(session) {\n        try {\n            var resp = await ApiClient.get('/api/v1/tenants/' + encodeURIComponent(session.tenantId) + '/users');\n            renderUsers((resp && resp.data && resp.data.users) || []);\n        } catch (err) {\n            renderUsers([]);\n            console.error('[Team] users load failed:', err);\n            toast(err && err.message ? err.message : 'Failed to load team members');\n        }\n    }\n\n    async function loadInvites() {\n        try {\n            var resp = await ApiClient.get('/api/v1/auth/invites');\n            renderInvites((resp && resp.invites) || []);\n        } catch (err) {\n            renderInvites([]);\n            console.error('[Team] invites load failed:', err);\n        }\n    }\n\n    async function loadDepartments(session) {\n        if (session.role === 'DEPT_ADMIN') {\n            populateDepartmentSelect(session, []);\n            return;\n        }\n        try {\n            var resp = await ApiClient.get('/api/v1/auth/tenant-lookup?tenant_id=' + encodeURIComponent(session.tenantId));\n            populateDepartmentSelect(session, (resp && resp.applicable_departments) || []);\n        } catch (err) {\n            populateDepartmentSelect(session, []);\n            console.error('[Team] department load failed:', err);\n        }\n    }\n\n    function attachInviteForm() {\n        var form = document.getElementById('inviteForm');\n        if (!form) return;\n        form.addEventListener('submit', async function (e) {\n            e.preventDefault();\n            var department = document.getElementById('inviteDepartment').value;\n            var role = document.getElementById('inviteRole').value;\n            if (!department || !role) {\n                toast('Select a department and role first');\n                return;\n            }\n            var submit = form.querySelector('button[type=\"submit\"]');\n            submit.disabled = true;\n            try {\n                var resp = await ApiClient.post('/api/v1/auth/invite', { department: department, role: role });\n                document.getElementById('inviteResultCode').textContent = (resp && resp.code) || '—';\n                document.getElementById('inviteResultDept').textContent = (resp && (resp.department_label || resp.department)) || '';\n                document.getElementById('inviteResultRole').textContent = roleLabel((resp && resp.role) || role);\n                document.getElementById('inviteResult').style.display = 'block';\n                toast('Invite code generated');\n                loadInvites();\n            } catch (err) {\n                console.error('[Team] invite failed:', err);\n                toast(err && err.message ? err.message : 'Unable to generate invite');\n            } finally {\n                submit.disabled = false;\n            }\n        });\n    }\n\n    async function initTeamPage() {\n        try {\n            await waitForFirebase();\n            var session = await getCurrentUser();\n            if (!session) {\n                window.location.href = '/login.html';\n                return;\n            }\n            if (INVITER_ROLES.indexOf(session.role) === -1) {\n                showDenied();\n                return;\n            }\n            if (!session.tenantId) {\n                showError('No tenant is associated with this account.');\n                return;\n            }\n\n            if (typeof window.updateShellTenant === 'function') {\n                window.updateShellTenant(\n                    (session.tenantId || '').toUpperCase(),\n                    session.role === 'DEPT_ADMIN' ? 'Team Management · Department Admin' : 'Team Management · Safety Manager'\n                );\n            }\n\n            populateRoleSelect(session);\n            attachInviteForm();\n            showPage();\n\n            await loadDepartments(session);\n            await Promise.all([loadUsers(session), loadInvites()]);\n        } catch (err) {\n            console.error('[Team] init failed:', err);\n            showError(err && err.message ? err.message : 'Failed to initialise Team Management.');\n        }\n    }\n\n    global.initTeamPage = initTeamPage;\n})(window);\n",
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\js\\team.js"
}
```

**Output:**
```
Wrote file successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 22.0s)

_Thinking:_

Now:
1. Update `list_tenant_users` in users.py to include display_name.
2. Update firebase.js getRoleDestination + getDepartmentLabel for new roles.
3. Add Team nav link to safety.html + administration.html nav; add TENANT_ADMIN to Administration roles in those navs.
4. Update isAdministrationAllowed in administration.html for TENANT_ADMIN.

Let me do the users.py update first.

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\backend\\app\\services\\users.py",
  "newString": "    results = []\n    for snap in snapshots:\n        data = snap.to_dict() or {}\n        results.append(\n            {\n                \"uid\": data.get(\"uid\") or snap.id,\n                \"email\": data.get(\"email\"),\n                \"displayName\": data.get(\"display_name\"),\n                \"role\": data.get(\"role\"),\n                \"department\": data.get(\"department\") or \"\",\n                \"createdAt\": data.get(\"created_at\").isoformat() if data.get(\"created_at\") else None,\n                \"lastLogin\": data.get(\"last_login\").isoformat() if data.get(\"last_login\") else None,\n            }\n        )",
  "oldString": "    results = []\n    for snap in snapshots:\n        data = snap.to_dict() or {}\n        results.append(\n            {\n                \"uid\": data.get(\"uid\") or snap.id,\n                \"email\": data.get(\"email\"),\n                \"role\": data.get(\"role\"),\n                \"department\": data.get(\"department\") or \"\",\n                \"createdAt\": data.get(\"created_at\").isoformat() if data.get(\"created_at\") else None,\n                \"lastLogin\": data.get(\"last_login\").isoformat() if data.get(\"last_login\") else None,\n            }\n        )"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 35.5s)

Now update firebase.js role routing/labels

**Tool: edit**

**Input:**
```json
{
  "filePath": "C:\\Users\\CEO-LAPTOP\\Projects\\betasms-aviasafe\\public\\js\\firebase.js",
  "newString": "function getDepartmentLabel(claims) {\n    var role = (claims && claims.role) || 'USER';\n    var dept = (claims && claims.department) || '';\n    if (role === 'CAAN_SMD') return 'State Aviation Safety Oversight';\n    if (role === 'AIRLINE_ADMIN' || role === 'TENANT_ADMIN') return 'Corporate Safety Department';\n    if (dept === 'CAMO') return 'CAMO Department';\n    if (dept === 'Part-145') return 'Part-145 Maintenance Department';\n    if (dept === 'Flight Operations') return 'Flight Operations Department';\n    return dept || '';\n}\nwindow.getDepartmentLabel = getDepartmentLabel;",
  "oldString": "function getDepartmentLabel(claims) {\n    var role = (claims && claims.role) || 'USER';\n    var dept = (claims && claims.department) || '';\n    if (role === 'CAAN_SMD') return 'State Aviation Safety Oversight';\n    if (role === 'AIRLINE_ADMIN') return 'Corporate Safety Department';\n    if (dept === 'CAMO') return 'CAMO Department';\n    if (dept === 'Part-145') return 'Part-145 Maintenance Department';\n    if (dept === 'Flight Operations') return 'Flight Operations Department';\n    return dept || '';\n}\nwindow.getDepartmentLabel = getDepartmentLabel;"
}
```

**Output:**
```
Edit applied successfully.
```

---

## Assistant (Build · DeepSeek V4 Flash Free · 134.9s)

---

## User

continue

---

## User

---

## Assistant (Compaction · Big Pickle · 110.5s)

---

