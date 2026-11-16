from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .models import Board, NestedPart, NestingStrategyResult, Offcut, SheetLayout, WasteOptimizationReport


@dataclass
class _FreeRect:
    x: float
    y: float
    width: float
    height: float

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass(frozen=True)
class OptimizedLayout:
    sheets: list[SheetLayout]
    report: WasteOptimizationReport


def nest_rectangles(
    boards: list[Board],
    sheet_width: float = 2440.0,
    sheet_height: float = 1220.0,
    kerf: float = 3.0,
) -> list[SheetLayout]:
    return _pack_boards(
        sorted(boards, key=lambda board: board.length * board.width, reverse=True),
        sheet_width=sheet_width,
        sheet_height=sheet_height,
        kerf=kerf,
    )


def optimize_cutting_layout(
    boards: list[Board],
    sheet_width: float = 2440.0,
    sheet_height: float = 1220.0,
    kerf: float = 3.0,
    min_reusable_offcut_width: float = 300.0,
    min_reusable_offcut_height: float = 300.0,
    material: str = "default",
    sheet_cost: float = 0.0,
    currency: str = "USD",
    offcut_stock: tuple[tuple[float, float], ...] = (),
) -> OptimizedLayout:
    """Nest boards, consuming saved offcut stock before full sheets.

    `offcut_stock` entries are (width, height) mm of leftover pieces already in
    the shop. They are treated as free sheets: the packer tries them first and
    picks the piece that places the most board area. Boards that land on an
    offcut carry `is_offcut_stock=True` and cost nothing.
    """
    strategies = _ordering_strategies()
    candidates = []

    for strategy, ordering in strategies.items():
        sheets = _pack_boards(
            sorted(boards, key=ordering, reverse=True),
            sheet_width=sheet_width,
            sheet_height=sheet_height,
            kerf=kerf,
            min_reusable_offcut_width=min_reusable_offcut_width,
            min_reusable_offcut_height=min_reusable_offcut_height,
            material=material,
            sheet_cost=sheet_cost,
            currency=currency,
            offcut_stock=offcut_stock,
        )
        candidates.append((strategy, sheets))

    selected_strategy, selected_sheets = sorted(
        candidates,
        key=lambda item: (
            len(item[1]),
            _waste_percent(item[1]),
            -_reusable_offcut_area(item[1]),
        ),
    )[0]
    strategy_results = tuple(
        NestingStrategyResult(
            strategy=strategy,
            sheet_count=len(sheets),
            waste_percent=round(_waste_percent(sheets), 2),
            utilization_percent=round(100.0 - _waste_percent(sheets), 2),
            reusable_offcut_area=round(_reusable_offcut_area(sheets) / 1_000_000.0, 4),
        )
        for strategy, sheets in candidates
    )
    worst_sheet_count = max(result.sheet_count for result in strategy_results) if strategy_results else 0
    worst_waste = max(result.waste_percent for result in strategy_results) if strategy_results else 0.0
    selected_waste = _waste_percent(selected_sheets)

    return OptimizedLayout(
        sheets=selected_sheets,
        report=WasteOptimizationReport(
            selected_strategy=selected_strategy,
            strategy_results=strategy_results,
            sheet_savings_vs_worst=worst_sheet_count - len(selected_sheets),
            waste_reduction_vs_worst_percent=round(max(0.0, worst_waste - selected_waste), 2),
        ),
    )


