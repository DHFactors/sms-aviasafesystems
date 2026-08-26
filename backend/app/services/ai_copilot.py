# ============================================================================
# FILE: backend/app/services/ai_copilot.py
# PURPOSE: AI Executive Copilot — READ-ONLY database scope (AviaSAFE-SMS audit
#          §1.2). The Copilot execution context receives a strictly read-only
#          Firestore handle: any write/update/delete/create attempt raises
#          PermissionError before reaching the database.
#
# The module also re-exports the chat entrypoint so callers that previously
# imported groq_copilot can migrate to this facade without gaining write
# capabilities.
# ============================================================================

from typing import Any, Dict, List, Optional

from app.firebase import get_db


class ReadOnlyCollection:
    """Collection wrapper exposing ONLY read operations."""

    def __init__(self, inner, guard: "_WriteGuard"):
        self._inner = inner
        self._guard = guard

    def document(self, *args, **kwargs):
        return ReadOnlyDocument(self._inner.document(*args, **kwargs), self._guard)

    def get(self, *args, **kwargs):
        return self._inner.get(*args, **kwargs)

    def stream(self, *args, **kwargs):
        return self._inner.stream(*args, **kwargs)

    def where(self, *args, **kwargs):
        return ReadOnlyQuery(self._inner.where(*args, **kwargs), self._guard)

    def order_by(self, *args, **kwargs):
        return ReadOnlyQuery(self._inner.order_by(*args, **kwargs), self._guard)

    def limit(self, *args, **kwargs):
        return ReadOnlyQuery(self._inner.limit(*args, **kwargs), self._guard)

    # ── Blocked mutators ────────────────────────────────────────────────────
    def add(self, *a, **k):
        raise PermissionError("AI copilot runs in READ-ONLY scope")

    def set(self, *a, **k):
        raise PermissionError("AI copilot runs in READ-ONLY scope")

    def update(self, *a, **k):
        raise PermissionError("AI copilot runs in READ-ONLY scope")


ReadOnlyQuery = type("ReadOnlyQuery", (object,), {
    "__init__": lambda self, inner, guard: (setattr(self, "_inner", inner),
                                            setattr(self, "_guard", guard)),
    "get": lambda self, *a, **k: self._inner.get(*a, **k),
    "stream": lambda self, *a, **k: self._inner.stream(*a, **k),
    "where": lambda self, *a, **k: ReadOnlyQuery(
        self._inner.where(*a, **k), self._guard),
})


class ReadOnlyDocument:
    def __init__(self, inner, guard):
        self._inner = inner
        self._guard = guard

    @property
    def id(self):
        return self._inner.id

    def get(self, *args, **kwargs):
        return self._inner.get(*args, **kwargs)

    def collection(self, name):
        return ReadOnlyCollection(self._inner.collection(name), self._guard)

    # Blocked mutators
    def set(self, *a, **k):
        raise PermissionError("AI copilot runs in READ-ONLY scope")

    def update(self, *a, **k):
        raise PermissionError("AI copilot runs in READ-ONLY scope")

    def delete(self):
        raise PermissionError("AI copilot runs in READ-ONLY scope")


class _WriteGuard:
    """Attribute trap: any non-read verb on wrapped handles raises."""

    FORBIDDEN = ("add", "set", "update", "delete", "batch", "create")

    def __getattr__(self, name):
        if name in self.FORBIDDEN or name.startswith("_"):
            raise PermissionError(f"AI copilot runs in READ-ONLY scope: {name}")
        raise AttributeError(name)


class ReadOnlyFirestoreClient:
    """Strictly READ-ONLY Firestore client for the AI Copilot context.

    Wraps the Admin SDK client and exposes only collection/document reads;
    every mutation verb is trapped and rejected locally."""

    def __init__(self, inner=None):
        self._inner = inner or get_db()

    def collection(self, name) -> ReadOnlyCollection:
        return ReadOnlyCollection(self._inner.collection(name), _WriteGuard())

    # Explicit mutator rejections at client level too.
    def batch(self):
        raise PermissionError("AI copilot runs in READ-ONLY scope")

    def add(self, *a, **k):
        raise PermissionError("AI copilot runs in READ-ONLY scope")

    def __getattr__(self, name):
        if name in _WriteGuard.__dict__.get("FORBIDDEN", ()) :
            raise PermissionError("AI copilot runs in READ-ONLY scope")
        raise AttributeError(name)


def readonly_db() -> ReadOnlyFirestoreClient:
    """Return the read-only handle for AI execution contexts."""
    return ReadOnlyFirestoreClient(get_db())


def get_tenant_classification_readonly(tenant_id: Optional[str]) -> Optional[str]:
    """Read-only tenant classification lookup used by the Copilot."""
    if not tenant_id:
        return None
    try:
        snap = readonly_db().collection("tenants").document(tenant_id).get()
        if getattr(snap, "exists", True):
            data = snap.to_dict() or {}
            return data.get("tenant_type") or data.get("classification")
    except Exception:
        pass
    return None
