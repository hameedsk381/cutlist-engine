from __future__ import annotations

from dataclasses import dataclass, replace

from .geometry import align_to_min_rect, bounding_contour, cluster_planes, contour_loops, unique_vertices
from .models import Board, CutlistItem, ExtractionReport, PlaneCluster, Triangle, Vec3


# Sheet thicknesses (mm) a measured part is snapped to when within tolerance.
STOCK_THICKNESSES: tuple[float, ...] = (3.0, 4.0, 6.0, 8.0, 9.0, 12.0, 15.0, 16.0, 18.0, 19.0, 25.0)

# A closed solid thicker than this (mm) is treated as a non-panel part.
MAX_PANEL_THICKNESS = 60.0


@dataclass
class _Surface:
    id: str
    normal: Vec3
    offset: float
    triangles: list[Triangle]

    @property
    def area(self) -> float:
        return sum(triangle.area() for triangle in self.triangles)

    @property
    def centroid(self) -> Vec3:
        vertices = unique_vertices(self.triangles)
        return Vec3(
            sum(vertex.x for vertex in vertices) / len(vertices),
            sum(vertex.y for vertex in vertices) / len(vertices),
            sum(vertex.z for vertex in vertices) / len(vertices),
        )


@dataclass(frozen=True)
class BoardExtraction:
    boards: list[Board]
    report: ExtractionReport


def detect_boards(
    triangles: list[Triangle],
    expected_thickness: float | None = None,
    thickness_tolerance: float = 0.5,
    normal_tolerance: float = 0.999,
) -> list[Board]:
    return extract_boards(
        triangles,
        expected_thickness=expected_thickness,
        thickness_tolerance=thickness_tolerance,
        normal_tolerance=normal_tolerance,
    ).boards


def extract_boards(
    triangles: list[Triangle],
    expected_thickness: float | None = None,
    thickness_tolerance: float = 0.5,
    normal_tolerance: float = 0.999,
    stock_thicknesses: tuple[float, ...] = STOCK_THICKNESSES,
) -> BoardExtraction:
    """Extract boards part by part.

    Triangles are grouped by source object, then split into closed solids.
    Each closed solid is one modelled part and is measured directly, so parts
    that touch or share a plane never contaminate each other and every part
    keeps its own thickness. Faces that do not form a closed solid fall back
    to opposite-face pairing within their own source object.
    """
    usable_triangles = [triangle for triangle in triangles if triangle.area() > 0]
    warnings: list[str] = []
    if not usable_triangles:
        warnings.append("No usable triangle faces were found in the input geometry.")

    groups: dict[str | None, list[Triangle]] = {}
    for triangle in usable_triangles:
        groups.setdefault(triangle.source_object, []).append(triangle)

    boards: list[Board] = []
    skipped_parts: list[str] = []
    solid_part_count = 0
    solid_board_count = 0
    inferred_board_count = 0
    plane_count = 0
    surface_count = 0
    unmatched_surface_count = 0

    for name, group in groups.items():
        solids, loose = _split_closed_solids(group)
        solid_part_count += len(solids)
        for solid in solids:
            board, reason = _board_from_solid(
                solid,
                name,
                expected_thickness=expected_thickness,
                thickness_tolerance=thickness_tolerance,
                normal_tolerance=normal_tolerance,
                stock_thicknesses=stock_thicknesses,
            )
            if board is None:
                skipped_parts.append(f"{name or 'unnamed solid'} ({reason})")
                continue
            boards.append(board)
            solid_board_count += 1

        if loose:
            paired = _pair_loose_surfaces(loose, expected_thickness, thickness_tolerance, normal_tolerance)
            boards.extend(paired.boards)
            inferred_board_count += len(paired.boards)
            plane_count += paired.plane_count
            surface_count += paired.surface_count
            unmatched_surface_count += paired.unmatched_surface_count

    boards = [replace(board, id=f"panel_{index:03d}") for index, board in enumerate(boards, start=1)]

    if unmatched_surface_count:
        warnings.append(f"{unmatched_surface_count} planar surfaces were not paired into manufacturable boards.")
    if inferred_board_count:
        warnings.append(
            f"{inferred_board_count} board(s) were inferred by pairing loose faces because the geometry "
            "was not a closed solid; check their dimensions before cutting."
        )
    if skipped_parts:
        warnings.append(
            f"{len(skipped_parts)} solid part(s) are not flat panels and were left out of the cutlist: "
            + _summarize_names(skipped_parts)
        )

    paired_units = 2 * solid_board_count + (surface_count - unmatched_surface_count)
    total_units = 2 * solid_board_count + surface_count
    if total_units:
        board_confidence = sum(board.confidence for board in boards) / len(boards) if boards else 0.0
        confidence = round((paired_units / total_units) * 0.4 + board_confidence * 0.6, 3)
    else:
        confidence = 0.0

    report = ExtractionReport(
        triangle_count=len(triangles),
        usable_triangle_count=len(usable_triangles),
        plane_count=plane_count,
        surface_count=surface_count,
        board_count=len(boards),
        unmatched_surface_count=unmatched_surface_count,
        confidence=confidence,
        warnings=tuple(warnings),
        solid_part_count=solid_part_count,
        inferred_board_count=inferred_board_count,
        skipped_parts=tuple(skipped_parts),
    )
    return BoardExtraction(boards=boards, report=report)


