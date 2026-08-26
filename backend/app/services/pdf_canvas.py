from __future__ import annotations

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

CAR19_DISCLAIMER = (
    "This report is generated under ICAO Annex 19 and Nepal CAR-19 State Safety "
    "Programme (SSP) compliance requirements. Distribution is restricted to "
    "authorised aviation safety personnel. Unauthorised reproduction or "
    "dissemination is prohibited under applicable aviation safety regulations."
)

ICAO_DISCLAIMER = (
    "Prepared in accordance with ICAO Annex 19 — Safety Management, 3rd Edition "
    "(Attachment B — State Safety Programme). This document contains safety-sensitive "
    "information subject to the State's aviation safety data protection policy."
)


class NumberedCanvas(Canvas):
    """ReportLab Canvas subclass that renders total page numbers in the footer
    and ICAO/CAR-19 legal disclaimers on the final page.

    Uses the standard page-state replay pattern: each page's canvas state is
    captured during showPage(), then all pages are replayed at save() time with
    the correct "Page X of Y" footer and disclaimer annotations.

    Usage::

        doc.build(story, canvasmaker=NumberedCanvas)
    """

    def __init__(self, *args, **kwargs):
        self._disclaimer_text = kwargs.pop("disclaimer_text", CAR19_DISCLAIMER)
        self._saved_page_states: list[dict] = []
        super().__init__(*args, **kwargs)

    def showPage(self):
        """Save current page state, then start a fresh page."""
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        """Replay all saved pages, drawing page-number footers and the final-page
        disclaimer, then write the PDF to disk."""
        num_pages = len(self._saved_page_states)
        for page_idx, state in enumerate(self._saved_page_states, start=1):
            self.__dict__.update(state)
            self._draw_page_number(page_idx, num_pages)
            if page_idx == num_pages:
                self._draw_disclaimer()
            Canvas.showPage(self)
        Canvas.save(self)

    def _draw_page_number(self, page_num: int, total: int) -> None:
        width, _ = A4
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColorRGB(0.45, 0.45, 0.45)
        self.drawCentredString(
            width / 2,
            20 * mm,
            f"Page {page_num} of {total}",
        )
        self.restoreState()

    def _draw_disclaimer(self) -> None:
        width, height = A4
        self.saveState()
        self.setFont("Helvetica-Oblique", 6.5)
        self.setFillColorRGB(0.5, 0.5, 0.5)

        text_obj = self.beginText(50, 32 * mm)
        text_obj.textLine(self._disclaimer_text)
        self.drawText(text_obj)
        self.restoreState()
