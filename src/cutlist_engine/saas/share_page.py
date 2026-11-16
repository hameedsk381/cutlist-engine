"""Server-rendered public quote page for a shared project (no JS, no auth).

Reads the stored result summary and renders a clean, printable one-pager:
project header, headline numbers, parts table and sheet breakdown.
"""
from __future__ import annotations

import html
from datetime import datetime

_BRAND = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin:0; font-family:'Segoe UI',system-ui,sans-serif; background:#f4f3ef; color:#1c2430; }
.page { max-width: 900px; margin: 0 auto; padding: 32px 20px 64px; }
.badge { display:inline-block; background:#0e5c4a; color:#fff; font-weight:700;
         padding:6px 14px; border-radius:999px; font-size:13px; letter-spacing:.02em; }
h1 { font-size: 30px; letter-spacing:-0.02em; margin: 16px 0 4px; }
.meta { color:#5a6678; font-size:14px; }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; margin:28px 0; }
.card { background:#fff; border:1px solid #e3e1da; border-radius:14px; padding:16px 18px; }
.card .k { font-size:13px; color:#5a6678; font-weight:600; }
.card .v { font-size:26px; font-weight:800; letter-spacing:-0.02em; margin-top:4px; }
.card .s { font-size:12px; color:#5a6678; margin-top:2px; }
section { background:#fff; border:1px solid #e3e1da; border-radius:14px; padding:20px 22px; margin-bottom:16px; }
h2 { font-size:17px; margin:0 0 12px; }
table { width:100%; border-collapse:collapse; font-size:14px; }
th { text-align:left; color:#5a6678; font-weight:600; border-bottom:1px solid #e3e1da; padding:8px 6px; }
td { border-bottom:1px solid #f0efe9; padding:8px 6px; }
tr:last-child td { border-bottom:none; }
.num { font-variant-numeric: tabular-nums; }
.foot { color:#5a6678; font-size:12px; margin-top:24px; text-align:center; }
a { color:#0e5c4a; }
"""


def _n(value) -> str:
    """Format a dimension: whole floats as ints, others to 1 decimal."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(f)) if f.is_integer() else f"{f:.1f}"


def _fmt_money(value: float | None, currency: str) -> str:
    if value is None:
        return "—"
    return f"{currency} {value:,.0f}"


def render_share_page(
    project_name: str, original_filename: str, created_at, summary: dict, quote: dict | None = None,
) -> str:
    """Public, printable HTML for one project's result summary."""
    e = html.escape
    material = summary.get("material_summary") or {}
    currency = material.get("currency", "INR")
    cutlist = summary.get("cutlist") or []
    sheets = summary.get("sheets") or []

    date_str = ""
    if created_at:
        if isinstance(created_at, datetime):
            date_str = created_at.strftime("%d %b %Y")
        else:
            try:
                date_str = datetime.fromisoformat(str(created_at)).strftime("%d %b %Y")
            except ValueError:
                date_str = str(created_at)[:10]

    parts_rows = "".join(
        f"<tr><td>{e(str(item.get('id', '')))}</td>"
        f"<td class='num'>{e(_n(item.get('length', '')))} × {e(_n(item.get('width', '')))} × "
        f"{e(_n(item.get('thickness', '')))} mm</td>"
        f"<td class='num'>{e(str(item.get('quantity', '')))}</td>"
        f"<td>{e(str(item.get('material', '')))}</td></tr>"
        for item in cutlist
    )

    sheet_cards = "".join(
        f"<tr><td>Sheet {e(str(s.get('sheet_id', '')))}"
        + (" <em>(your offcut stock)</em>" if s.get("is_offcut_stock") else "")
        + f"</td>"
        f"<td>{e(_n(s.get('width', '')))} × {e(_n(s.get('height', '')))} mm</td>"
        f"<td>{e(str(len(s.get('parts', []))))}</td>"
        f"<td class='num'>{_n(round(float(s.get('utilization_percent', 0) or 0), 1))}%</td>"
        f"<td class='num'>{e(_fmt_money(s.get('sheet_cost'), currency))}</td></tr>"
        for s in sheets
    )

    if quote:
        # A client sees the price, not the workshop's costs or margin.
        price_card = (
            f'<div class="card"><div class="k">Quote total</div>'
            f'<div class="v num">{e(_fmt_money(quote.get("total"), quote.get("currency", currency)))}</div>'
            f'<div class="s">material, edge banding, hardware and labour</div></div>'
        )
        quote_block = ""
        if quote.get("customer") or quote.get("note"):
            quote_block = (
                "<section><h2>Quote</h2>"
                + (f"<p><strong>For:</strong> {e(quote['customer'])}</p>" if quote.get("customer") else "")
                + (f"<p>{e(quote['note'])}</p>" if quote.get("note") else "")
                + "</section>"
            )
        cost_header = ""
    else:
        price_card = (
            f'<div class="card"><div class="k">Material cost</div>'
            f'<div class="v num">{e(_fmt_money(material.get("total_material_cost"), currency))}</div>'
            f'<div class="s">at listed sheet prices</div></div>'
        )
        quote_block = ""
        cost_header = "<th>Cost</th>"
    if quote:
        sheet_cards = "".join(
            f"<tr><td>Sheet {e(str(s.get('sheet_id', '')))}</td>"
            f"<td>{e(_n(s.get('width', '')))} × {e(_n(s.get('height', '')))} mm</td>"
            f"<td>{e(str(len(s.get('parts', []))))}</td>"
            f"<td class='num'>{_n(round(float(s.get('utilization_percent', 0) or 0), 1))}%</td></tr>"
            for s in sheets
        )

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(project_name)} — cutting plan quote</title>
<style>{_BRAND}</style></head>
<body><div class="page">
<span class="badge">CutList</span>
<h1>{e(project_name)}</h1>
<p class="meta">Shared cutting plan · from {e(original_filename)}{(" · " + date_str) if date_str else ""}</p>

<div class="cards">
  <div class="card"><div class="k">Sheets to buy</div><div class="v num">{e(str(material.get("sheet_count", "—")))}</div><div class="s">18 mm plywood</div></div>
  {price_card}
  <div class="card"><div class="k">Wood used</div><div class="v num">{_n(round(float(material.get("utilization_percent", 0) or 0), 1))}%</div><div class="s">{_n(round(float(material.get("waste_percent", 0) or 0), 1))}% is left over</div></div>
  <div class="card"><div class="k">Spare pieces worth keeping</div><div class="v num">{e(f"{(material.get('reusable_offcut_area') or 0):.1f}")} m²</div><div class="s">offcuts above 300 mm</div></div>
</div>

{quote_block}
<section>
  <h2>Parts list</h2>
  <table><thead><tr><th>Part</th><th>Size (L × W × T)</th><th>Qty</th><th>Material</th></tr></thead>
  <tbody>{parts_rows or "<tr><td colspan='4'>No parts yet — the plan is still being processed.</td></tr>"}</tbody></table>
</section>

<section>
  <h2>Sheets</h2>
  <table><thead><tr><th>Sheet</th><th>Size</th><th>Parts</th><th>Used</th>{cost_header}</tr></thead>
  <tbody>{sheet_cards or "<tr><td colspan='5'>—</td></tr>"}</tbody></table>
</section>

<p class="foot">Generated with CutList — turn any 3D furniture model into a cut list, nested sheets and CNC files.</p>
</div></body></html>"""
