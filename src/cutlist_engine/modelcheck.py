"""Modelling problems: what is wrong with the 3D model, found by code.

A plan can look fine and still come from a poor model: handles counted as
boards, merged shapes, a dozen odd thicknesses. This module measures that from
the finished plan and gives each problem a plain title, what was seen, and how
to fix it. These texts are complete on their own. The AI layer only re-explains
the same facts in friendlier words (see ai.explain_model_problems), so with AI
off nothing is lost and a number is never invented.
"""

from __future__ import annotations

import re
from typing import Any

from .assistant import is_generic_name

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}
MANY_THICKNESSES = 4
LOW_USE_PERCENT = 35.0


def find_problems(summary: dict[str, Any]) -> dict[str, Any]:
    """Problems with the model behind a serialised plan.

    Returns {"severity": "none"|"low"|"medium"|"high", "items": [...]}. Each
    item: code, severity, title, detail (what was found, with numbers), fix.
    """
    items: list[dict[str, str]] = []
    extraction = summary.get("extraction_report") or {}
    fix = summary.get("model_fix_report") or {}
    material = summary.get("material_summary") or {}
    boards = summary.get("boards") or []
    sheets = summary.get("sheets") or []
    oversize = summary.get("oversize_parts") or []
    board_count = len(boards)

    def add(code: str, severity: str, title: str, detail: str, fix_text: str) -> None:
        items.append({"code": code, "severity": severity, "title": title, "detail": detail, "fix": fix_text})

    if fix and fix.get("passes_gate") is False:
        add(
            "low_confidence", "high",
            "The sizes could not be read reliably",
            f"Measurement confidence is {float(fix.get('confidence', 0)) * 100:.0f}%, "
            f"below the {float(fix.get('confidence_threshold', 0)) * 100:.0f}% needed to trust the plan.",
            "Model each panel as its own closed solid (a group or component) with both faces and its real "
            "thickness, then export again.",
        )

    if oversize:
        sizes = sorted({(round(b["length"]), round(b["width"]), b["thickness"]) for b in oversize}, reverse=True)
        listed = ", ".join(f"{l} x {w} mm ({t:g} thick)" for l, w, t in sizes[:5])
        add(
            "oversize", "high",
            "Parts bigger than the sheet",
            f"{len(oversize)} part(s) do not fit the sheet and are left out of the plan: {listed}.",
            "Check these are not merged or wrongly scaled shapes. Split a genuinely long panel at a joint, "
            "or choose a longer sheet.",
        )

    skipped = list(extraction.get("skipped_parts") or [])
    solids = int(extraction.get("solid_part_count") or 0)
    if len(skipped) >= 3 and (len(skipped) >= board_count or len(skipped) / max(solids, 1) >= 0.25):
        names = ", ".join(_short_names(skipped, 5))
        examples = f" (for example {names})" if names else ""
        add(
            "skipped_solids",
            "high" if len(skipped) >= max(board_count, 1) * 2 else "medium",
            "Many parts are not flat panels",
            f"{len(skipped)} solid part(s) were left out because they are not flat boards"
            f"{examples}, against {board_count} boards in the plan.",
            "Hide or delete handles, hardware, legs and decoration before exporting. Model every real panel "
            "as a flat solid of sheet thickness.",
        )

    thicknesses = sorted({round(float(b.get("thickness", 0)), 1) for b in boards})
    if len(thicknesses) >= MANY_THICKNESSES:
        listed = ", ".join(f"{t:g}" for t in thicknesses[:10]) + (", and more" if len(thicknesses) > 10 else "")
        add(
            "many_thicknesses", "medium",
            "Too many different thicknesses",
            f"The boards come in {len(thicknesses)} thicknesses ({listed} mm). A normal cabinet uses two or three.",
            "Odd thicknesses are usually decoration, thin surfaces or solids that overlap. Remove or hide them, "
            "and model panels at real board thicknesses (for example 18 mm and 6 mm).",
        )

    sheet_count = int(material.get("sheet_count") or 0)
    use = float(material.get("utilization_percent") or 0.0)
    if sheet_count >= 3 and use < LOW_USE_PERCENT:
        add(
            "low_use", "medium",
            "Sheets are mostly empty",
            f"{sheet_count} sheets are planned but only {use:.0f}% of their area is used.",
            "This usually means parts of different thicknesses each need their own sheet, or the model has "
            "extra pieces that are not real boards. Fix the thicknesses and extra pieces first.",
        )

    inferred = int(extraction.get("inferred_board_count") or 0)
    if inferred >= 3 and inferred / max(board_count, 1) >= 0.2:
        add(
            "inferred", "medium",
            "Many sizes were worked out, not measured",
            f"{inferred} of {board_count} boards were rebuilt from loose faces, so their sizes are less reliable.",
            "Make each panel a closed solid group or component so it is measured directly.",
        )

    labels = [b.get("label") or b.get("id") or "" for b in boards]
    unnamed = sum(1 for name in labels if is_generic_name(str(name)))
    if board_count >= 8 and unnamed / board_count >= 0.6:
        add(
            "unnamed", "low",
            "Parts have no names",
            f"{unnamed} of {board_count} boards have no real name, so the cut list and labels say things "
            "like 'Component 12'.",
            "Name each component in the 3D program (for example 'Left side', 'Shelf 1') before exporting.",
        )

    if not items:
        return {"severity": "none", "items": []}
    worst = max(items, key=lambda item: SEVERITY_ORDER[item["severity"]])["severity"]
    items.sort(key=lambda item: -SEVERITY_ORDER[item["severity"]])
    return {"severity": worst, "items": items}


_JUNK_WORD = re.compile(r"^(mesh|group|component|model|object|default|solid)[_\d]*$", re.IGNORECASE)


def _short_names(skipped: list[str], limit: int) -> list[str]:
    """Readable names of skipped solids: the reason in brackets and the generic
    words of a 3D program's hierarchy ("Group1 Component_33_1 Model") are dropped.
    Names with nothing readable left are skipped rather than shown as noise."""
    out: list[str] = []
    for raw in skipped:
        words = [w for w in raw.split(" (", 1)[0].split() if not _JUNK_WORD.match(w)]
        name = " ".join(words)[:36].strip()
        if name and name not in out:
            out.append(name)
        if len(out) >= limit:
            break
    return out


def problems_as_facts(problems: dict[str, Any], source_name: str | None = None) -> str:
    """The problems as plain lines, the only thing the AI is given."""
    lines = []
    if source_name:
        lines.append(f"File: {source_name}")
    for item in problems.get("items", []):
        lines.append(f"- [{item['severity']}] {item['title']}: {item['detail']}")
    return "\n".join(lines)
