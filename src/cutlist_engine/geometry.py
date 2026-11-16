from __future__ import annotations

from dataclasses import dataclass
from math import isclose

from .models import EPSILON, PlaneCluster, Triangle, Vec2, Vec3


@dataclass(frozen=True)
class ContourLoops:
    outer: tuple[Vec2, ...]
    holes: tuple[tuple[Vec2, ...], ...] = ()


def canonical_plane(normal: Vec3, point: Vec3) -> tuple[Vec3, float]:
    offset = normal.dot(point)
    if offset < 0:
        normal = normal * -1.0
        offset = -offset
    elif isclose(offset, 0.0, abs_tol=EPSILON):
        coords = normal.as_tuple()
        for value in coords:
            if abs(value) > EPSILON:
                if value < 0:
                    normal = normal * -1.0
                    offset = -offset
                break
    return normal, offset


def cluster_planes(
    triangles: list[Triangle],
    normal_tolerance: float = 0.999,
    distance_tolerance: float = 0.5,
) -> list[PlaneCluster]:
    clusters: list[PlaneCluster] = []
    buckets: dict[tuple[int, int, int, int], list[PlaneCluster]] = {}

    for triangle in triangles:
        if triangle.area() <= EPSILON:
            continue

        normal, offset = canonical_plane(triangle.normal(), triangle.a)
        
        nx = int(round(normal.x * 5))
        ny = int(round(normal.y * 5))
        nz = int(round(normal.z * 5))
        no = int(round(offset / max(0.1, distance_tolerance)))

        matched = None
        key = (nx, ny, nz, no)
        if key in buckets:
            for cluster in buckets[key]:
                if cluster.normal.dot(normal) >= normal_tolerance and abs(cluster.offset - offset) <= distance_tolerance:
                    matched = cluster
                    break

        if matched is None:
            matched = PlaneCluster(
                id=f"plane_{len(clusters) + 1:03d}",
                normal=normal,
                offset=offset,
            )
            clusters.append(matched)
            buckets.setdefault((nx, ny, nz, no), []).append(matched)

        matched.add(triangle)

    return clusters


def plane_basis(normal: Vec3) -> tuple[Vec3, Vec3]:
    reference = Vec3(1.0, 0.0, 0.0)
    if abs(normal.dot(reference)) > 0.9:
        reference = Vec3(0.0, 1.0, 0.0)

    u = normal.cross(reference).normalized()
    v = normal.cross(u).normalized()
    return u, v


def project_to_2d(points: list[Vec3], normal: Vec3) -> list[Vec2]:
    u, v = plane_basis(normal)
    projected = [Vec2(point.dot(u), point.dot(v)) for point in points]
    min_x = min(point.x for point in projected)
    min_y = min(point.y for point in projected)
    return [Vec2(point.x - min_x, point.y - min_y) for point in projected]


def unique_vertices(triangles: list[Triangle], tolerance: float = 0.01) -> list[Vec3]:
    vertices: dict[tuple[int, int, int], Vec3] = {}
    for triangle in triangles:
        for vertex in triangle.vertices:
            key = (
                round(vertex.x / tolerance),
                round(vertex.y / tolerance),
                round(vertex.z / tolerance),
            )
            vertices[key] = vertex
    return list(vertices.values())


def bounding_contour(points: list[Vec3], normal: Vec3) -> tuple[Vec2, ...]:
    projected = project_to_2d(points, normal)
    min_x = min(point.x for point in projected)
    max_x = max(point.x for point in projected)
    min_y = min(point.y for point in projected)
    max_y = max(point.y for point in projected)
    return (
        Vec2(min_x, min_y),
        Vec2(max_x, min_y),
        Vec2(max_x, max_y),
        Vec2(min_x, max_y),
    )


# ---------------------------------------------------------------------------
# True outer-loop contour (handles non-rectangular panels: notches, curves, cutouts)
# ---------------------------------------------------------------------------


def outer_loop_contour(
    triangles: list[Triangle],
    normal: Vec3,
    tolerance: float = 0.05,
    simplify_angle_deg: float = 1.5,
) -> tuple[Vec2, ...]:
    return contour_loops(triangles, normal, tolerance, simplify_angle_deg).outer


