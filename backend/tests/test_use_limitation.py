# ============================================================================
# P2-29 — Appendix-3 use-limitation statements in outputs.
# ============================================================================

from app.services.data_governance import (
    CONFIDENTIAL_USE_LIMITATION_STATEMENT,
    USE_LIMITATION_STATEMENT,
    limitation_html,
    limitation_text,
)


def test_statement_text_and_variant():
    assert "maintaining or improving aviation safety" in USE_LIMITATION_STATEMENT
    assert "Appendix 3" in USE_LIMITATION_STATEMENT
    assert CONFIDENTIAL_USE_LIMITATION_STATEMENT != USE_LIMITATION_STATEMENT
    assert "PROTECTED" in CONFIDENTIAL_USE_LIMITATION_STATEMENT


def test_limitation_helpers():
    assert USE_LIMITATION_STATEMENT in limitation_text()
    assert USE_LIMITATION_STATEMENT in limitation_html()
    assert "PROTECTED" in limitation_text("protected")


def test_dispatch_emails_carry_statement():
    """The SSP + SRB dispatch builders must embed the statement."""
    import inspect

    from app.workers import scheduler, tenant_scheduler

    assert "limitation_html" in inspect.getsource(scheduler)
    assert "limitation_text" in inspect.getsource(scheduler)
    assert "limitation_html" in inspect.getsource(tenant_scheduler)
    assert "limitation_text" in inspect.getsource(tenant_scheduler)


def test_caan_pdf_footer_carries_statement():
    import inspect

    from app.services import pdf_generator

    src = inspect.getsource(pdf_generator.CaanPdfGenerator.build_ssp_report_pdf)
    assert "USE_LIMITATION_STATEMENT" in src


def test_export_response_headers_carry_statement():
    import inspect

    from app.routes import regulator_dashboard

    src = inspect.getsource(regulator_dashboard)
    assert "X-Use-Limitation" in src
    assert "classification_header" in src
