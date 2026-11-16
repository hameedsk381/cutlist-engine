from __future__ import annotations

import re

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable

from .boards import STOCK_THICKNESSES, build_cutlist, extract_boards
from .models import (
    Board,
    CutlistItem,
    ExtractionReport,
    MaterialSpec,
    MaterialSummary,
    ModelFixReport,
    ReviewDecision,
    SheetLayout,
    SheetSizeOption,
    Triangle,
    WasteOptimizationReport,
)
from .nesting import optimize_cutting_layout


_DEFAULT_MATERIAL = "default"


@dataclass(frozen=True)
class ProcessConfig:
    sheet_width: float = 2440.0
    sheet_height: float = 1220.0
    material_thickness: float | None = 18.0
    thickness_tolerance: float = 0.5
    kerf: float = 3.0
    min_reusable_offcut_width: float = 300.0
    min_reusable_offcut_height: float = 300.0
    grain_locked: bool = False
    min_part_length: float = 50.0
    min_part_width: float = 50.0
    min_confidence: float = 0.6
    min_board_confidence: float = 0.3
    """Individual board confidence floor. Boards below this are discarded as false positives."""
    sheet_cost: float = 3500.0
    currency: str = "INR"
    candidate_sheet_sizes: tuple[tuple[str, float, float, float], ...] = ()
    overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    """Per-part overrides keyed by board id OR by source_object name. Fields:
       grain_locked (bool), priority ('visible'|'normal'|'hidden'),
       edge_band ([t,r,b,l] mm), material (str), label (str)."""
    materials: dict[str, MaterialSpec] = field(default_factory=dict)
    """Optional material registry. Boards routed to a material are nested on its sheets."""
    review: dict[str, ReviewDecision] = field(default_factory=dict)
    """Operator review decisions keyed by board id."""
    offcut_stock: tuple[tuple[float, float, str], ...] = ()
    """Saved offcuts as (width, height, material) mm. Consumed as free sheets
    before full sheets, for the matching material group."""


@dataclass(frozen=True)
class ProcessResult:
    boards: list[Board]
    cutlist: list[CutlistItem]
    sheets: list[SheetLayout]
    extraction_report: ExtractionReport
    material_summary: MaterialSummary
    waste_optimization_report: WasteOptimizationReport | None = None
    model_fix_report: ModelFixReport | None = None
    sheet_size_options: tuple[SheetSizeOption, ...] = ()
    per_material_summaries: tuple[MaterialSummary, ...] = ()
    rejected_boards: list[Board] = field(default_factory=list)
    oversize_boards: list[Board] = field(default_factory=list)
    """Parts longer than any sheet. Left out of the plan and reported, not nested."""
    kerf: float = 3.0
    """Saw blade width the sheets were nested with; the cut sequence needs it."""


# -----------------------------------------------------------------------------
# Public entry point
# -----------------------------------------------------------------------------

