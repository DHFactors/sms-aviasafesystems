# ============================================================================
# FILE: groq_copilot.py
# PATH: backend/app/services/groq_copilot.py
# PURPOSE: Groq-powered "Safety & Compliance Copilot" chat assistant.
#
# The copilot answers aviation-safety / SMS / human-factors questions for
# airline, helicopter, aerodrome and Part-145 AMO postholders, always grounded
# in ICAO Annex 19 + Doc 9859 and standard analysis frameworks (HFACS, Reason
# Swiss Cheese, 5M+1E Fishbone, 5x5 SRA matrix).
#
# Context awareness: the user's role, department, tenant classification and
# current page are injected into the conversation as system context so answers
# adapt to the operator's scope (e.g. an AMO never receives flight-ops advice
# as primary guidance).
#
# Resilience: if GROQ_API_KEY is missing or Groq errors, the endpoint still
# returns HTTP 200 with a helpful offline reply so the widget never hangs.
# ============================================================================

import re
from typing import Any, Dict, List, Optional

from loguru import logger

from app.core.config import settings
from app.firebase import get_db

COPILOT_SYSTEM_PROMPT = """
You are "Ghanshyam — Executive Safety & SMS Copilot", an intelligent aviation safety, human factors, and compliance assistant embedded in AviaSAFE Systems.
You represent the voice, expertise, and guidance of Ghanshyam Acharya: Former Airline Chief Executive Officer, Human Factors (HF) & SMS Specialist, and Aviation Data Analyst with 50 years of industry experience (1977–2026).

Your Core Mission & Objectives:
1. Regulatory Alignment: Assist operators (Fixed-Wing, Rotary, Part-145 AMO, Aerodrome) in achieving full operational compliance with ICAO Annex 19 (3rd Edition) and ICAO Doc 9859 Safety Management Manual standards.
2. Methodological Rigor: Guide postholders through:
   - Hazard Identification & Occurrence Reporting (VSR, MOR).
   - Safety Risk Assessment (5x5 SRA Matrix: Severity vs Probability).
   - Root Cause Analysis using 5M+1E Fishbone and Human Factors frameworks (HFACS, Reason Swiss Cheese, Safety-II / HOP principles).
   - Corrective Action Notices (CAN) and closed-loop Corrective Action Plans (CAP) with verifiable milestones.
3. Tone & Persona:
   - Executive, pragmatic, authoritative, and data-driven yet encouraging and approachable.
   - Address the user with clarity and operational precision, avoiding theoretical fluff.
   - Do NOT refer to yourself as "Captain". Refer to yourself as "Ghanshyam (Ex-CEO & SMS/HF Specialist)".
"""

# Hard guidance so answers stay concrete, ICAO-anchored and actionable.
COPILOT_GUARDRAILS = """
GROUND RULES:
- Keep answers concise (150–350 words unless asked to go deeper), structured with short bullet lists where useful.
- Always anchor recommendations to ICAO Annex 19 / Doc 9859 / ICAO occurrence or SMS frameworks.
- Be encouraging and operational. Never imply that any report is trivial or discouraged.
- If the user reports a hazard or occurrence, respond as if this is the formal record:
  advise on the correct reporting path in AviaSAFE (VSR for voluntary/confidential, MOR for mandatory),
  the ICAO severity/probability classification, and whether a CAN should be raised.
- When asked anything outside aviation safety / SMS, politely redirect back to safety topics.
"""


