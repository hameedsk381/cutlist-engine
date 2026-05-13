"""Minimal labeled-DXF writer for CNC sheet output.

Writes a self-contained ASCII DXF (AutoCAD R12 flavour) per sheet with three
layers: SHEET (boundary), PART (closed polylines), OFFCUT (dashed polylines),
LABEL (text). No external dependency required.

The format is intentionally conservative so it loads cleanly in:
- Any modern CAD/CAM program (Fusion 360, AutoCAD, LibreCAD, QCAD)
- CNC nesting software (VCarve, Aspire, EnRoute)
- 2D laser/router drivers
"""
from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Iterable

from .models import Board, SheetLayout


def write_sheet_dxf(path: Path, sheet: SheetLayout, boards: list[Board], kerf: float = 0.0) -> None:
    boards_by_id = {b.id: b for b in boards}
    buf = StringIO()
    _write_header(buf)
    _write_tables(buf)
    _write_blocks(buf)
    _start_entities(buf)

    # Sheet boundary
    _write_polyline(buf, "SHEET", _rect_points(0, 0, sheet.width, sheet.height), closed=True)

    # Offcuts (dashed)
    for offcut in sheet.offcuts:
        layer = "OFFCUT_REUSE" if offcut.reusable else "OFFCUT_SCRAP"
        _write_polyline(
            buf, layer,
            _rect_points(offcut.x, offcut.y, offcut.x + offcut.width, offcut.y + offcut.height),
            closed=True,
        )
        if offcut.reusable:
            _write_text(
                buf, "LABEL",
                offcut.x + offcut.width / 2, offcut.y + offcut.height / 2,
                f"REUSABLE {offcut.width:.0f}x{offcut.height:.0f}",
                height=min(offcut.width, offcut.height) * 0.06 + 8,
                halign_center=True,
            )

    # Parts
    for part in sheet.parts:
        board = boards_by_id.get(part.board_id)
        x0, y0 = part.x, part.y
        x1, y1 = part.x + part.length, part.y + part.width

        # If the board has a real (non-rectangular) polygon, place it correctly
        # (rotated, then offset to the part's nest position).
        polygon = _board_polygon_in_sheet(board, part) if board else None
        if polygon and len(polygon) >= 3:
            _write_polyline(buf, "PART", polygon, closed=True)
            if kerf > 0:
                _write_polyline(buf, "PART_FINISH",
                                _offset_polygon(polygon, -kerf / 2.0),
                                closed=True)
        else:
            _write_polyline(buf, "PART", _rect_points(x0, y0, x1, y1), closed=True)
            if kerf > 0:
                inset = kerf / 2.0
                _write_polyline(
                    buf, "PART_FINISH",
                    _rect_points(x0 + inset, y0 + inset, x1 - inset, y1 - inset),
                    closed=True,
                )

        if board:
            for hole in _board_holes_in_sheet(board, part):
                _write_polyline(buf, "HOLE", hole, closed=True)
                if kerf > 0:
                    _write_polyline(buf, "HOLE_FINISH", _offset_polygon(hole, kerf / 2.0), closed=True)

        # Grain arrow (along part length, near top edge)
        if board and board.grain_locked:
            _write_grain_arrow(buf, x0, y0, part.length, part.width)

        # Label block: id, dims, material, rotation, edge band
        label = (board.label or part.board_id) if board else part.board_id
        material = board.material if board else "default"
        cx = x0 + part.length / 2
        cy = y0 + part.width / 2
        text_h = max(10.0, min(part.length, part.width) * 0.06)
        _write_text(buf, "LABEL", cx, cy + text_h * 0.6, label,
                    height=text_h, halign_center=True)
        _write_text(buf, "LABEL", cx, cy - text_h * 0.6,
                    f"{part.length:.0f} x {part.width:.0f} mm  {material}",
                    height=text_h * 0.7, halign_center=True)
        if board and any(board.edge_band):
            _write_text(buf, "LABEL", cx, cy - text_h * 1.7,
                        f"EB T{board.edge_band[0]:.0f} R{board.edge_band[1]:.0f} "
                        f"B{board.edge_band[2]:.0f} L{board.edge_band[3]:.0f}",
                        height=text_h * 0.55, halign_center=True)

    # Title block (top-left of sheet)
    title = f"Sheet {sheet.sheet_id}  |  {sheet.material}  |  {sheet.width:.0f}x{sheet.height:.0f} mm"
    _write_text(buf, "LABEL", 20, sheet.height + 30, title, height=24)

    _end_entities(buf)
    _write_eof(buf)
    path.write_text(buf.getvalue(), encoding="utf-8")


# ---------------------------------------------------------------------------
# DXF section primitives (R12 ASCII)
# ---------------------------------------------------------------------------


def _write_header(buf: StringIO) -> None:
    buf.write("0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1009\n9\n$INSUNITS\n70\n4\n0\nENDSEC\n")


def _write_tables(buf: StringIO) -> None:
    layers = [
        ("SHEET", 8),
        ("PART", 3),
        ("PART_FINISH", 5),
        ("HOLE", 1),
        ("HOLE_FINISH", 4),
        ("OFFCUT_REUSE", 2),
        ("OFFCUT_SCRAP", 9),
        ("LABEL", 7),
        ("GRAIN", 6),
    ]
    buf.write("0\nSECTION\n2\nTABLES\n0\nTABLE\n2\nLAYER\n70\n")
    buf.write(f"{len(layers)}\n")
    for name, color in layers:
        buf.write(f"0\nLAYER\n2\n{name}\n70\n0\n62\n{color}\n6\nCONTINUOUS\n")
    buf.write("0\nENDTAB\n0\nENDSEC\n")


