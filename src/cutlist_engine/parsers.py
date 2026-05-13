from __future__ import annotations

import json
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .models import Triangle, Vec3


def load_mesh_json(path: Path) -> list[Triangle]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_triangles = payload.get("triangles")
    if not isinstance(raw_triangles, list):
        raise ValueError("Input JSON must contain a 'triangles' array")

    triangles = []
    for raw in raw_triangles:
        if not isinstance(raw, list) or len(raw) != 3:
            raise ValueError("Each triangle must contain exactly three vertices")
        triangles.append(Triangle(*[_vec3(vertex) for vertex in raw]))
    return triangles


def load_model(path: Path) -> list[Triangle]:
    suffix = path.suffix.lower()
    if suffix == ".dxf":
        return load_dxf(path)
    if suffix == ".obj":
        return load_obj(path)
    if suffix == ".stl":
        return load_stl(path)
    if suffix == ".json":
        return load_mesh_json(path)
    if suffix == ".dae":
        return load_dae(path)
    raise ValueError(f"Unsupported input format '{path.suffix}'. Supported formats: .json, .dxf, .obj, .stl, .dae")


def load_dxf(path: Path) -> list[Triangle]:
    try:
        import ezdxf
    except ImportError as exc:
        raise RuntimeError("DXF input requires installing the optional 'cad' dependencies") from exc

    doc = ezdxf.readfile(path)
    triangles: list[Triangle] = []
    for entity in doc.modelspace():
        entity_type = entity.dxftype()
        source_object = entity.dxf.layer if entity.dxf.hasattr("layer") else None
        if entity_type == "3DFACE":
            vertices = [Vec3(*entity.dxf.vtx0), Vec3(*entity.dxf.vtx1), Vec3(*entity.dxf.vtx2), Vec3(*entity.dxf.vtx3)]
            triangles.extend(_triangulate_face(vertices, source_object))
        elif entity_type == "MESH":
            vertices = [Vec3(float(v[0]), float(v[1]), float(v[2])) for v in entity.vertices]
            for face in entity.faces:
                triangles.extend(_triangulate_indexed_face(vertices, list(face), source_object))
        elif entity_type == "POLYLINE" and entity.is_poly_face_mesh:
            polyface = ezdxf.entities.Polyface.from_polyline(entity)
            for face in polyface.faces():
                vertices = [Vec3(*vertex.dxf.location) for vertex in face[:-1]]
                triangles.extend(_triangulate_face(vertices, source_object))
    return triangles


def _triangulate_indexed_face(vertices: list[Vec3], indexes: list[int], source_object: str | None) -> list[Triangle]:
    face_vertices = [vertices[index] for index in indexes if 0 <= index < len(vertices)]
    return _triangulate_face(face_vertices, source_object)


def _triangulate_face(vertices: list[Vec3], source_object: str | None) -> list[Triangle]:
    if len(vertices) < 3:
        return []
    # DXF 3DFACE repeats the third vertex for triangular faces.
    if len(vertices) == 4 and vertices[2].distance_to(vertices[3]) <= 0.01:
        vertices = vertices[:3]
    triangles = []
    for index in range(1, len(vertices) - 1):
        triangles.append(Triangle(vertices[0], vertices[index], vertices[index + 1], source_object))
    return triangles


def load_obj(path: Path) -> list[Triangle]:
    vertices: list[Vec3] = []
    triangles: list[Triangle] = []
    current_object = path.stem

    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if parts[0] in {"o", "g"} and len(parts) >= 2:
            current_object = " ".join(parts[1:])
        elif parts[0] == "v" and len(parts) >= 4:
            vertices.append(Vec3(float(parts[1]), float(parts[2]), float(parts[3])))
        elif parts[0] == "f" and len(parts) >= 4:
            indexes = [_obj_vertex_index(part, len(vertices)) for part in parts[1:]]
            for index in range(1, len(indexes) - 1):
                triangles.append(
                    Triangle(vertices[indexes[0]], vertices[indexes[index]], vertices[indexes[index + 1]], current_object)
                )

    return triangles


def load_stl(path: Path) -> list[Triangle]:
    data = path.read_bytes()
    if _looks_like_binary_stl(data):
        return _load_binary_stl(data)
    return _load_ascii_stl(data.decode("utf-8", errors="ignore"))


