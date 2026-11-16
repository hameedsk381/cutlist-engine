"""Part-first extraction: every closed solid is one board, measured directly."""
from math import cos, radians, sin

from cutlist_engine.boards import extract_boards
from cutlist_engine.models import Triangle, Vec3
from cutlist_engine.pipeline import ProcessConfig, process_triangles


def closed_box(name, x0, y0, z0, x1, y1, z1) -> list[Triangle]:
    corners = [
        Vec3(x0, y0, z0), Vec3(x1, y0, z0), Vec3(x1, y1, z0), Vec3(x0, y1, z0),
        Vec3(x0, y0, z1), Vec3(x1, y0, z1), Vec3(x1, y1, z1), Vec3(x0, y1, z1),
    ]
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    triangles = []
    for a, b, c, d in quads:
        triangles.append(Triangle(corners[a], corners[b], corners[c], name))
        triangles.append(Triangle(corners[a], corners[c], corners[d], name))
    return triangles


def base_cabinet(named: bool = True) -> list[Triangle]:
    """600W x 560D x 720H butt-jointed carcass: 18 mm panels, 6 mm back."""
    w, d, h, t = 600, 560, 720, 18
    parts = [
        ("left_side", 0, 0, 0, t, d, h),
        ("right_side", w - t, 0, 0, w, d, h),
        ("bottom", t, 0, 0, w - t, d, t),
        ("top", t, 0, h - t, w - t, d, h),
        ("shelf", t, 20, 351, w - t, d, 369),
        ("back", t, d - 6, t, w - t, d, h - t),
        ("shutter", 0, -20, 0, w, -2, h),
    ]
    triangles = []
    for name, *box in parts:
        triangles += closed_box(name if named else None, *box)
    return triangles


EXPECTED_CABINET = {
    "left_side": (720, 560, 18),
    "right_side": (720, 560, 18),
    "bottom": (564, 560, 18),
    "top": (564, 560, 18),
    "shelf": (564, 540, 18),
    "back": (684, 564, 6),
    "shutter": (720, 600, 18),
}


def test_cabinet_parts_are_measured_exactly():
    extraction = extract_boards(base_cabinet(), expected_thickness=18)

    measured = {b.source_objects[0]: (b.length, b.width, b.thickness) for b in extraction.boards}
    assert measured == EXPECTED_CABINET
    assert extraction.report.confidence == 1.0
    assert extraction.report.solid_part_count == 7
    assert extraction.report.inferred_board_count == 0


def test_touching_parts_without_names_stay_separate():
    extraction = extract_boards(base_cabinet(named=False), expected_thickness=18)

    sizes = sorted((b.length, b.width, b.thickness) for b in extraction.boards)
    assert sizes == sorted(EXPECTED_CABINET.values())


def test_off_thickness_parts_get_their_own_sheets():
    result = process_triangles(base_cabinet(), ProcessConfig(material_thickness=18))

    back = next(b for b in result.boards if b.source_objects == ("back",))
    assert back.material == "6mm"
    assert {s.material for s in result.sheets} == {"default", "6mm"}
    back_sheets = [s for s in result.sheets if s.material == "6mm"]
    assert [p.board_id for s in back_sheets for p in s.parts] == [back.id]
    assert result.model_fix_report.passes_gate is True
    assert any("6mm" in issue for issue in result.model_fix_report.issues)


def test_off_thickness_parts_use_matching_registered_material():
    from cutlist_engine.models import MaterialSpec

    config = ProcessConfig(
        material_thickness=18,
        materials={"hdf_6": MaterialSpec("hdf_6", 6, 2440, 1220, 900)},
    )
    result = process_triangles(base_cabinet(), config)

    back = next(b for b in result.boards if b.source_objects == ("back",))
    assert back.material == "hdf_6"


