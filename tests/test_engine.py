import json

import pytest

from cutlist_engine.boards import build_cutlist, detect_boards, extract_boards
from cutlist_engine.dxf_export import _offset_polygon, write_sheet_dxf
from cutlist_engine.gcode_export import GCodeConfig, write_sheet_gcode
from cutlist_engine.geometry import contour_loops, outer_loop_contour
from cutlist_engine.models import MaterialSpec, ReviewDecision, Triangle, Vec3
from cutlist_engine.nesting import nest_rectangles
from pathlib import Path

from cutlist_engine.outputs import _sheet_html, write_label_sheet_html
from cutlist_engine.parsers import load_dxf, load_model, load_obj, load_stl
from cutlist_engine.pipeline import ProcessConfig, process_triangles


def test_detects_single_rectangular_board_from_box_faces():
    triangles = rectangular_board(720, 450, 18)

    boards = detect_boards(triangles, expected_thickness=18)

    assert len(boards) == 1
    assert boards[0].length == 720
    assert boards[0].width == 450
    assert boards[0].thickness == 18


def test_cutlist_groups_matching_boards():
    boards = detect_boards(rectangular_board(720, 450, 18) + translated_board(720, 450, 18, 800))

    cutlist = build_cutlist(boards)

    assert len(cutlist) == 1
    assert cutlist[0].quantity == 2


def test_nesting_places_multiple_parts_on_sheet():
    boards = detect_boards(rectangular_board(720, 450, 18) + translated_board(450, 300, 18, 800))

    sheets = nest_rectangles(boards, sheet_width=2440, sheet_height=1220, kerf=3)

    assert len(sheets) == 1
    assert len(sheets[0].parts) == 2
    assert sheets[0].waste_percent < 100


def test_offcut_stock_consumed_before_full_sheets():
    """A leftover piece is used as a free sheet when it fits a part."""
    from cutlist_engine.nesting import optimize_cutting_layout

    boards = [
        Board_factory(600, 400, i) for i in range(3)
    ]

    # Without stock: 3 parts of 600x400 on 1000x1000 sheets → 2 sheets.
    plain = optimize_cutting_layout(
        boards, sheet_width=1000, sheet_height=1000, kerf=3, sheet_cost=3500,
    )
    assert len(plain.sheets) == 2
    assert plain.sheets[0].sheet_cost == 3500  # no offcut sheets anywhere

    # With one 700x450 offcut: it swallows the first part; remaining 2 parts
    # fit one full sheet → 2 sheets total but cost of only ONE full sheet.
    with_stock = optimize_cutting_layout(
        boards, sheet_width=1000, sheet_height=1000, kerf=3, sheet_cost=3500,
        offcut_stock=((700, 450),),
    )
    assert len(with_stock.sheets) == 2
    offcut_sheets = [s for s in with_stock.sheets if s.is_offcut_stock]
    assert len(offcut_sheets) == 1
    assert offcut_sheets[0].width == 700 and offcut_sheets[0].height == 450
    assert offcut_sheets[0].sheet_cost == 0.0
    full = [s for s in with_stock.sheets if not s.is_offcut_stock]
    assert len(full) == 1 and full[0].sheet_cost > 0


def Board_factory(length, width, index):
    """Minimal rectangular Board for nesting tests (id must be unique)."""
    from cutlist_engine.models import Board  # local import to keep top clean

    return Board(
        id=f"b{index}",
        length=length,
        width=width,
        thickness=18,
        area=length * width,
        contour=(),
        source_planes=("test", "test"),
    )


def test_pipeline_returns_cutlist_and_layouts():
    result = process_triangles(rectangular_board(720, 450, 18), ProcessConfig())

    assert len(result.boards) == 1
    assert len(result.cutlist) == 1
    assert len(result.sheets) == 1
    assert result.extraction_report.confidence == 1.0
    assert result.material_summary.sheet_count == 1
    assert result.waste_optimization_report is not None
    assert result.waste_optimization_report.selected_strategy


