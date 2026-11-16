"""glTF / GLB import: transforms applied, metres converted to mm, names kept."""
import base64
import json
import struct
from math import cos, radians, sin
from pathlib import Path

import pytest

from cutlist_engine.boards import extract_boards
from cutlist_engine.parsers import load_model

BOX_FACES = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]


def box_buffers(sx: float, sy: float, sz: float) -> tuple[bytes, int, int]:
    """A box in metres as (binary, vertex_bytes, index_count); positions then ushort indices."""
    corners = [(0, 0, 0), (sx, 0, 0), (sx, sy, 0), (0, sy, 0), (0, 0, sz), (sx, 0, sz), (sx, sy, sz), (0, sy, sz)]
    positions = b"".join(struct.pack("<fff", *c) for c in corners)
    indices = []
    for a, b, c, d in BOX_FACES:
        indices += [a, b, c, a, c, d]
    return positions + struct.pack(f"<{len(indices)}H", *indices), len(positions), len(indices)


def gltf_document(nodes: list[dict], vertex_bytes: int, index_count: int, total: int, uri: str | None = None) -> dict:
    buffer: dict = {"byteLength": total}
    if uri:
        buffer["uri"] = uri
    return {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": nodes,
        "meshes": [{"name": "box", "primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
        "buffers": [buffer],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": vertex_bytes},
            {"buffer": 0, "byteOffset": vertex_bytes, "byteLength": index_count * 2},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 8, "type": "VEC3"},
            {"bufferView": 1, "componentType": 5123, "count": index_count, "type": "SCALAR"},
        ],
    }


def write_glb(path: Path, document: dict, binary: bytes) -> None:
    text = json.dumps(document).encode("utf-8")
    text += b" " * (-len(text) % 4)
    binary += b"\0" * (-len(binary) % 4)
    body = struct.pack("<II", len(text), 0x4E4F534A) + text + struct.pack("<II", len(binary), 0x004E4942) + binary
    path.write_bytes(struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body)


def test_glb_panel_is_read_in_mm_with_its_node_name(tmp_path: Path):
    binary, vertex_bytes, index_count = box_buffers(0.72, 0.45, 0.018)
    nodes = [{"name": "Left side", "mesh": 0, "translation": [1.0, 2.0, 3.0]}]
    path = tmp_path / "panel.glb"
    write_glb(path, gltf_document(nodes, vertex_bytes, index_count, len(binary)), binary)

    triangles = load_model(path)
    boards = extract_boards(triangles, expected_thickness=18).boards

    assert len(triangles) == 12
    assert min(v.x for t in triangles for v in t.vertices) == pytest.approx(1000.0)
    assert [(b.length, b.width, b.thickness, b.source_objects) for b in boards] == [(720, 450, 18, ("Left side",))]


def test_gltf_applies_parent_rotation_and_child_scale(tmp_path: Path):
    # Unit cube scaled to a 600 x 300 x 18 mm panel by the child, rotated 90 degrees by the parent.
    binary, vertex_bytes, index_count = box_buffers(1.0, 1.0, 1.0)
    half = radians(90) / 2
    nodes = [
        {"name": "assembly", "children": [1], "rotation": [0.0, sin(half), 0.0, cos(half)]},
        {"name": "Shelf", "mesh": 0, "scale": [0.6, 0.3, 0.018], "translation": [0.1, 0.0, 0.0]},
    ]
    uri = "data:application/octet-stream;base64," + base64.b64encode(binary).decode()
    path = tmp_path / "shelf.gltf"
    path.write_text(json.dumps(gltf_document(nodes, vertex_bytes, index_count, len(binary), uri)), encoding="utf-8")

    boards = extract_boards(load_model(path), expected_thickness=18).boards

    assert len(boards) == 1
    assert (boards[0].length, boards[0].width, boards[0].thickness) == pytest.approx((600, 300, 18), abs=0.01)
    assert boards[0].source_objects == ("Shelf",)


def test_gltf_with_external_bin_explains_what_to_do(tmp_path: Path):
    binary, vertex_bytes, index_count = box_buffers(0.5, 0.5, 0.018)
    nodes = [{"name": "p", "mesh": 0}]
    path = tmp_path / "split.gltf"
    path.write_text(json.dumps(gltf_document(nodes, vertex_bytes, index_count, len(binary), "split.bin")), encoding="utf-8")

    with pytest.raises(ValueError, match="single .glb"):
        load_model(path)


def test_truncated_glb_is_rejected(tmp_path: Path):
    path = tmp_path / "bad.glb"
    path.write_bytes(b"glTF\x02\x00\x00\x00")

    with pytest.raises(ValueError):
        load_model(path)