def _pack_boards(
    ordered_boards: list[Board],
    sheet_width: float,
    sheet_height: float,
    kerf: float,
    min_reusable_offcut_width: float = 300.0,
    min_reusable_offcut_height: float = 300.0,
    material: str = "default",
    sheet_cost: float = 0.0,
    currency: str = "USD",
    offcut_stock: tuple[tuple[float, float], ...] = (),
) -> list[SheetLayout]:
    remaining = ordered_boards
    sheets: list[SheetLayout] = []
    # Largest offcuts first — they place the most board area.
    stock = sorted(offcut_stock, key=lambda wh: wh[0] * wh[1], reverse=True)

    while remaining:
        parts, used_area, not_placed, free_rects, sheet_w, sheet_h, on_stock = (
            _pack_next_sheet(
                remaining, stock, sheet_width, sheet_height, kerf,
            )
        )
        if not parts:
            oversized = not_placed[0]
            raise ValueError(
                f"{oversized.id} ({oversized.length:.1f}x{oversized.width:.1f}) does not fit "
                f"sheet {sheet_w:.1f}x{sheet_h:.1f}"
            )

        # Cut sequence: top-to-bottom (y), then left-to-right (x) — matches a
        # CNC operator's natural flow and minimises blade re-positioning.
        ordered_parts = tuple(sorted(parts, key=lambda p: (round(p.y, 1), round(p.x, 1))))
        sheets.append(
            SheetLayout(
                sheet_id=len(sheets) + 1,
                width=sheet_w,
                height=sheet_h,
                parts=ordered_parts,
                used_area=used_area,
                offcuts=_build_offcuts(free_rects, min_reusable_offcut_width, min_reusable_offcut_height),
                material=material,
                sheet_cost=0.0 if on_stock else sheet_cost,
                currency=currency,
                is_offcut_stock=on_stock,
            )
        )
        remaining = not_placed

    return sheets


def _pack_next_sheet(
    remaining: list[Board],
    stock: list[tuple[float, float]],
    sheet_width: float,
    sheet_height: float,
    kerf: float,
) -> tuple[list[NestedPart], float, list[Board], list[_FreeRect], float, float, bool]:
    """Pack one sheet. Returns (parts, used_area, not_placed, free_rects,
    sheet_w, sheet_h, on_stock). Consumes the chosen stock piece.

    Saved offcuts are tried first — they are free. The piece that places the
    most board area wins; if none fits anything, they can never help (boards
    only shrink) and are dropped.
    """
    if stock:
        best = None  # (used_area, index, ...)
        for index, (w, h) in enumerate(stock):
            parts, used_area, not_placed, free_rects = _attempt_pack(
                remaining, w, h, kerf,
            )
            if parts and (best is None or used_area > best[0]):
                best = (used_area, index, parts, used_area, not_placed, free_rects, w, h)
        if best is not None:
            _, index, parts, used_area, not_placed, free_rects, w, h = best
            stock.pop(index)
            return parts, used_area, not_placed, free_rects, w, h, True
        stock.clear()  # no offcut fits any remaining board — drop them all

    parts, used_area, not_placed, free_rects = _attempt_pack(
        remaining, sheet_width, sheet_height, kerf,
    )
    return parts, used_area, not_placed, free_rects, sheet_width, sheet_height, False


def _attempt_pack(
    boards: list[Board],
    sheet_width: float,
    sheet_height: float,
    kerf: float,
) -> tuple[list[NestedPart], float, list[Board], list[_FreeRect]]:
    """Try to place boards on a single sheet. Nothing is mutated outside."""
    free_rects = [_FreeRect(0.0, 0.0, sheet_width, sheet_height)]
    parts: list[NestedPart] = []
    used_area = 0.0
    not_placed: list[Board] = []

    for board in boards:
        placement = _place_with_maxrects(board, free_rects, kerf)
        if placement is None:
            not_placed.append(board)
            continue

        x, y, rotation, length, width = placement
        parts.append(
            NestedPart(
                board_id=board.id,
                x=x,
                y=y,
                rotation=rotation,
                length=length,
                width=width,
            )
        )
        used_area += board.length * board.width

    return parts, used_area, not_placed, free_rects


def _place_with_maxrects(
    board: Board,
    free_rects: list[_FreeRect],
    kerf: float,
) -> tuple[float, float, int, float, float] | None:
    candidates = []
    for index, free_rect in enumerate(free_rects):
        for length, width, rotation in _orientations(board):
            packed_width = length + kerf
            packed_height = width + kerf
            if packed_width <= free_rect.width and packed_height <= free_rect.height:
                short_side = min(free_rect.width - packed_width, free_rect.height - packed_height)
                long_side = max(free_rect.width - packed_width, free_rect.height - packed_height)
                area_waste = free_rect.width * free_rect.height - packed_width * packed_height
                candidates.append((short_side, area_waste, long_side, index, free_rect, length, width, rotation))

    if not candidates:
        return None

    _, _, _, index, free_rect, length, width, rotation = sorted(candidates, key=lambda item: (item[0], item[1], item[2]))[0]
    used_width = length + kerf
    used_height = width + kerf
    del free_rects[index]
    free_rects.extend(_split_free_rect(free_rect, used_width, used_height))
    _prune_free_rects(free_rects)
    return free_rect.x, free_rect.y, rotation, length, width