def _load_ascii_stl(text: str) -> list[Triangle]:
    triangles: list[Triangle] = []
    current_vertices: list[Vec3] = []
    source_object = "stl_solid"
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0].lower() == "solid":
            source_object = " ".join(parts[1:]) or "stl_solid"
        elif len(parts) == 4 and parts[0].lower() == "vertex":
            current_vertices.append(Vec3(float(parts[1]), float(parts[2]), float(parts[3])))
            if len(current_vertices) == 3:
                triangles.append(Triangle(current_vertices[0], current_vertices[1], current_vertices[2], source_object))
                current_vertices = []
    return triangles


def _load_binary_stl(data: bytes) -> list[Triangle]:
    triangle_count = struct.unpack_from("<I", data, 80)[0]
    expected_length = 84 + triangle_count * 50
    if len(data) < expected_length:
        raise ValueError("Binary STL appears truncated")

    triangles = []
    offset = 84
    for _ in range(triangle_count):
        values = struct.unpack_from("<12fH", data, offset)
        a = Vec3(values[3], values[4], values[5])
        b = Vec3(values[6], values[7], values[8])
        c = Vec3(values[9], values[10], values[11])
        triangles.append(Triangle(a, b, c, "binary_stl"))
        offset += 50
    return triangles


def load_dae(path: Path) -> list[Triangle]:
    root = ET.parse(path).getroot()
    ns = _namespace(root.tag)
    geometries = _parse_dae_geometries(root, ns)
    triangles: list[Triangle] = []

    for node, transform, node_name in _iter_dae_nodes(root, ns, path.stem):
        for instance in node.findall(f"{ns}instance_geometry"):
            geometry_id = instance.attrib.get("url", "").lstrip("#")
            for triangle in geometries.get(geometry_id, []):
                triangles.append(
                    Triangle(
                        _transform_point(triangle.a, transform),
                        _transform_point(triangle.b, transform),
                        _transform_point(triangle.c, transform),
                        node_name,
                    )
                )

    if triangles:
        return triangles

    for geometry_id, geometry_triangles in geometries.items():
        for triangle in geometry_triangles:
            triangles.append(Triangle(triangle.a, triangle.b, triangle.c, geometry_id))
    return triangles


def _vec3(value: Any) -> Vec3:
    if not isinstance(value, list | tuple) or len(value) != 3:
        raise ValueError("Vertex must be a three-number array")
    return Vec3(float(value[0]), float(value[1]), float(value[2]))


def _obj_vertex_index(raw: str, vertex_count: int) -> int:
    index = int(raw.split("/")[0])
    if index < 0:
        return vertex_count + index
    return index - 1


def _looks_like_binary_stl(data: bytes) -> bool:
    if len(data) < 84:
        return False
    if data[:5].lower() == b"solid":
        triangle_count = struct.unpack_from("<I", data, 80)[0]
        return len(data) == 84 + triangle_count * 50
    return True