def _summarize_names(names: list[str], limit: int = 8) -> str:
    counts: dict[str, int] = {}
    for name in names:
        counts[name] = counts.get(name, 0) + 1
    parts = [f"{name} x{count}" if count > 1 else name for name, count in counts.items()]
    shown = ", ".join(parts[:limit])
    return shown + (f", and {len(parts) - limit} more" if len(parts) > limit else "")


# ---------------------------------------------------------------------------
# Closed solids: one modelled part -> one board, measured directly
# ---------------------------------------------------------------------------


def _split_closed_solids(
    triangles: list[Triangle], tolerance: float = 0.01
) -> tuple[list[list[Triangle]], list[Triangle]]:
    """Split triangles into closed solids and leftover loose triangles.

    Triangles are joined only across edges used by exactly two triangles, so
    two boxes that touch along an edge or a face stay separate solids.
    """
    edge_to_triangles: dict[tuple, list[int]] = {}
    for index, triangle in enumerate(triangles):
        keys = [_vertex_key(vertex, tolerance) for vertex in triangle.vertices]
        for i in range(3):
            ka, kb = keys[i], keys[(i + 1) % 3]
            if ka == kb:
                continue
            edge_to_triangles.setdefault((ka, kb) if ka < kb else (kb, ka), []).append(index)

    parent = list(range(len(triangles)))

    def find(i: int) -> int:
        root = i
        while parent[root] != root:
            root = parent[root]
        while parent[i] != root:
            parent[i], i = root, parent[i]
        return root

    for indexes in edge_to_triangles.values():
        if len(indexes) == 2:
            root_a, root_b = find(indexes[0]), find(indexes[1])
            if root_a != root_b:
                parent[root_a] = root_b

    open_roots: set[int] = set()
    for indexes in edge_to_triangles.values():
        per_root: dict[int, int] = {}
        for index in indexes:
            root = find(index)
            per_root[root] = per_root.get(root, 0) + 1
        for root, count in per_root.items():
            if count != 2:
                open_roots.add(root)

    components: dict[int, list[Triangle]] = {}
    for index, triangle in enumerate(triangles):
        components.setdefault(find(index), []).append(triangle)

    solids: list[list[Triangle]] = []
    loose: list[Triangle] = []
    for root, component in components.items():
        if root in open_roots or len(component) < 4:
            loose.extend(component)
        else:
            solids.append(component)
    return solids, loose


