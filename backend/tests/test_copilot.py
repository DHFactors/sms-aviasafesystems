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

    def __init__(self, **kwargs):
        pass


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
    assert kwargs["model"] == "llama-3.3-70b-versatile"
    assert kwargs["temperature"] == groq_copilot.settings.GROQ_TEMPERATURE


def test_chat_unauthorized_returns_401(monkeypatch):
    _patch_env(monkeypatch, groq=True)
    resp = _chat(authorized=False)
    assert resp.status_code in (401, 403)


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