def process_triangles(triangles: list[Triangle], config: ProcessConfig) -> ProcessResult:
    extraction = extract_boards(
        triangles,
        expected_thickness=config.material_thickness,
        thickness_tolerance=config.thickness_tolerance,
        stock_thicknesses=tuple(spec.thickness for spec in config.materials.values()) + STOCK_THICKNESSES,
    )

    raw_boards = extraction.boards
    boards, discarded_slivers = _filter_slivers(raw_boards, config.min_part_length, config.min_part_width)

    # Reject low-confidence false-positive boards before any downstream processing.
    boards, discarded_low_conf = _filter_low_confidence(boards, config.min_board_confidence)

    # Apply per-part overrides (grain, priority, edge-band, material, label).
    boards = [_apply_overrides(b, config) for b in boards]

    # Parts whose thickness differs from the default stock cannot be cut from
    # the default sheets; give them a material (and so sheets) of their own.
    boards = [_route_by_thickness(b, config) for b in boards]
    auto_materials = sorted({b.material for b in boards} - set(config.materials) - {_DEFAULT_MATERIAL})

    # Material registry. Resolves material name -> MaterialSpec. Falls back to defaults.
    material_registry = _resolve_materials(boards, config)

    # Apply material-level defaults after overrides assign the material, but
    # before cut-size adjustments and review/cutlist generation.
    boards = [_apply_material_defaults(b, material_registry) for b in boards]

    # Apply edge-banding oversize (cut size = finished + band thickness).
    boards = [_apply_edge_band(b) for b in boards]

    # Apply operator review (accept / reject / rename).
    boards, rejected = _apply_review(boards, config.review)

    # A part longer than every sheet can never be nested. Set it aside and say
    # so; one such part must not stop the plan for all the others.
    boards, oversize = _split_oversize(boards, material_registry, config)

    cutlist = build_cutlist(boards, tolerance=config.thickness_tolerance)

    # Sheet-size simulation only meaningful when there's a single default material.
    sheet_options: list[SheetSizeOption] = []
    if boards and _is_single_default_material(boards):
        sheet_options = _simulate_sheet_sizes(boards, config)

    chosen = sheet_options[0] if sheet_options else None
    chosen_label_for_summary: str | None = None
    if chosen and _DEFAULT_MATERIAL in material_registry:
        # Replace the default spec with the cheapest candidate.
        material_registry[_DEFAULT_MATERIAL] = MaterialSpec(
            name=_DEFAULT_MATERIAL,
            thickness=config.material_thickness or 18.0,
            sheet_width=chosen.width,
            sheet_height=chosen.height,
            sheet_cost=chosen.sheet_cost,
            currency=config.currency,
        )
        chosen_label_for_summary = chosen.label

    # Nest each material independently and combine sheets.
    all_sheets: list[SheetLayout] = []
    waste_reports: list[WasteOptimizationReport] = []
    per_material: list[MaterialSummary] = []
    next_sheet_id = 1

    for material_name, group in _group_by_material(boards).items():
        spec = material_registry.get(material_name) or material_registry[_DEFAULT_MATERIAL]
        stock_for_material = tuple(
            (float(w), float(h)) for w, h, m in config.offcut_stock if m == material_name
        )
        layout = optimize_cutting_layout(
            group,
            sheet_width=spec.sheet_width,
            sheet_height=spec.sheet_height,
            kerf=config.kerf,
            min_reusable_offcut_width=config.min_reusable_offcut_width,
            min_reusable_offcut_height=config.min_reusable_offcut_height,
            material=material_name,
            sheet_cost=spec.sheet_cost,
            currency=spec.currency,
            offcut_stock=stock_for_material,
        )
        # Renumber so global sheet ids are contiguous across materials.
        renumbered = []
        for sheet in layout.sheets:
            renumbered.append(replace(sheet, sheet_id=next_sheet_id))
            next_sheet_id += 1
        all_sheets.extend(renumbered)
        waste_reports.append(layout.report)

        if material_name == _DEFAULT_MATERIAL and chosen_label_for_summary:
            label = f"{chosen_label_for_summary} ({int(spec.sheet_width)}x{int(spec.sheet_height)})"
        else:
            label = f"{spec.name} {int(spec.sheet_width)}x{int(spec.sheet_height)}"
        per_material.append(
            summarize_material(
                group,
                renumbered,
                sheet_width=spec.sheet_width,
                sheet_height=spec.sheet_height,
                sheet_cost=spec.sheet_cost,
                currency=spec.currency,
                sheet_label=label,
                waste_report=layout.report,
            )
        )

    # Top-level summary aggregates across materials.
    material_summary = _aggregate_summary(per_material, config.currency)

    model_fix_report = _build_model_fix_report(
        extraction.report,
        config.min_confidence,
        discarded_slivers=discarded_slivers,
        discarded_low_confidence=discarded_low_conf,
        min_part_dimension=min(config.min_part_length, config.min_part_width),
        min_board_confidence=config.min_board_confidence,
        board_count=len(boards),
        auto_materials=tuple(auto_materials),
        oversize=oversize,
        material_registry=material_registry,
        scaled_from_metres=bool(getattr(triangles, "scaled_from_metres", False)),
        declared_unit=getattr(triangles, "declared_unit", None),
    )

    waste_optimization_report = waste_reports[0] if len(waste_reports) == 1 else _merge_waste_reports(waste_reports)

    return ProcessResult(
        boards=boards,
        cutlist=cutlist,
        sheets=all_sheets,
        extraction_report=extraction.report,
        material_summary=material_summary,
        waste_optimization_report=waste_optimization_report,
        model_fix_report=model_fix_report,
        sheet_size_options=tuple(sheet_options),
        per_material_summaries=tuple(per_material),
        rejected_boards=rejected,
        oversize_boards=oversize,
        kerf=config.kerf,
    )