def _board_from_solid(
    triangles: list[Triangle],
    name: str | None,
    *,
    expected_thickness: float | None,
    thickness_tolerance: float,
    normal_tolerance: float,
    stock_thicknesses: tuple[float, ...],
) -> tuple[Board | None, str]:
    # Thickness axis = normal direction carrying the most surface area.
    directions: dict[tuple[int, int, int], list] = {}
    for triangle in triangles:
        normal = triangle.normal()
        dominant = max(normal.as_tuple(), key=abs)
        if dominant < 0:
            normal = normal * -1.0
        key = (round(normal.x * 50), round(normal.y * 50), round(normal.z * 50))
        entry = directions.setdefault(key, [normal, 0.0])
        entry[1] += triangle.area()
    axis: Vec3 = max(directions.values(), key=lambda entry: entry[1])[0]

    depths = [vertex.dot(axis) for triangle in triangles for vertex in triangle.vertices]
    low, high = min(depths), max(depths)
    measured = high - low
    if measured <= 0.01:
        return None, "no measurable thickness"

    plane_tolerance = min(0.1, measured / 4.0)
    low_face: list[Triangle] = []
    high_face: list[Triangle] = []
    for triangle in triangles:
        if abs(triangle.normal().dot(axis)) < normal_tolerance:
            continue
        depth = triangle.a.dot(axis)
        if depth - low <= plane_tolerance:
            low_face.append(triangle)
        elif high - depth <= plane_tolerance:
            high_face.append(triangle)

    low_area = sum(triangle.area() for triangle in low_face)
    high_area = sum(triangle.area() for triangle in high_face)
    if low_area <= 0 or high_area <= 0:
        return None, "no pair of flat opposite faces"
    face_ratio = min(low_area, high_area) / max(low_area, high_area)
    if face_ratio < 0.5:
        return None, "opposite faces do not match"

    face = low_face if low_area >= high_area else high_face
    loops = contour_loops(face, axis)
    contour, holes = loops.outer, loops.holes
    if not contour:
        contour, holes = bounding_contour(unique_vertices(face), axis), ()
    contour, holes = align_to_min_rect(contour, holes)
    size_x = max(point.x for point in contour) - min(point.x for point in contour)
    size_y = max(point.y for point in contour) - min(point.y for point in contour)
    if max(low_area, high_area) < 0.3 * size_x * size_y:
        return None, "faces are not panel-shaped"
    if measured > min(size_x, size_y) + thickness_tolerance:
        return None, f"{measured:.0f} mm deep, thicker than it is wide"
    if measured > MAX_PANEL_THICKNESS:
        return None, f"{measured:.0f} mm thick, not sheet material"

    warnings: list[str] = []
    confidence = face_ratio
    candidates = ([expected_thickness] if expected_thickness else []) + list(stock_thicknesses)
    nearest = min(candidates, key=lambda value: abs(value - measured)) if candidates else None
    if nearest is not None and abs(nearest - measured) <= thickness_tolerance:
        thickness = float(nearest)
    else:
        thickness = round(measured, 2)
        confidence -= 0.25
        warnings.append(f"Thickness {thickness:g} mm is not a standard sheet thickness.")
    if face_ratio < 0.98:
        warnings.append(
            f"Opposite faces differ in area by {(1.0 - face_ratio) * 100.0:.1f}% (rebate, pocket or profile)."
        )

    board = _make_board(
        contour,
        holes,
        thickness,
        source_planes=("solid", name or ""),
        confidence=round(max(0.05, min(1.0, confidence)), 3),
        warnings=tuple(warnings),
        source_objects=(name,) if name else (),
    )
    return board, ""


# ---------------------------------------------------------------------------
# Loose faces: fall back to pairing opposite planar surfaces
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _PairingResult:
    boards: list[Board]
    plane_count: int
    surface_count: int
    unmatched_surface_count: int


