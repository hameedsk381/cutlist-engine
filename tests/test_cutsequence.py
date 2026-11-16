"""The cut sequence: straight edge-to-edge saw cuts that free every part."""

import random

from cutlist_engine.cutsequence import cut_sequence
from cutlist_engine.models import Board, NestedPart, SheetLayout
from cutlist_engine.nesting import optimize_cutting_layout

KERF = 3.0


def _board(i, length, width):
    return Board(
        id=f"b{i}", length=length, width=width, thickness=18, area=length * width,
        contour=(), source_planes=("a", "b"),
    )


def _sheet(parts, width=2440.0, height=1220.0):
    return SheetLayout(
        sheet_id=1, width=width, height=height,
        parts=tuple(NestedPart(board_id=i, x=x, y=y, rotation=0, length=l, width=w) for i, x, y, l, w in parts),
        used_area=0.0,
    )


def _verify(sheet, result):
    """Replay the cuts: no blade may touch a part, and every part is freed once."""
    assert result["ok"]
    parts = {p.board_id: (p.x, p.y, p.x + p.length, p.y + p.width) for p in sheet.parts}
    freed = []
    for step in result["steps"]:
        x0, y0, x1, y1 = step["line"]
        if step["direction"] == "horizontal":
            blade = (x0, y0, x1, y0 + KERF)
        else:
            blade = (x0, y0, x0 + KERF, y1)
        for pid, (a, b, c, d) in parts.items():
            overlap = min(blade[2], c) - max(blade[0], a) > 1e-6 and min(blade[3], d) - max(blade[1], b) > 1e-6
            assert not overlap, f"step {step['step']} cuts into {pid}"
        freed += step["frees"]
    assert sorted(freed) == sorted(parts) or len(parts) == 1
    assert [s["step"] for s in result["steps"]] == list(range(1, len(result["steps"]) + 1))


def test_two_strips_need_one_cut_across_then_cuts_down_each():
    sheet = _sheet([
        ("a", 0, 0, 1000, 600),
        ("b", 1003, 0, 1000, 600),
        ("c", 0, 603, 2000, 500),
    ], width=2003, height=1103)  # parts fill the sheet, so there is no waste to trim
    result = cut_sequence(sheet, KERF)
    _verify(sheet, result)
    first = result["steps"][0]
    assert first["kind"] == "split" and first["direction"] == "horizontal"
    assert first["position"] == 600 and first["stage"] == 0
    assert first["piece"] == [2003, 1103]


def test_waste_is_trimmed_with_one_cut_for_the_whole_piece():
    # Both strips end at x=2003: one vertical trim, not one per strip.
    sheet = _sheet([("a", 0, 0, 2000, 600), ("b", 0, 603, 2000, 500)])
    result = cut_sequence(sheet, KERF)
    _verify(sheet, result)
    vertical_trims = [s for s in result["steps"] if s["kind"] == "trim" and s["direction"] == "vertical"]
    assert len(vertical_trims) == 1 and vertical_trims[0]["position"] == 2000


def test_single_part_that_fills_the_sheet_needs_no_cuts():
    sheet = _sheet([("a", 0, 0, 2440, 1220)])
    assert cut_sequence(sheet, KERF) == {"ok": True, "steps": []}


def test_pinwheel_is_reported_as_not_cuttable():
    sheet = _sheet(
        [("a", 0, 0, 60, 40), ("b", 60, 0, 40, 60), ("c", 40, 60, 60, 40), ("d", 0, 40, 40, 60)],
        width=100, height=100,
    )
    # Parts touch, so no saw line fits between any two groups.
    assert cut_sequence(sheet, KERF)["ok"] is False


def test_every_sheet_the_nester_makes_can_be_cut_and_replayed():
    random.seed(11)
    lengths = [300, 450, 564, 600, 720, 900, 1200, 1800, 2100]
    widths = [300, 350, 450, 560, 600, 720]
    sheets_checked = 0
    for _ in range(25):
        boards = [_board(i, random.choice(lengths), random.choice(widths)) for i in range(random.randint(8, 40))]
        layout = optimize_cutting_layout(boards, 2440, 1220, KERF)
        for sheet in layout.sheets:
            _verify(sheet, cut_sequence(sheet, KERF))
            sheets_checked += 1
    assert sheets_checked > 25


def test_the_serialised_sheet_carries_its_cuts():
    from cutlist_engine.furniture import describe_to_model
    from cutlist_engine.parsers import load_model
    from cutlist_engine.pipeline import ProcessConfig, process_triangles
    from cutlist_engine.server import _serialize_result
    import tempfile
    from pathlib import Path

    obj = describe_to_model("Kitchen base unit 720 high, 600 wide, 560 deep, 1 shelf, 1 shutter")["obj"]
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "m.obj"
        path.write_text(obj)
        result = process_triangles(load_model(path), ProcessConfig(kerf=4.0))
    payload = _serialize_result(result)
    assert payload["sheets"]
    for sheet in payload["sheets"]:
        assert sheet["cuts"]["ok"]
        assert all(step["kerf"] == 4.0 for step in sheet["cuts"]["steps"])


def test_report_json_carries_the_cuts(tmp_path):
    """The web app reads report.json, so the cuts must be in it."""
    import json

    from cutlist_engine.furniture import describe_to_model
    from cutlist_engine.outputs import write_json_report
    from cutlist_engine.parsers import load_model
    from cutlist_engine.pipeline import ProcessConfig, process_triangles

    model = tmp_path / "m.obj"
    model.write_text(describe_to_model("Wardrobe 2100 high, 900 wide, 550 deep, 3 shelves, 2 doors")["obj"])
    result = process_triangles(load_model(model), ProcessConfig(kerf=3.0))
    report = tmp_path / "report.json"
    write_json_report(report, result.boards, result.cutlist, result.sheets, kerf=result.kerf)
    sheets = json.loads(report.read_text(encoding="utf-8"))["sheets"]
    assert sheets and all(s["cuts"]["ok"] for s in sheets)
    write_json_report(report, result.boards, result.cutlist, result.sheets)  # old callers: no cuts, no crash
    assert "cuts" not in json.loads(report.read_text(encoding="utf-8"))["sheets"][0]