def _fits_sheet(board: Board, width: float, height: float) -> bool:
    if board.grain_locked:
        return board.length <= width and board.width <= height
    return (
        min(board.length, board.width) <= min(width, height)
        and max(board.length, board.width) <= max(width, height)
    )


def _split_oversize(
    boards: list[Board], registry: dict[str, MaterialSpec], config: ProcessConfig,
) -> tuple[list[Board], list[Board]]:
    """Split boards into (fits some sheet, longer than every sheet)."""
    default_sizes = [(config.sheet_width, config.sheet_height)] + [
        (w, h) for _, w, h, _ in config.candidate_sheet_sizes
    ]
    fitting: list[Board] = []
    oversize: list[Board] = []
    for board in boards:
        name = board.material or _DEFAULT_MATERIAL
        spec = registry.get(name) or registry.get(_DEFAULT_MATERIAL)
        sizes = default_sizes if name == _DEFAULT_MATERIAL or spec is None else [(spec.sheet_width, spec.sheet_height)]
        (fitting if any(_fits_sheet(board, w, h) for w, h in sizes) else oversize).append(board)
    return fitting, oversize


def summarize_material(
    boards: list[Board],
    sheets: list[SheetLayout],
    *,
    sheet_width: float,
    sheet_height: float,
    sheet_cost: float = 0.0,
    currency: str = "USD",
    sheet_label: str = "",
    waste_report: WasteOptimizationReport | None = None,
) -> MaterialSummary:
    total_board_area_mm2 = sum(b.length * b.width for b in boards)
    sheet_area = sheet_width * sheet_height
    # Actual area across all sheets — offcut-stock sheets are smaller than the
    # nominal sheet size, so sum the real geometry rather than nominal × count.
    used_sheet_area = sum(s.width * s.height for s in sheets)
    waste_area = max(0.0, used_sheet_area - total_board_area_mm2)
    reusable_offcut_area_mm2 = sum(
        offcut.area * 1_000_000.0 for sheet in sheets for offcut in sheet.offcuts if offcut.reusable
    )
    lost_waste_area_mm2 = max(0.0, waste_area - reusable_offcut_area_mm2)
    waste_percent = (waste_area / used_sheet_area * 100.0) if used_sheet_area else 0.0

    sheet_savings = waste_report.sheet_savings_vs_worst if waste_report else 0
    cost_savings = round(sheet_savings * sheet_cost, 2)
    # Sum the real per-sheet cost: offcut-stock sheets are free.
    total_cost = round(sum(s.sheet_cost for s in sheets), 2)

    return MaterialSummary(
        total_board_area=total_board_area_mm2 / 1_000_000.0,
        sheet_area=sheet_area / 1_000_000.0,
        sheet_count=len(sheets),
        used_sheet_area=used_sheet_area / 1_000_000.0,
        waste_area=waste_area / 1_000_000.0,
        waste_percent=round(waste_percent, 2),
        utilization_percent=round(100.0 - waste_percent, 2) if used_sheet_area else 0.0,
        reusable_offcut_area=round(reusable_offcut_area_mm2 / 1_000_000.0, 4),
        lost_waste_area=round(lost_waste_area_mm2 / 1_000_000.0, 4),
        sheet_cost=round(sheet_cost, 2),
        currency=currency,
        total_material_cost=total_cost,
        sheet_savings_vs_worst_strategy=sheet_savings,
        cost_savings_vs_worst_strategy=cost_savings,
        sheet_size_label=sheet_label,
    )


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _filter_slivers(boards: list[Board], min_length: float, min_width: float) -> tuple[list[Board], int]:
    kept: list[Board] = []
    discarded = 0
    for board in boards:
        long_edge = max(board.length, board.width)
        short_edge = min(board.length, board.width)
        if long_edge < min_length or short_edge < min_width:
            discarded += 1
            continue
        kept.append(board)
    return kept, discarded


