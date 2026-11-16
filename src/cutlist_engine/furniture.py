"""Description -> furniture model, with every size computed in code.

A sentence such as "Wardrobe 2100 high, 1200 wide, 600 deep, 2 shutters,
4 shelves" is parsed into a `FurnitureSpec` (rule-based, no network needed).
`build_parts` applies fixed, documented carcass rules to get every panel, and
`to_obj` writes them as a real assembled 3D model with one named solid per
panel. That file goes through the normal extraction pipeline, so a described
job gets the same review, DXF, G-code and labels as an uploaded one.

No language model does arithmetic here. An LLM may optionally be used only to
pull the parameters out of free text when the rules cannot (see `parse_spec`).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from typing import Any, Callable

KINDS = ("wardrobe", "tall_unit", "base_cabinet", "wall_cabinet", "loft", "bookshelf", "cabinet")

SHELF_SETBACK = 20.0     # shelves stop this far behind the front edge
DOOR_GAP = 3.0           # gap around and between shutters
MAX_SHELF_SPAN = 900.0   # wider than this and a vertical partition is added
DEFAULT_PLINTH = {"wardrobe": 75.0}

SLIDE_CLEARANCE = 13.0     # per side, for side-mounted telescopic drawer channels
CHANNEL_STEP = 50.0        # channels are sold in 50 mm length steps
CHANNEL_MAX = 600.0
INTERNAL_DRAWER_HEIGHT = 150.0
DRAWER_SPACING = 30.0


@dataclass(frozen=True)
class FurnitureSpec:
    kind: str
    width: float
    height: float
    depth: float
    shelves: int = 0
    shutters: int = 0
    drawers: int = 0
    partitions: int | None = None   # None = decide from MAX_SHELF_SPAN
    thickness: float = 18.0
    back_thickness: float = 6.0
    plinth: float = 0.0
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Part:
    name: str
    length: float
    width: float
    thickness: float
    box: tuple[float, float, float, float, float, float] = field(repr=False, default=(0, 0, 0, 0, 0, 0))


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_KIND_WORDS: tuple[tuple[str, str], ...] = (
    (r"wardrobe|almirah|almari|cupboard|closet", "wardrobe"),
    (r"loft", "loft"),
    (r"tall\s*(unit|cabinet)|tallboy|pantry", "tall_unit"),
    (r"wall\s*(unit|cabinet)|overhead|upper\s*(unit|cabinet)", "wall_cabinet"),
    (r"base\s*(unit|cabinet)|kitchen\s*(base|unit|cabinet)|under\s*counter", "base_cabinet"),
    (r"book\s*shel(f|ves)|bookcase|shelf\s*unit|shelving|rack", "bookshelf"),
)
_UNIT_MM = {
    "mm": 1.0, "cm": 10.0, "m": 1000.0,
    "ft": 304.8, "feet": 304.8, "foot": 304.8, "'": 304.8,
    "in": 25.4, "inch": 25.4, "inches": 25.4, '"': 25.4,
}
_NUM = r"(\d+(?:\.\d+)?)"
_UNIT = r"(mm|cm|m|ft|feet|foot|inches|inch|in|'|\")?"
_WORD_NUMBERS = {
    "no": 0, "zero": 0, "a": 1, "an": 1, "one": 1, "single": 1, "two": 2, "double": 2, "three": 3,
    "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_DIMENSIONS = {
    "height": r"high|height|tall|ht|h",
    "width": r"wide|width|w",
    "depth": r"deep|depth|d",
}


def _to_mm(value: str, unit: str | None) -> float:
    return float(value) * _UNIT_MM.get((unit or "mm").lower(), 1.0)


def _find_dimension(text: str, words: str) -> float | None:
    after = re.search(rf"{_NUM}\s*{_UNIT}\s*(?:{words})\b", text)
    if after:
        return _to_mm(after.group(1), after.group(2))
    before = re.search(rf"\b(?:{words})\s*(?:of|is|=|:)?\s*{_NUM}\s*{_UNIT}", text)
    if before:
        return _to_mm(before.group(1), before.group(2))
    return None


def _find_count(text: str, words: str) -> int | None:
    match = re.search(rf"\b(\d+|{'|'.join(_WORD_NUMBERS)})\s+(?:\w+\s+)?(?:{words})\b", text)
    if not match:
        return None
    raw = match.group(1)
    return int(raw) if raw.isdigit() else _WORD_NUMBERS[raw]


def parse_spec(
    description: str,
    thickness: float = 18.0,
    llm_extract: Callable[[str], dict[str, Any]] | None = None,
) -> FurnitureSpec:
    """Read a furniture description into a spec.

    Rules are tried first. `llm_extract`, when given, is asked only for the
    parameters the rules could not find; it never supplies panel sizes.
    Raises ValueError, in plain language, when the overall size is missing.
    """
    text = " ".join(description.lower().replace("×", "x").split())
    notes: list[str] = []

    kind = "cabinet"
    for pattern, name in _KIND_WORDS:
        if re.search(pattern, text):
            kind = name
            break

    found: dict[str, float | None] = {key: _find_dimension(text, words) for key, words in _DIMENSIONS.items()}
    if any(value is None for value in found.values()):
        triple = re.search(rf"{_NUM}\s*{_UNIT}\s*(?:x|by)\s*{_NUM}\s*{_UNIT}\s*(?:x|by)\s*{_NUM}\s*{_UNIT}", text)
        if triple:
            unit = triple.group(6) or triple.group(4) or triple.group(2)
            values = [_to_mm(triple.group(i), triple.group(i + 1) or unit) for i in (1, 3, 5)]
            found = dict(zip(("height", "width", "depth"), values))
            notes.append(
                f"Read {values[0]:g} x {values[1]:g} x {values[2]:g} mm as height x width x depth."
            )

    counts: dict[str, int | None] = {
        "shelves": _find_count(text, r"shelf|shelves|racks?"),
        "shutters": _find_count(text, r"shutters?|doors?"),
        "partitions": _find_count(text, r"partitions?|dividers?|verticals?"),
        "drawers": _find_count(text, r"drawers?"),
    }
    if re.search(r"\bopen\b|without (shutters?|doors?)", text):
        counts["shutters"] = 0

    if llm_extract is not None and (any(v is None for v in found.values()) or kind == "cabinet"):
        try:
            extra = llm_extract(description) or {}
        except Exception:  # noqa: BLE001 - the rules' own error below is clearer
            extra = {}
        for key in ("height", "width", "depth"):
            if found.get(key) is None and isinstance(extra.get(key), (int, float)) and extra[key] > 0:
                found[key] = float(extra[key])
        for key in counts:
            if counts[key] is None and isinstance(extra.get(key), int) and extra[key] >= 0:
                counts[key] = extra[key]
        if kind == "cabinet" and extra.get("kind") in KINDS:
            kind = extra["kind"]

    missing = [key for key in ("height", "width", "depth") if not found.get(key)]
    if missing:
        raise ValueError(
            f"Please give the {', '.join(missing)} in mm, for example "
            '"Wardrobe 2100 high, 1200 wide, 600 deep, 2 shutters, 4 shelves".'
        )

    board = re.search(rf"{_NUM}\s*mm\s*(?:ply|plywood|board|mdf|carcass|thick)", text)
    if board:
        thickness = float(board.group(1))

    plinth = DEFAULT_PLINTH.get(kind, 0.0)
    skirting = re.search(rf"(?:skirting|plinth|kicker)\s*(?:of|is|=|:)?\s*{_NUM}|{_NUM}\s*(?:mm)?\s*(?:skirting|plinth|kicker)", text)
    if re.search(r"no (skirting|plinth|kicker)", text):
        plinth = 0.0
    elif skirting:
        plinth = float(skirting.group(1) or skirting.group(2))

    drawers = counts["drawers"] or 0
    shutters = counts["shutters"]
    if shutters is None:
        if kind == "bookshelf" or (kind == "base_cabinet" and drawers):
            shutters = 0  # a drawer base unit has drawer fronts instead of shutters
        else:
            shutters = 2 if found["width"] > 600 else 1  # type: ignore[operator]
            notes.append(f"No shutter count given, so {shutters} {'was' if shutters == 1 else 'were'} assumed.")

    spec = FurnitureSpec(
        kind=kind,
        width=float(found["width"]),    # type: ignore[arg-type]
        height=float(found["height"]),  # type: ignore[arg-type]
        depth=float(found["depth"]),    # type: ignore[arg-type]
        shelves=counts["shelves"] or 0,
        shutters=shutters,
        drawers=drawers,
        partitions=counts["partitions"],
        thickness=thickness,
        plinth=plinth,
        notes=tuple(notes),
    )
    validate_spec(spec)
    return spec


def validate_spec(spec: FurnitureSpec) -> None:
    t = spec.thickness
    problems = []
    if not 200 <= spec.width <= 6000:
        problems.append(f"width {spec.width:g} mm (expected 200 to 6000)")
    if not 200 <= spec.height <= 3000:
        problems.append(f"height {spec.height:g} mm (expected 200 to 3000)")
    if not 100 <= spec.depth <= 1200:
        problems.append(f"depth {spec.depth:g} mm (expected 100 to 1200)")
    if problems:
        raise ValueError("These sizes do not look right: " + "; ".join(problems) + ". Sizes are read as mm unless you give a unit.")
    if not 3 <= t <= 40:
        raise ValueError(f"Board thickness {t:g} mm does not look right.")
    if spec.height - spec.plinth - 2 * t < 100:
        raise ValueError("The skirting is too tall for this height.")
    if spec.shelves > 40 or spec.shutters > 12 or spec.drawers > 12 or (spec.partitions or 0) > 10:
        raise ValueError("That is more shelves, shutters, drawers or partitions than we can lay out.")


# ---------------------------------------------------------------------------
# Carcass rules
# ---------------------------------------------------------------------------


def build_parts(spec: FurnitureSpec) -> tuple[list[Part], tuple[str, ...]]:
    """Apply the carcass rules. Returns the parts and the assumptions made.

    Coordinates: x across the width, y from the front (0) to the back, z up.
    """
    validate_spec(spec)
    w, h, d, t, bt, p = spec.width, spec.height, spec.depth, spec.thickness, spec.back_thickness, spec.plinth
    inner_w = w - 2 * t
    inner_h = h - p - 2 * t
    notes = list(spec.notes)
    parts: list[Part] = []

    def add(name: str, x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> None:
        dims = sorted((round(x1 - x0, 1), round(y1 - y0, 1), round(z1 - z0, 1)), reverse=True)
        parts.append(Part(name, dims[0], dims[1], dims[2], (x0, y0, z0, x1, y1, z1)))

    add("Left side", 0, 0, 0, t, d, h)
    add("Right side", w - t, 0, 0, w, d, h)
    add("Bottom", t, 0, p, w - t, d, p + t)
    add("Top", t, 0, h - t, w - t, d, h)
    if p > 0:
        add("Skirting", t, SHELF_SETBACK, 0, w - t, SHELF_SETBACK + t, p)
    add("Back", t, d - bt, p + t, w - t, d, h - t)

    partitions = spec.partitions
    if partitions is None:
        partitions = max(0, math.ceil(inner_w / MAX_SHELF_SPAN) - 1)
        if partitions:
            notes.append(
                f"Added {partitions} vertical partition{'s' if partitions > 1 else ''} so no shelf spans more than {MAX_SHELF_SPAN:g} mm."
            )
    bays = partitions + 1
    bay_w = (inner_w - partitions * t) / bays
    if bay_w < 100:
        raise ValueError("Too many partitions for this width.")
    bay_x = [t + i * (bay_w + t) for i in range(bays)]
    for i in range(partitions):
        x = bay_x[i] + bay_w
        add("Partition" if partitions == 1 else f"Partition {i + 1}", x, 0, p + t, x + t, d - bt, h - t)

    # Drawers go in the first bay. A kitchen base unit with no shutters gets
    # drawer fronts across the whole front; anywhere else they are internal
    # drawers stacked from the bottom, behind the shutters.
    external_drawers = spec.drawers > 0 and spec.kind == "base_cabinet" and spec.shutters == 0
    drawer_stack = 0.0
    if spec.drawers:
        box_w = bay_w - 2 * SLIDE_CLEARANCE
        front_y = 0.0 if external_drawers else SHELF_SETBACK
        usable_depth = d - bt - (10.0 if external_drawers else SHELF_SETBACK)
        box_d = min(CHANNEL_MAX, math.floor(usable_depth / CHANNEL_STEP) * CHANNEL_STEP)
        if box_d < 250 or box_w - 2 * t < 100:
            raise ValueError("This unit is too small for drawers.")
        if external_drawers:
            slot = (inner_h - 10) / spec.drawers
            box_h = float(math.floor(min(200.0, slot - DRAWER_SPACING)))
            front_h = math.floor((h - p - DOOR_GAP * (spec.drawers + 1)) / spec.drawers)
            if box_h < 60 or front_h < 100:
                raise ValueError("Too many drawers for this height.")
            drawer_stack = inner_h  # the drawers fill this bay
        else:
            slot = INTERNAL_DRAWER_HEIGHT + DRAWER_SPACING
            box_h = INTERNAL_DRAWER_HEIGHT
            drawer_stack = spec.drawers * slot
            if drawer_stack > inner_h - 100:
                raise ValueError("Too many drawers for this height.")
        x0 = bay_x[0] + SLIDE_CLEARANCE
        for i in range(spec.drawers):
            tag = "Drawer" if spec.drawers == 1 else f"Drawer {i + 1}"
            z0 = p + t + 10 + i * slot
            add(f"{tag} bottom", x0, front_y, z0, x0 + box_w, front_y + box_d, z0 + bt)
            add(f"{tag} side L", x0, front_y, z0 + bt, x0 + t, front_y + box_d, z0 + bt + box_h)
            add(f"{tag} side R", x0 + box_w - t, front_y, z0 + bt, x0 + box_w, front_y + box_d, z0 + bt + box_h)
            add(f"{tag} box front", x0 + t, front_y, z0 + bt, x0 + box_w - t, front_y + t, z0 + bt + box_h)
            add(f"{tag} box back", x0 + t, front_y + box_d - t, z0 + bt, x0 + box_w - t, front_y + box_d, z0 + bt + box_h)
            if external_drawers:
                fz = p + DOOR_GAP + i * (front_h + DOOR_GAP)
                add(f"{tag} front", DOOR_GAP, -t - 2, fz, w - DOOR_GAP, -2, fz + front_h)
        notes.append(
            f"{spec.drawers} drawer box{'es' if spec.drawers > 1 else ''} {box_w:g} wide x {box_d:g} deep for "
            f"side-mounted telescopic channels ({SLIDE_CLEARANCE:g} mm clearance each side), with a {bt:g} mm bottom fixed underneath."
            + (" Drawer fronts cover the whole front." if external_drawers else " The drawers are internal, at the bottom of the first bay.")
        )

    # Shelves are shared out across the bays that have room, left to right,
    # evenly spaced in the height above any drawers.
    floor = [drawer_stack if i == 0 else 0.0 for i in range(bays)]
    open_bays = [i for i in range(bays) if inner_h - floor[i] >= 150]
    per_bay = [0] * bays
    if spec.shelves and not open_bays:
        notes.append("Shelves were left out because the drawers fill the unit.")
    else:
        for n in range(spec.shelves):
            per_bay[open_bays[n % len(open_bays)]] += 1
    number = 0
    shelf_total = sum(per_bay)
    for bay, count in enumerate(per_bay):
        clear = inner_h - floor[bay] - count * t
        if count and clear / (count + 1) < 50:
            raise ValueError("Too many shelves for this height.")
        for k in range(count):
            number += 1
            z = p + t + floor[bay] + (k + 1) * clear / (count + 1) + k * t
            add(
                "Shelf" if shelf_total == 1 else f"Shelf {number}",
                bay_x[bay], SHELF_SETBACK, z, bay_x[bay] + bay_w, d - bt, z + t,
            )

    if spec.shutters:
        door_w = math.floor((w - DOOR_GAP * (spec.shutters + 1)) / spec.shutters)
        if door_w < 100:
            raise ValueError("Too many shutters for this width.")
        for i in range(spec.shutters):
            x = DOOR_GAP + i * (door_w + DOOR_GAP)
            add(
                "Shutter" if spec.shutters == 1 else f"Shutter {i + 1}",
                x, -t - 2, p + DOOR_GAP, x + door_w, -2, h - DOOR_GAP,
            )

    notes.append(
        f"Carcass in {t:g} mm board with a {bt:g} mm back fitted between the sides. "
        f"Top and bottom sit between the sides. Shelves are fixed, {SHELF_SETBACK:g} mm back from the front."
    )
    if spec.shutters:
        notes.append(f"Shutters overlay the front with {DOOR_GAP:g} mm gaps.")
    if p > 0:
        notes.append(f"{p:g} mm skirting under the bottom panel.")
    return parts, tuple(notes)


def hardware_for(parts: list[Part]) -> list[dict[str, Any]]:
    """Suggested hardware counts, read off the generated parts."""
    hinges = 0
    for part in parts:
        if part.name.startswith("Shutter"):
            height = part.length
            hinges += 2 if height <= 900 else 3 if height <= 1600 else 4 if height <= 2100 else 5
    channels: dict[float, int] = {}
    for part in parts:
        if part.name.endswith(" side L"):
            depth = max(part.length, part.width)
            channels[depth] = channels.get(depth, 0) + 1
    items: list[dict[str, Any]] = []
    if hinges:
        items.append({"item": "Hinges", "quantity": hinges})
    for depth, pairs in sorted(channels.items()):
        items.append({"item": f"Drawer channels {depth:g} mm (pairs)", "quantity": pairs})
    return items


def to_obj(parts: list[Part], title: str = "furniture") -> str:
    """Write the parts as an assembled OBJ model in mm, one named solid each."""
    lines = [f"# {title}", "# Generated by CutList from a description. Units: millimetres."]
    faces = ((1, 4, 3, 2), (5, 6, 7, 8), (1, 2, 6, 5), (2, 3, 7, 6), (3, 4, 8, 7), (4, 1, 5, 8))
    base = 0
    for part in parts:
        x0, y0, z0, x1, y1, z1 = part.box
        lines.append(f"o {part.name}")
        for x, y, z in (
            (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
            (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
        ):
            lines.append(f"v {x:.3f} {y:.3f} {z:.3f}")
        for face in faces:
            lines.append("f " + " ".join(str(base + i) for i in face))
        base += 8
    return "\n".join(lines) + "\n"


def describe_to_model(
    description: str,
    thickness: float = 18.0,
    llm_extract: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Description -> {filename, obj, parts, notes, spec}. Raises ValueError on bad input."""
    spec = parse_spec(description, thickness=thickness, llm_extract=llm_extract)
    parts, notes = build_parts(spec)
    hardware = hardware_for(parts)
    title = f"{spec.kind.replace('_', ' ').capitalize()} {spec.height:g} x {spec.width:g} x {spec.depth:g}"
    return {
        "filename": re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_") + ".obj",
        "title": title,
        "obj": to_obj(parts, title),
        "parts": [{"name": q.name, "length": q.length, "width": q.width, "thickness": q.thickness} for q in parts],
        "notes": list(notes) + (
            ["Suggested hardware: " + ", ".join(f"{h['quantity']} x {h['item']}" for h in hardware) + "."]
            if hardware else []
        ),
        "hardware": hardware,
        "spec": {key: value for key, value in replace(spec, notes=()).__dict__.items() if key != "notes"},
    }
