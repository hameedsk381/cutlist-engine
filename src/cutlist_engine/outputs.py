from __future__ import annotations

import csv
import html
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .cutsequence import cut_sequence
from .models import (
    Board,
    CutlistItem,
    ExtractionReport,
    MaterialSummary,
    ModelFixReport,
    SheetLayout,
    SheetSizeOption,
    WasteOptimizationReport,
)


def write_json_report(
    path: Path,
    boards: list[Board],
    cutlist: list[CutlistItem],
    sheets: list[SheetLayout],
    extraction_report: ExtractionReport | None = None,
    material_summary: MaterialSummary | None = None,
    waste_optimization_report: WasteOptimizationReport | None = None,
    model_fix_report: ModelFixReport | None = None,
    sheet_size_options: tuple[SheetSizeOption, ...] = (),
    kerf: float | None = None,
) -> None:
    """`kerf` (the saw blade width) adds each sheet's cut sequence to the report."""
    payload: dict[str, Any] = {
        "extraction_report": asdict(extraction_report) if extraction_report else None,
        "material_summary": asdict(material_summary) if material_summary else None,
        "waste_optimization_report": asdict(waste_optimization_report) if waste_optimization_report else None,
        "model_fix_report": asdict(model_fix_report) if model_fix_report else None,
        "sheet_size_options": [asdict(option) for option in sheet_size_options],
        "manufacturing_insights": _manufacturing_insights(
            boards, sheets, extraction_report, material_summary, model_fix_report
        ),
        "boards": [_board_dict(board) for board in boards],
        "cutlist": [asdict(item) for item in cutlist],
        "sheets": [
            asdict(sheet)
            | {"waste_percent": sheet.waste_percent, "utilization_percent": sheet.utilization_percent}
            | ({"cuts": cut_sequence(sheet, kerf)} if kerf is not None else {})
            for sheet in sheets
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_cutlist_csv(path: Path, cutlist: list[CutlistItem]) -> None:
    fieldnames = [
        "id", "label", "material", "length", "width", "thickness",
        "finished_length", "finished_width", "edge_band",
        "grain_locked", "area", "quantity", "board_ids",
    ]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for item in cutlist:
            row = {
                "id": item.id,
                "label": " | ".join(item.labels) if item.labels else "",
                "material": item.material,
                "length": item.length,
                "width": item.width,
                "thickness": item.thickness,
                "finished_length": item.finished_length or item.length,
                "finished_width": item.finished_width or item.width,
                "edge_band": "/".join(f"{b:g}" for b in item.edge_band),
                "grain_locked": "yes" if item.grain_locked else "no",
                "area": item.area,
                "quantity": item.quantity,
                "board_ids": ",".join(item.board_ids),
            }
            writer.writerow(row)


def write_label_sheet_html(
    path: Path,
    cutlist: list[CutlistItem],
    sheets: list[SheetLayout],
) -> None:
    """One printable card per part. A4-friendly, 6 cards per page."""
    # Build a board-id -> sheet number lookup so each label says where it lives.
    sheet_of: dict[str, int] = {}
    for sheet in sheets:
        for part in sheet.parts:
            sheet_of[part.board_id] = sheet.sheet_id

    cards: list[str] = []
    for item in cutlist:
        for index, board_id in enumerate(item.board_ids, start=1):
            sheet_num = sheet_of.get(board_id, "-")
            label_name = item.labels[index - 1] if item.labels and index - 1 < len(item.labels) else item.id
            grain_arrow = "<div class='grain'>&rarr; grain</div>" if item.grain_locked else ""
            edge_band_block = ""
            if any(item.edge_band):
                t, r, b, l = item.edge_band
                edge_band_block = (
                    f"<div class='band'>Edge band  T:{t:g}  R:{r:g}  B:{b:g}  L:{l:g} mm</div>"
                )
            finished = ""
            if item.finished_length and (item.finished_length, item.finished_width) != (item.length, item.width):
                finished = (
                    f"<div class='finished'>Finished: {item.finished_length:.0f} x {item.finished_width:.0f} mm</div>"
                )
            cards.append(
                f"""<article class='card'>
  <header><span class='id'>{html.escape(item.id)}</span><span class='sheet'>Sheet {sheet_num}</span></header>
  <h3>{html.escape(label_name)}</h3>
  <div class='dims'>{item.length:.0f} <span>x</span> {item.width:.0f} <small>mm</small></div>
  <div class='thickness'>{item.thickness:.1f} mm  &middot;  {html.escape(item.material)}</div>
  {finished}
  {edge_band_block}
  {grain_arrow}
  <footer>{index} of {item.quantity}</footer>
</article>"""
            )

    css = """
    @page { size: A4; margin: 12mm; }
    body { font-family: ui-sans-serif, system-ui, sans-serif; margin: 0; padding: 12mm; background: #f5f7f8; color: #172026; }
    h1 { margin: 0 0 12px 0; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8mm; }
    .card { background: #fff; border: 1.5px solid #172026; border-radius: 6px; padding: 12px 14px; min-height: 60mm;
            page-break-inside: avoid; position: relative; }
    .card header { display: flex; justify-content: space-between; font-size: 12px; color: #43525a; text-transform: uppercase; letter-spacing: 0.06em; }
    .card .id { font-weight: 600; }
    .card h3 { margin: 6px 0 12px 0; font-size: 18px; }
    .card .dims { font-size: 36px; font-weight: 700; line-height: 1; }
    .card .dims span { font-weight: 400; color: #5b6a72; padding: 0 4px; }
    .card .dims small { font-size: 16px; color: #5b6a72; font-weight: 500; }
    .card .thickness { margin-top: 6px; font-size: 14px; color: #43525a; }
    .card .finished { margin-top: 6px; font-size: 13px; color: #2f6f4e; }
    .card .band { margin-top: 4px; font-size: 12px; color: #b06b00; }
    .card .grain { margin-top: 8px; font-size: 14px; font-weight: 600; color: #1d4ed8; letter-spacing: 0.08em; }
    .card footer { position: absolute; bottom: 8px; right: 12px; font-size: 11px; color: #5b6a72; }
    """
    grid = "\n".join(cards)
    path.write_text(
        f"<!doctype html><html><head><meta charset='utf-8'><title>Cut labels</title><style>{css}</style></head>"
        f"<body><h1>Cut labels &mdash; {sum(item.quantity for item in cutlist)} parts</h1>"
        f"<div class='grid'>{grid}</div></body></html>",
        encoding="utf-8",
    )


def write_sheet_layout_html(
    path: Path,
    sheets: list[SheetLayout],
    material_summary: MaterialSummary,
    boards: list[Board] | None = None,
    model_fix_report: ModelFixReport | None = None,
    sheet_size_options: tuple[SheetSizeOption, ...] = (),
) -> None:
    board_labels = _board_labels(boards or [])
    body = "\n".join(_sheet_html(sheet, board_labels) for sheet in sheets) if sheets else ""

    cost_block = ""
    if material_summary.sheet_cost > 0:
        cost_block = (
            f'<div class="metric">Material cost'
            f'<strong>{material_summary.currency} {material_summary.total_material_cost:,.2f}</strong></div>'
        )
        if material_summary.cost_savings_vs_worst_strategy > 0:
            cost_block += (
                f'<div class="metric saved">Saved vs worst strategy'
                f'<strong>{material_summary.currency} {material_summary.cost_savings_vs_worst_strategy:,.2f}</strong></div>'
            )

    sheet_label_block = ""
    if material_summary.sheet_size_label:
        sheet_label_block = (
            f'<div class="metric">Sheet<strong>{html.escape(material_summary.sheet_size_label)}</strong></div>'
        )

    fix_block = _model_fix_html(model_fix_report) if model_fix_report else ""
    options_block = _sheet_options_html(sheet_size_options, material_summary.currency) if sheet_size_options else ""

    path.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Cutting Plan</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: ui-sans-serif, system-ui, sans-serif;
      color: #172026;
      background: #f5f7f8;
    }}
    body {{ margin: 0; padding: 28px; }}
    h1, h2, h3, p {{ margin: 0; }}
    header {{ margin-bottom: 24px; }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-top: 16px;
      max-width: 1100px;
    }}
    .metric {{
      background: #ffffff;
      border: 1px solid #d7dee2;
      border-radius: 8px;
      padding: 12px;
    }}
    .metric strong {{ display: block; font-size: 22px; margin-top: 4px; }}
    .metric.saved {{ background: #e6f4ea; border-color: #2f6f4e; }}
    .sheet {{
      margin: 22px 0;
      padding: 18px;
      background: #ffffff;
      border: 1px solid #d7dee2;
      border-radius: 8px;
      overflow-x: auto;
    }}
    svg {{
      width: min(100%, 980px);
      height: auto;
      border: 1px solid #9ba9b0;
      background: #fbfcfd;
      margin-top: 14px;
    }}
    .part {{ fill: #8fc7b5; stroke: #24584e; stroke-width: 2; }}
    .part.grain {{ fill: #b6d8c8; }}
    .offcut {{ fill: #eef2f4; stroke: #9ba9b0; stroke-width: 1.5; stroke-dasharray: 8 6; }}
    .reusable {{ fill: #e6f4ea; stroke: #2f6f4e; }}
    text {{ font-size: 26px; fill: #172026; }}
    text.dim {{ font-size: 22px; fill: #43525a; }}
    .alert {{
      margin: 18px 0;
      padding: 16px 18px;
      border-radius: 8px;
      border: 1px solid #d99a2a;
      background: #fff7e0;
    }}
    .alert.danger {{ border-color: #c43c3c; background: #fde8e8; }}
    .alert h2 {{ font-size: 18px; margin-bottom: 8px; }}
    .alert ul {{ margin: 6px 0 0 18px; padding: 0; }}
    table.options {{
      border-collapse: collapse;
      margin-top: 8px;
      width: 100%;
      max-width: 1100px;
      background: #ffffff;
    }}
    table.options th, table.options td {{
      border: 1px solid #d7dee2;
      padding: 8px 10px;
      text-align: left;
      font-size: 14px;
    }}
    table.options tr.best td {{ background: #e6f4ea; font-weight: 600; }}
  </style>
</head>
<body>
  <header>
    <h1>Cutting Plan</h1>
    <div class="metrics">
      <div class="metric">Sheets required<strong>{material_summary.sheet_count}</strong></div>
      {sheet_label_block}
      <div class="metric">Utilization<strong>{material_summary.utilization_percent:.1f}%</strong></div>
      <div class="metric">Waste<strong>{material_summary.waste_percent:.1f}%</strong></div>
      <div class="metric">Reusable offcuts<strong>{material_summary.reusable_offcut_area:.2f} sq m</strong></div>
      {cost_block}
    </div>
  </header>
  {fix_block}
  {options_block}
  {body}
</body>
</html>
""",
        encoding="utf-8",
    )


def _board_dict(board: Board) -> dict[str, Any]:
    return {
        "id": board.id,
        "length": board.length,
        "width": board.width,
        "thickness": board.thickness,
        "area": board.area,
        "contour": [point.as_tuple() for point in board.contour],
        "holes": [[point.as_tuple() for point in hole] for hole in board.holes],
        "source_planes": board.source_planes,
        "confidence": board.confidence,
        "warnings": list(board.warnings),
        "source_objects": list(board.source_objects),
        "grain_locked": board.grain_locked,
    }


def _sheet_html(sheet: SheetLayout, board_labels: dict[str, str] | None = None) -> str:
    board_labels = board_labels or {}
    parts_pieces = []
    for part in sheet.parts:
        css_class = "part"
        # We don't have access to the Board object here, but the label encodes grain via labels dict.
        label = board_labels.get(part.board_id, part.board_id)
        if "[grain]" in label:
            css_class = "part grain"
            label = label.replace(" [grain]", "")
        parts_pieces.append(
            f"""      <g>
        <rect class="{css_class}" x="{part.x:.2f}" y="{part.y:.2f}" width="{part.length:.2f}" height="{part.width:.2f}" />
        <text x="{part.x + 12:.2f}" y="{part.y + 36:.2f}">{html.escape(label)} ({part.rotation} deg)</text>
        <text class="dim" x="{part.x + 12:.2f}" y="{part.y + 70:.2f}">{part.length:.0f} x {part.width:.0f} mm</text>
      </g>"""
        )
    parts = "\n".join(parts_pieces)
    offcuts = "\n".join(
        f"""      <rect class="offcut {'reusable' if offcut.reusable else ''}" x="{offcut.x:.2f}" y="{offcut.y:.2f}" width="{offcut.width:.2f}" height="{offcut.height:.2f}" />"""
        for offcut in sheet.offcuts
    )
    material_tag = f" &middot; {html.escape(sheet.material)}" if sheet.material and sheet.material != "default" else ""
    return f"""  <section class="sheet">
    <h2>Sheet {sheet.sheet_id}{material_tag}</h2>
    <p>{sheet.width:.0f} x {sheet.height:.0f} mm | Utilization {sheet.utilization_percent:.1f}% | Waste {sheet.waste_percent:.1f}% | Cut order: top &rarr; bottom, left &rarr; right</p>
    <svg viewBox="0 0 {sheet.width:.0f} {sheet.height:.0f}" role="img" aria-label="Sheet {sheet.sheet_id} cutting layout">
{offcuts}
{parts}
    </svg>
  </section>"""


def _board_labels(boards: list[Board]) -> dict[str, str]:
    labels = {}
    for board in boards:
        base = board.id
        if board.source_objects:
            base = f"{board.id}: {', '.join(board.source_objects)}"
        if board.grain_locked:
            base += " [grain]"
        labels[board.id] = base
    return labels


def _model_fix_html(report: ModelFixReport) -> str:
    severity = "alert" if report.passes_gate else "alert danger"
    title = "Model quality check passed" if report.passes_gate else "Model needs fixing before cutting"
    issues = "".join(f"<li>{html.escape(issue)}</li>" for issue in report.issues)
    recs = "".join(f"<li>{html.escape(rec)}</li>" for rec in report.recommendations)
    return f"""<section class="{severity}">
    <h2>{title} - confidence {report.confidence:.1%} (threshold {report.confidence_threshold:.0%})</h2>
    <p><strong>Issues</strong></p>
    <ul>{issues}</ul>
    <p><strong>Recommendations</strong></p>
    <ul>{recs}</ul>
  </section>"""


def _sheet_options_html(options: tuple[SheetSizeOption, ...], currency: str) -> str:
    if not options:
        return ""
    rows = []
    for index, option in enumerate(options):
        cls = "best" if index == 0 else ""
        rows.append(
            f"<tr class='{cls}'><td>{html.escape(option.label)}</td>"
            f"<td>{option.width:.0f} x {option.height:.0f} mm</td>"
            f"<td>{option.sheet_count}</td>"
            f"<td>{option.utilization_percent:.1f}%</td>"
            f"<td>{option.waste_percent:.1f}%</td>"
            f"<td>{currency} {option.sheet_cost:,.2f}</td>"
            f"<td>{currency} {option.total_cost:,.2f}</td></tr>"
        )
    return f"""<section class="sheet">
    <h2>Sheet size comparison</h2>
    <table class="options">
      <thead><tr><th>Option</th><th>Size</th><th>Sheets</th><th>Utilization</th><th>Waste</th><th>Per sheet</th><th>Total</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </section>"""


def _manufacturing_insights(
    boards: list[Board],
    sheets: list[SheetLayout],
    extraction_report: ExtractionReport | None,
    material_summary: MaterialSummary | None,
    model_fix_report: ModelFixReport | None = None,
) -> list[str]:
    insights = []
    low_confidence = [board for board in boards if board.confidence < 0.85]
    if low_confidence:
        insights.append(f"Review {len(low_confidence)} low-confidence board detections before CNC export.")
    if extraction_report and extraction_report.unmatched_surface_count:
        insights.append("Geometry cleanup is recommended because some planar surfaces were not paired into boards.")
    if material_summary and material_summary.waste_percent > 20:
        insights.append("Sheet waste is above 20%; review part orientation, sheet size, and reusable offcuts before purchase.")
    if material_summary and material_summary.reusable_offcut_area:
        insights.append(f"Reusable offcuts total {material_summary.reusable_offcut_area:.2f} sq m.")
    if material_summary and material_summary.cost_savings_vs_worst_strategy > 0:
        insights.append(
            f"Selected nesting strategy saved {material_summary.currency} "
            f"{material_summary.cost_savings_vs_worst_strategy:,.2f} vs the worst-performing strategy."
        )
    if model_fix_report and not model_fix_report.passes_gate:
        insights.append("Cutlist gated: model confidence below threshold. See model_fix_report for what to fix.")
    if sheets:
        best = max(sheet.utilization_percent for sheet in sheets)
        insights.append(f"Best sheet utilization is {best:.1f}%.")
    if not insights:
        insights.append("No major manufacturability risks were detected in this run.")
    return insights