def test_panel_tilted_in_its_own_plane_keeps_true_size():
    angle = radians(30)
    c, s = cos(angle), sin(angle)
    tilted = [
        Triangle(*(Vec3(v.x * c - v.y * s, v.x * s + v.y * c, v.z) for v in t.vertices), "tilted")
        for t in closed_box("tilted", 0, 0, 0, 720, 450, 18)
    ]

    boards = extract_boards(tilted, expected_thickness=18).boards

    assert len(boards) == 1
    assert abs(boards[0].length - 720) < 0.01
    assert abs(boards[0].width - 450) < 0.01
    assert not any("Non-rectangular" in w for w in boards[0].warnings)


def test_non_panel_solid_is_skipped_and_reported():
    triangles = closed_box("side", 0, 0, 0, 18, 560, 720) + closed_box("plinth_block", 500, 0, 0, 700, 200, 200)

    result = process_triangles(triangles, ProcessConfig())

    assert [b.source_objects for b in result.boards] == [("side",)]
    assert any("plinth_block" in part for part in result.extraction_report.skipped_parts)
    assert any("plinth_block" in issue for issue in result.model_fix_report.issues)


def test_non_standard_thickness_is_kept_with_warning():
    boards = extract_boards(closed_box("worktop", 0, 0, 0, 2000, 600, 38), expected_thickness=18).boards

    assert len(boards) == 1
    assert boards[0].thickness == 38
    assert boards[0].confidence < 1.0
    assert any("not a standard sheet thickness" in w for w in boards[0].warnings)


def test_loose_faces_straddling_the_origin_are_paired():
    def face(z):
        a, b, c, d = Vec3(0, 0, z), Vec3(720, 0, z), Vec3(720, 450, z), Vec3(0, 450, z)
        return [Triangle(a, b, c), Triangle(a, c, d)]

    extraction = extract_boards(face(-9) + face(9), expected_thickness=18)

    assert len(extraction.boards) == 1
    assert extraction.boards[0].thickness == 18
    assert extraction.report.inferred_board_count == 1


def test_part_longer_than_every_sheet_is_reported_not_fatal(tmp_path):
    """One panel too long for the sheet used to fail the whole job with a bare error."""
    from cutlist_engine.furniture import describe_to_model
    from cutlist_engine.parsers import load_model
    from cutlist_engine.pipeline import ProcessConfig, process_triangles

    model = describe_to_model("Wardrobe 2100 high, 3100 wide, 600 deep, 4 shutters, 2 shelves")
    path = tmp_path / "wide.obj"
    path.write_text(model["obj"])

    result = process_triangles(load_model(path), ProcessConfig())

    assert {b.label for b in result.oversize_boards} == {"Bottom", "Top", "Skirting", "Back"}
    assert result.material_summary.sheet_count > 0  # the parts that fit are still planned
    assert not any(b in result.boards for b in result.oversize_boards)
    assert any("NOT in the plan" in issue for issue in result.model_fix_report.issues)

    # A big enough sheet takes them all.
    result = process_triangles(load_model(path), ProcessConfig(sheet_width=3200, sheet_height=2100))
    assert result.oversize_boards == []


def test_model_exported_in_metres_is_scaled_and_flagged(tmp_path):
    """A Blender export in metres was read as mm: every part came out a few mm and the plan was empty."""
    from cutlist_engine.furniture import describe_to_model
    from cutlist_engine.parsers import load_model
    from cutlist_engine.pipeline import ProcessConfig, process_triangles

    model = describe_to_model("Kitchen base unit 720 high, 600 wide, 560 deep, 1 shelf, 1 shutter")
    in_mm = tmp_path / "mm.obj"
    in_mm.write_text(model["obj"])
    in_metres = tmp_path / "metres.obj"
    lines = []
    for line in model["obj"].splitlines():
        if line.startswith("v "):
            lines.append("v " + " ".join(f"{float(x) / 1000:.6f}" for x in line.split()[1:4]))
        else:
            lines.append(line)
    in_metres.write_text("\n".join(lines))

    reference = process_triangles(load_model(in_mm), ProcessConfig())
    triangles = load_model(in_metres)
    result = process_triangles(triangles, ProcessConfig())

    assert triangles.scaled_from_metres
    assert not getattr(load_model(in_mm), "scaled_from_metres", False)
    size = lambda r: sorted((round(b.length), round(b.width), b.thickness) for b in r.boards)  # noqa: E731
    assert size(result) == size(reference) and len(result.boards) > 0
    assert any("read as metres" in issue for issue in result.model_fix_report.issues)


