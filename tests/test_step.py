"""STEP import. The kernel is optional, so most of this runs only where it is installed."""
from pathlib import Path

import pytest

from cutlist_engine.boards import extract_boards
from cutlist_engine.parsers import load_model
from cutlist_engine.step import step_supported


def test_step_without_kernel_says_how_to_fix_it(tmp_path: Path):
    if step_supported():
        pytest.skip("CAD kernel is installed here")
    path = tmp_path / "cabinet.step"
    path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")

    with pytest.raises(ValueError, match="optional CAD kernel"):
        load_model(path)


def _write_cabinet_step(path: Path) -> None:
    from OCP.BRep import BRep_Builder
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.TopoDS import TopoDS_Compound

    w, d, h, t = 600, 560, 720, 18
    boxes = [
        (0, 0, 0, t, d, h), (w - t, 0, 0, w, d, h),            # sides
        (t, 0, 0, w - t, d, t), (t, 0, h - t, w - t, d, h),    # bottom, top
        (t, 20, 351, w - t, d - 6, 369),                       # shelf
        (t, d - 6, t, w - t, d, h - t),                        # 6 mm back
    ]
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for x0, y0, z0, x1, y1, z1 in boxes:
        builder.Add(compound, BRepPrimAPI_MakeBox(gp_Pnt(x0, y0, z0), gp_Pnt(x1, y1, z1)).Shape())
    # A round handle: must be reported as not a panel.
    builder.Add(compound, BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(300, -40, 400), gp_Dir(1, 0, 0)), 6, 128).Shape())

    writer = STEPControl_Writer()
    writer.Transfer(compound, STEPControl_AsIs)
    writer.Write(str(path))


def test_step_cabinet_is_measured_per_solid(tmp_path: Path):
    pytest.importorskip("OCP")
    path = tmp_path / "cabinet.step"
    _write_cabinet_step(path)

    extraction = extract_boards(load_model(path), expected_thickness=18)

    assert sorted((b.length, b.width, b.thickness) for b in extraction.boards) == sorted([
        (720, 560, 18), (720, 560, 18), (564, 560, 18), (564, 560, 18), (564, 534, 18), (684, 564, 6),
    ])
    assert len(extraction.report.skipped_parts) == 1
    assert extraction.report.inferred_board_count == 0


def test_unreadable_step_is_rejected(tmp_path: Path):
    pytest.importorskip("OCP")
    path = tmp_path / "broken.step"
    path.write_text("this is not a step file", encoding="utf-8")

    with pytest.raises(ValueError):
        load_model(path)
