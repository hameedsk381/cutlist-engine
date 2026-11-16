"""Cut sequence: the order of straight edge-to-edge saw cuts that turns a sheet
into its parts.

The nesting step places parts with guillotine-style free-space splits, so every
sheet it produces can be cut apart with full-length cuts. This module works the
cuts out again from the finished layout (parts and their positions), so it does
not depend on how the layout was made and can check any layout.

All numbers are millimetres. x runs along the sheet width, y along its height,
both from the top-left corner, as in the sheet drawing.

A cut at `position` uses the saw blade's kerf: the blade removes the strip from
`position` to `position + kerf`. Distances are measured to the near side of the
blade.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from .models import SheetLayout

_GAP_EPS = 1e-6
"""Parts closer than this count as touching: no saw cut fits between them."""
_TRIM_EPS = 0.5
"""Waste thinner than this is ignored: it is rounding, not a cut."""


@dataclass(frozen=True)
class _Rect:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


def cut_sequence(sheet: SheetLayout, kerf: float) -> dict[str, Any]:
    """The cuts for one sheet, in the order to make them.

    Returns {"ok": bool, "steps": [...]}. `ok` is False only when some group of
    parts cannot be separated by straight cuts (never produced by this
    project's nesting); the steps found so far are still returned.

    Each step: step (1-based), stage (0 = first cuts across the whole sheet),
    kind ("split" between parts or "trim" off waste), direction ("horizontal":
    the cut line runs left-right, "vertical": top-bottom), position (mm from
    the sheet's top edge for horizontal, left edge for vertical), from_edge
    (the same distance measured from the edge of the piece being cut), piece
    ([width, height] of the piece being cut), line ([x0, y0, x1, y1] of the cut
    line on the sheet) and frees (ids of parts that are finished by this cut).
    """
    parts = [
        (p.board_id, p.x, p.y, p.x + p.length, p.y + p.width) for p in sheet.parts
    ]
    steps: list[dict[str, Any]] = []
    ok = True
    # Whole-sheet region first, then each piece in turn, one stage at a time
    # (every cut across the full sheet before any cut across a strip).
    queue: deque[tuple[_Rect, list[tuple], int, int | None]] = deque(
        [(_Rect(0.0, 0.0, sheet.width, sheet.height), parts, 0, None)]
    )

    def emit(kind, direction, pos, region, stage) -> int:
        if direction == "horizontal":
            line = [region.x0, pos, region.x1, pos]
            from_edge = pos - region.y0
        else:
            line = [pos, region.y0, pos, region.y1]
            from_edge = pos - region.x0
        steps.append({
            "step": len(steps) + 1,
            "stage": stage,
            "kind": kind,
            "direction": direction,
            "position": round(pos, 2),
            "from_edge": round(from_edge, 2),
            "piece": [round(region.width, 2), round(region.height, 2)],
            "line": [round(v, 2) for v in line],
            "kerf": kerf,
            "frees": [],
        })
        return len(steps) - 1

    while queue:
        region, group, stage, producer = queue.popleft()
        if not group:
            continue

        # Trim waste off the outside of the group first: one cut can clear
        # waste for every part inside the piece.
        trimmed = True
        while trimmed:
            trimmed = False
            bx0 = min(p[1] for p in group)
            by0 = min(p[2] for p in group)
            bx1 = max(p[3] for p in group)
            by1 = max(p[4] for p in group)
            if region.x1 - bx1 > _TRIM_EPS:
                producer = emit("trim", "vertical", bx1, region, stage)
                region = _Rect(region.x0, region.y0, bx1, region.y1)
                trimmed = True
            elif region.y1 - by1 > _TRIM_EPS:
                producer = emit("trim", "horizontal", by1, region, stage)
                region = _Rect(region.x0, region.y0, region.x1, by1)
                trimmed = True
            elif bx0 - region.x0 > kerf + _TRIM_EPS:
                producer = emit("trim", "vertical", bx0 - kerf, region, stage)
                region = _Rect(bx0, region.y0, region.x1, region.y1)
                trimmed = True
            elif by0 - region.y0 > kerf + _TRIM_EPS:
                producer = emit("trim", "horizontal", by0 - kerf, region, stage)
                region = _Rect(region.x0, by0, region.x1, region.y1)
                trimmed = True

        if len(group) == 1:
            if producer is not None:
                steps[producer]["frees"].append(group[0][0])
            continue

        split = _find_split(group)
        if split is None:
            ok = False
            continue
        axis, pos, first, second = split
        direction = "horizontal" if axis == 1 else "vertical"
        index = emit("split", direction, pos, region, stage)
        if axis == 1:
            a = _Rect(region.x0, region.y0, region.x1, pos)
            b = _Rect(region.x0, pos + kerf, region.x1, region.y1)
        else:
            a = _Rect(region.x0, region.y0, pos, region.y1)
            b = _Rect(pos + kerf, region.y0, region.x1, region.y1)
        queue.append((a, first, stage + 1, index))
        queue.append((b, second, stage + 1, index))

    return {"ok": ok, "steps": steps}


def _find_split(group: list[tuple]) -> tuple[int, float, list[tuple], list[tuple]] | None:
    """A full-length cut that separates the group in two, or None.

    Tries a cut across the piece (horizontal) before a cut down it (vertical),
    as the nesting step lays strips out that way. Returns (axis, position,
    parts before the cut, parts after it); axis 1 is y (horizontal cut).
    """
    for axis in (1, 0):
        ordered = sorted(group, key=lambda p: p[1 + axis])
        reach = ordered[0][3 + axis]
        for k in range(1, len(ordered)):
            if ordered[k][1 + axis] >= reach - _GAP_EPS:
                return axis, reach, ordered[:k], ordered[k:]
            reach = max(reach, ordered[k][3 + axis])
    return None
