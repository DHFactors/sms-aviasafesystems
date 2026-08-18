"""Safety & Compliance Copilot chat endpoint + service tests.

Covers:
  * POST /api/v1/copilot/chat -- 200 with a real (mocked) Groq reply when a
    Firebase JWT is present, 401 without one.
  * Graceful degradation: missing GROQ_API_KEY and upstream Groq failures still
    return 200 with a helpful offline reply (the widget must never hang).
  * Context injection: role / department / tenant classification / page_context
    reach the Groq messages payload.
  * Prompt-injection sanitisation on user input.
"""

import sys

from fastapi.testclient import TestClient

from app.main import app
from app.services import groq_copilot


# ============================================================================
# Fakes
# ============================================================================

class _FakeTenantDoc:
    def __init__(self, data, exists=True):
        self._data = data or {}
        self.exists = exists

    def to_dict(self):
        return self._data


class _FakeTenantRef:
    def __init__(self, db, tid):
        self._db = db
        self._tid = tid

    def get(self):
        if self._tid not in self._db.tenants:
            return _FakeTenantDoc(None, exists=False)
        return _FakeTenantDoc(dict(self._db.tenants[self._tid]))


class _FakeTenantsColl:
    def __init__(self, db):
        self._db = db

    def document(self, tid):
        return _FakeTenantRef(self._db, tid)


class _FakeDB:
    def __init__(self):
        self.tenants = {}

    def collection(self, name):
        if name == "tenants":
            return _FakeTenantsColl(self)
        raise AssertionError(f"unexpected collection {name}")


class _FakeGroqMessage:
    def __init__(self, content):
        self.content = content


class _FakeGroqChoice:
    def __init__(self, content):
        self.message = _FakeGroqMessage(content)


class _FakeGroqCompletion:
    def __init__(self, content):
        self.choices = [_FakeGroqChoice(content)]


class _FakeGroqCompletions:
    last_kwargs = None

    @classmethod
    def create(cls, **kwargs):
        cls.last_kwargs = dict(kwargs)
        return _FakeGroqCompletion(
            "Use the 5x5 SRA matrix: classify severity vs probability, then decide accept/tolerate/action."
        )


class _FakeGroqChat:
    completions = _FakeGroqCompletions


class _FakeGroqClient:
    chat = _FakeGroqChat
    last_api_key = None

    def __init__(self, **kwargs):
        _FakeGroqClient.last_api_key = kwargs.get("api_key")


class _FakeGroqModule:
    Groq = _FakeGroqClient


# ============================================================================
# Patching helpers
# ============================================================================

def _patch_env(monkeypatch, db=None, groq=True, api_key="gsk_test_key"):
    def _fake_verify_firebase_token(token):
        return {
            "uid": "u-admin",
            "email": "admin@yeti.com.np",
            "role": "AIRLINE_ADMIN",
            "tenant_id": "yeti-airlines",
            "department": "safety",
        }
    monkeypatch.setattr("app.middleware.auth.verify_firebase_token", _fake_verify_firebase_token)
    monkeypatch.setattr(groq_copilot.settings, "GROQ_API_KEY", api_key)
    if db is not None:
        monkeypatch.setattr("app.services.groq_copilot.get_db", lambda: db)
    if groq:
        monkeypatch.setitem(sys.modules, "groq", _FakeGroqModule())


def _chat(payload=None, headers=None, authorized=True):
    body = payload or {"message": "How do I classify a bird strike?"}
    req_headers = {"Authorization": "Bearer faketoken"} if authorized else {}
    if headers:
        req_headers.update(headers)
    return TestClient(app).post("/api/v1/copilot/chat", json=body, headers=req_headers)


def _seed_tenant(db, classification="AIRLINE_FIXED_WING"):
    db.tenants["yeti-airlines"] = {
        "tenant_id": "yeti-airlines",
        "name": "Yeti Airlines",
        "tenant_type": classification,
        "classification": classification,
    }


# ============================================================================
# POST /api/v1/copilot/chat
# ============================================================================

def test_chat_returns_mocked_groq_reply(monkeypatch):
    db = _FakeDB()
    _seed_tenant(db)
    _patch_env(monkeypatch, db=db)

    resp = _chat()

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "5x5 SRA" in data["reply"]
    assert data["model"] == "groq"


def test_chat_injects_context_into_groq_payload(monkeypatch):
    db = _FakeDB()
    _seed_tenant(db)
    module = _FakeGroqModule()
    monkeypatch.setitem(sys.modules, "groq", module)
    _patch_env(monkeypatch, db=db, groq=False)

    resp = _chat({
        "message": "What CAP timeline is acceptable?",
        "page_context": "Corrective Action Plans",
        "history": [
            {"role": "user", "content": "What CAP timeline is acceptable?"},
        ],
    })

    assert resp.status_code == 200
    kwargs = _FakeGroqCompletions.last_kwargs
    messages = kwargs["messages"]
    system_content = messages[0]["content"]
    assert "AIRLINE_FIXED_WING" in system_content
    assert "AIRLINE_ADMIN" in system_content
    assert "safety" in system_content
    assert "Corrective Action Plans" in system_content
    assert messages[-1] == {"role": "user", "content": "What CAP timeline is acceptable?"}
    assert kwargs["model"] == "openai/gpt-oss-120b"
    assert kwargs["temperature"] == groq_copilot.settings.GROQ_TEMPERATURE