def _namespace(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[0] + "}"
    return ""


def _parse_dae_geometries(root: ET.Element, ns: str) -> dict[str, list[Triangle]]:
    geometries: dict[str, list[Triangle]] = {}
    for geometry in root.findall(f".//{ns}library_geometries/{ns}geometry"):
        geometry_id = geometry.attrib.get("id")
        mesh = geometry.find(f"{ns}mesh")
        if not geometry_id or mesh is None:
            continue

        positions = _dae_positions(mesh, ns)
        vertices_map = _dae_vertices_map(mesh, ns)
        triangles = []
        triangles.extend(_dae_triangles(mesh, ns, positions, vertices_map, geometry_id))
        triangles.extend(_dae_polylists(mesh, ns, positions, vertices_map, geometry_id))
        geometries[geometry_id] = triangles
    return geometries


def _dae_positions(mesh: ET.Element, ns: str) -> dict[str, list[Vec3]]:
    positions = {}
    for source in mesh.findall(f"{ns}source"):
        source_id = source.attrib.get("id")
        float_array = source.find(f"{ns}float_array")
        if not source_id or float_array is None or not float_array.text:
            continue
        values = [float(value) for value in float_array.text.split()]
        positions[source_id] = [Vec3(values[index], values[index + 1], values[index + 2]) for index in range(0, len(values), 3)]
    return positions


def _dae_vertices_map(mesh: ET.Element, ns: str) -> dict[str, str]:
    mapping = {}
    for vertices in mesh.findall(f"{ns}vertices"):
        vertices_id = vertices.attrib.get("id")
        position_input = vertices.find(f"{ns}input[@semantic='POSITION']")
        if vertices_id and position_input is not None:
            mapping[vertices_id] = position_input.attrib.get("source", "").lstrip("#")
    return mapping


def _dae_triangles(
    mesh: ET.Element,
    ns: str,
    positions: dict[str, list[Vec3]],
    vertices_map: dict[str, str],
    source_object: str,
) -> list[Triangle]:
    triangles = []
    for primitive in mesh.findall(f"{ns}triangles"):
        vertex_source, vertex_offset, stride = _dae_vertex_input(primitive, ns, vertices_map)
        raw_p = primitive.find(f"{ns}p")
        if not vertex_source or raw_p is None or not raw_p.text:
            continue
        indexes = [int(value) for value in raw_p.text.split()]
        points = positions[vertex_source]
        for index in range(0, len(indexes), stride * 3):
            a = points[indexes[index + vertex_offset]]
            b = points[indexes[index + stride + vertex_offset]]
            c = points[indexes[index + stride * 2 + vertex_offset]]
            triangles.append(Triangle(a, b, c, source_object))
    return triangles


def _dae_polylists(
    mesh: ET.Element,
    ns: str,
    positions: dict[str, list[Vec3]],
    vertices_map: dict[str, str],
    source_object: str,
) -> list[Triangle]:
    triangles = []
    for primitive in mesh.findall(f"{ns}polylist"):
        vertex_source, vertex_offset, stride = _dae_vertex_input(primitive, ns, vertices_map)
        raw_p = primitive.find(f"{ns}p")
        raw_vcount = primitive.find(f"{ns}vcount")
        if not vertex_source or raw_p is None or raw_vcount is None or not raw_p.text or not raw_vcount.text:
            continue
        indexes = [int(value) for value in raw_p.text.split()]
        counts = [int(value) for value in raw_vcount.text.split()]
        points = positions[vertex_source]
        cursor = 0
        for count in counts:
            polygon_indexes = [indexes[cursor + vertex_offset + vertex_index * stride] for vertex_index in range(count)]
            cursor += count * stride
            for index in range(1, len(polygon_indexes) - 1):
                triangles.append(
                    Triangle(points[polygon_indexes[0]], points[polygon_indexes[index]], points[polygon_indexes[index + 1]], source_object)
                )
    return triangles


def _dae_vertex_input(primitive: ET.Element, ns: str, vertices_map: dict[str, str]) -> tuple[str | None, int, int]:
    inputs = primitive.findall(f"{ns}input")
    stride = max(int(item.attrib.get("offset", "0")) for item in inputs) + 1 if inputs else 1
    for item in inputs:
        if item.attrib.get("semantic") == "VERTEX":
            vertices_id = item.attrib.get("source", "").lstrip("#")
            return vertices_map.get(vertices_id), int(item.attrib.get("offset", "0")), stride
    return None, 0, stride


def _node_matrix(node: ET.Element, ns: str) -> tuple[float, ...]:
    matrix = node.find(f"{ns}matrix")
    if matrix is None or not matrix.text:
        return (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)
    values = tuple(float(value) for value in matrix.text.split())
    if len(values) != 16:
        raise ValueError("DAE node matrix must contain 16 values")
    return values


def _iter_dae_nodes(
    root: ET.Element,
    ns: str,
    fallback_name: str,
) -> list[tuple[ET.Element, tuple[float, ...], str]]:
    identity = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)
    items = []
    for node in root.findall(f".//{ns}visual_scene/{ns}node"):
        items.extend(_walk_dae_node(node, ns, identity, fallback_name))
    return items


def _walk_dae_node(
    node: ET.Element,
    ns: str,
    parent_matrix: tuple[float, ...],
    fallback_name: str,
) -> list[tuple[ET.Element, tuple[float, ...], str]]:
    local_matrix = _node_matrix(node, ns)
    transform = _multiply_matrix(parent_matrix, local_matrix)
    node_name = node.attrib.get("name") or node.attrib.get("id") or fallback_name
    items = [(node, transform, node_name)]
    for child in node.findall(f"{ns}node"):
        items.extend(_walk_dae_node(child, ns, transform, node_name))
    return items


def _multiply_matrix(left: tuple[float, ...], right: tuple[float, ...]) -> tuple[float, ...]:
    values = []
    for row in range(4):
        for column in range(4):
            values.append(sum(left[row * 4 + item] * right[item * 4 + column] for item in range(4)))
    return tuple(values)


def _transform_point(point: Vec3, matrix: tuple[float, ...]) -> Vec3:
    return Vec3(
        point.x * matrix[0] + point.y * matrix[1] + point.z * matrix[2] + matrix[3],
        point.x * matrix[4] + point.y * matrix[5] + point.z * matrix[6] + matrix[7],
        point.x * matrix[8] + point.y * matrix[9] + point.z * matrix[10] + matrix[11],
    )
