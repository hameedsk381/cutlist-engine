"""The code side of the plan assistant.

`plan_facts` writes down what the software already knows about a plan, so the
model answers from computed numbers instead of doing arithmetic.
`resolve_actions` turns the model's proposed changes into concrete, validated
settings. Nothing here calls a model and nothing here applies a change.
"""
from __future__ import annotations

import math
import re
from typing import Any

LOW_SHEET_USE_PERCENT = 35.0
LONG_SHELF_MM = 900.0
MAX_ROWS_IN_FACTS = 150

_EDGE_CHOICES = ("front", "long", "all", "none")
_EDGE_WORDS = {"front": "the front edge", "long": "both long edges", "all": "all 4 edges"}
_GENERIC_NAME = re.compile(r"^(part|object|mesh|group|component|solid|board|panel|cube|box)?[\s_#-]*\d*$", re.I)


def _band(choice: str, tape: float) -> list[float]:
    """[top, right, bottom, left]: top/bottom are the short edges."""
    if choice == "front":
        return [0, 0, 0, tape]
    if choice == "long":
        return [0, tape, 0, tape]
    return [tape, tape, tape, tape]


def _describe_band(band: list[float] | None) -> str:
    if not band or not any(v > 0 for v in band):
        return "none"
    top, right, bottom, left = band
    tape = max(band)
    if top > 0 and bottom > 0 and left > 0 and right > 0:
        return f"{tape:g} mm on all 4 edges"
    if left > 0 and right > 0:
        return f"{tape:g} mm on both long edges"
    return f"{tape:g} mm on the front edge"


def _row_name(item: dict[str, Any]) -> str:
    labels = [str(x) for x in (item.get("labels") or []) if x]
    seen: list[str] = []
    for label in labels:
        if label not in seen:
            seen.append(label)
    return ", ".join(seen) or str(item.get("id", "part"))


def is_generic_name(name: str) -> bool:
    return bool(_GENERIC_NAME.match(name.strip()))


def plan_facts(summary: dict[str, Any], quote_totals: dict[str, Any] | None = None) -> str:
    """A compact, numbered description of a finished plan for the model."""
    boards = {b["id"]: b for b in summary.get("boards", [])}
    cutlist = summary.get("cutlist", [])
    sheets = summary.get("sheets", [])
    material = summary.get("material_summary") or {}
    currency = material.get("currency") or "INR"
    lines: list[str] = []

    def sheet_thickness(sheet: dict[str, Any]) -> float | None:
        parts = sheet.get("parts") or []
        return boards.get(parts[0].get("board_id"), {}).get("thickness") if parts else None

    by_thickness: dict[float, int] = {}
    for sheet in sheets:
        t = sheet_thickness(sheet) or 0
        by_thickness[t] = by_thickness.get(t, 0) + 1
    split = ", ".join(f"{n} x {t:g} mm" for t, n in sorted(by_thickness.items(), reverse=True))
    lines.append(
        f"SUMMARY: {material.get('sheet_count', len(sheets))} sheets ({split}). "
        f"Material cost {currency} {float(material.get('total_material_cost') or 0):.0f}. "
        f"Wood used {float(material.get('utilization_percent') or 0):.0f}%, "
        f"left over {float(material.get('waste_percent') or 0):.0f}%. "
        f"Reusable spare pieces {float(material.get('reusable_offcut_area') or 0):.2f} m2."
    )

    lines.append("PARTS (row. quantity x name, cut length x width x thickness in mm, tape):")
    for row, item in enumerate(cutlist[:MAX_ROWS_IN_FACTS], start=1):
        ids = item.get("board_ids") or []
        band = boards.get(ids[0], {}).get("edge_band") if ids else None
        lines.append(
            f"{row}. {item.get('quantity', 1)} x {_row_name(item)}, "
            f"{float(item.get('length') or 0):.0f} x {float(item.get('width') or 0):.0f} x "
            f"{float(item.get('thickness') or 0):g}, tape: {_describe_band(band)}"
        )
    if len(cutlist) > MAX_ROWS_IN_FACTS:
        lines.append(f"... and {len(cutlist) - MAX_ROWS_IN_FACTS} more rows not listed.")

    lines.append("SHEETS:")
    for sheet in sheets[:40]:
        t = sheet_thickness(sheet)
        source = " (cut from a saved offcut, free)" if sheet.get("is_offcut_stock") else ""
        lines.append(
            f"Sheet {sheet.get('sheet_id')}: {float(sheet.get('width') or 0):.0f} x "
            f"{float(sheet.get('height') or 0):.0f} mm{f', {t:g} mm thick' if t else ''}, "
            f"{len(sheet.get('parts') or [])} parts, "
            f"{float(sheet.get('utilization_percent') or 0):.0f}% used{source}"
        )

    banding = summary.get("edge_banding") or {}
    if float(banding.get("total_m") or 0) > 0:
        per = ", ".join(f"{b['metres']} m of {b['thickness']:g} mm" for b in banding.get("by_thickness", []))
        lines.append(f"EDGE BANDING: {banding['total_m']} m of tape in total ({per}).")
    else:
        lines.append("EDGE BANDING: none set.")

    if quote_totals:
        q = quote_totals
        lines.append(
            f"QUOTE (saved): material {q['material']:.0f}, edge banding {q['edge_banding']:.0f}, "
            f"labour {q['labour']:.0f}, hardware {q['hardware']:.0f}, other {q['other']:.0f}, "
            f"margin {q['margin']:.0f}, TOTAL FOR CUSTOMER {q['currency']} {q['total']:.0f}."
            + (f" Customer: {q['customer']}." if q.get("customer") else "")
            + (f" Note: {q['note']}." if q.get("note") else "")
        )
    else:
        lines.append("QUOTE: none saved.")

    observations = _observations(summary, boards, sheet_thickness)
    if observations:
        lines.append("OBSERVATIONS (computed):")
        lines.extend(f"- {o}" for o in observations)
    return "\n".join(lines)


