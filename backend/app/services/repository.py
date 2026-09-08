from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from functools import lru_cache
from loguru import logger

from app.core.config import settings
from app.db import pg
from app.db.db_models import Report as PgReport
from app.db.ids import tenant_uuid
from app.db.isolation import demo_scope


def coerce_utc_datetime(value) -> Optional[datetime]:
    """Coerce a stored timestamp (aware/naive datetime, ISO string, or a
    Firestore-like Timestamp object) into a timezone-aware UTC datetime so date
    range comparisons are timezone-safe. Returns None for unparseable values."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    for attr in ("to_datetime", "datetime"):
        conv = getattr(value, attr, None)
        if callable(conv):
            try:
                dt = conv()
            except Exception:
                continue
            if isinstance(dt, datetime):
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
    ts = getattr(value, "timestamp", None)
    if callable(ts):
        try:
            return datetime.fromtimestamp(ts(), tz=timezone.utc)
        except (TypeError, ValueError, OSError, OverflowError):
            return None
    return None


class ReportFilter:
    def __init__(
        self,
        tenant_id: Optional[str] = None,
        cross_tenant: bool = False,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        report_type: Optional[str] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        occurrence_type: Optional[str] = None,
        page: int = 1,
        page_size: int = settings.REPO_DEFAULT_PAGE_SIZE,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        cursor: Optional[str] = None,
    ):
        self.tenant_id = tenant_id
        self.cross_tenant = cross_tenant
        self.date_from = date_from
        self.date_to = date_to
        self.report_type = report_type
        self.status = status
        self.severity = severity
        self.occurrence_type = occurrence_type
        self.page = max(page, 1)
        self.page_size = min(max(page_size, 1), settings.REPO_MAX_PAGE_SIZE)
        self.sort_by = sort_by
        self.sort_order = sort_order if sort_order in ("asc", "desc") else "desc"
        self.cursor = cursor

    def clone(self, **overrides) -> "ReportFilter":
        params = {
            "tenant_id": self.tenant_id,
            "cross_tenant": self.cross_tenant,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "report_type": self.report_type,
            "status": self.status,
            "severity": self.severity,
            "occurrence_type": self.occurrence_type,
            "page": self.page,
            "page_size": self.page_size,
            "sort_by": self.sort_by,
            "sort_order": self.sort_order,
            "cursor": self.cursor,
        }
        params.update(overrides)
        return ReportFilter(**params)


class ReportRepository:
    COLLECTION = settings.FIREBASE_COLLECTION_REPORTS

    _cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
    _CACHE_TTL_SECONDS = settings.REPO_CACHE_TTL_SECONDS

    def query_reports(self, filter: ReportFilter) -> Dict[str, Any]:
        try:
            all_items = self.get_all_in_range(filter, limit=settings.REPO_QUERY_LIMIT)
            # Apply cursor offset if present (cursor is sort_by value)
            start = 0
            if filter.cursor:
                parsed = self._parse_cursor(filter.cursor, filter)
                if parsed is not None:
                    # Find index after cursor value
                    for idx, item in enumerate(all_items):
                        val = coerce_utc_datetime(item.get(filter.sort_by))
                        if val is not None and parsed is not None:
                            if filter.sort_order == "desc" and val < parsed:
                                start = idx
                                break
                            if filter.sort_order == "asc" and val > parsed:
                                start = idx
                                break
            total = len(all_items)
            # Pagination slice
            offset = (filter.page - 1) * filter.page_size
            # If cursor provided, ignore page offset and start from cursor
            if filter.cursor and start:
                offset = start
            items = all_items[offset: offset + filter.page_size]
            next_cursor = None
            if offset + filter.page_size < total:
                last = items[-1] if items else None
                next_cursor = self._encode_cursor(last, filter) if last else None
            total_pages = max((total + filter.page_size - 1) // filter.page_size, 1)
            return {
                "items": items,
                "total": total,
                "page": filter.page,
                "page_size": filter.page_size,
                "total_pages": total_pages,
                "has_next": bool(next_cursor),
                "has_prev": filter.page > 1 or bool(filter.cursor),
                "next_cursor": next_cursor,
            }
        except Exception as e:
            logger.error(f"ReportRepository.query_reports failed: {e}")
            raise

    def get_all_in_range(
        self,
        filter: ReportFilter,
        limit: int = settings.REPO_QUERY_LIMIT,
    ) -> List[Dict[str, Any]]:
        cache_key = self._cache_key(filter)
        now = datetime.now().timestamp()
        cached = self._cache.get(cache_key)
        if cached and (now - cached[0]) < self._CACHE_TTL_SECONDS:
            logger.debug(f"Cache hit for {cache_key}")
            return cached[1]

        try:
            where = []
            if not filter.cross_tenant and filter.tenant_id:
                # Tenant-scoped reads surface every row the tenant owns (both
                # demo and production scope) so admin-seeded dummy data stays
                # visible on the operator dashboard — the same rule the hazard
                # stats and master-register reads already apply. Strict
                # demo_scope() isolation is preserved for cross-tenant /
                # system-level reads so no demo data leaks between clusters.
                try:
                    where.append(PgReport.tenant_id == tenant_uuid(filter.tenant_id))
                except Exception:
                    where.append(PgReport.is_demo == demo_scope())
            else:
                where.append(PgReport.is_demo == demo_scope())
            if filter.report_type:
                where.append(PgReport.report_type == filter.report_type)
            if filter.status:
                where.append(PgReport.status == filter.status)
            if filter.severity:
                where.append(PgReport.severity == filter.severity)
            if filter.occurrence_type:
                where.append(PgReport.occurrence_type == filter.occurrence_type)

            # Push the Python-side date range into SQL so tenant-scoped reads
            # are bounded by the (tenant_id, created_at) index instead of
            # pulling every tenant row and discarding out-of-window rows in
            # Python. The typed sort columns are non-null so the predicate is
            # equivalent to the Python coerce-UTC comparison below (inclusive).
            if filter.date_from or filter.date_to:
                if filter.sort_by in ("created_at", "occurrence_date", "updated_at"):
                    date_col = getattr(PgReport, filter.sort_by)
                    if filter.date_from:
                        where.append(date_col >= filter.date_from)
                    if filter.date_to:
                        where.append(date_col <= filter.date_to)

            rows = pg.fetch_all(PgReport, where=where)
            results: List[Dict[str, Any]] = []
            for r in rows:
                d = dict(r)
                self._serialize_timestamps(d)
                # Date range filtering (applies to sort_by field)
                if filter.date_from or filter.date_to:
                    dt = coerce_utc_datetime(d.get(filter.sort_by))
                    if dt is None:
                        # fallback to occurrence_date/created_at
                        dt = coerce_utc_datetime(d.get("created_at")) or coerce_utc_datetime(d.get("occurrence_date"))
                    if not self._doc_in_date_range(dt, filter.date_from, filter.date_to):
                        continue
                results.append(d)

            # Sorting
            reverse = filter.sort_order == "desc"
            def _sort_key(x):
                v = coerce_utc_datetime(x.get(filter.sort_by)) or coerce_utc_datetime(x.get("created_at"))
                return v or datetime.min.replace(tzinfo=timezone.utc)
            results.sort(key=_sort_key, reverse=reverse)

            if limit:
                results = results[:limit]

            self._cache[cache_key] = (now, results)
            if len(results) == 0:
                logger.warning(f"Report query returned 0 results for tenant_id={filter.tenant_id}, cross_tenant={filter.cross_tenant}, date_from={filter.date_from}, date_to={filter.date_to}")
            logger.debug(f"Cached {len(results)} results for {cache_key}")
            return results
        except Exception as e:
            logger.error(f"ReportRepository.get_all_in_range failed: {e}")
            raise

    def invalidate_cache(self, prefix: Optional[str] = None):
        if prefix:
            self._cache = {k: v for k, v in self._cache.items() if not k.startswith(prefix)}
        else:
            self._cache.clear()
        logger.debug("Repository cache invalidated")

    def get_by_id(self, report_id: str, filter: ReportFilter) -> Optional[Dict[str, Any]]:
        try:
            row = pg.fetch_by(PgReport, "id", report_id)
            if row is None:
                return None
            # Enforce tenant isolation when not cross-tenant
            if not filter.cross_tenant and filter.tenant_id:
                tid = tenant_uuid(filter.tenant_id)
                if str(row.get("tenant_id") or "") != str(tid):
                    return None
            self._serialize_timestamps(row)
            return row
        except Exception as e:
            logger.error(f"ReportRepository.get_by_id({report_id}) failed: {e}")
            raise

    def count_by_status(self, filter: ReportFilter) -> Dict[str, int]:
        items = self.get_all_in_range(filter)
        return {"total": len(items)}

    def count_by_severity(self, filter: ReportFilter) -> Dict[str, int]:
        items = self.get_all_in_range(filter)
        return {"total": len(items)}

    @staticmethod
    def _count_total(count_result) -> int:
        """Parse the Firestore count() aggregation result across SDK versions."""
        if not count_result:
            return 0
        try:
            first = count_result[0]
        except (IndexError, TypeError):
            return 0
        if hasattr(first, "value"):
            return first.value or 0
        if isinstance(first, (list, tuple)) and first and hasattr(first[0], "value"):
            return first[0].value or 0
        return 0

    def _build_collection(self, filter: ReportFilter):
        # Kept for compatibility; no longer used (PG primary)
        return None

    def _apply_filters(self, collection, filter: ReportFilter):
        return collection

    @staticmethod
    def _sort_order(order: str):
        # Kept for compatibility
        return order

    @staticmethod
    def _encode_cursor(doc, filter: ReportFilter) -> Optional[str]:
        if doc is None:
            return None
        sort_val = doc.get(filter.sort_by) if isinstance(doc, dict) else doc.get(filter.sort_by) if hasattr(doc, "get") else None
        if sort_val is None:
            return None
        if hasattr(sort_val, "isoformat"):
            sort_val = sort_val.isoformat()
        return str(sort_val)

    @staticmethod
    def _parse_cursor(cursor: str, filter: ReportFilter):
        target = cursor
        if filter.sort_by == "created_at" or filter.sort_by == "occurrence_date":
            try:
                return datetime.fromisoformat(target.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return None
        return target

    @staticmethod
    def _cache_key(filter: ReportFilter) -> str:
        parts = [
            str(filter.tenant_id or "cross"),
            str(filter.cross_tenant),
            str(filter.date_from.isoformat() if filter.date_from else ""),
            str(filter.date_to.isoformat() if filter.date_to else ""),
            str(filter.report_type or ""),
            str(filter.status or ""),
            str(filter.severity or ""),
            str(filter.occurrence_type or ""),
            filter.sort_by,
            filter.sort_order,
        ]
        return "::".join(parts)

    @staticmethod
    def _doc_in_date_range(
        value, date_from: Optional[datetime], date_to: Optional[datetime]
    ) -> bool:
        if not date_from and not date_to:
            return True
        dt = coerce_utc_datetime(value)
        if dt is None:
            return False
        if date_from and dt < date_from:
            return False
        if date_to and dt > date_to:
            return False
        return True

    @staticmethod
    def _serialize_timestamps(data: dict) -> None:
        for key in (
            "created_at", "updated_at", "occurrence_date",
            "processed_at", "reviewed_at",
        ):
            if key in data and hasattr(data[key], "isoformat"):
                data[key] = data[key].isoformat()