def _dae_from_obj(obj_text: str, unit_attr: str, scale: float) -> str:
    """A minimal COLLADA file with a box per OBJ... built from the model's vertices/faces."""
    verts, faces = [], []
    for line in obj_text.splitlines():
        if line.startswith("v "):
            verts.append([float(x) * scale for x in line.split()[1:4]])
        elif line.startswith("f "):
            idx = [int(p.split("/")[0]) - 1 for p in line.split()[1:]]
            for i in range(1, len(idx) - 1):
                faces.append((idx[0], idx[i], idx[i + 1]))
    flat = " ".join(f"{c:.6f}" for v in verts for c in v)
    tri = " ".join(str(i) for f in faces for i in f)
    return (
        '<?xml version="1.0"?><COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">'
        f"<asset>{unit_attr}</asset><library_geometries><geometry id=\"g\"><mesh>"
        f'<source id="p"><float_array id="pa" count="{len(verts) * 3}">{flat}</float_array>'
        '<technique_common><accessor source="#pa" count="%d" stride="3"/></technique_common></source>'
        '<vertices id="v"><input semantic="POSITION" source="#p"/></vertices>'
        f'<triangles count="{len(faces)}"><input semantic="VERTEX" source="#v" offset="0"/><p>{tri}</p></triangles>'
        '</mesh></geometry></library_geometries><library_visual_scenes><visual_scene id="s">'
        '<node id="n" name="cab"><instance_geometry url="#g"/></node></visual_scene></library_visual_scenes>'
        "</COLLADA>"
    ) % len(verts)


def test_dae_declared_units_are_converted(tmp_path):
    """A SketchUp DAE in inches was read as mm: every part came out about 25 times too small."""
    from cutlist_engine.furniture import describe_to_model
    from cutlist_engine.parsers import load_model
    from cutlist_engine.pipeline import ProcessConfig, process_triangles

    obj = describe_to_model("Kitchen base unit 720 high, 600 wide, 560 deep, 1 shelf, 1 shutter")["obj"]
    ref = tmp_path / "ref.obj"
    ref.write_text(obj)
    reference = process_triangles(load_model(ref), ProcessConfig())
    size = lambda r: sorted((round(b.length), round(b.width), b.thickness) for b in r.boards)  # noqa: E731

    cases = {
        "inch": ('<unit name="inch" meter="0.0254"/>', 1 / 25.4),
        "cm": ('<unit name="centimeter" meter="0.01"/>', 0.1),
        "metre": ('<unit name="meter" meter="1"/>', 0.001),
        "mm": ('<unit name="millimeter" meter="0.001"/>', 1.0),
    }
    for name, (attr, scale) in cases.items():
        path = tmp_path / f"{name}.dae"
        path.write_text(_dae_from_obj(obj, attr, scale))
        triangles = load_model(path)
        result = process_triangles(triangles, ProcessConfig())
        assert size(result) == size(reference), name
        assert bool(triangles.declared_unit) == (name != "mm"), name
        if name == "inch":
            assert any("declares its unit as 'inch'" in i for i in result.model_fix_report.issues)

    # A file that declares metres but is really in mm is not blown up 1000x.
    liar = tmp_path / "liar.dae"
    liar.write_text(_dae_from_obj(obj, '<unit name="meter" meter="1"/>', 1.0))
    assert size(process_triangles(load_model(liar), ProcessConfig())) == size(reference)

    # No unit declared: the old size guess still applies.
    plain = tmp_path / "plain.dae"
    plain.write_text(_dae_from_obj(obj, "", 1.0))
    assert size(process_triangles(load_model(plain), ProcessConfig())) == size(reference)
