from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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


AE_DECISION_WORDS = {
    "acknowledge": "Acknowledge",
    "direct": "Direct",
    "continue": "Continue",
}

AE_IMMUTABILITY_NOTICE = (
    "This is the authoritative record of a terminal Accountable Executive "
    "decision under ICAO Annex 19 / Doc 9859. The decision is immutable and "
    "cannot be modified or re-issued within the AviaSAFE platform."
)


def _wrap_paragraph(text: str, font_name: str, font_size: float,
                    max_width: float, canvas: Canvas) -> List[str]:
    """Greedy word-wrap a paragraph to canvas string-widths (no truncation)."""
    words = str(text or "").split()
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        if canvas.stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def render_ae_decision_pdf(cap: Dict[str, Any],
                           signature: Dict[str, Any],
                           signed_at: Any) -> bytes:
    """Render the authoritative record of a terminal AE decision as PDF bytes.

    ``cap`` is the CAP document, ``signature`` the parsed ae_signature JSONB
    ({name, decision, notes, signed_by, signed_at}), ``signed_at`` the
    decision timestamp. All fields are read defensively; the caller decides
    what a missing signature means.
    """
    cap = cap or {}
    signature = signature or {}

    decision_raw = str(signature.get("decision") or "").strip().lower()
    decision_word = AE_DECISION_WORDS.get(decision_raw, decision_raw or "-")

    if isinstance(signed_at, datetime):
        stamp = signed_at
    else:
        try:
            stamp = datetime.fromisoformat(str(signed_at))
        except (ValueError, TypeError):
            stamp = None
    if stamp is not None and stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    stamp_text = stamp.strftime("%d %b %Y, %H:%M %Z") if stamp else "-"

    buf = io.BytesIO()
    canvas = Canvas(buf, pagesize=A4)
    width, height = A4
    left = 20 * mm
    usable = width - 40 * mm
    y = height - 25 * mm

    def need_space(lines: int = 1) -> None:
        nonlocal y
        if y - lines * 14 < 30 * mm:
            canvas.showPage()
            y = height - 25 * mm

    def heading(text: str) -> None:
        nonlocal y
        need_space()
        canvas.setFont("Helvetica-Bold", 11)
        canvas.setFillColorRGB(0.04, 0.16, 0.26)
        canvas.drawString(left, y, text)
        y -= 16

    def body_line(label: str, value: str) -> None:
        nonlocal y
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColorRGB(0.2, 0.2, 0.2)
        canvas.drawString(left, y, label)
        y -= 12
        canvas.setFont("Helvetica", 9)
        canvas.setFillColorRGB(0, 0, 0)
        for line in _wrap_paragraph(value if str(value).strip() else "-", "Helvetica", 9, usable, canvas):
            need_space()
            canvas.drawString(left, y, line)
            y -= 12
        y -= 4

    canvas.setFont("Helvetica-Bold", 16)
    canvas.setFillColorRGB(0.04, 0.16, 0.26)
    canvas.drawString(left, y, "Accountable Executive Decision Record")
    y -= 14
    canvas.setFont("Helvetica", 10)
    canvas.setFillColorRGB(0.3, 0.3, 0.3)
    canvas.drawString(left, y, "AviaSAFE")
    y -= 24

    body_line("CAP reference:", str(cap.get("cap_reference") or cap.get("id") or "-"))
    body_line("Department:", str(cap.get("department") or "-"))
    body_line("Decision:", decision_word)
    body_line("Signer name:", str(signature.get("name") or "-"))
    body_line("Signer email:", str(signature.get("signed_by") or "-"))
    body_line("Signed at:", stamp_text)
    body_line("Notes:", str(signature.get("notes") or "-"))

    heading("Immutability")
    for line in _wrap_paragraph(AE_IMMUTABILITY_NOTICE, "Helvetica", 9, usable, canvas):
        need_space()
        canvas.drawString(left, y, line)
        y -= 12
    y -= 8

    heading("Disclaimer")
    for line in _wrap_paragraph(CAR19_DISCLAIMER, "Helvetica-Oblique", 8, usable, canvas):
        need_space()
        canvas.setFont("Helvetica-Oblique", 8)
        canvas.setFillColorRGB(0.3, 0.3, 0.3)
        canvas.drawString(left, y, line)
        y -= 11

    canvas.showPage()
    canvas.save()
    return buf.getvalue()