def contour_loops(
    triangles: list[Triangle],
    normal: Vec3,
    tolerance: float = 0.05,
    simplify_angle_deg: float = 1.5,
) -> ContourLoops:
    """Extract the true outer perimeter of a triangle-mesh face.

    Algorithm: build the edge multiset across all triangles. Edges that appear
    exactly once are boundary edges (interior edges are shared by two
    triangles). Stitch boundary edges into closed loops via vertex-key hashing.
    Pick the loop with the largest absolute signed area as the outer loop;
    smaller loops are internal holes (currently dropped — v1.2 will keep holes
    as separate cut paths).

    Falls back to the axis-aligned bounding box when the boundary cannot be
    closed into a loop (degenerate / non-manifold geometry).
    """
    if not triangles:
        return ContourLoops(())

    # 1. Build edge counts by undirected vertex-key pair.
    edge_count: dict[frozenset[tuple[int, int, int]], int] = {}
    edge_endpoints: dict[frozenset[tuple[int, int, int]], tuple[Vec3, Vec3]] = {}

    def vkey(v: Vec3) -> tuple[int, int, int]:
        return (round(v.x / tolerance), round(v.y / tolerance), round(v.z / tolerance))

    for triangle in triangles:
        verts = [triangle.a, triangle.b, triangle.c]
        for i in range(3):
            a, b = verts[i], verts[(i + 1) % 3]
            ka, kb = vkey(a), vkey(b)
            if ka == kb:
                continue
            key = frozenset({ka, kb})
            edge_count[key] = edge_count.get(key, 0) + 1
            edge_endpoints.setdefault(key, (a, b))

    # 2. Pick boundary edges (used by exactly one triangle).
    boundary_keys = [k for k, c in edge_count.items() if c == 1]
    if not boundary_keys:
        return ContourLoops(bounding_contour(unique_vertices(triangles), normal))

    # 3. Build adjacency: vertex_key -> list of (neighbor_key, point)
    adj: dict[tuple[int, int, int], list[tuple[tuple[int, int, int], Vec3]]] = {}
    point_of: dict[tuple[int, int, int], Vec3] = {}
    for key in boundary_keys:
        ka, kb = tuple(key)[0], tuple(key)[1]
        a, b = edge_endpoints[key]
        if vkey(a) != ka:
            a, b = b, a
        point_of[ka] = a
        point_of[kb] = b
        adj.setdefault(ka, []).append((kb, b))
        adj.setdefault(kb, []).append((ka, a))

    # 4. Stitch loops by walking neighbours; remove edges as consumed.
    loops_3d: list[list[Vec3]] = []
    consumed: set[frozenset[tuple[int, int, int]]] = set()
    for start in adj:
        if not any(frozenset({start, n}) not in consumed for n, _ in adj[start]):
            continue
        loop: list[Vec3] = [point_of[start]]
        prev = None
        current = start
        steps = 0
        max_steps = len(boundary_keys) * 2 + 4
        while steps < max_steps:
            steps += 1
            choices = [(n, p) for n, p in adj[current] if frozenset({current, n}) not in consumed]
            if not choices:
                break
            # Prefer not to backtrack to the previous vertex on a non-junction.
            forward = [c for c in choices if c[0] != prev] or choices
            next_key, next_pt = forward[0]
            consumed.add(frozenset({current, next_key}))
            if next_key == start:
                break
            loop.append(next_pt)
            prev, current = current, next_key
        if len(loop) >= 3:
            loops_3d.append(loop)

    if not loops_3d:
        return ContourLoops(bounding_contour(unique_vertices(triangles), normal))

    # 5. Project each loop and pick the largest by absolute signed area.
    u, v = plane_basis(normal)
    loops_2d: list[list[Vec2]] = []
    for loop in loops_3d:
        loops_2d.append([Vec2(p.dot(u), p.dot(v)) for p in loop])

    def signed_area(poly: list[Vec2]) -> float:
        n = len(poly)
        return 0.5 * sum(poly[i].x * poly[(i + 1) % n].y - poly[(i + 1) % n].x * poly[i].y for i in range(n))

    loops_2d = [loop for loop in loops_2d if len(loop) >= 3 and abs(signed_area(loop)) > EPSILON]
    if not loops_2d:
        return ContourLoops(bounding_contour(unique_vertices(triangles), normal))

    outer = max(loops_2d, key=lambda p: abs(signed_area(p)))
    holes = [loop for loop in loops_2d if loop is not outer]

    # 6. Ensure CCW orientation so downstream offset logic has a consistent sign.
    if signed_area(outer) < 0:
        outer = list(reversed(outer))
    normalized_holes: list[list[Vec2]] = []
    for hole in holes:
        if signed_area(hole) < 0:
            hole = list(reversed(hole))
        normalized_holes.append(hole)

    # 7. Translate to origin (min_x, min_y) -> (0, 0) so the contour aligns with
    # part placement coordinates used by nesting.
    min_x = min(p.x for p in outer)
    min_y = min(p.y for p in outer)
    outer = [Vec2(p.x - min_x, p.y - min_y) for p in outer]
    normalized_holes = [
        [Vec2(p.x - min_x, p.y - min_y) for p in hole]
        for hole in normalized_holes
    ]

    # 8. Simplify near-collinear vertices (keeps DXF / G-code clean).
    outer = _simplify_collinear(outer, simplify_angle_deg)
    normalized_holes = [
        _simplify_collinear(hole, simplify_angle_deg)
        for hole in normalized_holes
    ]

    return ContourLoops(tuple(outer), tuple(tuple(hole) for hole in normalized_holes))