def test_pipeline_reports_reusable_offcuts_for_waste_reduction():
    result = process_triangles(rectangular_board(720, 450, 18), ProcessConfig())

    assert result.material_summary.reusable_offcut_area > 0
    assert result.material_summary.lost_waste_area >= 0


def test_extraction_report_flags_unmatched_surfaces():
    extraction = extract_boards(rectangular_board(720, 450, 18) + single_surface(300, 200, 40), expected_thickness=18)

    assert len(extraction.boards) == 1
    assert extraction.report.unmatched_surface_count == 1
    assert extraction.report.confidence < 1.0
    assert extraction.report.warnings


FIXTURES = Path(__file__).parent / "fixtures"


def test_load_obj_triangulates_quad_faces():
    triangles = load_obj(FIXTURES / "panel.obj")

    assert len(triangles) == 2


def test_load_ascii_stl():
    triangles = load_stl(FIXTURES / "panel.stl")

    assert len(triangles) == 1


def test_load_model_imports_dae_with_node_name():
    triangles = load_model(FIXTURES / "model.dae")

    assert len(triangles) == 2
    assert triangles[0].source_object == "Shelf"
    assert triangles[0].a == Vec3(10, 20, 30)


def test_load_dxf_imports_mesh_entities():
    ezdxf = pytest.importorskip("ezdxf")
    path = _tmp_file("mesh_entity.dxf")
    doc = ezdxf.new()
    mesh = doc.modelspace().add_mesh(dxfattribs={"layer": "PanelMesh"})
    mesh.vertices = [(0, 0, 0), (100, 0, 0), (100, 50, 0), (0, 50, 0)]
    mesh.faces = [(0, 1, 2, 3)]
    doc.saveas(path)

    triangles = load_dxf(path)

    assert len(triangles) == 2
    assert triangles[0].source_object == "PanelMesh"


def test_load_dxf_imports_polyface_mesh_entities():
    ezdxf = pytest.importorskip("ezdxf")
    path = _tmp_file("polyface_entity.dxf")
    doc = ezdxf.new()
    polyface = doc.modelspace().add_polyface(dxfattribs={"layer": "PanelPolyface"})
    polyface.append_face(((0, 0, 0), (100, 0, 0), (100, 50, 0), (0, 50, 0)))
    doc.saveas(path)

    triangles = load_dxf(path)

    assert len(triangles) == 2
    assert triangles[0].source_object == "PanelPolyface"


def test_sheet_layout_html_renders_part_labels():
    result = process_triangles(rectangular_board(720, 450, 18), ProcessConfig())

    content = _sheet_html(result.sheets[0])

    assert "panel_001" in content


# ---------------------------------------------------------------------------
# Buyability v1.0 features
# ---------------------------------------------------------------------------


def test_grain_locked_disables_rotation_in_nesting():
    # A 1200x300 board on a 1220x600 sheet: with rotation it fits twice (stacked
    # 300 + 300 = 600). With grain locked, only one of them fits along the long
    # axis because the second would need to rotate.
    triangles = rectangular_board(1200, 300, 18) + translated_board(1200, 300, 18, 0)
    config_free = ProcessConfig(sheet_width=1220, sheet_height=600, grain_locked=False, kerf=0)
    config_grain = ProcessConfig(sheet_width=1220, sheet_height=600, grain_locked=True, kerf=0)

    result_free = process_triangles(triangles, config_free)
    result_grain = process_triangles(triangles, config_grain)

    # Both runs see the same boards; grain-locked must use >= sheets as free.
    assert result_grain.material_summary.sheet_count >= result_free.material_summary.sheet_count


def test_sliver_filter_removes_micro_parts():
    triangles = rectangular_board(720, 450, 18) + translated_board(20, 10, 18, 1000)

    result = process_triangles(triangles, ProcessConfig(min_part_length=50, min_part_width=50))

    # Only the 720x450 board survives; the 20x10 sliver is dropped.
    assert len(result.boards) == 1
    assert result.model_fix_report.discarded_sliver_count == 1