def test_chat_unauthorized_returns_401(monkeypatch):
    _patch_env(monkeypatch, groq=True)
    resp = _chat(authorized=False)
    assert resp.status_code in (401, 403)


def test_chat_initializes_client_from_env_api_key(monkeypatch):
    module = _FakeGroqModule()
    monkeypatch.setitem(sys.modules, "groq", module)
    monkeypatch.setattr(groq_copilot.settings, "GROQ_API_KEY", None)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_from_environment")

    reply = groq_copilot.chat("How do I report a near miss?", page_context="safety.html")

    assert _FakeGroqClient.last_api_key == "gsk_from_environment"
    assert "currently unavailable" not in reply
    assert "5x5 SRA" in reply


def test_chat_uses_explicit_model_and_params(monkeypatch):
    module = _FakeGroqModule()
    monkeypatch.setitem(sys.modules, "groq", module)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key")

    groq_copilot.chat("hello", page_context="caan.html")

    kwargs = _FakeGroqCompletions.last_kwargs
    assert kwargs["model"] == "openai/gpt-oss-120b"
    assert kwargs["temperature"] == groq_copilot.settings.GROQ_TEMPERATURE
    assert kwargs["max_tokens"] == groq_copilot.settings.GROQ_MAX_TOKENS
    assert kwargs["stream"] is False


def test_build_messages_payload_structure(monkeypatch):
    _patch_env(monkeypatch, groq=False)
    messages = groq_copilot.build_messages(
        "user question",
        history=[{"role": "user", "content": "previous turn"}],
        page_context="register.html",
    )
    assert messages[0]["role"] == "system"
    assert messages[0]["content"].lstrip().startswith("You are")
    assert messages[1] == {"role": "user", "content": "previous turn"}
    assert messages[-1] == {"role": "user", "content": "user question"}


def test_chat_logs_groq_error_status_code(monkeypatch):
    class _GroqError(Exception):
        def __init__(self, status_code=429, message="rate limit hit"):
            super().__init__(message)
            self.status_code = status_code
            self.message = message
            self.type = "rate_limit_error"
            self.body = {"error": {"message": message}}

    class _BoomCompletions:
        @classmethod
        def create(cls, **kwargs):
            raise _GroqError()

    class _BoomChat:
        completions = _BoomCompletions

    class _BoomClient:
        chat = _BoomChat

        def __init__(self, **kwargs):
            pass

    class _BoomModule:
        Groq = _BoomClient

    monkeypatch.setitem(sys.modules, "groq", _BoomModule())
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key")

    from loguru import logger as loguru_logger

    sink = []
    sink_id = loguru_logger.add(sink.append, level="ERROR", format="{message}")
    try:
        reply = groq_copilot.chat("how to file a VSR", page_context="safety.html")
    finally:
        loguru_logger.remove(sink_id)

    assert "currently unavailable" in reply
    joined = "\n".join(sink)
    assert "Groq API error encountered" in joined
    assert "429" in joined
    assert "rate limit hit" in joined


