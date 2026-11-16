"""Direct reader for SketchUp models.

The SketchUp extension reads each component's real size from SketchUp itself
(its box in its own axes, its name, material and tag) and sends a short list of
parts. That is far more reliable than rebuilding boards from an exported mesh:
there are no closed-solid, unit or naming problems to recover from.

This module is the server half. It decides which parts are boards, spots the
modelling problems a designer can fix in SketchUp, and builds the model file
that goes through the normal cutting pipeline. The extension itself does no
judging, so every rule here is covered by tests.

Payload (sizes in millimetres, already converted from SketchUp inches):

    {"model": "Wardrobe",
     "parts": [{"name": "Left side", "definition": "Component#3",
                "path": "Wardrobe > Carcass", "tag": "Carcass",
                "material": "Plywood 18mm",
                "dims": [2100.0, 600.0, 18.0],   # the part's own box, any order
                "fill": 1.0,                     # share of that box the board fills, or null
                "hidden": false}]}
"""
from __future__ import annotations

import html
import math
import re
from dataclasses import dataclass
from typing import Any

from .assistant import is_generic_name
from .boards import MAX_PANEL_THICKNESS, STOCK_THICKNESSES
from .furniture import Part, to_obj

MAX_PARTS = 5000
MIN_THICKNESS = 2.0       # thinner is a flat surface, not a board
MIN_PART_SIZE = 50.0      # matches the plan's default: smaller is trim or hardware
SNAP_TOLERANCE = 0.5      # 17.8 mm modelled is read as 18 mm board
GAP = 100.0               # space between parts in the generated model

# Whole words, so "Handle" matches but "Chandelier" does not.
_HARDWARE_WORDS = frozenset("""
hinge hinges handle handles knob knobs pull pulls screw screws nail nails dowel dowels
channel channels slide slides runner runners leg legs foot feet castor caster castors
casters hardware fitting fittings bracket brackets light lights lamp lamps bulb led
socket sockets switch switches plug mirror mirrors glass tv television plant plants
decor decoration decorations vase person people human figure figures dimension dimensions
text label labels rod rods hanger hangers accessory accessories
""".split())

_UNNAMED = re.compile(r"^(component|group)\s*#?\d*$", re.IGNORECASE)
_MATERIAL_MM = re.compile(r"(\d+(?:\.\d+)?)\s*mm", re.IGNORECASE)


@dataclass(frozen=True)
class Panel:
    name: str
    length: float
    width: float
    thickness: float
    material: str
    named: bool


@dataclass
class Report:
    model: str
    panels: list[Panel]
    excluded: list[dict[str, Any]]
    issues: list[dict[str, Any]]
    hidden: int

    @property
    def ready(self) -> bool:
        return bool(self.panels) and not any(i["level"] == "stop" for i in self.issues)

    def to_dict(self) -> dict[str, Any]:
        by_thickness: dict[float, int] = {}
        for panel in self.panels:
            by_thickness[panel.thickness] = by_thickness.get(panel.thickness, 0) + 1
        return {
            "model": self.model,
            "ready": self.ready,
            "panel_count": len(self.panels),
            "by_thickness": [{"thickness": t, "count": n} for t, n in sorted(by_thickness.items(), reverse=True)],
            "rows": _rows(self.panels),
            "excluded": self.excluded,
            "issues": self.issues,
            "hidden": self.hidden,
        }


def _words(text: str) -> set[str]:
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", text or "")
    return set(re.findall(r"[a-z]+", spaced.lower()))


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _meaningful(name: Any) -> str:
    text = " ".join(str(name or "").split())
    return "" if not text or _UNNAMED.match(text) or is_generic_name(text) else text[:80]


def _fmt(value: float) -> str:
    return f"{value:g}" if abs(value - round(value)) > 0.05 else f"{round(value)}"


def _snap(thickness: float) -> float:
    nearest = min(STOCK_THICKNESSES, key=lambda s: abs(s - thickness))
    return nearest if abs(nearest - thickness) <= SNAP_TOLERANCE else round(thickness, 2)


