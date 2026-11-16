from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt


EPSILON = 1e-9


@dataclass(frozen=True)
class Vec2:
    x: float
    y: float

    def as_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float

    def __add__(self, other: Vec3) -> Vec3:
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vec3) -> Vec3:
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> Vec3:
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)

    def dot(self, other: Vec3) -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: Vec3) -> Vec3:
        return Vec3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def length(self) -> float:
        return sqrt(self.dot(self))

    def normalized(self) -> Vec3:
        length = self.length()
        if length <= EPSILON:
            raise ValueError("Cannot normalize a zero-length vector")
        return self * (1.0 / length)

    def distance_to(self, other: Vec3) -> float:
        return (self - other).length()

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass(frozen=True)
class Triangle:
    a: Vec3
    b: Vec3
    c: Vec3
    source_object: str | None = None

    @property
    def vertices(self) -> tuple[Vec3, Vec3, Vec3]:
        return (self.a, self.b, self.c)

    def normal(self) -> Vec3:
        return (self.b - self.a).cross(self.c - self.a).normalized()

    def area(self) -> float:
        return 0.5 * (self.b - self.a).cross(self.c - self.a).length()

    def centroid(self) -> Vec3:
        return Vec3(
            (self.a.x + self.b.x + self.c.x) / 3.0,
            (self.a.y + self.b.y + self.c.y) / 3.0,
            (self.a.z + self.b.z + self.c.z) / 3.0,
        )


@dataclass
class PlaneCluster:
    id: str
    normal: Vec3
    offset: float
    triangles: list[Triangle] = field(default_factory=list)

    def add(self, triangle: Triangle) -> None:
        self.triangles.append(triangle)

    @property
    def area(self) -> float:
        return sum(triangle.area() for triangle in self.triangles)


@dataclass(frozen=True)
class Board:
    id: str
    length: float
    width: float
    thickness: float
    area: float
    contour: tuple[Vec2, ...]
    source_planes: tuple[str, str]
    holes: tuple[tuple[Vec2, ...], ...] = ()
    confidence: float = 1.0
    warnings: tuple[str, ...] = ()
    source_objects: tuple[str, ...] = ()
    grain_locked: bool = False
    # Real-shop attributes ----------------------------------------------------
    material: str = "default"
    """Material key. Boards of different materials are nested on separate sheets."""
    priority: str = "normal"
    """One of 'visible' (gets cleanest area / first placement), 'normal', 'hidden'."""
    edge_band: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    """Edge banding thickness in mm on (top, right, bottom, left) of the FINISHED panel.
    The cut size is reduced by these amounts so the part, once banded, reaches the
    finished dimension. top/bottom are the short edges, left/right the long edges."""
    label: str = ""
    """Human-readable name shown on the layout / labels. Falls back to id when blank."""
    finished_length: float = 0.0
    finished_width: float = 0.0
    """Original finished dimensions before edge-band oversize was added (0 == not adjusted)."""

    def dimensions_key(self, tolerance: float) -> tuple:
        dims = sorted((self.length, self.width), reverse=True)
        return (
            round(dims[0] / tolerance),
            round(dims[1] / tolerance),
            round(self.thickness / tolerance),
            self.material,
            self.grain_locked,
            tuple(round(b / tolerance) for b in self.edge_band),
            tuple(
                tuple((round(point.x / tolerance), round(point.y / tolerance)) for point in hole)
                for hole in self.holes
            ),
        )


@dataclass(frozen=True)
class CutlistItem:
    id: str
    length: float
    width: float
    thickness: float
    area: float
    quantity: int
    board_ids: tuple[str, ...] = ()
    material: str = "default"
    grain_locked: bool = False
    edge_band: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    finished_length: float = 0.0
    finished_width: float = 0.0
    labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class NestedPart:
    board_id: str
    x: float
    y: float
    rotation: int
    length: float
    width: float


@dataclass(frozen=True)
class Offcut:
    x: float
    y: float
    width: float
    height: float
    area: float
    reusable: bool


@dataclass(frozen=True)
class SheetLayout:
    sheet_id: int
    width: float
    height: float
    parts: tuple[NestedPart, ...]
    used_area: float
    offcuts: tuple[Offcut, ...] = ()
    material: str = "default"
    sheet_cost: float = 0.0
    currency: str = "USD"
    is_offcut_stock: bool = False
    """True when this sheet is a saved offcut from the shop's shelf (free stock)."""

    @property
    def waste_percent(self) -> float:
        sheet_area = self.width * self.height
        if sheet_area <= EPSILON:
            return 0.0
        return max(0.0, (1.0 - self.used_area / sheet_area) * 100.0)

    @property
    def utilization_percent(self) -> float:
        return 100.0 - self.waste_percent


@dataclass(frozen=True)
class ExtractionReport:
    triangle_count: int
    usable_triangle_count: int
    plane_count: int
    surface_count: int
    board_count: int
    unmatched_surface_count: int
    confidence: float
    warnings: tuple[str, ...] = ()
    solid_part_count: int = 0
    """Closed solids found in the model (one per modelled part)."""
    inferred_board_count: int = 0
    """Boards reconstructed by pairing loose faces rather than measured from a solid."""
    skipped_parts: tuple[str, ...] = ()
    """Names of closed solids that are not flat panels (hardware, legs, decoration)."""


@dataclass(frozen=True)
class MaterialSummary:
    total_board_area: float
    sheet_area: float
    sheet_count: int
    used_sheet_area: float
    waste_area: float
    waste_percent: float
    utilization_percent: float
    reusable_offcut_area: float = 0.0
    lost_waste_area: float = 0.0
    sheet_cost: float = 0.0
    currency: str = "USD"
    total_material_cost: float = 0.0
    sheet_savings_vs_worst_strategy: int = 0
    cost_savings_vs_worst_strategy: float = 0.0
    sheet_size_label: str = ""


@dataclass(frozen=True)
class SheetSizeOption:
    label: str
    width: float
    height: float
    sheet_cost: float
    sheet_count: int
    total_cost: float
    waste_percent: float
    utilization_percent: float


@dataclass(frozen=True)
class ModelFixReport:
    confidence: float
    confidence_threshold: float
    passes_gate: bool
    issues: tuple[str, ...]
    recommendations: tuple[str, ...]
    discarded_sliver_count: int = 0
    sliver_min_dimension: float = 0.0


@dataclass(frozen=True)
class MaterialSpec:
    """A stockable plywood / sheet material."""
    name: str
    thickness: float
    sheet_width: float
    sheet_height: float
    sheet_cost: float
    grain_locked_default: bool = False
    currency: str = "USD"


@dataclass(frozen=True)
class ReviewDecision:
    """Operator review of a detected board."""
    accepted: bool
    rename: str = ""
    reason: str = ""


@dataclass(frozen=True)
class NestingStrategyResult:
    strategy: str
    sheet_count: int
    waste_percent: float
    utilization_percent: float
    reusable_offcut_area: float


@dataclass(frozen=True)
class WasteOptimizationReport:
    selected_strategy: str
    strategy_results: tuple[NestingStrategyResult, ...]
    sheet_savings_vs_worst: int
    waste_reduction_vs_worst_percent: float
