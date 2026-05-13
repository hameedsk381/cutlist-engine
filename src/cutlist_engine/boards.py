from __future__ import annotations

from dataclasses import dataclass

from .geometry import bounding_contour, cluster_planes, contour_loops, unique_vertices
from .models import Board, CutlistItem, ExtractionReport, PlaneCluster, Triangle, Vec3


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
) -> BoardExtraction:
    usable_triangles = [triangle for triangle in triangles if triangle.area() > 0]
    planes = cluster_planes(
        usable_triangles,
        normal_tolerance=normal_tolerance,
        distance_tolerance=thickness_tolerance,
    )
    # Filter out planes with very small total area (e.g. less than 50x50mm) 
    # to avoid O(N^2) explosion on highly curved organic surfaces
    planes = [p for p in planes if sum(t.area() for t in p.triangles) >= 2500.0]
    surfaces = _split_surfaces(planes)
    boards: list[Board] = []
    used_pairs: set[tuple[str, str]] = set()
    used_surfaces: set[str] = set()
    warnings: list[str] = []

    if not usable_triangles:
        warnings.append("No usable triangle faces were found in the input geometry.")

    for first in surfaces:
        if first.id in used_surfaces:
            continue
        candidates = []
        for second in surfaces:
            if first.id == second.id:
                continue
            if second.id in used_surfaces:
                continue
            pair_key = tuple(sorted((first.id, second.id)))
            if pair_key in used_pairs:
                continue
            if abs(first.normal.dot(second.normal) - 1.0) > (1.0 - normal_tolerance):
                continue

            thickness = abs(first.offset - second.offset)
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

            candidates.append(
                (
                    lateral_dist,
                    abs(thickness - (expected_thickness or thickness)),
                    thickness,
                    second,
                )
            )

        if not candidates:
            continue

        lateral_distance, thickness_error, thickness, second = sorted(candidates, key=lambda item: (item[0], item[1]))[0]
        if expected_thickness is not None and abs(thickness - expected_thickness) <= thickness_tolerance:
            thickness = expected_thickness
        pair_key = tuple(sorted((first.id, second.id)))
        used_pairs.add(pair_key)
        used_surfaces.update((first.id, second.id))
        boards.append(
            _board_from_planes(
                len(boards) + 1,
                first,
                second,
                thickness,
                confidence=_pair_confidence(first, second, lateral_distance, thickness_error, thickness_tolerance),
                warnings=_pair_warnings(first, second, lateral_distance, thickness_error, thickness_tolerance),
            )
        )

    unmatched_surface_count = len([surface for surface in surfaces if surface.id not in used_surfaces])
    if unmatched_surface_count:
        warnings.append(f"{unmatched_surface_count} planar surfaces were not paired into manufacturable boards.")

    confidence = _overall_confidence(boards, surfaces, unmatched_surface_count)
    report = ExtractionReport(
        triangle_count=len(triangles),
        usable_triangle_count=len(usable_triangles),
        plane_count=len(planes),
        surface_count=len(surfaces),
        board_count=len(boards),
        unmatched_surface_count=unmatched_surface_count,
        confidence=confidence,
        warnings=tuple(warnings),
    )
    return BoardExtraction(boards=boards, report=report)


def _board_from_planes(
    index: int,
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
    width = max(point.x for point in contour) - min(point.x for point in contour)
    height = max(point.y for point in contour) - min(point.y for point in contour)
    length, board_width = sorted((width, height), reverse=True)

    # Tag boards whose outer loop departs significantly from a plain rectangle so
    # downstream consumers (DXF, G-code, label sheet) know to use the polygon.
    extra_warnings = list(warnings)
    is_rectangular = _is_axis_aligned_rectangle(contour)
    if not is_rectangular:
        extra_warnings.append("Non-rectangular outer contour detected; cut path will follow the polygon, not the bounding box.")
    if holes:
        extra_warnings.append(f"{len(holes)} interior cutout(s) detected; DXF and G-code will include hole cut paths.")

    return Board(
        id=f"panel_{index:03d}",
        length=length,
        width=board_width,
        thickness=thickness,
        area=(length * board_width) / 1_000_000.0,
        contour=contour,
        source_planes=(first.id, second.id),
        holes=holes,
        confidence=confidence,
        warnings=tuple(extra_warnings),
        source_objects=tuple(
            sorted({triangle.source_object for triangle in first.triangles + second.triangles if triangle.source_object})
        ),
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


def _overall_confidence(boards: list[Board], surfaces: list[_Surface], unmatched_surface_count: int) -> float:
    if not surfaces:
        return 0.0
    paired_surface_ratio = (len(surfaces) - unmatched_surface_count) / len(surfaces)
    board_confidence = sum(board.confidence for board in boards) / len(boards) if boards else 0.0
    return round((paired_surface_ratio * 0.4) + (board_confidence * 0.6), 3)


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