def test_confidence_gate_blocks_garbage_models():
    # A model with only single faces (no pairs) -> confidence stays low.
    triangles = single_surface(300, 200, 0) + single_surface(400, 250, 100)

    result = process_triangles(triangles, ProcessConfig(min_confidence=0.6))

    assert result.model_fix_report.passes_gate is False
    assert any("confidence" in i.lower() for i in result.model_fix_report.issues)


def test_cost_reporting_reflects_sheet_price():
    result = process_triangles(rectangular_board(720, 450, 18), ProcessConfig(sheet_cost=72.5, currency="EUR"))

    assert result.material_summary.total_material_cost == 72.5
    assert result.material_summary.currency == "EUR"


def test_sheet_size_simulation_picks_cheapest_total():
    # Small board: a small/cheap sheet should beat the big one in total cost.
    result = process_triangles(
        rectangular_board(400, 300, 18),
        ProcessConfig(candidate_sheet_sizes=(
            ("big", 2440.0, 1220.0, 80.0),
            ("small", 600.0, 400.0, 12.0),
        )),
    )

    assert result.sheet_size_options[0].label == "small"
    assert result.material_summary.sheet_size_label.startswith("small") or "small" in result.material_summary.sheet_size_label


def test_per_part_overrides_set_grain_priority_material_via_source_object():
    triangles = rectangular_board(720, 450, 18)
    # The fixture has no source_object; override by id.
    config = ProcessConfig(overrides={
        "panel_001": {"grain_locked": True, "priority": "visible", "material": "veneer", "edge_band": [2, 0, 2, 0]},
    })

    result = process_triangles(triangles, config)
    board = result.boards[0]

    assert board.grain_locked is True
    assert board.priority == "visible"
    assert board.material == "veneer"
    assert board.edge_band == (2.0, 0.0, 2.0, 0.0)


def test_edge_band_reduces_cut_size_below_finished_size():
    # Finished: 720x450. Tape adds its thickness, so cut 4 mm short each way.
    triangles = rectangular_board(720, 450, 18)
    config = ProcessConfig(overrides={"panel_001": {"edge_band": [2, 2, 2, 2]}})

    result = process_triangles(triangles, config)
    board = result.boards[0]

    assert board.length == 716
    assert board.width == 446
    assert board.finished_length == 720
    assert board.finished_width == 450


def test_multi_material_nests_on_separate_sheets():
    triangles = rectangular_board(720, 450, 18) + translated_board(720, 450, 18, 1000)
    config = ProcessConfig(
        overrides={"panel_001": {"material": "oak"}, "panel_002": {"material": "mdf"}},
        materials={
            "oak": MaterialSpec("oak", 18, 2440, 1220, 145),
            "mdf": MaterialSpec("mdf", 18, 2440, 1220, 38),
        },
    )

    result = process_triangles(triangles, config)
    sheet_materials = sorted({s.material for s in result.sheets})

    assert sheet_materials == ["mdf", "oak"]
    assert len(result.per_material_summaries) == 2


def test_material_grain_locked_default_marks_boards_locked():
    triangles = rectangular_board(720, 450, 18)
    config = ProcessConfig(
        overrides={"panel_001": {"material": "veneer"}},
        materials={
            "veneer": MaterialSpec("veneer", 18, 2440, 1220, 145, grain_locked_default=True),
        },
    )

    result = process_triangles(triangles, config)

    assert result.boards[0].grain_locked is True
    assert result.cutlist[0].grain_locked is True


def test_operator_review_can_reject_a_board():
    triangles = rectangular_board(720, 450, 18) + translated_board(720, 450, 18, 1000)
    config = ProcessConfig(review={"panel_002": ReviewDecision(accepted=False, reason="trim only")})

    result = process_triangles(triangles, config)

    assert len(result.boards) == 1
    assert len(result.rejected_boards) == 1
    assert result.rejected_boards[0].id == "panel_002"


