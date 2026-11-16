"""1D nesting for timber, beading, pipe and profiles."""
import pytest

from cutlist_engine.linear import LinearPiece, nest_linear


def test_pieces_are_packed_with_kerf_between_cuts():
    # 3 x 1000 + 2 kerfs of 3 = 3006 > 3000, so only two fit per bar.
    plan = nest_linear([LinearPiece("rail", 1000, 3)], stock_length=3000, kerf=3)

    assert plan.new_bar_count == 2
    assert [len(bar.cuts) for bar in plan.bars] == [2, 1]
    assert plan.bars[0].remaining == 997


def test_exact_fit_needs_no_kerf_after_the_last_piece():
    plan = nest_linear([LinearPiece("a", 1497, 2)], stock_length=2997, kerf=3)

    assert plan.new_bar_count == 1
    assert plan.bars[0].remaining == 0


def test_best_fit_fills_gaps_and_reports_waste():
    pieces = [LinearPiece("long", 1800, 2), LinearPiece("mid", 1100, 2), LinearPiece("short", 550, 4)]

    plan = nest_linear(pieces, stock_length=3000, kerf=0, stock_cost=400)

    assert plan.new_bar_count == 3  # 8000 mm of pieces cannot fit on fewer than 3 bars
    assert plan.total_cost == 1200
    assert plan.waste_percent == pytest.approx((1 - 8000 / 9000) * 100, abs=0.01)
    assert sum(len(bar.cuts) for bar in plan.bars) == 8
    assert all(bar.used <= bar.stock_length for bar in plan.bars)


def test_saved_leftovers_are_used_before_new_stock_and_cost_nothing():
    plan = nest_linear(
        [LinearPiece("leg", 700, 2)], stock_length=3000, kerf=3, leftovers=(800, 750, 200), stock_cost=500,
    )

    assert plan.new_bar_count == 0
    assert plan.leftover_bar_count == 2
    assert sorted(bar.stock_length for bar in plan.bars) == [750, 800]
    assert plan.total_cost == 0


def test_end_trim_is_taken_off_every_bar():
    plan = nest_linear([LinearPiece("a", 1490, 2)], stock_length=3000, kerf=3, end_trim=20)

    assert plan.new_bar_count == 2  # 20 + 1490 + 3 + 1490 = 3003


def test_reusable_leftovers_are_listed():
    plan = nest_linear([LinearPiece("a", 2000, 1)], stock_length=3000, kerf=3, min_reusable_leftover=300)

    assert plan.reusable_leftovers == (1000,)


def test_piece_longer_than_stock_is_refused_by_name():
    with pytest.raises(ValueError, match="'cornice'"):
        nest_linear([LinearPiece("cornice", 3200, 1)], stock_length=3000)
