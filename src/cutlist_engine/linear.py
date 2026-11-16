"""1D (linear) nesting: cut a list of lengths from stock bars.

For timber, beading, edge profiles, pipe and aluminium sections. Uses
best-fit decreasing, which is fast and within a bar or two of optimal for
workshop-sized jobs. Saved leftover lengths are used before new stock.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LinearPiece:
    label: str
    length: float
    quantity: int = 1


@dataclass
class LinearBar:
    bar_id: int
    stock_length: float
    is_leftover: bool = False
    cuts: list[tuple[str, float]] = field(default_factory=list)
    used: float = 0.0   # piece lengths plus the kerf between them

    @property
    def remaining(self) -> float:
        return max(0.0, self.stock_length - self.used)


@dataclass(frozen=True)
class LinearPlan:
    bars: tuple[LinearBar, ...]
    new_bar_count: int
    leftover_bar_count: int
    total_piece_length: float
    total_stock_length: float
    waste_percent: float
    total_cost: float
    reusable_leftovers: tuple[float, ...]


def nest_linear(
    pieces: list[LinearPiece],
    stock_length: float,
    kerf: float = 3.0,
    end_trim: float = 0.0,
    leftovers: tuple[float, ...] = (),
    stock_cost: float = 0.0,
    min_reusable_leftover: float = 300.0,
) -> LinearPlan:
    """Pack pieces onto bars.

    `end_trim` is removed once from every bar (squaring the factory end).
    `leftovers` are lengths already on the shelf; they are tried before new
    stock and cost nothing. Raises ValueError if a piece cannot fit any bar.
    """
    if stock_length <= 0:
        raise ValueError("Stock length must be positive.")
    if kerf < 0 or end_trim < 0:
        raise ValueError("Kerf and end trim cannot be negative.")

    lengths: list[tuple[str, float]] = []
    for piece in pieces:
        if piece.length <= 0 or piece.quantity < 0:
            raise ValueError(f"'{piece.label}' needs a positive length and quantity.")
        lengths.extend((piece.label, piece.length) for _ in range(piece.quantity))
    lengths.sort(key=lambda item: item[1], reverse=True)

    usable_new = stock_length - end_trim
    longest_available = max([usable_new, *[length - end_trim for length in leftovers]])
    for label, length in lengths:
        if length > longest_available + 1e-9:
            raise ValueError(
                f"'{label}' is {length:g} mm, longer than the {longest_available:g} mm usable on a bar."
            )

    shelf = sorted(leftovers)
    bars: list[LinearBar] = []

    def fits(bar: LinearBar, length: float) -> bool:
        extra = length + (kerf if bar.cuts else 0.0)
        return bar.used + extra <= bar.stock_length + 1e-9

    def place(bar: LinearBar, label: str, length: float) -> None:
        bar.used += length + (kerf if bar.cuts else 0.0)
        bar.cuts.append((label, length))

    def open_bar(length: float, is_leftover: bool) -> LinearBar:
        bar = LinearBar(bar_id=len(bars) + 1, stock_length=length, is_leftover=is_leftover, used=end_trim)
        bars.append(bar)
        return bar

    for label, length in lengths:
        # Best fit: the open bar this piece leaves the least space on.
        candidates = [bar for bar in bars if fits(bar, length)]
        if candidates:
            place(min(candidates, key=lambda bar: bar.remaining), label, length)
            continue
        # Otherwise the shortest shelf leftover that takes it, then new stock.
        shelf_fit = next((s for s in shelf if s - end_trim >= length - 1e-9), None)
        if shelf_fit is not None:
            shelf.remove(shelf_fit)
            place(open_bar(shelf_fit, True), label, length)
        else:
            place(open_bar(stock_length, False), label, length)

    total_piece = sum(length for _, length in lengths)
    total_stock = sum(bar.stock_length for bar in bars)
    new_bars = sum(1 for bar in bars if not bar.is_leftover)
    return LinearPlan(
        bars=tuple(bars),
        new_bar_count=new_bars,
        leftover_bar_count=len(bars) - new_bars,
        total_piece_length=total_piece,
        total_stock_length=total_stock,
        waste_percent=round((1 - total_piece / total_stock) * 100.0, 2) if total_stock else 0.0,
        total_cost=round(new_bars * stock_cost, 2),
        reusable_leftovers=tuple(
            sorted((round(bar.remaining, 1) for bar in bars if bar.remaining >= min_reusable_leftover), reverse=True)
        ),
    )


def plan_payload(plan: LinearPlan) -> dict:
    return {
        "bars": [
            {
                "bar_id": bar.bar_id,
                "stock_length": bar.stock_length,
                "is_leftover": bar.is_leftover,
                "cuts": [{"label": label, "length": length} for label, length in bar.cuts],
                "remaining": round(bar.remaining, 1),
            }
            for bar in plan.bars
        ],
        "new_bar_count": plan.new_bar_count,
        "leftover_bar_count": plan.leftover_bar_count,
        "total_piece_length": plan.total_piece_length,
        "total_stock_length": plan.total_stock_length,
        "waste_percent": plan.waste_percent,
        "total_cost": plan.total_cost,
        "reusable_leftovers": list(plan.reusable_leftovers),
    }


def plan_from_payload(payload: dict) -> dict:
    """Validate a JSON request body and return the plan payload.

    Raises ValueError with a message that is safe to show the user.
    """
    raw_pieces = payload.get("pieces")
    if not isinstance(raw_pieces, list) or not raw_pieces:
        raise ValueError("Add at least one piece to cut.")
    if len(raw_pieces) > 2000:
        raise ValueError("Too many piece rows (limit 2000).")
    try:
        pieces = [
            LinearPiece(
                label=str(item.get("label") or f"Piece {index}"),
                length=float(item["length"]),
                quantity=int(item.get("quantity", 1)),
            )
            for index, item in enumerate(raw_pieces, start=1)
        ]
        if sum(piece.quantity for piece in pieces) > 20000:
            raise ValueError("Too many pieces (limit 20000).")
        plan = nest_linear(
            pieces,
            stock_length=float(payload.get("stock_length", 0)),
            kerf=float(payload.get("kerf", 3.0)),
            end_trim=float(payload.get("end_trim", 0.0)),
            leftovers=tuple(float(v) for v in payload.get("leftovers", []) or []),
            stock_cost=float(payload.get("stock_cost", 0.0)),
            min_reusable_leftover=float(payload.get("min_reusable_leftover", 300.0)),
        )
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Each piece needs a numeric length.") from exc
    return plan_payload(plan)