def test_guest_chat_route_returns_offline_on_service_error(monkeypatch):
    _patch_env(monkeypatch, groq=True)

    def _boom(message, **kwargs):
        raise RuntimeError("service boom")

    import app.routes.copilot as copilot_route
    monkeypatch.setattr(copilot_route, "chat", _boom)

    resp = TestClient(app).post(
        "/api/v1/copilot/guest/chat",
        json={"message": "help me register my airline", "page_context": "register.html"},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert "currently unavailable" in resp.json()["reply"]


def test_guest_chat_works_without_authentication(monkeypatch):
    _patch_env(monkeypatch, groq=True)

    resp = TestClient(app).post(
        "/api/v1/copilot/guest/chat",
        json={"message": "How do I register my airline?", "page_context": "register.html — Organization registration"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["model"] == "groq"
    assert "5x5 SRA" in data["reply"]


def test_guest_chat_injects_page_context_into_groq_payload(monkeypatch):
    module = _FakeGroqModule()
    monkeypatch.setitem(sys.modules, "groq", module)
    _patch_env(monkeypatch, groq=False)

    resp = TestClient(app).post(
        "/api/v1/copilot/guest/chat",
        json={"message": "What classification fits a helicopter operator?", "page_context": "register.html — Organization registration"},
    )

    assert resp.status_code == 200
    kwargs = _FakeGroqCompletions.last_kwargs
    system_content = kwargs["messages"][0]["content"]
    # Guest chat must be strictly page-scoped (no user/tenant context).
    assert "STRICT PAGE-SCOPE BOUNDARY" in system_content
    assert "register.html" in system_content
    assert "AIRLINE_ROTARY" in system_content or "Helicopter" in system_content or "Rotary" in system_content
    assert "AIRLINE_ADMIN" not in system_content


def test_guest_chat_requires_valid_message(monkeypatch):
    _patch_env(monkeypatch, groq=True)
    resp = TestClient(app).post("/api/v1/copilot/guest/chat", json={"message": ""})
    assert resp.status_code == 422


def test_chat_without_groq_api_key_returns_graceful_200(monkeypatch):
    db = _FakeDB()
    _seed_tenant(db)
    _patch_env(monkeypatch, db=db, groq=False, api_key=None)

    resp = _chat({"message": "How do I start an RCA?"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "Ghanshyam" in data["reply"]
    assert "currently unavailable" in data["reply"]


def test_chat_when_groq_errors_returns_graceful_200(monkeypatch):
    class _BoomModule:
        class Groq:
            def __init__(self, **kw):
                raise RuntimeError("groq is down")
    monkeypatch.setitem(sys.modules, "groq", _BoomModule())
    _patch_env(monkeypatch, groq=False)

    resp = _chat({"message": "help"})

    assert resp.status_code == 200
    assert "currently unavailable" in resp.json()["reply"]


# ============================================================================
# Service-level behaviour
# ============================================================================

def test_build_messages_sanitizes_prompt_injection(monkeypatch):
    _patch_env(monkeypatch, groq=False)
    messages = groq_copilot.build_messages(
        "<script>alert(1)</script> how to report a near miss",
        page_context="Hazard Reporting",
    )
    last = messages[-1]
    assert "<script>" not in last["content"]
    assert "how to report a near miss" in last["content"]


def test_get_tenant_classification_reads_firestore(monkeypatch):
    db = _FakeDB()
    _seed_tenant(db, classification="AERODROME")
    _patch_env(monkeypatch, db=db, groq=False)
    assert groq_copilot.get_tenant_classification("yeti-airlines") == "AERODROME"
    assert groq_copilot.get_tenant_classification("missing-tenant") is None
    assert groq_copilot.get_tenant_classification(None) is None


def test_build_system_prompt_persona(monkeypatch):
    _patch_env(monkeypatch, groq=False)
    prompt = groq_copilot.build_system_prompt(role="QA", department="qa", page_context="Caps")
    assert "Ghanshyam" in prompt
    assert "Executive Safety & SMS Copilot" in prompt
    assert "ICAO Annex 19" in prompt
    assert "Doc 9859" in prompt
    assert "5x5 SRA" in prompt
    assert "5M+1E" in prompt
    assert "QA" in prompt
    assert "qa" in prompt
    assert "Caps" in prompt


def test_build_system_prompt_includes_strict_page_scope(monkeypatch):
    _patch_env(monkeypatch, groq=False)
    prompt = groq_copilot.build_system_prompt(page_context="register.html — Organization registration")
    assert "STRICT PAGE-SCOPE BOUNDARY" in prompt
    assert "only authorized to help with the workflow" in prompt or "ONLY authorized" in prompt
    assert "politely" in prompt.lower() or "Politely" in prompt
    assert "register.html" in prompt
    assert "organization self-service registration".lower() in prompt.lower()


def test_detect_page_name_parses_filename(monkeypatch):
    _patch_env(monkeypatch, groq=False)
    assert groq_copilot.detect_page_name("caan.html — State Safety Programme") == "caan.html"
    assert groq_copilot.detect_page_name("Register Your Organization — register.html") == "register.html"
    assert groq_copilot.detect_page_name("Safety Dashboard") is None
    assert groq_copilot.detect_page_name(None) is None
    assert groq_copilot.detect_page_name("") is None


def test_build_page_scope_instruction_known_page(monkeypatch):
    _patch_env(monkeypatch, groq=False)
    instruction = groq_copilot.build_page_scope_instruction("register.html — Organization registration")
    assert "register.html" in instruction
    assert "CURRENT PAGE SCOPE" in instruction
    assert "Fixed-Wing Airline" in instruction


def test_build_page_scope_instruction_unknown_page(monkeypatch):
    _patch_env(monkeypatch, groq=False)
    instruction = groq_copilot.build_page_scope_instruction("Some Unknown Dashboard")
    assert "CURRENT PAGE SCOPE" in instruction
    assert "decline or redirect" in instruction


def test_time_salutation_returns_welcome_greeting(monkeypatch):
    _patch_env(monkeypatch, groq=False)
    greeting = groq_copilot.time_salutation()
    assert "welcome aboard" in greeting
    assert greeting in (
        "Good morning and welcome aboard.",
        "Good afternoon and welcome aboard.",
        "Good evening and welcome aboard.",
    )


def test_offline_reply_uses_time_salutation_and_markdown(monkeypatch):
    _patch_env(monkeypatch, groq=False)
    reply = groq_copilot._offline_reply("how to file a VSR")
    assert "welcome aboard" in reply
    assert "**Ghanshyam**" in reply
    assert "currently unavailable" in reply
    assert "<strong>" not in reply