def _pair_loose_surfaces(
    triangles: list[Triangle],
    expected_thickness: float | None,
    thickness_tolerance: float,
    normal_tolerance: float,
) -> _PairingResult:
    planes = cluster_planes(
        triangles,
        normal_tolerance=normal_tolerance,
        distance_tolerance=thickness_tolerance,
    )
    # Filter out planes with very small total area (e.g. less than 50x50mm)
    # to avoid O(N^2) explosion on highly curved organic surfaces
    planes = [p for p in planes if sum(t.area() for t in p.triangles) >= 2500.0]
    surfaces = _split_surfaces(planes)
    boards: list[Board] = []
    used_surfaces: set[str] = set()

    for first in surfaces:
        if first.id in used_surfaces:
            continue
        candidates = []
        for second in surfaces:
            if first.id == second.id or second.id in used_surfaces:
                continue
            # Plane normals are canonicalised to a non-negative offset, so the two
            # faces of a panel that straddles the origin carry opposite normals.
            alignment = first.normal.dot(second.normal)
            if abs(abs(alignment) - 1.0) > (1.0 - normal_tolerance):
                continue
            second_offset = second.offset if alignment > 0 else -second.offset

            thickness = abs(first.offset - second_offset)
            if thickness <= 0:
                continue
            if expected_thickness is not None and abs(thickness - expected_thickness) > thickness_tolerance:
                continue

            # Hard-reject obvious mismatches before scoring.
            lateral_dist = _lateral_distance(first.centroid, second.centroid, first.normal)
            if lateral_dist > 100.0:
                continue  # Surfaces are too far apart laterally to be opposite faces

            area_ratio = min(first.area, second.area) / max(first.area, second.area) if max(first.area, second.area) > 0 else 0
            if area_ratio < 0.5:
                continue  # Opposite faces must have at least 50% area overlap

            candidates.append((lateral_dist, abs(thickness - (expected_thickness or thickness)), thickness, second))

        if not candidates:
            continue

        lateral_distance, thickness_error, thickness, second = sorted(candidates, key=lambda item: (item[0], item[1]))[0]
        if expected_thickness is not None and abs(thickness - expected_thickness) <= thickness_tolerance:
            thickness = expected_thickness
        used_surfaces.update((first.id, second.id))
        boards.append(
            _board_from_planes(
                first,
                second,
                thickness,
                confidence=_pair_confidence(first, second, lateral_distance, thickness_error, thickness_tolerance),
                warnings=_pair_warnings(first, second, lateral_distance, thickness_error, thickness_tolerance),
            )
        )

    unmatched = len([surface for surface in surfaces if surface.id not in used_surfaces])
    return _PairingResult(boards, len(planes), len(surfaces), unmatched)


def _board_from_planes(
    first: _Surface,
    second: _Surface,
    thickness: float,
    confidence: float,
    warnings: tuple[str, ...],
) -> Board:
    face = first if first.area >= second.area else second
    # Real outer polygon (handles notches, curves, cutouts). Falls back to AABB
    # internally when the boundary cannot be closed.
    loops = contour_loops(face.triangles, face.normal)
    contour = loops.outer
    holes = loops.holes
    if not contour:
        vertices = unique_vertices(face.triangles)
        contour = bounding_contour(vertices, face.normal)
        holes = ()
    contour, holes = align_to_min_rect(contour, holes)
    return _make_board(
        contour,
        holes,
        thickness,
        source_planes=(first.id, second.id),
        confidence=confidence,
        warnings=warnings,
        source_objects=tuple(
            sorted({triangle.source_object for triangle in first.triangles + second.triangles if triangle.source_object})
        ),
    )


def _make_board(
    contour: tuple,
    holes: tuple,
    thickness: float,
    *,
    source_planes: tuple[str, str],
    confidence: float,
    warnings: tuple[str, ...],
    source_objects: tuple[str, ...],
) -> Board:
    width = max(point.x for point in contour) - min(point.x for point in contour)
    height = max(point.y for point in contour) - min(point.y for point in contour)
    length, board_width = sorted((round(width, 3), round(height, 3)), reverse=True)

    # Tag boards whose outer loop departs significantly from a plain rectangle so
    # downstream consumers (DXF, G-code, label sheet) know to use the polygon.
    extra_warnings = list(warnings)
    if not _is_axis_aligned_rectangle(contour):
        extra_warnings.append("Non-rectangular outer contour detected; cut path will follow the polygon, not the bounding box.")
    if holes:
        extra_warnings.append(f"{len(holes)} interior cutout(s) detected; DXF and G-code will include hole cut paths.")

    return Board(
        id="panel_000",
        length=length,
        width=board_width,
        thickness=thickness,
        area=(length * board_width) / 1_000_000.0,
        contour=contour,
        source_planes=source_planes,
        holes=holes,
        confidence=confidence,
        warnings=tuple(extra_warnings),
        source_objects=source_objects,
    )


def _is_axis_aligned_rectangle(contour: tuple, tolerance: float = 0.5) -> bool:
    if len(contour) != 4:
        return False
    xs = sorted({round(p.x / tolerance) for p in contour})
    ys = sorted({round(p.y / tolerance) for p in contour})
    return len(xs) == 2 and len(ys) == 2