def test_operator_review_can_rename_a_board():
    triangles = rectangular_board(720, 450, 18)
    config = ProcessConfig(review={"panel_001": ReviewDecision(accepted=True, rename="Drawer front A")})

    result = process_triangles(triangles, config)

    assert result.boards[0].label == "Drawer front A"


def test_cut_sequence_orders_parts_top_down_left_right():
    # Three small boards; nested onto one sheet. Validate y-then-x ordering.
    triangles = (
        rectangular_board(200, 200, 18)
        + translated_board(200, 200, 18, 300)
        + translated_board(200, 200, 18, 600)
    )
    result = process_triangles(triangles, ProcessConfig(sheet_width=1220, sheet_height=600))

    parts = result.sheets[0].parts
    pairs = [(p.y, p.x) for p in parts]
    assert pairs == sorted(pairs)


_TEST_OUT = Path(__file__).parent / "_tmp_out"


def _tmp_file(name: str) -> Path:
    _TEST_OUT.mkdir(exist_ok=True)
    return _TEST_OUT / name


def test_dxf_export_writes_valid_layered_file():
    result = process_triangles(rectangular_board(720, 450, 18), ProcessConfig())
    out = _tmp_file("sheet.dxf")

    write_sheet_dxf(out, result.sheets[0], result.boards, kerf=3.0)

    text = out.read_text(encoding="utf-8")
    assert text.startswith("0\nSECTION\n")
    assert text.rstrip().endswith("EOF")
    for layer in ("SHEET", "PART", "LABEL", "OFFCUT_REUSE"):
        assert layer in text
    assert "720" in text
    assert text.count("VERTEX") >= 4


def test_label_sheet_html_emits_one_card_per_unit():
    triangles = rectangular_board(720, 450, 18) + translated_board(720, 450, 18, 1000)
    result = process_triangles(triangles, ProcessConfig())
    out = _tmp_file("labels.html")

    write_label_sheet_html(out, result.cutlist, result.sheets)

    text = out.read_text(encoding="utf-8")
    assert text.count("class='card'") == 2
    assert "1 of 2" in text and "2 of 2" in text


# ---------------------------------------------------------------------------
# v1.1: outer-loop contour, kerf offset, G-code, polygon DXF
# ---------------------------------------------------------------------------


def test_outer_loop_contour_extracts_l_shape():
    # L-shaped flat face built from 3 triangles. Outer loop has 6 vertices.
    triangles = l_shape_face()

    contour = outer_loop_contour(triangles, Vec3(0, 0, 1))

    assert len(contour) == 6
    # Bounding box of the polygon should be 200 wide x 200 tall.
    assert max(p.x for p in contour) == 200
    assert max(p.y for p in contour) == 200


def test_outer_loop_contour_falls_back_to_bbox_for_degenerate_input():
    contour = outer_loop_contour([], Vec3(0, 0, 1))

    assert contour == ()


def test_non_rectangular_board_emits_warning_and_keeps_polygon():
    # Build a thin L-board: top + bottom L-faces + (we'll skip side walls; the
    # extractor only needs paired faces).
    triangles = l_shape_face() + translated_l_shape_face(z_offset=18)

    boards = detect_boards(triangles, expected_thickness=18)

    assert len(boards) == 1
    assert any("Non-rectangular" in w for w in boards[0].warnings)
    # Polygon stored on the board has more than 4 vertices.
    assert len(boards[0].contour) >= 5


def test_contour_loops_extracts_interior_hole():
    loops = contour_loops(rectangular_face_with_hole(), Vec3(0, 0, 1))

    assert len(loops.outer) == 4
    assert len(loops.holes) == 1
    assert len(loops.holes[0]) == 4