def _issue(level: str, title: str, detail: str, fix: str, names: list[str]) -> dict[str, Any]:
    unique: list[str] = []
    for name in names:
        if name not in unique:
            unique.append(name)
    return {"level": level, "title": title, "detail": detail, "fix": fix, "names": unique[:12], "count": len(names)}


def analyse(payload: Any) -> Report:
    """Decide which parts are boards and what a designer should fix. Raises ValueError."""
    if not isinstance(payload, dict) or not isinstance(payload.get("parts"), list):
        raise ValueError("Send a list of parts: {\"parts\": [...]}.")
    raw_parts = payload["parts"]
    if len(raw_parts) > MAX_PARTS:
        raise ValueError(f"That is {len(raw_parts):,} parts; the limit is {MAX_PARTS:,}. Select just the furniture.")

    panels: list[Panel] = []
    excluded: dict[tuple[str, str], int] = {}
    hidden = 0
    unnamed: list[str] = []
    not_stock: list[str] = []
    mismatch: list[str] = []
    cutouts: list[str] = []
    shaped: list[str] = []
    surfaces: list[str] = []

    def leave_out(name: str, reason: str) -> None:
        excluded[(name, reason)] = excluded.get((name, reason), 0) + 1

    for raw in raw_parts:
        if not isinstance(raw, dict):
            raise ValueError("Each part must be an object.")
        if raw.get("hidden"):
            hidden += 1
            continue
        dims = raw.get("dims")
        numbers = [_number(v) for v in dims] if isinstance(dims, list) and len(dims) == 3 else []
        if len(numbers) != 3 or any(v is None for v in numbers):
            raise ValueError("Each part needs dims: three sizes in mm.")
        length, width, thickness = sorted(numbers, reverse=True)  # type: ignore[type-var]

        own = _meaningful(raw.get("name")) or _meaningful(raw.get("definition"))
        shown = own or f"Unnamed {_fmt(length)} x {_fmt(width)}"

        words = _words(raw.get("name")) | _words(raw.get("definition")) | _words(raw.get("tag"))
        found = sorted(words & _HARDWARE_WORDS)
        if found:
            leave_out(shown, f"hardware or decoration (\"{found[0]}\")")
            continue
        if length <= 0 or width <= 0:
            leave_out(shown, "no size")
            continue
        if thickness < MIN_THICKNESS:
            surfaces.append(shown)
            leave_out(shown, f"a flat surface with no thickness ({thickness:.1f} mm)")
            continue
        if thickness > MAX_PANEL_THICKNESS:
            leave_out(shown, f"a block {_fmt(thickness)} mm thick, not sheet material")
            continue
        if width < MIN_PART_SIZE:
            leave_out(shown, f"smaller than {MIN_PART_SIZE:g} mm across (trim, edge strip or hardware)")
            continue

        board = _snap(thickness)
        if board not in STOCK_THICKNESSES:
            not_stock.append(f"{shown} ({board:g} mm)")
        hint = _MATERIAL_MM.search(str(raw.get("material") or ""))
        if hint and 3 <= float(hint.group(1)) <= 40 and abs(float(hint.group(1)) - board) > 1.0:
            mismatch.append(f"{shown}: material {hint.group(1)} mm, drawn {_fmt(board)} mm")
        fill = _number(raw.get("fill"))
        if fill is not None:
            if fill < 0.6:
                shaped.append(shown)
            elif fill < 0.97:
                cutouts.append(shown)
        if not own:
            unnamed.append(shown)

        panels.append(Panel(shown, round(length, 1), round(width, 1), board, str(raw.get("material") or ""), bool(own)))

    issues: list[dict[str, Any]] = []
    if not panels:
        issues.append(_issue(
            "stop", "No boards found",
            "None of the selected parts looked like a board.",
            "Select the furniture, make each board its own group or component, and give it its real thickness.",
            [],
        ))
    if surfaces:
        issues.append(_issue(
            "warn", "Flat surfaces without thickness",
            f"{len(surfaces)} part(s) are a single face, so there is nothing to measure as a board.",
            "Give each one its thickness with Push/Pull, then check again.", surfaces,
        ))
    if mismatch:
        issues.append(_issue(
            "warn", "Material does not match the drawn thickness",
            "The material name says one thickness and the board is drawn another. We use the drawn size.",
            "Fix whichever is wrong: the drawn thickness or the material name.", mismatch,
        ))
    if not_stock:
        issues.append(_issue(
            "warn", "Not a common board thickness",
            "These boards are used at the drawn thickness and get sheets of their own.",
            "If they should be a standard board, redraw them at 6, 12, 15, 16, 18, 19 or 25 mm.", not_stock,
        ))
    if shaped:
        issues.append(_issue(
            "warn", "Shaped or curved boards",
            "These boards are far from rectangular. They are planned as their full rectangle, which wastes sheet.",
            "Cut them from a drawing of the real shape on the CNC, or accept the rectangle.", shaped,
        ))
    if cutouts:
        issues.append(_issue(
            "info", "Boards with notches or holes",
            "They are planned as a full rectangle. Holes and notches are cut afterwards.",
            "Nothing to do unless the notch is large.", cutouts,
        ))
    if unnamed:
        issues.append(_issue(
            "warn", "Boards without a name",
            f"{len(unnamed)} board(s) are named after their size, so labels will not say what they are.",
            "Name each component: select it, then type a name in Entity Info (for example \"Left side\").", unnamed,
        ))
    if excluded:
        issues.append(_issue(
            "info", "Parts left out of the plan",
            f"{sum(excluded.values())} part(s) were not treated as boards. They are listed below.",
            "If one of them is a real board, redraw it as a solid at sheet thickness.", [],
        ))
    if hidden:
        issues.append(_issue(
            "info", "Hidden parts ignored",
            f"{hidden} hidden part(s) or parts on hidden tags were not sent.",
            "Show them first if they should be cut.", [],
        ))
    order = {"stop": 0, "warn": 1, "info": 2}
    issues.sort(key=lambda i: order[i["level"]])

    left_out = [
        {"name": name, "reason": reason, "count": count}
        for (name, reason), count in sorted(excluded.items(), key=lambda kv: (kv[0][1], kv[0][0]))
    ]
    return Report(str(payload.get("model") or "SketchUp model")[:120], panels, left_out, issues, hidden)


