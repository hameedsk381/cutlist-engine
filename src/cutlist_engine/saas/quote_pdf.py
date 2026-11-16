"""The client's quote as a PDF: the studio's name, logo and colour, the price, and what it covers.

A client sees a price, never the workshop's costs or margin. With the breakdown on, the
price is split into a few lines (material, hardware, labour, other) with the margin spread
across them, so the lines add up to the total and the margin is not shown.

All money is rounded to whole rupees here, once, so every line and total on the page agree.
Text is drawn in a standard PDF font, which covers Western letters only (see brand.printable).
"""
from __future__ import annotations

import io
from datetime import datetime, timedelta
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (
    HRFlowable, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from .brand import DEFAULT_ACCENT, printable

MARGIN = 18 * mm


def money(value: float | int, currency: str = "INR") -> str:
    """Whole-number money. Rupees use Indian grouping (12,34,567); other currencies use 1,234,567."""
    number = int(round(value))
    digits = str(abs(number))
    if currency == "INR" and len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups + [tail])
    elif len(digits) > 3:
        digits = f"{int(digits):,}"
    return f"{currency} {'-' if number < 0 else ''}{digits}"


def price_lines(totals: dict[str, Any], breakdown: bool, tax_percent: float) -> dict[str, Any]:
    """What the client sees: optional lines that add up to the total, then tax and the grand total.

    Returns {"lines": [(label, rupees)], "total": rupees, "tax": rupees, "grand": rupees}.
    """
    total = int(round(float(totals.get("total") or 0)))
    lines: list[tuple[str, int]] = []
    if breakdown:
        parts = [
            ("Material and edge banding", float(totals.get("material") or 0) + float(totals.get("edge_banding") or 0)),
            ("Hardware", float(totals.get("hardware") or 0)),
            ("Labour and installation", float(totals.get("labour") or 0)),
            ("Other", float(totals.get("other") or 0)),
        ]
        parts = [(label, value) for label, value in parts if value > 0]
        subtotal = sum(value for _, value in parts)
        if parts and subtotal > 0:
            factor = total / subtotal  # spreads the margin; it is never printed
            amounts = [int(round(value * factor)) for _, value in parts]
            biggest = max(range(len(amounts)), key=lambda i: amounts[i])
            amounts[biggest] += total - sum(amounts)
            lines = [(label, amount) for (label, _), amount in zip(parts, amounts)]
    tax = int(round(total * float(tax_percent or 0) / 100.0))
    return {"lines": lines, "total": total, "tax": tax, "grand": total + tax}


def _scope(summary: dict[str, Any]) -> list[str]:
    """Short lines saying what the price covers. Detail stays in the parts list."""
    cutlist = summary.get("cutlist") or []
    parts = sum(int(item.get("quantity") or 1) for item in cutlist)
    sheets = [s for s in summary.get("sheets") or [] if not s.get("is_offcut_stock")]  # offcut stock is the shop's own
    lines = [f"{parts} cut parts."] if parts else []
    if sheets:
        by_material: dict[str, int] = {}
        for sheet in sheets:
            material = str(sheet.get("material") or "")
            by_material[material] = by_material.get(material, 0) + 1
        sizes = sorted({(round(s.get("width") or 0), round(s.get("height") or 0)) for s in sheets})
        size = f"{sizes[0][0]} x {sizes[0][1]} mm" if len(sizes) == 1 else "mixed sizes"
        count = len(sheets)
        head = f"{count} sheet{'s' if count != 1 else ''} of board ({size})"
        named = [(m, n) for m, n in sorted(by_material.items()) if m and m != "default"]
        if 1 < len(named) <= 4:
            head += ": " + ", ".join(f"{n} x {m.replace('mm', ' mm')}" for m, n in named)
        elif len(named) > 4:
            head += f", in {len(named)} thicknesses"
        lines.append(head + ".")
    return lines


class _NumberedCanvas(pdfcanvas.Canvas):
    """A canvas that can print "Page 1 of 3" by saving pages until the total is known."""

    footer_left = ""
    accent = DEFAULT_ACCENT

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved: list[dict] = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total: int) -> None:
        width, _ = A4
        self.setStrokeColor(colors.HexColor("#d9d7cf"))
        self.setLineWidth(0.5)
        self.line(MARGIN, 14 * mm, width - MARGIN, 14 * mm)
        self.setFillColor(colors.HexColor("#6b6b64"))
        self.setFont("Helvetica", 8)
        self.drawString(MARGIN, 9.5 * mm, self.footer_left[:110])
        self.drawRightString(width - MARGIN, 9.5 * mm, f"Page {self._pageNumber} of {total}")