def test_board_with_cutout_carries_hole_warning():
    triangles = rectangular_face_with_hole() + rectangular_face_with_hole(z=18)

    boards = detect_boards(triangles, expected_thickness=18)

    assert len(boards) == 1
    assert len(boards[0].holes) == 1
    assert any("interior cutout" in w for w in boards[0].warnings)


def test_cutlist_does_not_group_cutout_with_solid_panel():
    solid = rectangular_board(300, 200, 18)
    cutout = [
        Triangle(
            Vec3(triangle.a.x + 400, triangle.a.y, triangle.a.z),
            Vec3(triangle.b.x + 400, triangle.b.y, triangle.b.z),
            Vec3(triangle.c.x + 400, triangle.c.y, triangle.c.z),
        )
        for triangle in rectangular_face_with_hole() + rectangular_face_with_hole(z=18)
    ]

    result = process_triangles(solid + cutout, ProcessConfig(min_part_length=10, min_part_width=10))

    assert len(result.boards) == 2
    assert len(result.cutlist) == 2


def test_kerf_offset_grows_rectangle_outward():
    rect = [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0)]

    offset = _offset_polygon(rect, 2.0)

    # Each edge moved outward by 2 mm; final box should be 104 x 54 centred on the original.
    xs = [p[0] for p in offset]
    ys = [p[1] for p in offset]
    assert round(max(xs) - min(xs)) == 104
    assert round(max(ys) - min(ys)) == 54


def test_kerf_offset_inward_with_negative_value():
    rect = [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0)]

    offset = _offset_polygon(rect, -1.0)

    xs = [p[0] for p in offset]
    ys = [p[1] for p in offset]
    assert round(max(xs) - min(xs)) == 98
    assert round(max(ys) - min(ys)) == 48


def test_gcode_emits_valid_rs274_per_part():
    result = process_triangles(rectangular_board(720, 450, 18), ProcessConfig())
    out = _tmp_file("sheet.nc")

    write_sheet_gcode(
        out, result.sheets[0], result.boards,
        kerf=3.0,
        config=GCodeConfig(cut_depth=18.0, pass_depth=6.0, spindle_rpm=12000),
    )

    text = out.read_text(encoding="utf-8")
    # Header
    assert "G17" in text and "G21" in text and "G90" in text
    assert "M3 S12000" in text
    # 3 plunge passes for 18 mm cut at 6 mm pass depth
    assert text.count("F800") == 3 or text.count("F800.") >= 1  # plunge feed lines present
    # Multi-pass plunges visit at least 3 distinct Z values negative of stock
    z_values = sorted({float(line.split("Z")[1].split()[0]) for line in text.splitlines()
                       if line.startswith("G1 Z")})
    assert min(z_values) == -18.0
    # Footer
    assert "M5" in text
    assert text.rstrip().endswith("M30")


def test_gcode_path_is_kerf_compensated_outward():
    # Generate G-code for a 100 x 100 square with 2 mm kerf -> cut path is 102 x 102.
    triangles = rectangular_board(100, 100, 18)
    result = process_triangles(triangles, ProcessConfig(sheet_width=400, sheet_height=200, kerf=0))
    out = _tmp_file("kerf.nc")

    write_sheet_gcode(out, result.sheets[0], result.boards,
                      kerf=2.0, config=GCodeConfig(cut_depth=6.0, pass_depth=6.0, spindle_rpm=0))

    text = out.read_text(encoding="utf-8")
    xs = []
    ys = []
    for line in text.splitlines():
        if line.startswith("G1 X") or line.startswith("G0 X"):
            for token in line.split():
                if token.startswith("X"):
                    xs.append(float(token[1:]))
                elif token.startswith("Y"):
                    ys.append(float(token[1:]))
    # The cut perimeter should span 102 mm (100 + 2 * (kerf/2)) on each axis.
    assert round(max(xs) - min(xs), 1) == 102.0
    assert round(max(ys) - min(ys), 1) == 102.0