def _rows(panels: list[Panel]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, float, float, float], int] = {}
    for panel in panels:
        key = (panel.name, panel.length, panel.width, panel.thickness)
        grouped[key] = grouped.get(key, 0) + 1
    return [
        {"name": name, "length": length, "width": width, "thickness": thickness, "quantity": count}
        for (name, length, width, thickness), count in sorted(grouped.items(), key=lambda kv: (-kv[0][3], kv[0][0], -kv[0][1]))
    ]


def main_thickness(panels: list[Panel]) -> float:
    """The board thickness that covers the most area: the plan's main sheet."""
    area: dict[float, float] = {}
    for panel in panels:
        area[panel.thickness] = area.get(panel.thickness, 0.0) + panel.length * panel.width
    return max(area, key=lambda t: area[t]) if area else 18.0


def build_model(report: Report) -> dict[str, Any]:
    """The boards as an OBJ model in mm, one named solid each, laid out in a row."""
    parts: list[Part] = []
    x = 0.0
    for panel in report.panels:
        name = " ".join(panel.name.split())
        parts.append(Part(name, panel.length, panel.width, panel.thickness,
                          (x, 0.0, 0.0, x + panel.length, panel.width, panel.thickness)))
        x += panel.length + GAP
    title = report.model
    return {
        "filename": (re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_") or "sketchup") + ".obj",
        "title": title,
        "obj": to_obj(parts, title),
        "thickness": main_thickness(report.panels),
    }


# ---------------------------------------------------------------------------
# Check screen (shown inside SketchUp)
# ---------------------------------------------------------------------------

_CSS = """
:root{color-scheme:light dark;--bg:#fff;--fg:#1c1917;--muted:#6b645d;--line:#e2ddd6;--stop:#b91c1c;--warn:#a16207;--info:#0e5c4a;--accent:#0e5c4a}
@media (prefers-color-scheme:dark){:root{--bg:#1c1917;--fg:#f5f1ea;--muted:#a8a095;--line:#3a3530;--stop:#f87171;--warn:#fbbf24;--info:#5eead4;--accent:#2dd4bf}}
body{font:15px/1.5 system-ui,Segoe UI,sans-serif;margin:0;padding:20px 20px 90px;background:var(--bg);color:var(--fg)}
h1{font-size:20px;margin:0 0 4px}h2{font-size:16px;margin:24px 0 8px}p{margin:4px 0}.muted{color:var(--muted)}
.issue{border-left:4px solid var(--line);padding:6px 12px;margin:10px 0}.issue b{display:block}
.stop{border-color:var(--stop)}.warn{border-color:var(--warn)}.info{border-color:var(--info)}
.tag{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.04em}
.stop .tag{color:var(--stop)}.warn .tag{color:var(--warn)}.info .tag{color:var(--info)}
table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.bar{position:fixed;left:0;right:0;bottom:0;padding:12px 20px;background:var(--bg);border-top:1px solid var(--line);display:flex;gap:10px;align-items:center}
button{font:inherit;font-weight:600;padding:10px 18px;border-radius:8px;border:1px solid var(--line);background:transparent;color:var(--fg);cursor:pointer}
button.go{background:var(--accent);border-color:var(--accent);color:#fff}button:disabled{opacity:.45;cursor:not-allowed}
"""

_LABELS = {"stop": "Fix first", "warn": "Check", "info": "Good to know"}


def render_check_page(report: Report, interactive: bool = False) -> str:
    """A self-contained page. With `interactive`, it carries Send and Close buttons for SketchUp."""
    data = report.to_dict()
    e = html.escape
    out = [f"<!doctype html><meta charset=utf-8><title>CutList check</title><style>{_CSS}</style>"]
    out.append(f"<h1>{e(report.model)}</h1>")
    if report.ready:
        sizes = ", ".join(f"{b['count']} × {_fmt(b['thickness'])} mm" for b in data["by_thickness"])
        out.append(f"<p><b>{data['panel_count']} boards found</b> ({e(sizes)}). Check the notes, then send.</p>")
    else:
        out.append("<p><b>Not ready to send.</b> Fix the first item below.</p>")

    for issue in report.issues:
        out.append(f"<div class='issue {issue['level']}'><span class=tag>{_LABELS[issue['level']]}</span>"
                   f"<b>{e(issue['title'])}</b><p>{e(issue['detail'])}</p>")
        if issue["names"]:
            more = issue["count"] - len(issue["names"])
            out.append(f"<p class=muted>{e(', '.join(issue['names']))}{f' and {more} more' if more > 0 else ''}</p>")
        out.append(f"<p>{e(issue['fix'])}</p></div>")

    if data["rows"]:
        out.append("<h2>Boards</h2><table><tr><th class=n>Qty</th><th>Name</th><th class=n>Length</th>"
                   "<th class=n>Width</th><th class=n>Thick</th></tr>")
        for row in data["rows"]:
            out.append(f"<tr><td class=n>{row['quantity']}</td><td>{e(row['name'])}</td>"
                       f"<td class=n>{_fmt(row['length'])}</td><td class=n>{_fmt(row['width'])}</td>"
                       f"<td class=n>{_fmt(row['thickness'])}</td></tr>")
        out.append("</table>")
    if data["excluded"]:
        out.append("<h2>Left out of the plan</h2><table><tr><th>Part</th><th>Why</th></tr>")
        for row in data["excluded"]:
            qty = f" × {row['count']}" if row["count"] > 1 else ""
            out.append(f"<tr><td>{e(row['name'])}{qty}</td><td>{e(row['reason'])}</td></tr>")
        out.append("</table>")

    if interactive:
        disabled = "" if report.ready else " disabled"
        out.append(
            "<div class=bar><button class=go id=send" + disabled + " onclick=\"if(window.sketchup)sketchup.send_to_cutlist()\">"
            "Send to CutList</button><button onclick=\"if(window.sketchup)sketchup.close_dialog()\">Close</button>"
            "<span class=muted>Run the check again after fixing the model.</span></div>"
        )
    return "".join(out)
