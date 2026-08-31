# ============================================================================
# FILE: data.py
# PATH: backend/app/routes/data.py
# PURPOSE: aviaSDCPS Universal Data Query Engine.
#
#   POST /api/v1/data/query - parse a filter expression into a parameterized
#                             SQL WHERE clause, execute against the relevant
#                             PostgreSQL register(s) under tenant isolation,
#                             apply field projection and a row limit.
#
# Supported operators: ==  !=  >  <  IN [a, b]   AND   OR   (parens)
# Datasets: all | hazards | occurrences | spis | caps
# ============================================================================

import re
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.db.ids import tenant_uuid
from app.db.session import session_scope
from app.db import db_models
from app.middleware.auth import get_tenant_user
from app.middleware.rate_limit import rate_limit
from app.services.audit_service import log_audit, request_context

router = APIRouter(prefix="/api/v1/data", tags=["Universal Data Query"])


# ── Schemas ──────────────────────────────────────────────────────────────────
class DataQueryRequest(BaseModel):
    dataset: str = "all"  # all | hazards | occurrences | spis | caps
    expression: Optional[str] = None
    fields: List[str] = Field(default_factory=list)  # field projection
    limit: int = 100


class DataQueryResponse(BaseModel):
    fields: List[str]
    rows: List[Dict[str, Any]]
    total: int


# ── Expression parser ────────────────────────────────────────────────────────
# Grammar (recursive descent, no SQL injection: identifiers are whitelisted,
# values are emitted as bound params):
#
#   expr    := or_expr
#   or_expr := and_expr ( 'OR' and_expr )*
#   and_expr:= atom ( 'AND' atom )*
#   atom    := '(' expr ')' | comparison | in_expr
#   comparison := FIELD OP value          OP in { ==, !=, >, < }
#   in_expr := FIELD 'IN' '[' value ( ',' value )* ']'

# Whitelisted field -> (list of dataset tables it applies to). Anything not
# listed is rejected with a helpful message rather than interpolated into SQL.
ALLOWED_FIELDS: Dict[str, List[str]] = {
    "status": ["hazards", "reports", "cans", "caps"],
    "severity": ["hazards", "reports", "cans"],
    "probability": ["hazards", "reports"],
    "severity_index": ["hazards", "reports", "cans"],
    "priority": ["hazards", "cans"],
    "occurrence_type": ["hazards", "reports"],
    "title": ["hazards", "reports", "cans"],
}
_ALIASES = {
    "record_type": "occurrence_type",
    "type": "occurrence_type",
    "title_desc": "title",
    "description": "title",
}
_NUMERIC_FIELDS = {"severity", "probability", "severity_index"}


class _ExprError(ValueError):
    pass


class _Parser:
    """Tiny tokenizer + recursive-descent parser yielding (sql, params)."""

    _TOKEN_RE = re.compile(
        r"\s*(==|!=|>=|<=|>|<|\(|\)|\[|\]|,|[A-Za-z_][A-Za-z0-9_]*|[0-9]*\.?[0-9]+|'[^']*'|\"[^\"]*\")"
    )

    def __init__(self, text: str):
        self._tokens: List[str] = []
        pos = 0
        while pos < len(text):
            m = self._TOKEN_RE.match(text, pos)
            if not m:
                raise _ExprError(
                    f"Unsupported character near: {text[pos:pos+20]!r}. "
                    "Supported operators: ==, !=, >, < , IN [...], AND, OR, parentheses."
                )
            tok = m.group(1)
            if tok not in (" ", ""):
                self._tokens.append(tok)
            pos = m.end()
        self._params: List[Any] = []
        # Allow chained comparison aliases to be resolved in _field().

    def _peek(self) -> Optional[str]:
        return self._tokens[0] if self._tokens else None

    def _next(self) -> str:
        if not self._tokens:
            raise _ExprError("Unexpected end of expression.")
        return self._tokens.pop(0)

    def _value(self) -> Any:
        tok = self._next()
        if (tok.startswith("'") and tok.endswith("'")) or (
            tok.startswith('"') and tok.endswith('"')
        ):
            return tok[1:-1]
        if tok == "True" or tok == "true":
            return True
        if tok == "False" or tok == "false":
            return False
        try:
            return int(tok)
        except ValueError:
            try:
                return float(tok)
            except ValueError:
                return tok

    @staticmethod
    def _field(name: str) -> str:
        alias = _ALIASES.get(name.lower(), name.lower())
        if alias not in ALLOWED_FIELDS:
            raise _ExprError(
                f"Unsupported field '{name}'. Allowed fields: "
                f"{sorted(ALLOWED_FIELDS)}."
            )
        return alias

    def _comparison(self):
        field = self._field(self._next())
        op = self._next()
        if op not in ("==", "!=", ">", "<", ">=", "<="):
            raise _ExprError(f"Expected ==, !=, >, < after field, got '{op}'.")
        value = self._value()
        param = f"p{len(self._params)}"
        self._params.append(value)
        return f"{field} {op} :{param}"

    def _in_expr(self):
        field = self._field(self._next())
        if self._next() != "IN":
            raise _ExprError("Expected IN after field.")
        if self._next() != "[":
            raise _ExprError("Expected '[' after IN.")
        values = [self._value()]
        while self._peek() == ",":
            self._next()
            values.append(self._value())
        if self._next() != "]":
            raise _ExprError("Expected ']' to close IN list.")
        params = []
        placeholders = []
        for v in values:
            param = f"p{len(self._params)}"
            self._params.append(v)
            placeholders.append(f":{param}")
        return f"{field} IN ({', '.join(placeholders)})"

    def _atom(self):
        tok = self._peek()
        if tok == "(":
            self._next()
            inner = self._parse_or()
            if self._next() != ")":
                raise _ExprError("Expected ')'.")
            return f"({inner})"
        if tok is None:
            raise _ExprError("Unexpected end of expression.")
        # Peek: if the token after the field is IN, parse an IN expression.
        # Otherwise treat as a comparison.
        return self._parse_primary()

    def _parse_primary(self):
        field_tok = self._next()
        save = self._tokens[:]
        if self._tokens and self._tokens[0] == "IN":
            self._tokens = [field_tok] + self._tokens
            return self._in_expr()
        self._tokens = [field_tok] + save
        return self._comparison()

    def _parse_and(self):
        parts = [self._atom()]
        while self._peek() == "AND":
            self._next()
            parts.append(self._atom())
        return " AND ".join(parts)

    def _parse_or(self):
        parts = [self._parse_and()]
        while self._peek() == "OR":
            self._next()
            parts.append(self._parse_and())
        return " OR ".join(parts)

    def parse(self):
        if not self._tokens:
            return "", []
        sql = self._parse_or()
        if self._tokens:
            raise _ExprError(f"Unexpected trailing token: {self._tokens[0]!r}.")
        return sql, self._params


