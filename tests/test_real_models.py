"""Accuracy library: real exporter files with a known, hand-checked cut list.

Each folder under tests/real_models/ holds:
  expected.json   {"thickness": 18, "parts": [{name, length, width, thickness}], "not_panels": [names]}
  model.<ext>     one or more exports of the same design (obj, glb, gltf, dae, stl, dxf)

To add a model: export it from your CAD program, drop it in a new folder, and
write expected.json from the drawing (not from this engine's output).
"""
import json
from pathlib import Path

import pytest

from cutlist_engine.boards import extract_boards
from cutlist_engine.parsers import load_model

LIBRARY = Path(__file__).parent / "real_models"
MODEL_SUFFIXES = {".obj", ".glb", ".gltf", ".dae", ".stl", ".dxf"}
NAMED_FORMATS = {".obj", ".glb", ".gltf", ".dae"}   # STL carries no part names
TOLERANCE_MM = 0.5

CASES = sorted(
    path
    for folder in (LIBRARY.iterdir() if LIBRARY.is_dir() else [])
    if (folder / "expected.json").is_file()
    for path in folder.iterdir()
    if path.suffix.lower() in MODEL_SUFFIXES
)


def _norm(name: str) -> str:
    return name.replace("_", " ").strip().lower()


@pytest.mark.parametrize("model", CASES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_real_model_matches_its_known_cutlist(model: Path):
    expected = json.loads((model.parent / "expected.json").read_text(encoding="utf-8"))

    extraction = extract_boards(load_model(model), expected_thickness=expected.get("thickness", 18))

    want = sorted((p["length"], p["width"], p["thickness"]) for p in expected["parts"])
    got = sorted((b.length, b.width, b.thickness) for b in extraction.boards)
    assert len(got) == len(want), f"expected {len(want)} parts, got {len(got)}: {got}"
    for (gl, gw, gt), (wl, ww, wt) in zip(got, want):
        assert abs(gl - wl) <= TOLERANCE_MM and abs(gw - ww) <= TOLERANCE_MM and gt == wt, (
            f"got {gl} x {gw} x {gt}, expected {wl} x {ww} x {wt}"
        )

    if model.suffix.lower() in NAMED_FORMATS:
        by_name = {_norm(b.source_objects[0]): (b.length, b.width, b.thickness) for b in extraction.boards}
        for part in expected["parts"]:
            dims = by_name.get(_norm(part["name"]))
            assert dims is not None, f"part '{part['name']}' was not found by name"
            assert abs(dims[0] - part["length"]) <= TOLERANCE_MM and abs(dims[1] - part["width"]) <= TOLERANCE_MM
        skipped = " ".join(extraction.report.skipped_parts).lower()
        for name in expected.get("not_panels", []):
            assert _norm(name) in skipped.replace("_", " "), f"'{name}' should be reported as not a panel"

    assert extraction.report.inferred_board_count == 0, "parts should be measured from solids, not guessed"


def test_library_is_not_empty():
    assert CASES, "tests/real_models has no models"