def _observations(summary: dict[str, Any], boards: dict[str, Any], sheet_thickness) -> list[str]:
    notes: list[str] = []
    sheets = summary.get("sheets", [])
    fresh = [s for s in sheets if not s.get("is_offcut_stock")]

    if len(fresh) > 1:
        weakest = min(fresh, key=lambda s: float(s.get("utilization_percent") or 0))
        used = float(weakest.get("utilization_percent") or 0)
        if used < LOW_SHEET_USE_PERCENT:
            cost = float(weakest.get("sheet_cost") or 0)
            notes.append(
                f"Sheet {weakest.get('sheet_id')} is only {used:.0f}% used "
                f"({len(weakest.get('parts') or [])} parts). If those parts were smaller or cut from "
                f"offcuts, one sheet" + (f" (cost {cost:.0f})" if cost else "") + " could be saved."
            )

    # Area-based floor for making several copies. The real count needs a new plan.
    area_by_thickness: dict[float, float] = {}
    sheet_area: dict[float, float] = {}
    for sheet in fresh:
        t = sheet_thickness(sheet)
        if t is None:
            continue
        area_by_thickness[t] = area_by_thickness.get(t, 0.0) + float(sheet.get("used_area") or 0)
        sheet_area[t] = float(sheet.get("width") or 0) * float(sheet.get("height") or 0)
    for t in sorted(area_by_thickness, reverse=True):
        if sheet_area.get(t) and area_by_thickness[t] > 0:
            now = sum(1 for s in fresh if sheet_thickness(s) == t)
            floors = ", ".join(
                f"{n} copies: at least {max(now, math.ceil(n * area_by_thickness[t] / sheet_area[t]))}"
                for n in (2, 3, 4, 5)
            )
            notes.append(
                f"{t:g} mm sheets needed for more copies, by area only ({floors}). "
                "These are minimums; the exact count needs a new plan."
            )

    for item in summary.get("cutlist", []):
        name = _row_name(item)
        if "shel" in name.lower() and float(item.get("length") or 0) > LONG_SHELF_MM and float(item.get("thickness") or 0) <= 18:
            notes.append(
                f"{name} is {float(item['length']):.0f} mm long. Shelves over {LONG_SHELF_MM:.0f} mm "
                "in 18 mm board can sag; a partition or support under it is advised."
            )
            break

    fix = summary.get("model_fix_report") or {}
    for issue in (fix.get("issues") or [])[:4]:
        notes.append(f"Check: {issue}")
    report = summary.get("extraction_report") or {}
    if report.get("skipped_parts"):
        skipped = ", ".join(str(x) for x in report["skipped_parts"][:6])
        notes.append(f"Not in the plan because they are not flat boards: {skipped}.")
    return notes