# ── Dataset table resolution ─────────────────────────────────────────────────
# Returns SQLAlchemy model classes and the SQL column for each headline output
# field so the response matches the frontend projection contract.
def _dataset_models(dataset: str):
    ds = dataset.lower()
    if ds in ("all", "hazards", "spis"):
        return (db_models.Hazard,)
    if ds in ("occurrences",):
        return (db_models.Report,)
    if ds in ("caps",):
        return (db_models.Cap,)
    raise HTTPException(status_code=400, detail=(
        f"Unsupported dataset '{dataset}'. Supported: all, hazards, occurrences, spis, caps."
    ))


# Maps a unified / headline field name to a SQL column expression per model.
# Each lambda returns (sql_expression, actual_column) built from the model.
def _projection(model) -> Dict[str, Any]:
    if model is db_models.Hazard:
        return {
            "record_id": model.hazard_id,
            "event_date": model.created_at,
            "record_type": model.source,
            "title_desc": model.title,
            "severity_index": model.severity,
            "status": model.status,
            "tenant_id": model.tenant_id,
            "severity": model.severity,
            "probability": model.probability,
            "priority": model.priority,
            "occurrence_type": model.occurrence_type,
            "title": model.title,
        }
    if model is db_models.Report:
        return {
            "record_id": model.id,
            "event_date": model.occurrence_date,
            "record_type": model.report_type,
            "title_desc": model.narrative,
            "severity_index": model.severity_level,
            "status": model.status,
            "tenant_id": model.tenant_id,
            "severity": model.severity_level,
            "probability": model.probability_level,
            "occurrence_type": model.occurrence_type,
            "title": model.narrative,
        }
    if model is db_models.Cap:
        return {
            "record_id": model.cap_reference,
            "event_date": model.submitted_at,
            "record_type": "Corrective Action",
            "title_desc": model.action_plan,
            "severity_index": 0,
            "status": model.status,
            "tenant_id": model.tenant_id,
        }
    return {}


# ── Query execution ──────────────────────────────────────────────────────────
@router.post("/query", response_model=DataQueryResponse)
@rate_limit("data_query")
async def execute_query(
    request: Request,
    payload: DataQueryRequest,
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    if payload.limit < 1 or payload.limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 1000.")

    tid_uuid = tenant_uuid(user["tenant_id"])
    models = _dataset_models(payload.dataset)
    model = models[0]  # single-table queries for deterministic projection
    proj = _projection(model)

    sql_where, params = "", []
    if payload.expression:
        try:
            sql_where, params = _Parser(payload.expression).parse()
        except _ExprError as e:
            raise HTTPException(status_code=400, detail=f"Invalid expression: {e}")

    # Resolve requested projection fields (defaults to the headline set).
    default_fields = ["record_id", "event_date", "record_type", "title_desc", "severity_index", "status"]
    requested = payload.fields or default_fields
    requested = [f for f in requested if f in proj]
    if not requested:
        requested = default_fields

    from sqlalchemy import select, text as sql_text
    tenant_col = getattr(model, "tenant_id", None)
    stmt = select(model).where(tenant_col == tid_uuid)
    if sql_where:
        bound = sql_text(sql_where).bindparams(
            **{f"p{i}": v for i, v in enumerate(params)}
        )
        stmt = stmt.where(bound)
    stmt = stmt.limit(payload.limit)

    rows: List[Dict[str, Any]] = []
    async with session_scope() as session:
        result = await session.execute(stmt)
        objects = result.scalars().all()
        for obj in objects:
            row: Dict[str, Any] = {}
            for f in requested:
                col = proj.get(f)
                if hasattr(col, "key"):
                    row[f] = _serialize(getattr(obj, col.key, None))
                else:
                    row[f] = col  # literal value (int/str constant)
            rows.append(row)

    total = len(rows)

    ip, req_id = request_context(request)
    log_audit(
        action="DATA_QUERY_EXECUTED",
        user=user.get("email"),
        tenant_id=user["tenant_id"],
        target_type="data_query",
        target_id=str(uuid.uuid4()),
        ip=ip,
        request_id=req_id,
        metadata={
            "dataset": payload.dataset,
            "expression": payload.expression,
            "limit": payload.limit,
            "rows": total,
        },
    )

    return DataQueryResponse(fields=requested, rows=rows, total=total)


def _serialize(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    return str(value)