def build_quote_pdf(
    *, project_name: str, quote_number: str, created_at, summary: dict[str, Any], totals: dict[str, Any],
    quote: dict[str, Any], brand: dict[str, Any], logo_png: bytes | None = None, include_parts: bool = False,
    now: datetime | None = None,
) -> bytes:
    """Render the quote. Raises ValueError if the project name or quote text cannot be printed."""
    for label, text in (("project name", project_name), ("customer name", quote.get("customer", "")),
                        ("note", quote.get("note", ""))):
        if not printable(text or ""):
            raise ValueError(f"The {label} has characters the PDF cannot print yet. Write it with English letters.")

    currency = totals.get("currency") or "INR"
    accent = colors.HexColor(brand.get("accent") or DEFAULT_ACCENT)
    ink, muted = colors.HexColor("#1d1d1b"), colors.HexColor("#6b6b64")
    now = now or datetime.now()
    valid_until = now + timedelta(days=int(brand.get("validity_days") or 15))

    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=ink)
    small = ParagraphStyle("small", parent=base, fontSize=8.5, leading=12, textColor=muted)
    h_title = ParagraphStyle("title", parent=base, fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=accent)
    h_studio = ParagraphStyle("studio", parent=base, fontName="Helvetica-Bold", fontSize=14, leading=18)
    h_project = ParagraphStyle("project", parent=base, fontName="Helvetica-Bold", fontSize=15, leading=19)
    h_section = ParagraphStyle("section", parent=base, fontName="Helvetica-Bold", fontSize=10, leading=14, textColor=accent,
                               spaceBefore=12, spaceAfter=4)
    right = ParagraphStyle("right", parent=base, alignment=TA_RIGHT)
    right_small = ParagraphStyle("rsmall", parent=small, alignment=TA_RIGHT)

    def esc(text: str) -> str:
        return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    story: list = []

    # --- Header: studio on the left, the quote's number and dates on the right ---
    studio_cell: list = []
    if logo_png:
        from reportlab.lib.utils import ImageReader

        reader = ImageReader(io.BytesIO(logo_png))
        iw, ih = reader.getSize()
        height = min(18 * mm, 60 * mm * ih / iw)
        studio_cell.append(Image(io.BytesIO(logo_png), width=height * iw / ih, height=height))
        studio_cell.append(Spacer(1, 3))
    studio_cell.append(Paragraph(esc(brand.get("studio_name") or "Quotation"), h_studio))
    contact = [brand.get("phone"), brand.get("email")]
    contact_line = "  |  ".join(esc(c) for c in contact if c)
    if contact_line:
        studio_cell.append(Paragraph(contact_line, small))
    if brand.get("address"):
        studio_cell.append(Paragraph(esc(brand["address"]), small))
    if brand.get("tax_id"):
        studio_cell.append(Paragraph(f"{esc(brand.get('tax_name') or 'Tax ID')}: {esc(brand['tax_id'])}", small))

    meta_cell = [
        Paragraph("QUOTATION", ParagraphStyle("qt", parent=h_title, alignment=TA_RIGHT)),
        Paragraph(f"No. {esc(quote_number)}", right),
        Paragraph(f"Date: {now.strftime('%d %b %Y')}", right_small),
        Paragraph(f"Valid until: {valid_until.strftime('%d %b %Y')}", right_small),
    ]
    header = Table([[studio_cell, meta_cell]], colWidths=[100 * mm, A4[0] - 2 * MARGIN - 100 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [header, Spacer(1, 6), HRFlowable(width="100%", thickness=1.5, color=accent), Spacer(1, 8)]

    # --- Who it is for, and what ---
    if quote.get("customer"):
        story += [Paragraph("PREPARED FOR", small), Paragraph(esc(quote["customer"]), ParagraphStyle(
            "cust", parent=base, fontName="Helvetica-Bold", fontSize=11.5, leading=15)), Spacer(1, 6)]
    story += [Paragraph(esc(project_name), h_project)]

    # --- Price ---
    priced = price_lines(totals, bool(brand.get("show_breakdown")), float(brand.get("tax_percent") or 0))
    rows: list[list] = []
    styles: list = []
    for label, amount in priced["lines"]:
        rows.append([Paragraph(esc(label), base), Paragraph(money(amount, currency), right)])
    if priced["tax"]:
        if priced["lines"]:
            rows.append([Paragraph("Total before tax", ParagraphStyle("b", parent=base, fontName="Helvetica-Bold")),
                         Paragraph(f"<b>{money(priced['total'], currency)}</b>", right)])
        else:
            rows.append([Paragraph("Price", base), Paragraph(money(priced["total"], currency), right)])
        tax_label = f"{esc(brand.get('tax_name') or 'Tax')} {brand.get('tax_percent'):g}%"
        rows.append([Paragraph(tax_label, base), Paragraph(money(priced["tax"], currency), right)])
        grand_label = "Total (including tax)"
    else:
        grand_label = "Total"
    rows.append([Paragraph(f"<b>{grand_label}</b>", ParagraphStyle("g", parent=base, fontSize=11.5)),
                 Paragraph(f"<b>{money(priced['grand'], currency)}</b>", ParagraphStyle("gr", parent=right, fontSize=11.5))])
    last = len(rows) - 1
    styles += [
        ("LINEABOVE", (0, last), (-1, last), 1, accent),
        ("BACKGROUND", (0, last), (-1, last), colors.HexColor("#f4f2ec")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, last - 1), 0.4, colors.HexColor("#e5e3dc")),
    ]
    price_table = Table(rows, colWidths=[A4[0] - 2 * MARGIN - 50 * mm, 50 * mm])
    price_table.setStyle(TableStyle(styles))
    story += [Paragraph("PRICE", h_section), price_table]

    # --- What it covers ---
    scope = _scope(summary)
    if scope:
        story += [Paragraph("WHAT THIS COVERS", h_section)]
        story += [Paragraph(f"&bull; {esc(line)}", base) for line in scope]

    if quote.get("note"):
        story.append(KeepTogether([Paragraph("NOTES", h_section), Paragraph(esc(quote["note"]).replace("\n", "<br/>"), base)]))
    if brand.get("terms"):
        story.append(KeepTogether([Paragraph("TERMS", h_section), Paragraph(esc(brand["terms"]).replace("\n", "<br/>"), base)]))

    # --- Parts list (optional annexure) ---
    cutlist = summary.get("cutlist") or []
    if include_parts and cutlist:
        data = [[Paragraph("<b>#</b>", small), Paragraph("<b>Qty</b>", small), Paragraph("<b>Part</b>", small),
                 Paragraph("<b>Size (mm)</b>", small), Paragraph("<b>Thickness</b>", small)]]
        for index, item in enumerate(cutlist, start=1):
            names = [n for n in (item.get("labels") or []) if n] or [str(item.get("id", ""))]
            finished_l = item.get("finished_length") or item.get("length") or 0
            finished_w = item.get("finished_width") or item.get("width") or 0
            data.append([
                Paragraph(str(index), small), Paragraph(str(item.get("quantity", 1)), small),
                Paragraph(esc(", ".join(dict.fromkeys(n.replace("_", " ") for n in names))[:80]), small),
                Paragraph(f"{round(finished_l)} x {round(finished_w)}", small),
                Paragraph(f"{item.get('thickness', ''):g} mm" if isinstance(item.get("thickness"), (int, float)) else "", small),
            ])
        parts_table = Table(data, colWidths=[10 * mm, 14 * mm, 76 * mm, 40 * mm, 24 * mm], repeatRows=1)
        parts_table.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, accent), ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#e5e3dc")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story += [Spacer(1, 6), KeepTogether([Paragraph("PARTS LIST", h_section)]), parts_table]

    buffer = io.BytesIO()
    footer = " | ".join(str(x) for x in (brand.get("studio_name"), brand.get("phone"), brand.get("email")) if x)

    class Canvas(_NumberedCanvas):
        footer_left = (footer + "  -  " if footer else "") + "Prepared with CutList"

    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=16 * mm, bottomMargin=20 * mm,
        title=f"Quotation {quote_number} - {project_name}", author=brand.get("studio_name") or "CutList",
    )
    doc.build(story, canvasmaker=Canvas)
    return buffer.getvalue()
