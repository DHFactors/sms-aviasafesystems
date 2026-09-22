# ============================================================================
# P2-14 — historical import pipeline (CSV + XLSX staging/validate/promote).
# ============================================================================

import io

import pytest
from sqlalchemy import select

from app.db.db_models import Hazard
from app.db.session import session_scope
from app.services.historical_import_service import HistoricalImportService

from _mbb import cleanup, create_tenant, run, unique_slug

# hazards.import_batch_id FK -> import_batches, so hazards must be deleted first.
TABLES = ("hazards", "import_rows", "import_batches")

CSV = (
    "title,description,source,taxonomy,priority,hazard_id\n"
    "Old hazard A,desc a,voluntary,Organizational,M,OPS/001/M/2020\n"
    "Bad row,,voluntary,Organizational,M,OPS/002/M/2020\n"
).encode("utf-8")


def test_csv_stage_validate_promote():
    slug = unique_slug("imp")
    create_tenant(slug)
    try:
        svc = HistoricalImportService(slug)
        batch = svc.create_batch({"role": "TENANT_ADMIN"}, CSV, "hazards.csv")
        assert batch["source_format"] == "csv"
        assert batch["total_rows"] == 2
        assert batch["valid_rows"] == 1
        assert batch["error_rows"] == 1

        valid = svc.list_rows(batch["id"], "valid")
        assert len(valid) == 1
        errors = svc.list_rows(batch["id"], "error")
        assert errors and "description is required" in (errors[0]["validation_errors"] or [""])[0]

        result = svc.promote_batch(batch["id"], {"role": "TENANT_ADMIN"})
        assert result["promoted"] == 1

        async def _fetch():
            async with session_scope() as s:
                return (await s.execute(
                    select(Hazard).where(Hazard.legacy_hazard_code == "OPS/001/M/2020")
                )).scalars().first()

        hazard = run(_fetch())
        assert hazard is not None
        assert hazard.imported_at is not None
        assert hazard.import_batch_id is not None
        assert hazard.original_row_ref == "line 2"
    finally:
        cleanup(slug, TABLES)


def test_xlsx_parsing():
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Hazards"
    ws.append(["title", "description", "source", "taxonomy", "priority"])
    ws.append(["Workbook hazard", "desc", "audit", "Technical", "H"])
    buf = io.BytesIO()
    wb.save(buf)

    slug = unique_slug("impx")
    create_tenant(slug)
    try:
        batch = HistoricalImportService(slug).create_batch(
            {"role": "TENANT_ADMIN"}, buf.getvalue(), "hazards.xlsx")
        assert batch["source_format"] == "xlsx"
        assert batch["valid_rows"] == 1
    finally:
        cleanup(slug, TABLES)


def test_macro_and_content_type_rejected():
    slug = unique_slug("impbad")
    create_tenant(slug)
    try:
        svc = HistoricalImportService(slug)
        with pytest.raises(ValueError):
            svc.create_batch({}, b"x", "macro.xlsm")
        # .xlsx extension with non-zip content is rejected by content sniffing.
        with pytest.raises(ValueError):
            svc.create_batch({}, b"not a zip", "fake.xlsx")
        # Unsupported extension.
        with pytest.raises(ValueError):
            svc.create_batch({}, b"x", "data.pdf")
    finally:
        cleanup(slug, TABLES)
