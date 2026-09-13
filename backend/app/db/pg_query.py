# ============================================================================
# FILE: pg_query.py
# PATH: backend/app/db/pg_query.py
# PURPOSE: Firestore-shaped query adapter over the Postgres bridge for the
#          master register (A2). Provides a chainable query collection
#          (.where/.order_by/.limit/.start_after/.get/.count) and a document
#          wrapper (.id/.to_dict()/.reference) so the master_register query
#          layer keeps working now that the Firestore client has been removed.
#
#          DESIGN: the adapter always fetches via pg.fetch_all(model,
#          where=<collection-scope clauses>), so tenant isolation stays
#          SQL-side. The remaining chainable filters mirror the semantics the
#          Firestore query engine gave master_register; because
#          master_register re-validates every match in Python
#          (department/status/assignee/search), results are identical to the
#          removed Firestore path.
# ============================================================================

from __future__ import annotations

import uuid as _uuid
from typing import Any, Dict, List, Optional

from loguru import logger

from app.db import pg
from app.db.db_models import Can, Cap, Hazard

DESCENDING = "descending"
ASCENDING = "ascending"

# Firestore collection name -> Postgres model exposed as that collection.
_MODEL_BY_COLLECTION = {
    "hazards": Hazard,
    "can_cap": Can,
    "caps": Cap,
}


def _is_uuid(value: Any) -> bool:
    try:
        _uuid.UUID(str(value))
        return True
    except Exception:
        return False


def _tenant_uuid_of(tenant_id: Any) -> _uuid.UUID:
    """Map a tenant slug (or existing uuid string) onto the PG tenant id."""
    from app.db.ids import tenant_uuid

    s = str(tenant_id)
    if _is_uuid(s):
        return _uuid.UUID(s)
    return _uuid.UUID(tenant_uuid(s))


def _norm(value: Any) -> Any:
    if isinstance(value, _uuid.UUID):
        return str(value)
    if isinstance(value, bytes):
        try:
            return value.decode()
        except Exception:
            return value
    return value


def _compare(a: Any, b: Any, op: str) -> bool:
    try:
        if a is None or b is None:
            return False
        if not (isinstance(a, type(b)) or isinstance(b, type(a))):
            return False
        if op == ">=":
            return a >= b
        if op == "<=":
            return a <= b
        if op == "<":
            return a < b
        if op == ">":
            return a > b
        return a == b
    except Exception:
        return False


def _match(doc: Dict[str, Any], field: str, op: str, value: Any) -> bool:
    """Apply a Firestore-style where() clause on a flattened document.

    ``tenant_id`` is normalized on both sides onto string UUIDs: PG rows expose
    the typed UUID column while master_register passes the claim slug, so a
    naive string compare would silently drop every row.
    """
    actual = doc.get(field)
    if field == "tenant_id":
        expected = value
        if not _is_uuid(value):
            try:
                expected = str(_tenant_uuid_of(value))
            except Exception:
                expected = str(value)
        a, b = str(_norm(actual) or ""), str(_norm(expected) or "")
        if op == "==":
            return a == b
        return _compare(a, b, op)

    a, b = _norm(actual), _norm(value)
    if op == "==":
        if a is None and b is None:
            return True
        if a is None or b is None:
            return False
        if isinstance(a, type(b)) or isinstance(b, type(a)):
            try:
                return a == b
            except Exception:
                return str(a) == str(b)
        return str(a) == str(b)
    return _compare(a, b, op)


class QueryReference:
    """Minimal reference exposing ``.collection()`` (the per-CAN CAP fallback
    path) and a synthetic ``.path``/``._path`` for master_register's can-path
    inference on caps without a resolvable ``can_id`` field."""

    def __init__(self, owner: "QueryDoc"):
        self._owner = owner
        self._path = getattr(owner, "_synthetic_path", "") or ""
        self.path = self._path
        self._path = self._path

    def collection(self, name: str):
        if name != "caps":
            raise AssertionError(f"unexpected collection {name}")
        owner_id = self._owner.id
        if not owner_id or not _is_uuid(owner_id):
            return Query(Cap)
        return Query(Cap, scope_where=[Cap.can_id == _uuid.UUID(owner_id)])


class QueryDoc:
    """Firestore-shaped document wrapper consumed by the master register."""

    def __init__(
        self,
        doc: Dict[str, Any],
        model: Optional[type] = None,
        synthetic_path: Optional[str] = None,
    ):
        self._doc = doc
        self.id = str(doc.get("id") or "")
        self._synthetic_path = synthetic_path or ""
        self.reference = QueryReference(self)
        self._model = model

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._doc)

    def get(self, field: str, default: Any = None) -> Any:
        return self._doc.get(field, default)


class _CountValue:
    __slots__ = ("value",)

    def __init__(self, value: int):
        self.value = value


