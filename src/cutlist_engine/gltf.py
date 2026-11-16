"""glTF 2.0 / GLB loader (standard library only).

Reads triangle meshes from `.glb` and self-contained `.gltf` files, applies
the node hierarchy transforms, and converts from metres (the glTF unit) to
millimetres. Each mesh node becomes a named source object, so panels keep
their names through extraction.
"""
from __future__ import annotations

import base64
import json
import struct
from math import sqrt
from pathlib import Path
from typing import Any

from .models import Triangle, Vec3

METRES_TO_MM = 1000.0

_GLB_MAGIC = 0x46546C67   # "glTF"
_CHUNK_JSON = 0x4E4F534A
_CHUNK_BIN = 0x004E4942

_COMPONENT = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
_TYPE_SIZE = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}

Matrix = tuple[float, ...]  # 4x4, column-major as in the glTF spec
_IDENTITY: Matrix = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)


def load_gltf(path: Path) -> list[Triangle]:
    data = path.read_bytes()
    if path.suffix.lower() == ".glb" or data[:4] == b"glTF":
        document, embedded = _split_glb(data)
    else:
        document, embedded = json.loads(data.decode("utf-8")), None

    buffers = [_load_buffer(buffer, index, embedded, path) for index, buffer in enumerate(document.get("buffers", []))]
    nodes = document.get("nodes", [])
    scenes = document.get("scenes", [])
    if scenes:
        roots = scenes[document.get("scene", 0)].get("nodes", [])
    else:
        children = {child for node in nodes for child in node.get("children", [])}
        roots = [index for index in range(len(nodes)) if index not in children]

    triangles: list[Triangle] = []
    stack: list[tuple[int, Matrix, int]] = [(index, _IDENTITY, 0) for index in roots]
    while stack:
        index, parent, depth = stack.pop()
        if depth > 64 or not 0 <= index < len(nodes):
            continue
        node = nodes[index]
        world = _multiply(parent, _node_matrix(node))
        if "mesh" in node:
            mesh = document["meshes"][node["mesh"]]
            name = node.get("name") or mesh.get("name") or f"mesh_{node['mesh']}"
            for primitive in mesh.get("primitives", []):
                triangles.extend(_primitive_triangles(document, buffers, primitive, world, name))
        stack.extend((child, world, depth + 1) for child in node.get("children", []))
    return triangles


def _split_glb(data: bytes) -> tuple[dict[str, Any], bytes | None]:
    if len(data) < 20:
        raise ValueError("This GLB file is too short to be valid")
    magic, version, _length = struct.unpack_from("<III", data, 0)
    if magic != _GLB_MAGIC:
        raise ValueError("This is not a GLB file")
    if version != 2:
        raise ValueError(f"Only glTF version 2 is supported (this file is version {version})")
    document: dict[str, Any] | None = None
    binary: bytes | None = None
    offset = 12
    while offset + 8 <= len(data):
        chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
        chunk = data[offset + 8: offset + 8 + chunk_length]
        if chunk_type == _CHUNK_JSON:
            document = json.loads(chunk.decode("utf-8"))
        elif chunk_type == _CHUNK_BIN and binary is None:
            binary = chunk
        offset += 8 + chunk_length
    if document is None:
        raise ValueError("This GLB file has no JSON chunk")
    return document, binary


def _load_buffer(buffer: dict[str, Any], index: int, embedded: bytes | None, path: Path) -> bytes:
    uri = buffer.get("uri")
    if uri is None:
        if embedded is None or index != 0:
            raise ValueError("This glTF file is missing its binary data")
        return embedded
    if uri.startswith("data:"):
        return base64.b64decode(uri.split(",", 1)[1])
    raise ValueError(
        "This .gltf file keeps its geometry in a separate .bin file. "
        "Export it as a single .glb file instead."
    )