def _filter_low_confidence(boards: list[Board], min_confidence: float) -> tuple[list[Board], int]:
    """Remove boards whose individual pairing confidence is below the floor.
    These are almost always false-positive matches (e.g. dome arch surface
    force-paired with an unrelated panel face)."""
    kept: list[Board] = []
    discarded = 0
    for board in boards:
        if board.confidence < min_confidence:
            discarded += 1
            continue
        kept.append(board)
    return kept, discarded


def _apply_overrides(board: Board, config: ProcessConfig) -> Board:
    keys = [board.id, *board.source_objects]
    merged: dict[str, Any] = {}
    for key in keys:
        if key in config.overrides:
            merged.update(config.overrides[key])

    grain = bool(merged.get("grain_locked", config.grain_locked or board.grain_locked))
    priority = str(merged.get("priority", board.priority))
    if priority not in {"visible", "normal", "hidden"}:
        priority = "normal"
    edge_band = merged.get("edge_band", board.edge_band)
    if isinstance(edge_band, list):
        edge_band = tuple(float(x) for x in (edge_band + [0.0] * 4)[:4])
    elif not isinstance(edge_band, tuple):
        edge_band = (0.0, 0.0, 0.0, 0.0)
    material = str(merged.get("material", board.material) or _DEFAULT_MATERIAL)
    raw_label = merged.get("label", board.label or (board.source_objects[0] if board.source_objects else ""))
    label = _smart_label(str(raw_label))

    return replace(
        board,
        grain_locked=grain,
        priority=priority,
        edge_band=edge_band,
        material=material,
        label=label,
    )


def _route_by_thickness(board: Board, config: ProcessConfig) -> Board:
    base = config.material_thickness
    if board.material != _DEFAULT_MATERIAL or base is None:
        return board
    if abs(board.thickness - base) <= config.thickness_tolerance:
        return board
    matches = [
        name for name, spec in config.materials.items()
        if abs(spec.thickness - board.thickness) <= config.thickness_tolerance
    ]
    material = matches[0] if len(matches) == 1 else f"{board.thickness:g}mm"
    return replace(board, material=material)


def _smart_label(raw: str) -> str:
    """Shorten a SketchUp group hierarchy name to the part's own name.

    The name reads innermost first and ends at the model root, for example
    'Mesh9 Component30_1 Group4 Group3 Group1 Component_33_1 Model'. The part's
    own name is the first token that is not mesh, group or model scaffolding;
    the root at the end is shared by every part and says nothing about this one.
    """
    if not raw or len(raw) <= 40:
        return raw
    scaffolding = re.compile(r"^(mesh|group|model|default)\d*$", re.IGNORECASE)
    tokens = [t for t in raw.split() if not scaffolding.match(t)]
    if tokens:
        return tokens[0]
    return " ".join(raw.split()[-2:])


def _apply_material_defaults(board: Board, materials: dict[str, MaterialSpec]) -> Board:
    spec = materials.get(board.material or _DEFAULT_MATERIAL)
    if spec is None or not spec.grain_locked_default or board.grain_locked:
        return board
    return replace(board, grain_locked=True)


def _apply_edge_band(board: Board) -> Board:
    """Shrink the cut size so the part reaches its finished size after banding.

    Edge banding is glued onto the cut edge and adds its own thickness, so a
    600 mm finished panel with 2 mm tape on both ends is cut at 596 mm.
    `edge_band` is (top, right, bottom, left) tape thickness in mm: top/bottom
    are the two short edges (they change the length), left/right are the two
    long edges (they change the width).
    """
    top, right, bottom, left = board.edge_band
    if not any((top, right, bottom, left)):
        return board
    cut_length = board.length - (top + bottom)
    cut_width = board.width - (left + right)
    if cut_length <= 0 or cut_width <= 0:
        return board  # tape thicker than the part: leave the size alone
    return replace(
        board,
        finished_length=board.length,
        finished_width=board.width,
        length=cut_length,
        width=cut_width,
        area=(cut_length * cut_width) / 1_000_000.0,
    )