def _orientations(board: Board) -> list[tuple[float, float, int]]:
    if board.grain_locked:
        # Grain runs along the board's length; rotating 90 deg would cross the grain
        # of veneer / laminate stock, which is not acceptable for visible panels.
        return [(board.length, board.width, 0)]
    return [
        (board.length, board.width, 0),
        (board.width, board.length, 90),
    ]


def _split_free_rect(free_rect: _FreeRect, used_width: float, used_height: float) -> list[_FreeRect]:
    right_width = free_rect.width - used_width
    bottom_height = free_rect.height - used_height
    split = []

    if right_width > 0:
        split.append(
            _FreeRect(
                x=free_rect.x + used_width,
                y=free_rect.y,
                width=right_width,
                height=used_height,
            )
        )
    if bottom_height > 0:
        split.append(
            _FreeRect(
                x=free_rect.x,
                y=free_rect.y + used_height,
                width=free_rect.width,
                height=bottom_height,
            )
        )
    return split


def _prune_free_rects(free_rects: list[_FreeRect]) -> None:
    contained = set()
    for first_index, first in enumerate(free_rects):
        for second_index, second in enumerate(free_rects):
            if first_index == second_index:
                continue
            if _contains(second, first):
                contained.add(first_index)
                break

    if contained:
        free_rects[:] = [rect for index, rect in enumerate(free_rects) if index not in contained]


def _contains(outer: _FreeRect, inner: _FreeRect) -> bool:
    return (
        inner.x >= outer.x
        and inner.y >= outer.y
        and inner.x + inner.width <= outer.x + outer.width
        and inner.y + inner.height <= outer.y + outer.height
    )


_PRIORITY_RANK = {"visible": 2, "normal": 1, "hidden": 0}


def _priority_weight(board: Board) -> int:
    return _PRIORITY_RANK.get(board.priority, 1)


def _ordering_strategies() -> dict[str, Callable[[Board], tuple[float, ...]]]:
    # Priority dominates every strategy: visible parts get cleanest sheet area first.
    return {
        "largest_area_first": lambda board: (_priority_weight(board), board.length * board.width, max(board.length, board.width)),
        "longest_edge_first": lambda board: (_priority_weight(board), max(board.length, board.width), board.length * board.width),
        "widest_edge_first":  lambda board: (_priority_weight(board), min(board.length, board.width), board.length * board.width),
        "perimeter_first":    lambda board: (_priority_weight(board), 2 * (board.length + board.width), board.length * board.width),
        "squareness_first":   lambda board: (_priority_weight(board), min(board.length, board.width) / max(board.length, board.width), board.length * board.width),
    }


def _build_offcuts(
    free_rects: list[_FreeRect],
    min_reusable_offcut_width: float,
    min_reusable_offcut_height: float,
) -> tuple[Offcut, ...]:
    offcuts = []
    for rect in free_rects:
        reusable = rect.width >= min_reusable_offcut_width and rect.height >= min_reusable_offcut_height
        offcuts.append(
            Offcut(
                x=rect.x,
                y=rect.y,
                width=rect.width,
                height=rect.height,
                area=rect.area / 1_000_000.0,
                reusable=reusable,
            )
        )
    return tuple(sorted(offcuts, key=lambda offcut: offcut.area, reverse=True))


def _waste_percent(sheets: list[SheetLayout]) -> float:
    sheet_area = sum(sheet.width * sheet.height for sheet in sheets)
    used_area = sum(sheet.used_area for sheet in sheets)
    return ((sheet_area - used_area) / sheet_area * 100.0) if sheet_area else 0.0


def _reusable_offcut_area(sheets: list[SheetLayout]) -> float:
    return sum(offcut.area * 1_000_000.0 for sheet in sheets for offcut in sheet.offcuts if offcut.reusable)
