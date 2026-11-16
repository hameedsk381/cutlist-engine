"""STEP (.step / .stp) loader. Optional: needs the OpenCascade kernel.

Install with:  pip install "cutlist-engine[step]"

Each solid in the file is tessellated and returned as its own source object,
so the extractor measures it as one part. STEP lengths are converted to
millimetres by the kernel on read.
"""
from __future__ import annotations

from pathlib import Path

from .models import Triangle, Vec3

LINEAR_DEFLECTION_MM = 0.1
ANGULAR_DEFLECTION_RAD = 0.3

MISSING_KERNEL = (
    "STEP files need the optional CAD kernel, which is not installed on this server. "
    'Install it with: pip install "cutlist-engine[step]". '
    "Or export the design as OBJ, DAE or GLB instead."
)


def step_supported() -> bool:
    try:
        import OCP  # noqa: F401
    except ImportError:
        return False
    return True


def load_step(path: Path) -> list[Triangle]:
    try:
        from OCP.BRep import BRep_Tool
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.STEPControl import STEPControl_Reader
        from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED, TopAbs_SOLID
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS
    except ImportError as exc:
        raise ValueError(MISSING_KERNEL) from exc

    reader = STEPControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise ValueError("This STEP file could not be read. Check it opens in your CAD program and export it again.")
    reader.TransferRoots()
    shape = reader.OneShape()
    if shape.IsNull():
        raise ValueError("This STEP file contains no solid geometry.")

    BRepMesh_IncrementalMesh(shape, LINEAR_DEFLECTION_MM, False, ANGULAR_DEFLECTION_RAD, True)

    triangles: list[Triangle] = []
    solids = TopExp_Explorer(shape, TopAbs_SOLID)
    index = 0
    while solids.More():
        index += 1
        name = f"Part {index}"
        faces = TopExp_Explorer(solids.Current(), TopAbs_FACE)
        while faces.More():
            face = TopoDS.Face_s(faces.Current())
            location = TopLoc_Location()
            mesh = BRep_Tool.Triangulation_s(face, location)
            if mesh is not None:
                transform = location.Transformation()
                points = []
                for i in range(1, mesh.NbNodes() + 1):
                    p = mesh.Node(i).Transformed(transform)
                    points.append(Vec3(p.X(), p.Y(), p.Z()))
                flipped = face.Orientation() == TopAbs_REVERSED
                for i in range(1, mesh.NbTriangles() + 1):
                    a, b, c = mesh.Triangle(i).Get()
                    if flipped:
                        b, c = c, b
                    triangles.append(Triangle(points[a - 1], points[b - 1], points[c - 1], name))
            faces.Next()
        solids.Next()

    if not triangles:
        raise ValueError("This STEP file has no solids. Surfaces and wireframes cannot be cut from sheet.")
    return triangles