class _CountResult:
    """Shape for ``q.count().get()`` -> [<value wrapper>], matching the
    Firestore aggregation result the master register reads (``cnt[0].value``)."""

    def __init__(self, query: "Query"):
        self._query = query

    def get(self) -> List[_CountValue]:
        return [_CountValue(len(self._query._all_docs()))]


class Query:
    """Chainable Firestore-ish query over pg.fetch_all.

    Instances are immutable: every builder method returns a new Query so the
    existing master_register call chains (which reuse the intermediate query in
    fallbacks) behave exactly as they did against Firestore.
    """

    def __init__(
        self,
        model: type,
        scope_where: Optional[List[Any]] = None,
        filters: Optional[List[Any]] = None,
        order_field: Optional[str] = None,
        order_reverse: bool = False,
        limit_n: Optional[int] = None,
        after_field: Optional[str] = None,
        after_value: Any = None,
    ):
        self._model = model
        self._scope_where = list(scope_where or [])
        self._filters = list(filters or [])
        self._order_field = order_field
        self._order_reverse = order_reverse
        self._limit_n = limit_n
        self._after_field = after_field
        self._after_value = after_value

    def where(self, field: str, op: str, value: Any) -> "Query":
        return Query(
            self._model,
            self._scope_where,
            self._filters + [(field, op, value)],
            self._order_field,
            self._order_reverse,
            self._limit_n,
            self._after_field,
            self._after_value,
        )

    def order_by(self, field: str, direction: Optional[str] = None) -> "Query":
        return Query(
            self._model,
            self._scope_where,
            self._filters,
            field,
            direction == DESCENDING,
            self._limit_n,
            self._after_field,
            self._after_value,
        )

    def limit(self, n: Optional[int]) -> "Query":
        amount = None if n is None else int(n)
        return Query(
            self._model,
            self._scope_where,
            self._filters,
            self._order_field,
            self._order_reverse,
            amount,
            self._after_field,
            self._after_value,
        )

    def start_after(self, value: Any) -> "Query":
        """Strictly-after pagination on the order field (Firestore semantics)."""
        field = self._order_field or "created_at"
        v = value
        if isinstance(value, dict) and value:
            field = next(iter(value.keys()), field)
            v = next(iter(value.values()))
        return Query(
            self._model,
            self._scope_where,
            self._filters,
            self._order_field,
            self._order_reverse,
            self._limit_n,
            field,
            v,
        )

    def _all_docs(self) -> List[Dict[str, Any]]:
        """Fetch (scope-limited) rows and apply filters/ordering in-memory."""
        where = self._scope_where or None
        try:
            rows = pg.fetch_all(self._model, where=where)
        except Exception as e:
            logger.warning(f"[pg_query] fetch_all failed (table={self._model.__tablename__}): {e}")
            rows = []
        docs: List[Dict[str, Any]] = [dict(r) for r in rows or []]
        for field, op, value in self._filters:
            docs = [d for d in docs if _match(d, field, op, value)]
        if self._after_field is not None:
            docs = [d for d in docs if _match(d, self._after_field, "<", self._after_value)]
        if self._order_field:
            key = self._order_field
            try:
                docs.sort(
                    key=lambda d: (d.get(key) is None, d.get(key)),
                    reverse=self._order_reverse,
                )
            except Exception:
                pass
        return docs

    def get(self) -> List[QueryDoc]:
        docs = self._all_docs()
        if self._limit_n is not None:
            docs = docs[: self._limit_n]
        out: List[QueryDoc] = []
        for d in docs:
            path = None
            if self._model is Cap:
                d = dict(d)
                cid = d.get("can_id")
                if cid is not None:
                    d["can_id"] = str(cid) if not isinstance(cid, str) else cid
                if d.get("can_id") and d.get("tenant_id") is not None:
                    path = (
                        f"tenants/{_norm(d['tenant_id'])}/can_cap/"
                        f"{d['can_id']}/caps/{d.get('id')}"
                    )
            out.append(QueryDoc(d, self._model, synthetic_path=path))
        return out

    def count(self) -> _CountResult:
        return _CountResult(self)


class _DB:
    """Stand-in for the removed Firestore client, exposing the CAP group path
    the master register uses to batch-fetch caps (``collection_group``)."""

    def collection_group(self, name: str) -> Query:
        model = _MODEL_BY_COLLECTION.get(name)
        if model is None:
            raise ValueError(f"unknown collection_group {name}")
        return Query(model)


def get_db() -> "_DB":
    return _DB()


def get_tenant_collection(tenant_id: str, collection: str) -> Query:
    model = _MODEL_BY_COLLECTION.get(collection)
    if model is None:
        raise ValueError(f"unknown collection {collection}")
    return Query(model, scope_where=[model.tenant_id == _tenant_uuid_of(tenant_id)])


def get_cross_tenant_collection(collection: str) -> Query:
    model = _MODEL_BY_COLLECTION.get(collection)
    if model is None:
        raise ValueError(f"unknown collection {collection}")
    return Query(model)