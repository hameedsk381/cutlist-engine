"""RS-274 (G-code) emitter for CNC routers and panel saws.

Produces one .nc file per sheet. Output is intentionally vendor-neutral and
sticks to the common subset that loads cleanly in Mach3, LinuxCNC, GRBL,
Fanuc, Haas, Centroid, Acorn, UCCNC, and Mach4. Multi-pass plunging is used
when the requested cut depth exceeds `pass_depth`.

Per part:
  1. Rapid (G0) to contour entry point at safe Z
  2. Rapid down to clearance Z
  3. Feed plunge (G1) one pass-depth at a time until total cut depth reached
  4. Feed (G1) along the kerf-offset cut polygon (closes back to entry)
  5. Rapid (G0) up to safe Z

Kerf compensation: the path is offset OUTWARD from the part by kerf/2 so the
cutter centre traces a line that is exactly tangent to the finished part edge.
This works for rectangular parts and for the true outer-loop polygons that the
contour extractor now emits for non-rectangular panels.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from .dxf_export import _board_holes_in_sheet, _board_polygon_in_sheet, _offset_polygon
from .models import Board, SheetLayout


@dataclass(frozen=True)
class GCodeConfig:
    feed_rate: float = 2500.0       # mm/min, lateral cutting feed
    plunge_rate: float = 800.0      # mm/min, vertical plunge feed
    spindle_rpm: int = 18000        # for routers; ignored on plasma/laser
    cut_depth: float = 18.5         # total Z below 0 to cut through (slightly > stock thickness)
    pass_depth: float = 6.0         # max Z step per pass; engine will plunge in N passes
    safe_z: float = 15.0            # rapid-travel Z above stock
    clearance_z: float = 2.0        # height to drop to before plunge feed
    units: str = "mm"               # "mm" -> G21, "in" -> G20
    use_g54: bool = True            # emit G54 work-offset line; turn off if your post sets it


def write_sheet_gcode(
    path: Path,
    sheet: SheetLayout,
    boards: list[Board],
    *,
    kerf: float,
    config: GCodeConfig,
) -> None:
    boards_by_id = {b.id: b for b in boards}
    buf = StringIO()
    _emit_header(buf, sheet, config)

    for part in sheet.parts:
        board = boards_by_id.get(part.board_id)
        paths_2d = _cut_paths_for_part(board, part, kerf)
        for path_kind, path_2d in paths_2d:
            if not path_2d:
                continue
            _emit_part(buf, board, part, path_2d, config, path_kind=path_kind)

    _emit_footer(buf, config)
    path.write_text(buf.getvalue(), encoding="utf-8")


def write_sheets_gcode(
    directory: Path,
    sheets: list[SheetLayout],
    boards: list[Board],
    *,
    kerf: float,
    config: GCodeConfig,
) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for sheet in sheets:
        path = directory / f"sheet_{sheet.sheet_id:02d}_{sheet.material}.nc"
        write_sheet_gcode(path, sheet, boards, kerf=kerf, config=config)
        paths.append(path)
    return paths


# ---------------------------------------------------------------------------
# Cut-path construction
# ---------------------------------------------------------------------------


def _cut_path_for_part(board: Board | None, part, kerf: float) -> list[tuple[float, float]] | None:
    paths = _cut_paths_for_part(board, part, kerf)
    return paths[-1][1] if paths else None


def _cut_paths_for_part(board: Board | None, part, kerf: float) -> list[tuple[str, list[tuple[float, float]]]]:
    """Build the kerf-compensated cut path in sheet coordinates.

    Uses the board's true outer polygon when available; falls back to the
    placed bounding rectangle. Interior holes are emitted before the outer
    perimeter so the part remains fixed in the sheet until cut free.
    """
    if board is None:
        x0, y0 = part.x, part.y
        return [("outer", [(x0, y0), (x0 + part.length, y0), (x0 + part.length, y0 + part.width), (x0, y0 + part.width)])]

    polygon = _board_polygon_in_sheet(board, part)
    if not polygon or len(polygon) < 3:
        x0, y0 = part.x, part.y
        polygon = [(x0, y0), (x0 + part.length, y0), (x0 + part.length, y0 + part.width), (x0, y0 + part.width)]

    paths: list[tuple[str, list[tuple[float, float]]]] = []
    for hole in _board_holes_in_sheet(board, part):
        # Offset toward the cutout waste. Holes are normalized as standalone
        # CCW polygons, so a negative offset shrinks the path inside the hole.
        paths.append(("hole", _offset_polygon(hole, -kerf / 2.0) if kerf > 0 else hole))

    if kerf > 0:
        polygon = _offset_polygon(polygon, kerf / 2.0)
    paths.append(("outer", polygon))
    return paths


# ---------------------------------------------------------------------------
# G-code text emission
# ---------------------------------------------------------------------------


def _emit_header(buf: StringIO, sheet: SheetLayout, config: GCodeConfig) -> None:
    units_code = "G20" if config.units == "in" else "G21"
    buf.write(f"; Cutlist Engine G-code\n")
    buf.write(f"; Sheet {sheet.sheet_id} | {sheet.material} | "
              f"{sheet.width:.1f} x {sheet.height:.1f} mm | parts={len(sheet.parts)}\n")
    buf.write(f"; Feed: {config.feed_rate} mm/min  Plunge: {config.plunge_rate} mm/min  "
              f"Spindle: {config.spindle_rpm} RPM\n")
    buf.write(f"; Cut depth: {config.cut_depth} mm  Pass depth: {config.pass_depth} mm  "
              f"Safe Z: {config.safe_z}\n\n")
    buf.write("G17 ")
    buf.write(units_code + " ")
    buf.write("G90 G94\n")             # XY plane, units, absolute, units/min feed
    if config.use_g54:
        buf.write("G54\n")
    buf.write(f"G0 Z{config.safe_z:.3f}\n")
    if config.spindle_rpm > 0:
        buf.write(f"M3 S{config.spindle_rpm}\n")
    buf.write("G4 P1\n")                # pause 1s for spindle ramp-up
    buf.write("\n")


def _emit_part(buf: StringIO, board: Board | None, part, path_2d: list[tuple[float, float]],
               config: GCodeConfig, *, path_kind: str = "outer") -> None:
    label = (board.label if board and board.label else part.board_id)
    material = board.material if board else "default"
    buf.write(f"; --- {part.board_id}  {path_kind}  {label}  {material}  rotation={part.rotation}\n")
    entry_x, entry_y = path_2d[0]

    # Rapid to entry
    buf.write(f"G0 X{entry_x:.3f} Y{entry_y:.3f}\n")
    buf.write(f"G0 Z{config.clearance_z:.3f}\n")

    # Multi-pass plunge.
    pass_depth = max(0.1, abs(config.pass_depth))
    total_depth = abs(config.cut_depth)
    z_current = 0.0
    while z_current > -total_depth:
        z_current = max(-total_depth, z_current - pass_depth)
        # Plunge to this depth
        buf.write(f"G1 Z{z_current:.3f} F{config.plunge_rate:.0f}\n")
        # Cut the contour at this Z
        for x, y in path_2d[1:]:
            buf.write(f"G1 X{x:.3f} Y{y:.3f} F{config.feed_rate:.0f}\n")
        # Close the loop back to entry so each pass is a complete contour
        buf.write(f"G1 X{entry_x:.3f} Y{entry_y:.3f}\n")

    # Retract
    buf.write(f"G0 Z{config.safe_z:.3f}\n\n")


def _emit_footer(buf: StringIO, config: GCodeConfig) -> None:
    buf.write(f"G0 Z{config.safe_z:.3f}\n")
    buf.write("G0 X0 Y0\n")
    if config.spindle_rpm > 0:
        buf.write("M5\n")
    buf.write("M30\n")                  # program end + rewind