def align_to_min_rect(
    outer: tuple[Vec2, ...],
    holes: tuple[tuple[Vec2, ...], ...] = (),
) -> tuple[tuple[Vec2, ...], tuple[tuple[Vec2, ...], ...]]:
    """Rotate an outline so its minimum-area bounding rectangle is axis-aligned.

    The projection basis of a plane is arbitrary, so a panel that is tilted in
    its own plane would otherwise be measured by a bounding box that is larger
    than the panel. Outlines that are already aligned are returned unchanged.
    """
    from math import atan2, cos, pi, sin

    if len(outer) < 3:
        return outer, holes

    hull = _convex_hull(list(outer))
    if len(hull) < 3:
        return outer, holes

    best_angle = 0.0
    best_area = None
    for i in range(len(hull)):
        a, b = hull[i], hull[(i + 1) % len(hull)]
        dx, dy = b.x - a.x, b.y - a.y
        if dx * dx + dy * dy <= EPSILON:
            continue
        angle = atan2(dy, dx) % (pi / 2)
        if angle > pi / 4:
            angle -= pi / 2
        c, s = cos(-angle), sin(-angle)
        xs = [p.x * c - p.y * s for p in hull]
        ys = [p.x * s + p.y * c for p in hull]
        area = (max(xs) - min(xs)) * (max(ys) - min(ys))
        if (
            best_area is None
            or area < best_area * (1 - 1e-9)
            or (abs(area - best_area) <= best_area * 1e-9 and abs(angle) < abs(best_angle))
        ):
            best_area, best_angle = area, angle

    if abs(best_angle) < 1e-6:
        return outer, holes

    c, s = cos(-best_angle), sin(-best_angle)

    def rot(p: Vec2) -> Vec2:
        return Vec2(p.x * c - p.y * s, p.x * s + p.y * c)

    rotated = [rot(p) for p in outer]
    min_x = min(p.x for p in rotated)
    min_y = min(p.y for p in rotated)

    def place(p: Vec2) -> Vec2:
        r = rot(p)
        return Vec2(round(r.x - min_x, 4), round(r.y - min_y, 4))

    return tuple(place(p) for p in outer), tuple(tuple(place(p) for p in hole) for hole in holes)


def _convex_hull(points: list[Vec2]) -> list[Vec2]:
    pts = sorted({(p.x, p.y) for p in points})
    if len(pts) < 3:
        return [Vec2(x, y) for x, y in pts]

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return [Vec2(x, y) for x, y in lower[:-1] + upper[:-1]]


def _simplify_collinear(poly: list[Vec2], angle_deg: float) -> list[Vec2]:
    if len(poly) < 4:
        return poly
    from math import acos, degrees, sqrt

    def _norm(v: Vec2) -> Vec2:
        m = sqrt(v.x * v.x + v.y * v.y) or 1.0
        return Vec2(v.x / m, v.y / m)

    keep: list[Vec2] = []
    n = len(poly)
    for i in range(n):
        prev = poly[(i - 1) % n]
        cur = poly[i]
        nxt = poly[(i + 1) % n]
        a = _norm(Vec2(cur.x - prev.x, cur.y - prev.y))
        b = _norm(Vec2(nxt.x - cur.x, nxt.y - cur.y))
        dot = max(-1.0, min(1.0, a.x * b.x + a.y * b.y))
        turn = abs(degrees(acos(dot)))
        if turn >= angle_deg:
            keep.append(cur)
    return keep if len(keep) >= 3 else poly
