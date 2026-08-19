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

import os
import re
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from app.core.config import settings
from app.firebase import get_db

# Explicit Groq model identifier. Kept as a named constant so deployments can
# never silently drift to an invalid model name. This key's Groq plan exposes
# the OpenAI gpt-oss lineup (no llama-3.x); gpt-oss-120b is the strongest chat
# model available to it.
GROQ_MODEL_NAME = "openai/gpt-oss-120b"

# Curated allowlist of the chat models this plan/key actually exposes. The
# GROQ_MODEL env / setting is validated against this list before use so a stray,
# deprecated or renamed model cannot silently break chat (see resolve_groq_model).
GROQ_KNOWN_MODELS = {
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.6-27b",
    "allam-2-7b",
}


def resolve_groq_model() -> str:
    """Return the active Groq chat model, guarded against invalid config.

    Validates ``settings.GROQ_MODEL`` (env ``GROQ_MODEL``) against
    GROQ_KNOWN_MODELS. An unrecognised / deprecated value logs a warning and
    falls back to GROQ_MODEL_NAME instead of failing later inside Groq.
    """
    configured = (settings.GROQ_MODEL or os.environ.get("GROQ_MODEL") or "").strip()
    if configured:
        if configured in GROQ_KNOWN_MODELS:
            return configured
        logger.warning(
            "GROQ_MODEL={!r} is not in the known production model list {} — "
            "falling back to default model {!r}",
            configured,
            sorted(GROQ_KNOWN_MODELS),
            GROQ_MODEL_NAME,
        )
    return GROQ_MODEL_NAME

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

# Strict per-page scoping: the model may only assist with the workflow of the
# page the user currently has open. Unknown pages fall back to title inference.
PAGE_SCOPE_BOUNDARY = """
STRICT PAGE-SCOPE BOUNDARY (MANDATORY):
- You are ONLY authorized to help with the workflow of the page the user currently has open (see CURRENT PAGE SCOPE below).
- Provide guidance, clarification, and field-level support ONLY for that page's forms, fields, and workflow steps.
- If a question asks about tasks, features, or data that belong to a DIFFERENT page, do NOT answer it directly.
  Politely explain that the request is outside this page's scope and, when relevant, name the page the user should open for that task.
- Never invent features, fields, or workflows that do not exist on the current page.
- Stay concise and operational.
"""

# Human-readable scope profile per known page. Keys are the page filename as
# sent by the frontend page_context (e.g. "register.html").
PAGE_SCOPE_GUIDANCE = {
    "register.html": (
        "Organization self-service registration. Help the user complete organization setup: "
        "organization name, operator classification (Fixed-Wing Airline, Helicopter/Rotary Operator, "
        "Part-145 Maintenance Organization, or Certified Airport/Aerodrome), primary administrator "
        "name/title, official email, password, optional beta access key, and explain what happens "
        "after submission (tenant id + team invite code for onboarding postholders via the join page)."
    ),
    "join.html": (
        "Team member self-onboarding with an invite code. Guide the user through entering their "
        "organization invite code, selecting their department / operational role (flight operations, "
        "engineering & maintenance, ground handling, etc.), and completing account setup."
    ),
    "login.html": (
        "Sign-in. Assist only with logging into the platform or troubleshooting sign-in. Politely "
        "redirect everything else to the appropriate page after sign-in."
    ),
    "safety.html": (
        "Safety Management System dashboard. Support SMS reporting (VSR voluntary/confidential, MOR "
        "mandatory), hazard & risk management, corrective actions (CAN/CAP), and safety performance monitoring."
    ),
    "caan.html": (
        "State aviation safety oversight dashboard. Support State Safety Programme (SSP) activities, "
        "state safety objectives, regulatory oversight, inspections, operator audits, and safety "
        "performance monitoring for the civil aviation authority."
    ),
    "audits.html": (
        "Safety assurance / audits workflow. Support audit planning, conducting internal and external "
        "audits and inspections, recording findings, and closing corrective action plans (CAN/CAP)."
    ),
    "responsible-manager.html": (
        "Responsible Manager dashboard. Support the responsible manager's safety responsibilities, "
        "oversight of reports, risk review, and corrective action approval."
    ),
}


def detect_page_name(page_context: Optional[str]) -> Optional[str]:
    """Extract the page filename (e.g. 'caan.html') from the page_context string."""
    if not page_context:
        return None
    match = re.search(r"([A-Za-z0-9_.-]+\.html)", page_context)
    return match.group(1).lower() if match else None