def _accessor(document: dict[str, Any], buffers: list[bytes], index: int) -> list[tuple[float, ...]]:
    accessor = document["accessors"][index]
    if "bufferView" not in accessor:
        raise ValueError("This glTF file uses sparse geometry data, which is not supported")
    view = document["bufferViews"][accessor["bufferView"]]
    fmt = _COMPONENT.get(accessor["componentType"])
    width = _TYPE_SIZE.get(accessor["type"])
    if fmt is None or width is None:
        raise ValueError("This glTF file uses a data type that is not supported")
    item = struct.Struct("<" + fmt * width)
    stride = view.get("byteStride") or item.size
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    data = buffers[view["buffer"]]
    count = accessor["count"]
    if start + stride * (count - 1) + item.size > len(data):
        raise ValueError("This glTF file's geometry data is cut short")
    return [item.unpack_from(data, start + stride * i) for i in range(count)]


def _primitive_triangles(
    document: dict[str, Any], buffers: list[bytes], primitive: dict[str, Any], world: Matrix, name: str
) -> list[Triangle]:
    mode = primitive.get("mode", 4)
    if mode not in (4, 5, 6) or "POSITION" not in primitive.get("attributes", {}):
        return []  # points and lines are not panels
    points = [_transform(world, p) for p in _accessor(document, buffers, primitive["attributes"]["POSITION"])]
    if "indices" in primitive:
        order = [int(i[0]) for i in _accessor(document, buffers, primitive["indices"])]
    else:
        order = list(range(len(points)))

    if mode == 4:
        corners = [(order[i], order[i + 1], order[i + 2]) for i in range(0, len(order) - 2, 3)]
    elif mode == 5:  # triangle strip
        corners = [
            (order[i], order[i + 1], order[i + 2]) if i % 2 == 0 else (order[i + 1], order[i], order[i + 2])
            for i in range(len(order) - 2)
        ]
    else:  # triangle fan
        corners = [(order[0], order[i], order[i + 1]) for i in range(1, len(order) - 1)]

    triangles = []
    for a, b, c in corners:
        if max(a, b, c) >= len(points):
            raise ValueError("This glTF file's geometry indices are out of range")
        triangles.append(Triangle(points[a], points[b], points[c], name))
    return triangles


def _node_matrix(node: dict[str, Any]) -> Matrix:
    if "matrix" in node:
        return tuple(float(v) for v in node["matrix"])
    tx, ty, tz = node.get("translation", (0.0, 0.0, 0.0))
    sx, sy, sz = node.get("scale", (1.0, 1.0, 1.0))
    x, y, z, w = node.get("rotation", (0.0, 0.0, 0.0, 1.0))
    norm = sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / norm, y / norm, z / norm, w / norm
    return (
        (1 - 2 * (y * y + z * z)) * sx, (2 * (x * y + z * w)) * sx, (2 * (x * z - y * w)) * sx, 0.0,
        (2 * (x * y - z * w)) * sy, (1 - 2 * (x * x + z * z)) * sy, (2 * (y * z + x * w)) * sy, 0.0,
        (2 * (x * z + y * w)) * sz, (2 * (y * z - x * w)) * sz, (1 - 2 * (x * x + y * y)) * sz, 0.0,
        tx, ty, tz, 1.0,
    )


def _multiply(a: Matrix, b: Matrix) -> Matrix:
    return tuple(
        sum(a[k * 4 + row] * b[col * 4 + k] for k in range(4))
        for col in range(4)
        for row in range(4)
    )


def _transform(m: Matrix, p: tuple[float, ...]) -> Vec3:
    x, y, z = p[0], p[1], p[2]
    return Vec3(
        (m[0] * x + m[4] * y + m[8] * z + m[12]) * METRES_TO_MM,
        (m[1] * x + m[5] * y + m[9] * z + m[13]) * METRES_TO_MM,
        (m[2] * x + m[6] * y + m[10] * z + m[14]) * METRES_TO_MM,
    )