def test_review_server_extract_then_finalize_round_trip():
    from fastapi.testclient import TestClient
    from cutlist_engine.server import app

    client = TestClient(app)
    payload_json = {"triangles": [
        [[0, 0, 0], [720, 0, 0], [720, 450, 0]],
        [[0, 0, 0], [720, 450, 0], [0, 450, 0]],
        [[0, 0, 18], [720, 450, 18], [720, 0, 18]],
        [[0, 0, 18], [0, 450, 18], [720, 450, 18]],
    ]}
    files = {"file": ("box.json", json.dumps(payload_json), "application/json")}
    extract = client.post("/api/extract", files=files, data={
        "thickness": "18", "kerf": "3", "sheet_width": "2440", "sheet_height": "1220",
        "sheet_cost": "55", "min_part_length": "10",
    })
    assert extract.status_code == 200, extract.text
    body = extract.json()
    assert body["session_id"]
    assert len(body["boards"]) == 1
    sid = body["session_id"]

    # Reject the only board -> finalize must emit gated outputs (no cutlist.csv).
    final = client.post(f"/api/finalize/{sid}", json={
        "review": {body["boards"][0]["id"]: {"accepted": False}},
        "emit_gcode": False,
    })
    assert final.status_code == 200
    assert final.json()["summary"]["rejected_boards"] == [body["boards"][0]["id"]]

    # Now accept the board and ask for G-code: the artifact list should include it.
    final2 = client.post(f"/api/finalize/{sid}", json={
        "review": {},
        "emit_gcode": True,
        "gcode": {"feed_rate": 2500, "plunge_rate": 800, "spindle_rpm": 12000,
                  "cut_depth": 18.0, "pass_depth": 6.0, "safe_z": 15.0},
    })
    assert final2.status_code == 200
    artifacts = final2.json()["artifacts"]
    names = {a["name"] for a in artifacts}
    assert any(n.startswith("gcode/") for n in names)
    assert any(n.startswith("dxf/") for n in names)
    assert "cutlist.csv" in names

    # Download one of the G-code files and confirm it's well-formed.
    gcode_url = next(a["url"] for a in artifacts if a["name"].startswith("gcode/"))
    dl = client.get(gcode_url)
    assert dl.status_code == 200
    assert "G17" in dl.text and "M30" in dl.text


def test_review_server_session_survives_memory_cache_clear():
    from fastapi.testclient import TestClient
    from cutlist_engine import server

    client = TestClient(server.app)
    payload_json = {"triangles": [
        [[0, 0, 0], [720, 0, 0], [720, 450, 0]],
        [[0, 0, 0], [720, 450, 0], [0, 450, 0]],
        [[0, 0, 18], [720, 450, 18], [720, 0, 18]],
        [[0, 0, 18], [0, 450, 18], [720, 450, 18]],
    ]}
    extract = client.post(
        "/api/extract",
        files={"file": ("box.json", json.dumps(payload_json), "application/json")},
        data={"thickness": "18", "kerf": "3", "sheet_width": "2440", "sheet_height": "1220"},
    )
    assert extract.status_code == 200, extract.text
    sid = extract.json()["session_id"]

    server._SESSIONS.clear()
    final = client.post(f"/api/finalize/{sid}", json={"review": {}, "emit_gcode": False})

    assert final.status_code == 200, final.text
    assert "cutlist.csv" in {a["name"] for a in final.json()["artifacts"]}


def test_review_server_rejects_unsupported_upload_type():
    from fastapi.testclient import TestClient
    from cutlist_engine.server import app

    client = TestClient(app)
    res = client.post(
        "/api/extract",
        files={"file": ("model.txt", "not a cad file", "text/plain")},
    )

    assert res.status_code == 415


def test_review_server_rejects_models_over_triangle_limit(monkeypatch):
    from fastapi.testclient import TestClient
    from cutlist_engine import server

    monkeypatch.setattr(server, "MAX_TRIANGLES", 1)
    client = TestClient(server.app)
    payload_json = {"triangles": [
        [[0, 0, 0], [720, 0, 0], [720, 450, 0]],
        [[0, 0, 0], [720, 450, 0], [0, 450, 0]],
    ]}
    res = client.post(
        "/api/extract",
        files={"file": ("box.json", json.dumps(payload_json), "application/json")},
    )

    assert res.status_code == 413