def build_page_scope_instruction(page_context: Optional[str]) -> str:
    """Return the strict page-scoping directive for the system prompt."""
    page = detect_page_name(page_context)
    scope = PAGE_SCOPE_GUIDANCE.get(page) if page else None
    if scope:
        return (
            "\nCURRENT PAGE SCOPE (the ONLY workflow you may assist with):\n"
            f"- Page: {page}\n"
            f"- Scope: {scope}\n"
        )
    return (
        "\nCURRENT PAGE SCOPE (the ONLY workflow you may assist with):\n"
        f"- Page: {page or 'unknown'}"
        + (f" (context: {str(page_context)[:120]})" if page_context else "")
        + "\n- Assist only with the workflow visible on the current page as inferred from its title. "
        "Politely decline or redirect anything outside that scope.\n"
    )


def sanitize_message(text: str, limit: int = 2000) -> str:
    """Trim + neutralise obvious prompt-injection markers in user input."""
    text = re.sub(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", "", text, flags=re.I | re.S)
    return (text or "").strip()[:limit]


# ============================================================================
# AVIATION SAFETY BOUNDARY — strict topic + prompt-injection rejection
# ============================================================================
# The copilot may ONLY assist with SMS, flight operations, airworthiness,
# safety climate and regulatory compliance. Queries outside that scope, and any
# attempt to override / reveal / bypass the assistant's instructions, are
# rejected here in code — before any model call — so the boundary cannot be
# relaxed by prompt manipulation.
#
# Heuristic: hard injection markers are always rejected; clearly off-topic
# requests are rejected unless they also reference a safety-topic keyword (so a
# question such as "weather for a go-around" stays in scope).

SAFETY_TOPIC_MARKERS = (
    "sms", "safety", "hazard", "risk", "report", "occurrence", "incident",
    "accident", "aircraft", "flight", "airline", "aoc", "airworthiness",
    "maintenance", "amo", "part-145", "part 145", "camo", "aerodrome", "airport",
    "runway", "icao", "annex 19", "doc 9859", "easa", "faa", "compliance",
    "regulator", "caan", "ssp", "audit", "inspection", "hfacs", "human factors",
    "fatigue", "bird strike", "turbulence", "fuel", "engine", "crew", "pilot",
    "training", "emergency", "evacuation", "corrective action", "investigation",
    "root cause", "fishbone", "sra", "state safety", "certification", "landing",
    "takeoff", "near miss", "runway incursion", "ground handling", "de-icing",
    "airworthiness directive", "safety culture", "safety climate", "just culture",
    "operational",
)

INJECTION_MARKERS = (
    "ignore previous instructions", "ignore all previous instructions",
    "ignore all prior instructions", "disregard previous instructions",
    "disregard your instructions", "forget your instructions", "forget your role",
    "forget all instructions", "system prompt", "reveal your system prompt",
    "repeat your system prompt", "print your system prompt",
    "what is your system prompt", "what are your instructions",
    "show your instructions", "jailbreak", "developer mode", "dan mode",
    "do anything now", "act as a", "act as though", "you are now",
    "from now on", "new persona", "ignore your role", "ignore the rules",
    "override your instructions", "bypass your",
)

OFF_TOPIC_MARKERS = (
    "recipe", "cooking", "bake a", "poem", "poetry", "song", "lyrics", "joke",
    "stock market", "crypto", "bitcoin", "invest", "politics", "election",
    "celebrity", "horoscope", "astrology", "capital of", "geography", "movie",
    "video game", "playstation", "xbox", "football", "cricket", "homework",
    "translate", "write code", "python", "javascript", "html", "css",
    "programming", "hack", "crack", "credit card", "password",
)

SAFETY_BOUNDARY_REPLY = (
    "I'm **Ghanshyam** — Executive Safety & SMS Copilot. I'm strictly focused on "
    "aviation safety and compliance: Safety Management Systems (ICAO Annex 19 / "
    "Doc 9859), flight operations, airworthiness & Part-145, safety climate, and "
    "regulatory compliance (CAAN / EASA / FAA).\n\n"
    "I can't help with that request. If you have an aviation-safety question — hazard "
    "identification, reporting (VSR/MOR), risk assessment, corrective actions, or SMS "
    "implementation — I'm glad to assist. For anything else, please contact the "
    "AviaSAFE team at info@aviasafesystems.com."
)

INJECTION_REPLY = (
    "I can't comply with that request. As AviaSAFE's Safety & SMS Copilot, my "
    "operating boundaries are fixed to aviation safety guidance (ICAO Annex 19 / "
    "Doc 9859), and I do not respond to attempts to override, reveal, or bypass them.\n\n"
    "Please ask an aviation-safety question — hazard reporting, risk assessment, "
    "corrective actions, or SMS compliance — and I'll be glad to help."
)


def enforce_safety_boundary(
    message: str, history: Optional[List[Dict[str, Any]]] = None
) -> Optional[str]:
    """Return a canned boundary reply when the input violates the safety scope.

    Rejects prompt-injection attempts outright and redirects clearly off-topic
    queries (unless they also touch an aviation-safety topic). Returns None when
    the message is in scope and may be passed to the model.
    """
    texts = [message] + [str((entry or {}).get("content") or "") for entry in (history or [])]
    joined = " ".join(texts).lower()

    if any(marker in joined for marker in INJECTION_MARKERS):
        logger.warning("Copilot prompt-injection attempt blocked")
        return INJECTION_REPLY

    if any(marker in joined for marker in OFF_TOPIC_MARKERS) and not any(
        marker in joined for marker in SAFETY_TOPIC_MARKERS
    ):
        logger.info("Copilot off-topic query redirected to aviation-safety scope")
        return SAFETY_BOUNDARY_REPLY

    return None


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

    return (
        COPILOT_SYSTEM_PROMPT
        + COPILOT_GUARDRAILS
        + PAGE_SCOPE_BOUNDARY
        + build_page_scope_instruction(page_context)
        + context_block
    )


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


def time_salutation() -> str:
    """Time-based greeting from the server's local clock.

    Morning 00:00-11:59, afternoon 12:00-16:59, evening/night 17:00-23:59.
    """
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning and welcome aboard."
    if hour < 17:
        return "Good afternoon and welcome aboard."
    return "Good evening and welcome aboard."


def _offline_reply(message: str) -> str:
    """Graceful fallback when Groq is unavailable (API key missing / error)."""
    topic = sanitize_message(message, 120)
    return (
        f"{time_salutation()} I am **Ghanshyam** - Executive Safety & SMS Copilot. "
        "I'm standing by, but the Groq assistant service is currently unavailable - "
        "please try again in a moment. "
        f"(Your message was received: \"{topic or '(empty)'}\".)\n\n"
        "While offline, remember: log every hazard or occurrence through the correct "
        "reporting path (VSR for voluntary/confidential, MOR for mandatory), classify it "
        "on the ICAO 5x5 SRA matrix, and raise a CAN whenever the risk is Tolerable or higher."
    )


def _groq_error_detail(e: Exception) -> Dict[str, Any]:
    """Extract the exact HTTP status code + message from a Groq SDK error.

    Groq's SDK exposes ``status_code`` (e.g. 401 / 429 / 400) and ``message``
    on its APIError subclasses; ``body`` carries the raw JSON error payload.
    """
    return {
        "status_code": getattr(e, "status_code", None),
        "message": getattr(e, "message", None) or str(e),
        "type": getattr(e, "type", None) or type(e).__name__,
        "body": getattr(e, "body", None),
    }


def _innermost_exception(e: Exception) -> str:
    """Walk the exception chain to the bottom-most underlying error.

    Groq SDK errors often wrap an httpx / connection / auth failure in their
    ``__cause__`` chain; surfacing that exact cause is what makes server logs
    actionable instead of showing only the outer APIError.
    """
    cause = getattr(e, "__cause__", None) or getattr(e, "__context__", None)
    if cause is not None and cause is not e:
        return _innermost_exception(cause)
    return f"{type(e).__name__}: {e}"


def _is_model_rejected(e: Exception) -> bool:
    """True when Groq rejected the requested model (HTTP 400/404 'model not found').

    Used by the defensive fallback: if the configured model is valid-looking but
    Groq still rejects it (deprecated, unavailable on the plan, typo in a new
    deployment), we retry once with GROQ_MODEL_NAME instead of dropping straight
    into the offline reply.
    """
    status = getattr(e, "status_code", None)
    if status not in (400, 404):
        return False
    message = str(getattr(e, "message", "") or "")
    body = getattr(e, "body", None)
    text = "{} {}".format(message, body if body is not None else "").lower()
    markers = (
        "model_not_found",
        "model not found",
        "unknown model",
        "does not exist",
        "no model found",
        "model_id",
        "model id",
        "invalid model",
    )
    return any(marker in text for marker in markers)


_client_lock = threading.Lock()
# Lazily-created reusable Groq clients. Keyed by (api_key, Groq class) so the
# same client is shared across requests (no per-request re-instantiation) while
# a swap of the groq module/class (e.g. tests, SDK upgrade) still yields a new
# client instead of a stale cached one.
_client_cache: Dict[tuple, Any] = {}


def _get_groq_client(api_key: str) -> Any:
    """Return a lazily-initialised, reusable Groq client or None on failure.

    Thread-safe: concurrent requests share one client instance. Initialisation
    errors (missing SDK, auth/transport setup failures) are logged with the
    bottom-most cause and degrade to ``None`` so callers return the offline reply.
    """
    from groq import Groq

    cache_key = (api_key, Groq)
    cached = _client_cache.get(cache_key)
    if cached is not None:
        return cached
    with _client_lock:
        cached = _client_cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            client = Groq(api_key=api_key)
        except Exception as e:
            logger.exception(
                "Groq client initialization failed (bottom-most cause: {})",
                _innermost_exception(e),
            )
            return None
        _client_cache[cache_key] = client
        return client


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
    offline reply so the frontend chat widget keeps working. The exact Groq
    HTTP status code and error message are logged on every failure.
    """
    api_key = os.environ.get("GROQ_API_KEY") or settings.GROQ_API_KEY
    boundary_reply = enforce_safety_boundary(message, history)
    if boundary_reply:
        return boundary_reply
    if not api_key:
        logger.warning(
            "GROQ_API_KEY is not set in the environment — copilot returning offline reply. "
            "Set GROQ_API_KEY in the deployment environment (Render dashboard) to enable Groq."
        )
        return _offline_reply(message)

    client = _get_groq_client(api_key)
    if client is None:
        logger.error("Groq client unavailable (initialization failed) — copilot returning offline reply")
        return _offline_reply(message)

    tenant_classification = tenant_id and get_tenant_classification(tenant_id)
    messages = build_messages(
        message,
        history=history,
        role=role,
        department=department,
        tenant_id=tenant_id,
        tenant_classification=tenant_classification,
        page_context=page_context,
    )
    # Payload shape: [{"role": "system", "content": system_prompt}, ...history...,
    #                 {"role": "user", "content": user_message}]. Log the shape
    # (not the content) so request structure issues are immediately visible.
    model = resolve_groq_model()
    logger.debug(
        "Groq payload: model=%s messages=%d (first=%s, last=%s) max_tokens=%s temperature=%s stream=False",
        model,
        len(messages),
        messages[0].get("role") if messages else None,
        messages[-1].get("role") if messages else None,
        settings.GROQ_MAX_TOKENS,
        settings.GROQ_TEMPERATURE,
    )
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=settings.GROQ_TEMPERATURE,
            max_tokens=settings.GROQ_MAX_TOKENS,
            stream=False,
        )
        reply = completion.choices[0].message.content
        if not reply:
            logger.warning("Groq returned an empty completion — copilot returning offline reply")
        return reply.strip() if reply else _offline_reply(message)
    except Exception as e:
        detail = _groq_error_detail(e)
        logger.exception(
            "Groq API error encountered: {} (status={}, message={}, bottom-most={})",
            str(e),
            detail["status_code"],
            detail["message"],
            _innermost_exception(e),
        )
        logger.error(
            "Groq error payload: status={} type={} message={} body={}",
            detail["status_code"],
            detail["type"],
            detail["message"],
            detail["body"],
        )
        # Defensive fallback: a valid-looking but rejected model (HTTP 400/404
        # 'model not found' — deprecated / unavailable on the plan) retries once
        # with the proven GROQ_MODEL_NAME before degrading to the offline reply.
        if model != GROQ_MODEL_NAME and _is_model_rejected(e):
            logger.warning(
                "Groq rejected model {!r} (status={}, message={}) — retrying once with fallback model {!r}",
                model,
                detail["status_code"],
                detail["message"],
                GROQ_MODEL_NAME,
            )
            try:
                completion = client.chat.completions.create(
                    model=GROQ_MODEL_NAME,
                    messages=messages,
                    temperature=settings.GROQ_TEMPERATURE,
                    max_tokens=settings.GROQ_MAX_TOKENS,
                    stream=False,
                )
                reply = completion.choices[0].message.content
                return reply.strip() if reply else _offline_reply(message)
            except Exception as e2:
                detail2 = _groq_error_detail(e2)
                logger.exception(
                    "Groq fallback model {!r} also failed: {} (status={}, message={}, bottom-most={})",
                    GROQ_MODEL_NAME,
                    str(e2),
                    detail2["status_code"],
                    detail2["message"],
                    _innermost_exception(e2),
                )
        return _offline_reply(message)