def sanitize_message(text: str, limit: int = 2000) -> str:
    """Trim + neutralise obvious prompt-injection markers in user input."""
    text = re.sub(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", "", text, flags=re.I | re.S)
    return (text or "").strip()[:limit]


def get_tenant_classification(tenant_id: Optional[str]) -> Optional[str]:
    """Resolve the tenant's formal operational classification from Firestore."""
    if not tenant_id:
        return None
    try:
        doc = get_db().collection(settings.FIREBASE_COLLECTION_TENANTS).document(tenant_id).get()
        if doc.exists:
            data = doc.to_dict() or {}
            return data.get("tenant_type") or data.get("classification")
    except Exception as e:
        logger.warning(f"Copilot tenant classification lookup failed for {tenant_id}: {e}")
    return None


def build_system_prompt(
    *,
    role: Optional[str] = None,
    department: Optional[str] = None,
    tenant_id: Optional[str] = None,
    tenant_classification: Optional[str] = None,
    page_context: Optional[str] = None,
) -> str:
    """Assemble the persona prompt with the current user/tenant context injected."""
    context_lines = []
    if role:
        context_lines.append(f"- User role: {role}")
    if department:
        context_lines.append(f"- User department: {department}")
    if tenant_id:
        context_lines.append(f"- Tenant id: {tenant_id}")
    if tenant_classification:
        context_lines.append(f"- Operator classification: {tenant_classification}")
    if page_context:
        context_lines.append(f"- Current page / workflow: {page_context}")

    context_block = ""
    if context_lines:
        context_block = (
            "\nCURRENT USER CONTEXT (adapt your guidance to this — never echo it back verbatim):\n"
            + "\n".join(context_lines)
            + "\n"
        )

    return COPILOT_SYSTEM_PROMPT + COPILOT_GUARDRAILS + context_block


def build_messages(
    message: str,
    *,
    history: Optional[List[Dict[str, Any]]] = None,
    role: Optional[str] = None,
    department: Optional[str] = None,
    tenant_id: Optional[str] = None,
    tenant_classification: Optional[str] = None,
    page_context: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Build the Groq chat message list (system + recent history + user)."""
    messages: List[Dict[str, str]] = [
        {
            "role": "system",
            "content": build_system_prompt(
                role=role,
                department=department,
                tenant_id=tenant_id,
                tenant_classification=tenant_classification,
                page_context=page_context,
            ),
        }
    ]
    for entry in (history or [])[-8:]:
        role_name = (entry.get("role") or "user").strip().lower()
        content = sanitize_message(str(entry.get("content") or ""))
        if role_name not in ("user", "assistant"):
            role_name = "user"
        if content:
            messages.append({"role": role_name, "content": content})
    messages.append({"role": "user", "content": sanitize_message(message)})
    return messages


def _offline_reply(message: str) -> str:
    """Graceful fallback when Groq is unavailable (API key missing / error)."""
    topic = sanitize_message(message, 120)
    return (
        "Ghanshyam (Ex-CEO & SMS/HF Specialist): "
        "I'm standing by, but the Groq assistant service is currently unavailable — "
        "please try again in a moment. "
        f"(Your message was received: \"{topic or '(empty)'}\".)\n\n"
        "While offline, remember: log every hazard or occurrence through the correct "
        "reporting path (VSR for voluntary/confidential, MOR for mandatory), classify it "
        "on the ICAO 5x5 SRA matrix, and raise a CAN whenever the risk is Tolerable or higher."
    )


def chat(
    message: str,
    *,
    history: Optional[List[Dict[str, Any]]] = None,
    role: Optional[str] = None,
    department: Optional[str] = None,
    tenant_id: Optional[str] = None,
    page_context: Optional[str] = None,
) -> str:
    """Send the user message to Groq and return the assistant's reply.

    Always returns a string (never raises): network/API failures degrade to the
    offline reply so the frontend chat widget keeps working.
    """
    if not settings.GROQ_API_KEY:
        logger.info("GROQ_API_KEY not set — copilot returning offline reply")
        return _offline_reply(message)

    tenant_classification = tenant_id and get_tenant_classification(tenant_id)

    try:
        from groq import Groq

        client = Groq(api_key=settings.GROQ_API_KEY)
        messages = build_messages(
            message,
            history=history,
            role=role,
            department=department,
            tenant_id=tenant_id,
            tenant_classification=tenant_classification,
            page_context=page_context,
        )
        completion = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=messages,
            temperature=settings.GROQ_TEMPERATURE,
            max_tokens=settings.GROQ_MAX_TOKENS,
        )
        reply = completion.choices[0].message.content
        return reply.strip() if reply else _offline_reply(message)
    except Exception as e:
        logger.error(f"Groq copilot request failed: {e}")
        return _offline_reply(message)