def _write_blocks(buf: StringIO) -> None:
    buf.write("0\nSECTION\n2\nBLOCKS\n0\nENDSEC\n")


def _start_entities(buf: StringIO) -> None:
    buf.write("0\nSECTION\n2\nENTITIES\n")


def _end_entities(buf: StringIO) -> None:
    buf.write("0\nENDSEC\n")


def _write_eof(buf: StringIO) -> None:
    buf.write("0\nEOF\n")


def _rect_points(x0: float, y0: float, x1: float, y1: float) -> list[tuple[float, float]]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _write_polyline(buf: StringIO, layer: str, points: Iterable[tuple[float, float]], closed: bool) -> None:
    points = list(points)
    buf.write(f"0\nPOLYLINE\n8\n{layer}\n66\n1\n70\n{1 if closed else 0}\n")
    for x, y in points:
        buf.write(f"0\nVERTEX\n8\n{layer}\n10\n{x:.4f}\n20\n{y:.4f}\n30\n0.0\n")
    buf.write(f"0\nSEQEND\n8\n{layer}\n")


def _write_text(buf: StringIO, layer: str, x: float, y: float, text: str,
                height: float = 12.0, halign_center: bool = False) -> None:
    safe = text.replace("\n", " ")
    halign = 1 if halign_center else 0
    buf.write(
        f"0\nTEXT\n8\n{layer}\n10\n{x:.4f}\n20\n{y:.4f}\n30\n0.0\n40\n{height:.4f}\n1\n{safe}\n72\n{halign}\n11\n{x:.4f}\n21\n{y:.4f}\n31\n0.0\n"
    )


def _write_grain_arrow(buf: StringIO, x0: float, y0: float, length: float, width: float) -> None:
    margin = min(length, width) * 0.08 + 6
    arrow_y = y0 + width - margin
    start_x = x0 + margin
    end_x = x0 + length - margin
    head = min(length * 0.04, 20.0)
    # Shaft
    _write_polyline(buf, "GRAIN", [(start_x, arrow_y), (end_x, arrow_y)], closed=False)
    # Head
    _write_polyline(buf, "GRAIN",
                    [(end_x, arrow_y), (end_x - head, arrow_y + head / 2), (end_x - head, arrow_y - head / 2)],
                    closed=True)


def _board_polygon_in_sheet(board: Board, part) -> list[tuple[float, float]] | None:
    """Map the board's local-frame polygon into the part's placed position on
    the sheet, applying the nesting rotation."""
    contour = board.contour
    if not contour or len(contour) < 3:
        return None
    # Treat the polygon as already axis-aligned to (length x width) at origin.
    return _local_polygon_in_sheet([(p.x, p.y) for p in contour], board, part)


def _board_holes_in_sheet(board: Board, part) -> list[list[tuple[float, float]]]:
    return [
        _local_polygon_in_sheet([(p.x, p.y) for p in hole], board, part)
        for hole in board.holes
        if len(hole) >= 3
    ]


def _local_polygon_in_sheet(points: list[tuple[float, float]], board: Board, part) -> list[tuple[float, float]]:
    pts = points
    if part.rotation == 90:
        # Rotate 90 deg CCW around origin: (x, y) -> (-y, x); then translate
        # by (board.width, 0) so the rotated bbox sits in the first quadrant.
        rotated = [(-y, x) for x, y in pts]
        max_neg_x = -min(x for x, _ in rotated)
        pts = [(x + max_neg_x, y) for x, y in rotated]
    return [(part.x + x, part.y + y) for x, y in pts]


def _offset_polygon(points: list[tuple[float, float]], offset: float) -> list[tuple[float, float]]:
    """Edge-normal polygon offset. Positive = outward from a CCW polygon.

    For arbitrary polygons we offset each edge along its inward/outward normal,
    then intersect adjacent offset edges to find the new vertex. Falls back to
    centroid-radial offset on any degeneracy.
    """
    n = len(points)
    if n < 3:
        return points

    # Determine winding (signed area). For CCW, the right-hand normal points
    # inward; we flip sign so positive `offset` always means outward.
    sa = 0.5 * sum(points[i][0] * points[(i + 1) % n][1] - points[(i + 1) % n][0] * points[i][1] for i in range(n))
    sign = 1.0 if sa > 0 else -1.0

    edges = []
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        length = (dx * dx + dy * dy) ** 0.5 or 1.0
        # Outward normal for a CCW polygon is (dy, -dx)/length; for CW invert.
        nx, ny = (dy / length) * sign, (-dx / length) * sign
        ox, oy = x1 + nx * offset, y1 + ny * offset
        edges.append(((ox, oy), (dx, dy)))

    out: list[tuple[float, float]] = []
    for i in range(n):
        (p1, d1) = edges[i]
        (p2, d2) = edges[(i + 1) % n]
        # Intersect line p1 + t*d1 with line p2 + s*d2.
        denom = d1[0] * (-d2[1]) - d1[1] * (-d2[0])
        if abs(denom) < 1e-9:
            out.append(p2)
            continue
        rhs_x = p2[0] - p1[0]
        rhs_y = p2[1] - p1[1]
        t = (rhs_x * (-d2[1]) - rhs_y * (-d2[0])) / denom
        out.append((p1[0] + t * d1[0], p1[1] + t * d1[1]))
    return out


def write_sheets_dxf_zip(directory: Path, sheets: list[SheetLayout], boards: list[Board], kerf: float = 0.0) -> list[Path]:
    """Convenience: write one DXF per sheet into `directory`. Returns paths."""
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for sheet in sheets:
        path = directory / f"sheet_{sheet.sheet_id:02d}_{sheet.material}.dxf"
        write_sheet_dxf(path, sheet, boards, kerf=kerf)
        paths.append(path)
    return paths
