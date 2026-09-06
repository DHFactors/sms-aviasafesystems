# ============================================================================
# PG ↔ fake-Firestore test bridge
# ============================================================================
# During the Firestore→Postgres migration, migrated modules route all document
# I/O through app/db/pg.py. Legacy tests patch `get_db` on those modules to
# inject an in-memory fake Firestore. This bridge re-routes pg calls through
# the same fake (keyed by SQLAlchemy ``__tablename__``) so existing tests keep
# asserting against their fake stores without a database.
#
# Usage in a test:
#     from pg_bridge import patch_pg_through
#     patch_pg_through(monkeypatch, lambda: db)   # or db / () -> db
# ============================================================================

from sqlalchemy.sql.elements import BinaryExpression

from app.db import pg as pg_mod

# Firestore-style collection names our fake DBs expose for the new domain
# tables (model __tablename__ == fake collection name already for these).
_ID_KEYS = ("slug", "uid", "id", "report_id", "code")


def _col_name(node):
    name = getattr(node, "name", None)
    if name:
        return name
    clause = getattr(node, "clause", None)  # Cast / Coalesce wrapper
    if clause is not None:
        return _col_name(clause)
    # JSONB extraction (column['key'] / column['key'].astext): a nested
    # BinaryExpression whose right side is the literal key string.
    if isinstance(node, BinaryExpression):
        right = getattr(node, "right", None)
        if isinstance(right, str):
            return right
        value = getattr(right, "value", None)
        if isinstance(value, str):
            return value
    return None


def _simple_eq(expr):
    """Best-effort (field, value) from a `==` BinaryExpression.

    Plain-column equality is mirrored onto the fake docs. JSONB path filters
    (data['x'].astext == v, safety_manager['email'].astext == v) map to the
    extracted path key so Firestore-style fakes can apply the comparison.
    """
    if not isinstance(expr, BinaryExpression):
        return None, None
    if getattr(expr.operator, "__name__", None) != "eq":
        return None, None
    right = getattr(expr, "right", None)
    value = getattr(right, "value", right)
    return _col_name(getattr(expr, "left", None)), value


def _fetch_all(db, model, *, where=None, order_by=None, limit=None):
    coll = db.collection(model.__tablename__)
    conds = []
    for cond in where or []:
        field, value = _simple_eq(cond)
        conds.append((field, value))

    all_simple = all(field is not None for field, _ in conds)
    if all_simple and hasattr(coll, "where"):
        q = coll
        for field, value in conds:
            q = q.where(field, "==", value)
        if limit and hasattr(q, "limit"):
            q = q.limit(limit)
        rows = []
        for snap in q.get():
            data = dict(snap.to_dict())
            data.setdefault("id", getattr(snap, "id", None))
            rows.append(data)
        return rows

    if not hasattr(coll, "get"):
        return []  # cannot enumerate the collection on the fake
    docs = []
    for snap in coll.get():
        data = dict(snap.to_dict())
        data.setdefault("id", getattr(snap, "id", None))
        if all(field is None or data.get(field) == value for field, value in conds):
            docs.append(data)
    if limit:
        docs = docs[:limit]
    return docs


def _fetch_by(db, model, col, value):
    coll = db.collection(model.__tablename__)
    if col in _ID_KEYS:
        snap = coll.document(value).get()
        if getattr(snap, "exists", True) is False:
            return None
        data = dict(snap.to_dict())
        if not data:
            return None
        data.setdefault("id", getattr(snap, "id", None) or value)
        return data
    for snap in coll.get():
        data = dict(snap.to_dict())
        if data.get(col) == value:
            data.setdefault("id", getattr(snap, "id", None))
            return data
    return None


def _set_ref(ref, data, merge=True):
    try:
        ref.set(dict(data), merge=merge)
    except TypeError:
        ref.set(dict(data))


def _upsert(db, model, col, value, data):
    coll = db.collection(model.__tablename__)
    _set_ref(coll.document(value), data)


def _insert(db, model, data):
    id_col = pg_mod._ID_COLUMNS.get(model.__tablename__) or "id"
    id_value = (data or {}).get(id_col)
    _upsert(db, model, id_col, str(id_value), data)


def _update(db, model, col, value, doc):
    coll = db.collection(model.__tablename__)
    ref = coll.document(value)
    if hasattr(ref, "update"):
        ref.update(dict(doc))
        return
    snap = ref.get()
    merged = dict(snap.to_dict()) if getattr(snap, "exists", True) else {}
    merged.update(dict(doc))
    _set_ref(ref, merged)


def patch_pg_through(monkeypatch, db_or_getter):
    """Route app/db/pg.py I/O through a fake-firestore `db` (or () -> db)."""
    get_db = db_or_getter if callable(db_or_getter) else (lambda: db_or_getter)

    monkeypatch.setattr(
        pg_mod, "fetch_all",
        lambda model, **kw: _fetch_all(get_db(), model, **kw),
    )
    monkeypatch.setattr(
        pg_mod, "fetch_by",
        lambda model, col, value: _fetch_by(get_db(), model, col, value),
    )
    monkeypatch.setattr(
        pg_mod, "upsert",
        lambda model, col, value, data: _upsert(get_db(), model, col, value, data),
    )
    monkeypatch.setattr(
        pg_mod, "insert",
        lambda model, data: _insert(get_db(), model, data),
    )
    monkeypatch.setattr(
        pg_mod, "update",
        lambda model, col, value, doc: _update(get_db(), model, col, value, doc),
    )