# ---------------------------------------------------------------------------
# Proposed changes
# ---------------------------------------------------------------------------

def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _rows(raw: Any, count: int) -> list[int]:
    if raw == "all":
        return list(range(1, count + 1))
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    rows = []
    for value in raw:
        number = _number(value)
        if number is not None and number == int(number) and 1 <= int(number) <= count and int(number) not in rows:
            rows.append(int(number))
    return rows


def resolve_actions(
    actions: list[dict[str, Any]],
    summary: dict[str, Any],
    current_overrides: dict[str, Any] | None = None,
    current_quote: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Turn model-proposed actions into at most two concrete proposals.

    Returns a list of:
      {"type": "overrides", "title": str, "overrides": {board_id: {...}}}
      {"type": "quote", "title": str, "quote": {...}}
    Unknown, malformed or no-op actions are dropped. The caller still runs the
    result through the normal settings validation before saving.
    """
    cutlist = summary.get("cutlist", [])
    overrides: dict[str, dict[str, Any]] = {k: dict(v) for k, v in (current_overrides or {}).items()}
    before = {k: dict(v) for k, v in overrides.items()}
    override_titles: list[str] = []
    quote = dict(current_quote or {})
    quote_titles: list[str] = []

    for action in actions:
        kind = action.get("type")

        if kind == "edge_band":
            choice = action.get("edges")
            rows = _rows(action.get("rows"), len(cutlist))
            if choice not in _EDGE_CHOICES or not rows:
                continue
            tape = _number(action.get("tape_mm"))
            tape = 2.0 if tape is None else tape
            if choice != "none" and not 0 < tape <= 5:
                continue
            parts = 0
            for row in rows:
                item = cutlist[row - 1]
                parts += int(item.get("quantity") or 1)
                for board_id in item.get("board_ids") or []:
                    entry = overrides.setdefault(board_id, {})
                    if choice == "none":
                        entry.pop("edge_band", None)
                        if not entry:
                            overrides.pop(board_id, None)
                    else:
                        entry["edge_band"] = _band(choice, tape)
            unit = "part" if parts == 1 else "parts"
            if choice == "none":
                override_titles.append(f"Remove the tape from {parts} {unit}")
            else:
                override_titles.append(f"{tape:g} mm tape on {_EDGE_WORDS[choice]} of {parts} {unit}")

        elif kind == "rename":
            rows = _rows(action.get("row"), len(cutlist))
            name = " ".join(str(action.get("name") or "").split())[:80]
            if len(rows) != 1 or not name:
                continue
            item = cutlist[rows[0] - 1]
            ids = item.get("board_ids") or []
            for index, board_id in enumerate(ids, start=1):
                # Keep identical parts apart on labels: "Shelf 1", "Shelf 2".
                overrides.setdefault(board_id, {})["label"] = name if len(ids) == 1 else f"{name} {index}"[:80]
            override_titles.append(f'Name row {rows[0]} "{name}"')

        elif kind == "quote":
            changed = []
            for source, target, label in (
                ("labour", "labour", "labour"),
                ("hardware", "hardware", "hardware"),
                ("other", "other", "other costs"),
                ("tape_rate", "edge_band_rate", "tape per metre"),
            ):
                value = _number(action.get(source))
                if value is not None and value >= 0:
                    quote[target] = value
                    changed.append(f"{label} {value:g}")
            margin = _number(action.get("margin_percent"))
            if margin is not None and 0 <= margin <= 500:
                quote["margin_percent"] = margin
                changed.append(f"margin {margin:g}%")
            for field in ("customer", "note"):
                if isinstance(action.get(field), str) and action[field].strip():
                    quote[field] = action[field].strip()
                    changed.append(f"{field} \"{quote[field][:40]}\"")
            if changed:
                quote_titles.append(", ".join(changed))

    proposals: list[dict[str, Any]] = []
    if override_titles and overrides != before:
        shown = override_titles[:4] + ([f"and {len(override_titles) - 4} more"] if len(override_titles) > 4 else [])
        proposals.append({"type": "overrides", "title": "; ".join(shown), "overrides": overrides})
    if quote_titles:
        proposals.append({"type": "quote", "title": "Quote: " + "; ".join(quote_titles), "quote": quote})
    return proposals