def edge_banding_summary(boards: Iterable[Board]) -> dict[str, Any]:
    """Metres of edge tape a job needs, in total and per tape thickness.

    Lengths are net (the finished edge lengths). Workshops usually buy about
    10 percent more to allow for trimming.
    """
    by_thickness: dict[float, float] = {}
    banded_parts = 0
    for board in boards:
        top, right, bottom, left = board.edge_band
        if not any((top, right, bottom, left)):
            continue
        banded_parts += 1
        long_edge = board.finished_length or board.length
        short_edge = board.finished_width or board.width
        for thickness, edge in ((top, short_edge), (bottom, short_edge), (left, long_edge), (right, long_edge)):
            if thickness > 0:
                by_thickness[thickness] = by_thickness.get(thickness, 0.0) + edge
    return {
        "total_m": round(sum(by_thickness.values()) / 1000.0, 2),
        "by_thickness": [
            {"thickness": thickness, "metres": round(mm / 1000.0, 2)}
            for thickness, mm in sorted(by_thickness.items())
        ],
        "banded_parts": banded_parts,
    }


def _apply_review(boards: list[Board], review: dict[str, ReviewDecision]) -> tuple[list[Board], list[Board]]:
    if not review:
        return boards, []
    accepted: list[Board] = []
    rejected: list[Board] = []
    for board in boards:
        decision = review.get(board.id)
        if decision is None:
            accepted.append(board)
            continue
        if not decision.accepted:
            rejected.append(board)
            continue
        if decision.rename:
            accepted.append(replace(board, label=decision.rename))
        else:
            accepted.append(board)
    return accepted, rejected


def _group_by_material(boards: list[Board]) -> dict[str, list[Board]]:
    groups: dict[str, list[Board]] = {}
    for board in boards:
        groups.setdefault(board.material or _DEFAULT_MATERIAL, []).append(board)
    return groups


def _resolve_materials(boards: list[Board], config: ProcessConfig) -> dict[str, MaterialSpec]:
    registry: dict[str, MaterialSpec] = dict(config.materials)
    used = {b.material or _DEFAULT_MATERIAL for b in boards}
    for name in used | {_DEFAULT_MATERIAL}:
        if name not in registry:
            own = [b.thickness for b in boards if b.material == name] if name != _DEFAULT_MATERIAL else []
            registry[name] = MaterialSpec(
                name=name,
                thickness=own[0] if own else (config.material_thickness or 18.0),
                sheet_width=config.sheet_width,
                sheet_height=config.sheet_height,
                sheet_cost=config.sheet_cost,
                currency=config.currency,
            )
    return registry


def _is_single_default_material(boards: list[Board]) -> bool:
    materials = {b.material or _DEFAULT_MATERIAL for b in boards}
    return materials == {_DEFAULT_MATERIAL}


def _sheet_label(width: float, height: float) -> str:
    return f"{int(round(width))}x{int(round(height))}"


def _simulate_sheet_sizes(boards: list[Board], config: ProcessConfig) -> list[SheetSizeOption]:
    if not boards:
        return []
    candidates: list[tuple[str, float, float, float]] = list(config.candidate_sheet_sizes)
    if not candidates:
        candidates = [(_sheet_label(config.sheet_width, config.sheet_height),
                       config.sheet_width, config.sheet_height, config.sheet_cost)]

    options: list[SheetSizeOption] = []
    for label, width, height, cost in candidates:
        try:
            layout = optimize_cutting_layout(
                boards,
                sheet_width=width,
                sheet_height=height,
                kerf=config.kerf,
                min_reusable_offcut_width=config.min_reusable_offcut_width,
                min_reusable_offcut_height=config.min_reusable_offcut_height,
                sheet_cost=cost,
                currency=config.currency,
            )
        except ValueError:
            continue
        sheet_count = len(layout.sheets)
        total_area = sum(s.width * s.height for s in layout.sheets)
        used_area = sum(s.used_area for s in layout.sheets)
        waste_pct = ((total_area - used_area) / total_area * 100.0) if total_area else 0.0
        options.append(
            SheetSizeOption(
                label=label,
                width=width,
                height=height,
                sheet_cost=round(cost, 2),
                sheet_count=sheet_count,
                total_cost=round(sheet_count * cost, 2),
                waste_percent=round(waste_pct, 2),
                utilization_percent=round(100.0 - waste_pct, 2),
            )
        )

    options.sort(key=lambda o: (o.total_cost, o.waste_percent, o.sheet_count))
    return options


