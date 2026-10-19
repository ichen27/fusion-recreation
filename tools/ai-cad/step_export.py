"""Optional OCCT translation of an already validated analytic boundary; no booleans."""

from fractions import Fraction
import math
import os
from pathlib import Path
import tempfile
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeWire,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_Sewing,
    BRepBuilderAPI_MakeSolid,
)
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepLib import BRepLib
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2, gp_Circ, gp_Vec
from OCP.TopoDS import TopoDS
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_Writer, STEPControl_Reader, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone


def number(s):
    return float(Fraction(s))


def faces(shape):
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        yield TopoDS.Face(explorer.Current())
        explorer.Next()


def wire(edges):
    builder = BRepBuilderAPI_MakeWire()
    for edge in edges:
        builder.Add(TopoDS.Edge(edge))
    if not builder.IsDone():
        raise RuntimeError("STEP wire construction failed")
    return builder.Wire()


def measure(shape):
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass()


def translate(body):
    converted = []
    if "analytic" in body:
        shape = body["analytic"]
        h = number(shape["height"])
        points = [[number(v) for v in p] + [0.0] for p in shape["outer"]]
        disks = [
            (number(c["center"][0]), number(c["center"][1]), number(c["radius"]))
            for c in shape["holes"]
        ]
        if h <= 1e-6 or any(r <= 1e-6 for _, _, r in disks):
            raise RuntimeError("STEP adapter requires height/radii above 1e-6 mm")
        for i, (x, y, r) in enumerate(disks):
            for a, b in zip(points, points[1:] + points[:1]):
                dx, dy = b[0] - a[0], b[1] - a[1]
                length = math.hypot(dx, dy)
                if (
                    length <= 1e-6
                    or (dx * (y - a[1]) - dy * (x - a[0])) / length - r <= 1e-6
                ):
                    raise RuntimeError(
                        "STEP adapter requires edge length and hole clearance above 1e-6 mm"
                    )
            if any(
                math.hypot(x - xx, y - yy) - r - rr <= 1e-6 for xx, yy, rr in disks[:i]
            ):
                raise RuntimeError(
                    "STEP adapter requires hole separation above 1e-6 mm"
                )
        rings = [
            [
                BRepBuilderAPI_MakeEdge(gp_Pnt(*a), gp_Pnt(*b)).Edge()
                for a, b in zip(points, points[1:] + points[:1])
            ]
        ]
        for hole in shape["holes"]:
            x, y = map(number, hole["center"])
            circle = gp_Circ(
                gp_Ax2(gp_Pnt(x, y, 0), gp_Dir(0, 0, 1)), number(hole["radius"])
            )
            rings.append(
                [TopoDS.Edge(BRepBuilderAPI_MakeEdge(circle).Edge().Reversed())]
            )
        cap = BRepBuilderAPI_MakeFace(wire(rings[0]), True)
        for ring in rings[1:]:
            cap.Add(wire(ring))
        if not cap.IsDone():
            raise RuntimeError("STEP cap construction failed")
        # Translation only: sweep each boundary edge into its corresponding wall;
        # move the existing cap, then sew this supplied boundary. No solid cutting.
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
        from OCP.gp import gp_Trsf

        transform = gp_Trsf()
        transform.SetTranslation(gp_Vec(0, 0, h))
        converted.extend(
            [
                TopoDS.Face(cap.Face().Reversed()),
                TopoDS.Face(
                    BRepBuilderAPI_Transform(cap.Face(), transform, True).Shape()
                ),
            ]
        )
        for ring in rings:
            for edge in ring:
                converted.extend(
                    faces(BRepPrimAPI_MakePrism(edge, gp_Vec(0, 0, h)).Shape())
                )
        v = shape["volume"]
        expected = number(v["constant_mm3"]) - math.pi * number(v["pi_subtract_mm3"])
    else:
        boundary = body["boundary"]
        points = [gp_Pnt(*map(number, p)) for p in boundary["vertices"]]
        for face in boundary["faces"]:
            ids = [
                boundary["edges"][u["edge"]]["vertices"][0 if u["forward"] else 1]
                for u in face["loops"][0]
            ]
            edges = [
                BRepBuilderAPI_MakeEdge(points[a], points[b]).Edge()
                for a, b in zip(ids, ids[1:] + ids[:1])
            ]
            converted.append(BRepBuilderAPI_MakeFace(wire(edges), True).Face())
        expected = number(body["volume_mm3"])
    sew = BRepBuilderAPI_Sewing(1e-7)
    for face in converted:
        if not BRepCheck_Analyzer(face).IsValid():
            raise RuntimeError("STEP face is invalid at adapter tolerance")
        sew.Add(face)
    sew.Perform()
    solid = BRepBuilderAPI_MakeSolid(TopoDS.Shell(sew.SewedShape())).Solid()
    BRepLib.OrientClosedSolid_s(solid)
    if not BRepCheck_Analyzer(solid).IsValid() or abs(measure(solid) - expected) > max(
        1e-7, abs(expected) * 1e-9
    ):
        raise RuntimeError("STEP translation did not preserve a valid solid and volume")
    return solid, expected


def export_step(body, output):
    output = Path(output)
    if output.exists():
        raise FileExistsError(str(output))
    solid, expected = translate(body)
    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        path = Path(directory) / "export.step"
        Interface_Static.SetCVal_s("write.step.unit", "MM")
        writer = STEPControl_Writer()
        if (
            writer.Transfer(solid, STEPControl_AsIs) != IFSelect_RetDone
            or writer.Write(str(path)) != IFSelect_RetDone
        ):
            raise RuntimeError("STEP write failed")
        reader = STEPControl_Reader()
        if reader.ReadFile(str(path)) != IFSelect_RetDone or not reader.TransferRoots():
            raise RuntimeError("STEP readback failed")
        imported = reader.OneShape()
        ex = TopExp_Explorer(imported, TopAbs_SOLID)
        count = 0
        while ex.More():
            count += 1
            ex.Next()
        volume = measure(imported)
        if (
            count != 1
            or not BRepCheck_Analyzer(imported).IsValid()
            or abs(volume - expected) > max(1e-7, abs(expected) * 1e-9)
        ):
            raise RuntimeError("STEP round trip changed solid validity or volume")
        os.link(path, output)  # Atomic publication; never overwrite another file.
    return {
        "volume_mm3": volume,
        "expected_volume_mm3": expected,
        "valid_solid": True,
        "adapter_tolerance_mm": 1e-7,
    }