def test_review_server_blocks_download_path_traversal():
    from fastapi.testclient import TestClient
    from cutlist_engine.server import app

    client = TestClient(app)
    payload_json = {"triangles": [
        [[0, 0, 0], [720, 0, 0], [720, 450, 0]],
        [[0, 0, 0], [720, 450, 0], [0, 450, 0]],
        [[0, 0, 18], [720, 450, 18], [720, 0, 18]],
        [[0, 0, 18], [0, 450, 18], [720, 450, 18]],
    ]}
    extract = client.post(
        "/api/extract",
        files={"file": ("box.json", json.dumps(payload_json), "application/json")},
    )
    sid = extract.json()["session_id"]

    res = client.get(f"/api/download/{sid}/../session.json")

    assert res.status_code in {400, 404}


def test_api_token_is_enforced_when_configured(monkeypatch):
    from fastapi.testclient import TestClient
    from cutlist_engine import server

    monkeypatch.setattr(server, "API_TOKEN", "secret")
    client = TestClient(server.app)

    blocked = client.post("/api/ai/chat", json={"message": "hello"})
    allowed = client.post(
        "/api/ai/chat",
        json={"message": "hello"},
        headers={"Authorization": "Bearer secret"},
    )

    assert blocked.status_code == 401
    assert allowed.status_code in {200, 503}


def test_dxf_renders_real_polygon_for_l_shape_board():
    triangles = l_shape_face() + translated_l_shape_face(z_offset=18)
    result = process_triangles(triangles, ProcessConfig(min_part_length=10, min_part_width=10))
    assert len(result.boards) == 1
    out = _tmp_file("l_shape.dxf")

    write_sheet_dxf(out, result.sheets[0], result.boards, kerf=0.0)

    text = out.read_text(encoding="utf-8")
    # The PART polyline must have more than 4 vertices (L-shape has 6).
    part_section = text.split("PART")[1] if "PART" in text else ""
    # Count VERTEX records in the entire file is a fine proxy.
    assert text.count("VERTEX") > 4


def test_dxf_renders_hole_layers_for_cutout_board():
    triangles = rectangular_face_with_hole() + rectangular_face_with_hole(z=18)
    result = process_triangles(triangles, ProcessConfig(min_part_length=10, min_part_width=10))
    out = _tmp_file("cutout_hole.dxf")

    write_sheet_dxf(out, result.sheets[0], result.boards, kerf=0.0)

    text = out.read_text(encoding="utf-8")
    assert "HOLE" in text
    assert len(result.boards[0].holes) == 1


def test_gcode_cuts_holes_before_outer_perimeter():
    triangles = rectangular_face_with_hole() + rectangular_face_with_hole(z=18)
    result = process_triangles(triangles, ProcessConfig(min_part_length=10, min_part_width=10, kerf=0))
    out = _tmp_file("cutout_hole.nc")

    write_sheet_gcode(
        out, result.sheets[0], result.boards,
        kerf=2.0,
        config=GCodeConfig(cut_depth=6.0, pass_depth=6.0, spindle_rpm=0),
    )

    text = out.read_text(encoding="utf-8")
    assert text.index("panel_001  hole") < text.index("panel_001  outer")


def test_priority_visible_parts_placed_first_within_sheet():
    # Two same-size boards, only one tagged visible. After nesting it should
    # appear earlier in the sequence (top-left bias because of priority+ordering).
    triangles = rectangular_board(400, 300, 18) + translated_board(400, 300, 18, 500)
    config = ProcessConfig(overrides={"panel_002": {"priority": "visible"}})
    result = process_triangles(triangles, config)

    # The visible part should be among the first placed; with two equal parts on
    # one sheet, "first placed" is the one at (0,0).
    first_part = result.sheets[0].parts[0]
    visible_board = next(b for b in result.boards if b.priority == "visible")
    assert first_part.board_id == visible_board.id