def _aggregate_summary(per_material: list[MaterialSummary], currency: str) -> MaterialSummary:
    if not per_material:
        return MaterialSummary(
            total_board_area=0.0, sheet_area=0.0, sheet_count=0, used_sheet_area=0.0,
            waste_area=0.0, waste_percent=0.0, utilization_percent=0.0,
            currency=currency,
        )
    if len(per_material) == 1:
        return per_material[0]
    total_board = sum(s.total_board_area for s in per_material)
    used_area = sum(s.used_sheet_area for s in per_material)
    waste = sum(s.waste_area for s in per_material)
    sheet_count = sum(s.sheet_count for s in per_material)
    cost = sum(s.total_material_cost for s in per_material)
    savings = sum(s.cost_savings_vs_worst_strategy for s in per_material)
    sheet_savings = sum(s.sheet_savings_vs_worst_strategy for s in per_material)
    reusable = sum(s.reusable_offcut_area for s in per_material)
    lost = sum(s.lost_waste_area for s in per_material)
    waste_pct = (waste / used_area * 100.0) if used_area else 0.0
    return MaterialSummary(
        total_board_area=round(total_board, 4),
        sheet_area=0.0,
        sheet_count=sheet_count,
        used_sheet_area=round(used_area, 4),
        waste_area=round(waste, 4),
        waste_percent=round(waste_pct, 2),
        utilization_percent=round(100.0 - waste_pct, 2),
        reusable_offcut_area=round(reusable, 4),
        lost_waste_area=round(lost, 4),
        sheet_cost=0.0,
        currency=currency,
        total_material_cost=round(cost, 2),
        sheet_savings_vs_worst_strategy=sheet_savings,
        cost_savings_vs_worst_strategy=round(savings, 2),
        sheet_size_label=f"{len(per_material)} materials",
    )


def _merge_waste_reports(reports: list[WasteOptimizationReport]) -> WasteOptimizationReport | None:
    if not reports:
        return None
    return WasteOptimizationReport(
        selected_strategy=", ".join(sorted({r.selected_strategy for r in reports})),
        strategy_results=tuple(s for r in reports for s in r.strategy_results),
        sheet_savings_vs_worst=sum(r.sheet_savings_vs_worst for r in reports),
        waste_reduction_vs_worst_percent=round(
            sum(r.waste_reduction_vs_worst_percent for r in reports) / len(reports), 2
        ),
    )