def _split_surfaces(planes: list[PlaneCluster], tolerance: float = 0.01) -> list[_Surface]:
    surfaces: list[_Surface] = []
    for plane in planes:
        components = _connected_components(plane.triangles, tolerance)
        for index, component in enumerate(components, start=1):
            surfaces.append(
                _Surface(
                    id=f"{plane.id}_{index:02d}",
                    normal=plane.normal,
                    offset=plane.offset,
                    triangles=component,
                )
            )
    return surfaces


def _connected_components(triangles: list[Triangle], tolerance: float) -> list[list[Triangle]]:
    vertex_to_triangles: dict[tuple[int, int, int], list[int]] = {}
    for index, triangle in enumerate(triangles):
        for vertex in triangle.vertices:
            key = _vertex_key(vertex, tolerance)
            if key not in vertex_to_triangles:
                vertex_to_triangles[key] = []
            vertex_to_triangles[key].append(index)

    parent = list(range(len(triangles)))

    def find(i: int) -> int:
        root = i
        while parent[root] != root:
            root = parent[root]
        curr = i
        while curr != root:
            nxt = parent[curr]
            parent[curr] = root
            curr = nxt
        return root

    def union(i: int, j: int) -> None:
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            parent[root_i] = root_j

    for indexes in vertex_to_triangles.values():
        if not indexes:
            continue
        first = indexes[0]
        for index in indexes[1:]:
            union(first, index)

    components: dict[int, list[Triangle]] = {}
    for index, triangle in enumerate(triangles):
        root = find(index)
        if root not in components:
            components[root] = []
        components[root].append(triangle)

    return list(components.values())


def _vertex_key(vertex: Vec3, tolerance: float) -> tuple[int, int, int]:
    return (
        round(vertex.x / tolerance),
        round(vertex.y / tolerance),
        round(vertex.z / tolerance),
    )


def _lateral_distance(first: Vec3, second: Vec3, normal: Vec3) -> float:
    delta = second - first
    normal_component = normal * delta.dot(normal)
    return (delta - normal_component).length()


def _pair_confidence(
    first: _Surface,
    second: _Surface,
    lateral_distance: float,
    thickness_error: float,
    thickness_tolerance: float,
) -> float:
    area_ratio = min(first.area, second.area) / max(first.area, second.area)
    lateral_penalty = min(0.35, lateral_distance / 50.0)  # Steeper penalty: halved denominator
    thickness_penalty = min(0.25, thickness_error / max(thickness_tolerance, 0.01) * 0.25)
    confidence = area_ratio - lateral_penalty - thickness_penalty
    # Ensure a meaningful minimum — pairs that barely pass pre-filters
    # still need a baseline score above zero.
    return round(max(0.05, min(1.0, confidence)), 3)


def _pair_warnings(
    first: _Surface,
    second: _Surface,
    lateral_distance: float,
    thickness_error: float,
    thickness_tolerance: float,
) -> tuple[str, ...]:
    warnings = []
    area_ratio = min(first.area, second.area) / max(first.area, second.area)
    if area_ratio < 0.98:
        warnings.append(f"Opposite faces differ in area by {(1.0 - area_ratio) * 100.0:.1f}%.")
    if lateral_distance > 1.0:
        warnings.append(f"Opposite face centroids are laterally offset by {lateral_distance:.2f} mm.")
    if thickness_error > thickness_tolerance * 0.5:
        warnings.append(f"Detected thickness is close to tolerance limit by {thickness_error:.2f} mm.")
    return tuple(warnings)


def build_cutlist(boards: list[Board], tolerance: float = 0.5) -> list[CutlistItem]:
    grouped: dict[tuple[int, int, int], list[Board]] = {}
    for board in boards:
        grouped.setdefault(board.dimensions_key(tolerance), []).append(board)

    cutlist = []
    for index, group in enumerate(grouped.values(), start=1):
        sample = group[0]
        labels = tuple(b.label or b.id for b in group)
        cutlist.append(
            CutlistItem(
                id=f"part_{index:03d}",
                length=sample.length,
                width=sample.width,
                thickness=sample.thickness,
                area=sample.area,
                quantity=len(group),
                board_ids=tuple(board.id for board in group),
                material=sample.material,
                grain_locked=sample.grain_locked,
                edge_band=sample.edge_band,
                finished_length=sample.finished_length,
                finished_width=sample.finished_width,
                labels=labels,
            )
        )
    return sorted(cutlist, key=lambda item: (item.thickness, item.length, item.width), reverse=True)