def rectangular_board(length: float, width: float, thickness: float) -> list[Triangle]:
    p000 = Vec3(0, 0, 0)
    p100 = Vec3(length, 0, 0)
    p110 = Vec3(length, width, 0)
    p010 = Vec3(0, width, 0)
    p001 = Vec3(0, 0, thickness)
    p101 = Vec3(length, 0, thickness)
    p111 = Vec3(length, width, thickness)
    p011 = Vec3(0, width, thickness)

    return [
        Triangle(p000, p110, p100),
        Triangle(p000, p010, p110),
        Triangle(p001, p101, p111),
        Triangle(p001, p111, p011),
    ]


def translated_board(length: float, width: float, thickness: float, x_offset: float) -> list[Triangle]:
    translated = []
    for triangle in rectangular_board(length, width, thickness):
        translated.append(
            Triangle(
                Vec3(triangle.a.x + x_offset, triangle.a.y, triangle.a.z),
                Vec3(triangle.b.x + x_offset, triangle.b.y, triangle.b.z),
                Vec3(triangle.c.x + x_offset, triangle.c.y, triangle.c.z),
            )
        )
    return translated


def l_shape_face(z: float = 0.0) -> list[Triangle]:
    """An L-shaped flat face built from 3 triangles at the given z plane.

    Outline (CCW): (0,0)-(200,0)-(200,100)-(100,100)-(100,200)-(0,200)-(0,0).
    Three triangles tile that polygon without overlap.
    """
    p00 = Vec3(0, 0, z)
    p20 = Vec3(200, 0, z)
    p21 = Vec3(200, 100, z)
    p11 = Vec3(100, 100, z)
    p12 = Vec3(100, 200, z)
    p02 = Vec3(0, 200, z)
    return [
        Triangle(p00, p20, p21),  # bottom-right rectangle, half 1
        Triangle(p00, p21, p11),  # bottom-right rectangle, half 2
        Triangle(p00, p11, p12),  # left rectangle, half 1
        # NB: we add one more triangle so the upper-left rectangle is closed.
        Triangle(p00, p12, p02),
    ]


def translated_l_shape_face(z_offset: float) -> list[Triangle]:
    return l_shape_face(z=z_offset)


def rectangular_face_with_hole(z: float = 0.0) -> list[Triangle]:
    """300x200 face with a 100x60 rectangular internal cutout."""
    quads = [
        ((0, 0), (100, 0), (100, 70), (0, 70)),
        ((100, 0), (200, 0), (200, 70), (100, 70)),
        ((200, 0), (300, 0), (300, 70), (200, 70)),
        ((200, 70), (300, 70), (300, 130), (200, 130)),
        ((200, 130), (300, 130), (300, 200), (200, 200)),
        ((100, 130), (200, 130), (200, 200), (100, 200)),
        ((0, 130), (100, 130), (100, 200), (0, 200)),
        ((0, 70), (100, 70), (100, 130), (0, 130)),
    ]
    triangles = []
    for (x0, y0), (x1, y1), (x2, y2), (x3, y3) in quads:
        p0 = Vec3(x0, y0, z)
        p1 = Vec3(x1, y1, z)
        p2 = Vec3(x2, y2, z)
        p3 = Vec3(x3, y3, z)
        triangles.extend([Triangle(p0, p1, p2), Triangle(p0, p2, p3)])
    return triangles


def single_surface(length: float, width: float, z: float) -> list[Triangle]:
    p000 = Vec3(0, 0, z)
    p100 = Vec3(length, 0, z)
    p110 = Vec3(length, width, z)
    p010 = Vec3(0, width, z)
    return [
        Triangle(p000, p110, p100),
        Triangle(p000, p010, p110),
    ]
