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
    BRepBuilderAPI_Transform,
)
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepLib import BRepLib
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2, gp_Circ, gp_Vec, gp_Trsf
from OCP.BRep import BRep_Builder
from OCP.TopoDS import TopoDS, TopoDS_Compound
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID, TopAbs_SHELL
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
        bore = shape.get("counterbore")
        depth = number(
            bore["depth"] if bore else shape.get("hole_depth", shape["height"])
        )
        floor = h - depth
        if ("hole_depth" in shape or bore) and (depth <= 1e-6 or floor <= 1e-6):
            raise RuntimeError(
                "STEP adapter requires blind depth and remaining floor above 1e-6 mm"
            )
        points = [[number(v) for v in p] + [0.0] for p in shape.get("outer", [])]
        outer_circle = shape.get("outer_circle")
        round_outer = (
            (
                [number(v) for v in outer_circle["center"]]
                + [number(outer_circle["radius"])]
            )
            if outer_circle
            else None
        )
        if round_outer and round_outer[2] <= 1e-6:
            raise RuntimeError("STEP adapter requires outer radius above 1e-6 mm")
        disks = [
            (
                number(c["center"][0]),
                number(c["center"][1]),
                number(bore["radius"] if bore else c["radius"]),
            )
            for c in shape["holes"]
        ]
        if h <= 1e-6 or any(r <= 1e-6 for _, _, r in disks):
            raise RuntimeError("STEP adapter requires height/radii above 1e-6 mm")
        if bore and any(
            number(c["radius"]) <= 1e-6
            or number(bore["radius"]) - number(c["radius"]) <= 1e-6
            for c in shape["holes"]
        ):
            raise RuntimeError(
                "STEP adapter requires through radii and counterbore shoulders above 1e-6 mm"
            )
        for i, (x, y, r) in enumerate(disks):
            if (
                round_outer
                and round_outer[2]
                - math.hypot(x - round_outer[0], y - round_outer[1])
                - r
                <= 1e-6
            ):
                raise RuntimeError(
                    "STEP adapter requires outer circle clearance above 1e-6 mm"
                )
            for a, b in zip(points, points[1:] + points[:1]):
                dx, dy = b[0] - a[0], b[1] - a[1]
                length = math.hypot(dx, dy)
                if length <= 1e-6:
                    raise RuntimeError("STEP adapter requires edges above 1e-6 mm")
                t = max(
                    0.0,
                    min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / (length * length)),
                )
                if math.hypot(x - a[0] - t * dx, y - a[1] - t * dy) - r <= 1e-6:
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
        if round_outer:
            x, y, r = round_outer
            circle = gp_Circ(gp_Ax2(gp_Pnt(x, y, 0), gp_Dir(0, 0, 1)), r)
            rings = [[BRepBuilderAPI_MakeEdge(circle).Edge()]]
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

        def moved(value, z):
            transform = gp_Trsf()
            transform.SetTranslation(gp_Vec(0, 0, z))
            return BRepBuilderAPI_Transform(value, transform, True).Shape()

        bottom = (
            BRepBuilderAPI_MakeFace(wire(rings[0]), True).Face()
            if "hole_depth" in shape
            else cap.Face()
        )
        top = cap.Face()
        large_rings = []
        if bore:
            top_builder = BRepBuilderAPI_MakeFace(wire(rings[0]), True)
            for hole in shape["holes"]:
                x, y = map(number, hole["center"])
                circle = gp_Circ(
                    gp_Ax2(gp_Pnt(x, y, 0), gp_Dir(0, 0, 1)), number(bore["radius"])
                )
                large_ring = [
                    TopoDS.Edge(BRepBuilderAPI_MakeEdge(circle).Edge().Reversed())
                ]
                large_rings.append(large_ring)
                top_builder.Add(wire(large_ring))
            if not top_builder.IsDone():
                raise RuntimeError("STEP counterbore top construction failed")
            top = top_builder.Face()
        converted.extend([TopoDS.Face(bottom.Reversed()), TopoDS.Face(moved(top, h))])
        for index, ring in enumerate(rings):
            for edge in ring:
                start = floor if index and not bore else 0.0
                wall_height = (floor if bore else depth) if index else h
                converted.extend(
                    faces(
                        BRepPrimAPI_MakePrism(
                            moved(edge, start), gp_Vec(0, 0, wall_height)
                        ).Shape()
                    )
                )
            if index and bore:
                large = large_rings[index - 1]
                for edge in large:
                    converted.extend(
                        faces(
                            BRepPrimAPI_MakePrism(
                                moved(edge, floor), gp_Vec(0, 0, depth)
                            ).Shape()
                        )
                    )
                shoulder = BRepBuilderAPI_MakeFace(
                    wire([TopoDS.Edge(edge.Reversed()) for edge in reversed(large)]),
                    True,
                )
                shoulder.Add(wire(ring))
                if not shoulder.IsDone():
                    raise RuntimeError("STEP counterbore shoulder construction failed")
                converted.append(TopoDS.Face(moved(shoulder.Face(), floor)))
            if index and "hole_depth" in shape:
                floor_wire = wire(
                    [TopoDS.Edge(edge.Reversed()) for edge in reversed(ring)]
                )
                floor_face = BRepBuilderAPI_MakeFace(floor_wire, True).Face()
                converted.append(TopoDS.Face(moved(floor_face, floor)))
        v = shape["volume"]
        expected = number(v["constant_mm3"]) - math.pi * number(v["pi_subtract_mm3"])
    else:
        boundary = body["boundary"]
        points = [gp_Pnt(*map(number, p)) for p in boundary["vertices"]]
        for face in boundary["faces"]:
            rings = []
            for loop in face["loops"]:
                ids = [
                    boundary["edges"][u["edge"]]["vertices"][0 if u["forward"] else 1]
                    for u in loop
                ]
                rings.append(
                    wire(
                        [
                            BRepBuilderAPI_MakeEdge(points[a], points[b]).Edge()
                            for a, b in zip(ids, ids[1:] + ids[:1])
                        ]
                    )
                )
            maker = BRepBuilderAPI_MakeFace(rings[0], True)
            for ring in rings[1:]:
                maker.Add(ring)
            if not maker.IsDone():
                raise RuntimeError("STEP planar face construction failed")
            converted.append(maker.Face())
        expected = number(body["volume_mm3"])
    # The original engine supplies material-component face membership, including
    # cavity shells. OCCT only sews those faces and translates their topology.
    groups = body.get("components", [list(range(len(converted)))])
    solids = []
    for indices in groups:
        sew = BRepBuilderAPI_Sewing(1e-7)
        for index in indices:
            face = converted[index]
            if not BRepCheck_Analyzer(face).IsValid():
                raise RuntimeError("STEP face is invalid at adapter tolerance")
            sew.Add(face)
        sew.Perform()
        builder = BRepBuilderAPI_MakeSolid()
        explorer = TopExp_Explorer(sew.SewedShape(), TopAbs_SHELL)
        count = 0
        while explorer.More():
            builder.Add(TopoDS.Shell(explorer.Current()))
            count += 1
            explorer.Next()
        if not count or not builder.IsDone():
            raise RuntimeError("STEP component has no closed shells")
        part = builder.Solid()
        if (
            not BRepLib.OrientClosedSolid_s(part)
            or not BRepCheck_Analyzer(part).IsValid()
        ):
            raise RuntimeError("STEP component is invalid at adapter tolerance")
        solids.append(part)
    if len(solids) == 1:
        solid = solids[0]
    else:
        solid = TopoDS_Compound()
        builder = BRep_Builder()
        builder.MakeCompound(solid)
        for part in solids:
            builder.Add(solid, part)
    placement = body.get("analytic", {}).get("placement")
    if placement:
        transform = gp_Trsf()
        transform.SetValues(
            *[
                value
                for row in range(3)
                for value in [*placement["axes"][row], number(placement["origin"][row])]
            ]
        )
        solid = BRepBuilderAPI_Transform(solid, transform, True).Shape()
    if not BRepCheck_Analyzer(solid).IsValid() or abs(measure(solid) - expected) > max(
        1e-7, abs(expected) * 1e-9
    ):
        raise RuntimeError("STEP translation did not preserve valid solids and volume")
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
            count != len(body.get("components", [None]))
            or not BRepCheck_Analyzer(imported).IsValid()
            or abs(volume - expected) > max(1e-7, abs(expected) * 1e-9)
        ):
            raise RuntimeError("STEP round trip changed solid validity or volume")
        os.link(path, output)  # Atomic publication; never overwrite another file.
    return {
        "volume_mm3": volume,
        "expected_volume_mm3": expected,
        "valid_solid": True,
        "solid_count": count,
        "adapter_tolerance_mm": 1e-7,
    }