def _build_model_fix_report(
    extraction: ExtractionReport,
    threshold: float,
    *,
    discarded_slivers: int,
    discarded_low_confidence: int = 0,
    min_part_dimension: float,
    min_board_confidence: float = 0.3,
    board_count: int,
    auto_materials: tuple[str, ...] = (),
    oversize: list[Board] | None = None,
    material_registry: dict[str, MaterialSpec] | None = None,
    scaled_from_metres: bool = False,
    declared_unit: str | None = None,
) -> ModelFixReport:
    issues: list[str] = []
    recommendations: list[str] = []

    if declared_unit:
        issues.append(
            f"This file declares its unit as '{declared_unit}', so it was converted to millimetres."
        )
        recommendations.append(
            "Check one known size (the cabinet height) against the plan. "
            "If it is wrong, export again with the unit set to millimetres."
        )

    if scaled_from_metres:
        issues.append(
            "This file is only a few units across, so it was read as metres and scaled to millimetres."
        )
        recommendations.append(
            "Check the sizes. In Blender set Scene > Units to millimetres, or scale the export by 1000, so the file is in mm."
        )

    if oversize:
        sizes = sorted({(round(b.length), round(b.width), b.thickness) for b in oversize}, reverse=True)
        listed = ", ".join(f"{l} x {w} mm ({t:g} thick)" for l, w, t in sizes[:6])
        issues.append(
            f"{len(oversize)} part(s) are bigger than the sheet and are NOT in the plan: {listed}"
            f"{', and more' if len(sizes) > 6 else ''}."
        )
        recommendations.append(
            "Use a longer sheet, or split these parts in the design (for example a joint on a vertical), "
            "then make the plan again. Check they are not a wrongly scaled or merged shape."
        )

    if extraction.skipped_parts:
        shown = ", ".join(extraction.skipped_parts[:8])
        more = len(extraction.skipped_parts) - 8
        issues.append(
            f"{len(extraction.skipped_parts)} solid part(s) are not flat panels and are not in the cutlist: "
            f"{shown}{f', and {more} more' if more > 0 else ''}."
        )
        recommendations.append(
            "Check the skipped parts above. If one is a real panel, model it as a flat solid of sheet thickness."
        )
    if extraction.inferred_board_count > 0:
        issues.append(
            f"{extraction.inferred_board_count} board(s) were inferred by pairing loose faces, not measured "
            "from a closed solid. Their dimensions are less reliable."
        )
        recommendations.append(
            "Model each panel as its own closed group or component so it is measured directly."
        )
    if auto_materials:
        issues.append(
            f"Parts with a different thickness were nested on their own sheets ({', '.join(auto_materials)}) "
            "using the default sheet size and cost."
        )
        recommendations.append(
            "Add these thicknesses to the materials file to set their real sheet size and cost."
        )

    passes = extraction.confidence >= threshold and board_count > 0

    if extraction.confidence < threshold:
        issues.append(
            f"Extraction confidence {extraction.confidence:.1%} is below the minimum threshold of {threshold:.0%}."
        )
    if board_count == 0:
        issues.append("No manufacturable boards survived filtering.")
        recommendations.append(
            "Verify the model contains real plywood panels with thickness, not just decorative or hollow geometry."
        )
    if discarded_low_confidence > 0:
        issues.append(
            f"{discarded_low_confidence} board(s) were rejected as false positives "
            f"(individual confidence below {min_board_confidence:.0%}). "
            "These are typically mismatched surface pairs from decorative or curved geometry."
        )
        recommendations.append(
            "Separate decorative elements (domes, arches, carvings) from flat panel geometry before export."
        )
    if extraction.unmatched_surface_count > 0:
        issues.append(
            f"{extraction.unmatched_surface_count} planar surfaces could not be paired into boards "
            "(usually means a face is missing its opposite, or thicknesses are inconsistent)."
        )
        recommendations.append(
            "In SketchUp, ensure every panel is a closed solid group with both faces and the correct thickness."
        )
    if discarded_slivers > 0:
        issues.append(
            f"{discarded_slivers} micro-parts smaller than {min_part_dimension:.0f} mm were discarded as mesh noise."
        )
        recommendations.append(
            "Hide hardware, screws, dowels and decorative geometry before export, or model them as separate components."
        )
    if extraction.surface_count > 0 and extraction.board_count / max(extraction.surface_count, 1) < 0.3:
        recommendations.append(
            "Less than 30% of surfaces became boards. Consider exploding curved/decorative meshes that pollute plane clustering."
        )

    if not issues:
        issues.append("No structural issues detected.")
    if not recommendations:
        recommendations.append("Model is clean enough for production cutting.")

    return ModelFixReport(
        confidence=extraction.confidence,
        confidence_threshold=threshold,
        passes_gate=passes,
        issues=tuple(issues),
        recommendations=tuple(recommendations),
        discarded_sliver_count=discarded_slivers,
        sliver_min_dimension=min_part_dimension,
    )


# -----------------------------------------------------------------------------
# JSON loaders for sidecar files (overrides, materials, review)
# -----------------------------------------------------------------------------


def load_overrides(path: Path) -> dict[str, dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_materials(path: Path) -> dict[str, MaterialSpec]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, MaterialSpec] = {}
    for name, spec in raw.items():
        out[name] = MaterialSpec(
            name=name,
            thickness=float(spec.get("thickness", 18.0)),
            sheet_width=float(spec.get("sheet_width", 2440.0)),
            sheet_height=float(spec.get("sheet_height", 1220.0)),
            sheet_cost=float(spec.get("sheet_cost", 55.0)),
            grain_locked_default=bool(spec.get("grain_locked_default", False)),
            currency=str(spec.get("currency", "USD")),
        )
    return out


def load_review(path: Path) -> dict[str, ReviewDecision]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, ReviewDecision] = {}
    for board_id, decision in raw.items():
        out[board_id] = ReviewDecision(
            accepted=bool(decision.get("accepted", True)),
            rename=str(decision.get("rename", "")),
            reason=str(decision.get("reason", "")),
        )
    return out
