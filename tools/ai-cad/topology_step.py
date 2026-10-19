"""Verification-only OCCT translation of original-engine shared topology.

Consumes internally generated topology, not an untrusted B-rep import format.
No native modeling or Boolean operation is delegated to this adapter.
"""

import math
from fractions import Fraction as F
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_Sewing,
    BRepBuilderAPI_MakeSolid,
)
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepLib import BRepLib
from OCP.BRep import BRep_Builder
from OCP.TopoDS import TopoDS, TopoDS_Compound
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SHELL
from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2, gp_Ax3, gp_Circ, gp_Cylinder, gp_Cone, gp_Pln
from step_export import wire


def vector(values):
    return [F(v) for v in values]


def point(values):
    return gp_Pnt(*map(float, values))


def direction(values):
    return gp_Dir(*map(float, values))


def translate(topology):
    vertices = list(map(vector, topology["vertices"]))
    edges = []
    for edge in topology["edges"]:
        a, b = [vertices[i] for i in edge["vertices"]]
        curve = edge["curve"]
        if curve["kind"] == "line":
            builder = BRepBuilderAPI_MakeEdge(point(a), point(b))
        else:
            center = vector(curve["center"])
            radial = [x - y for x, y in zip(a, center)]
            circle = gp_Circ(
                gp_Ax2(point(center), direction(curve["axis"]), direction(radial)),
                float(F(curve["radius"])),
            )
            builder = BRepBuilderAPI_MakeEdge(circle, 0.0, math.pi / 2)
        if not builder.IsDone():
            raise RuntimeError("Shared edge cannot be translated at float tolerance")
        edges.append(builder.Edge())
    converted = []
    for face in topology["faces"]:
        surface = topology["surfaces"][face["surface"]]
        if surface["kind"] == "plane":
            normal = vector(surface["normal"])
            scale = F(surface["offset"]) / sum(v * v for v in normal)
            plane = gp_Pln(point([v * scale for v in normal]), direction(normal))
            loops = [
                wire(
                    [
                        edges[u["edge"]]
                        if u["forward"]
                        else edges[u["edge"]].Reversed()
                        for u in ring
                    ]
                )
                for ring in face["loops"]
            ]
            builder = BRepBuilderAPI_MakeFace(plane, loops[0], True)
            for loop in loops[1:]:
                builder.Add(loop)
            native = builder.Face()
        else:
            # Exact native validation established a rectangular quarter-cylinder.
            # Construct its bounded parameter surface, including the required p-curves.
            axis = surface["axis"]
            arcs = [
                topology["edges"][u["edge"]]
                for u in face["loops"][0]
                if topology["edges"][u["edge"]]["curve"]["kind"] == "quarter_circle"
            ]
            arcs.sort(
                key=lambda e: sum(
                    a * c for a, c in zip(axis, vector(e["curve"]["center"]))
                )
            )
            low, high = [vector(e["curve"]["center"]) for e in arcs]
            height = sum(
                a * (upper - lower) for a, upper, lower in zip(axis, high, low)
            )
            radial = [a - b for a, b in zip(vertices[arcs[0]["vertices"][0]], low)]
            if surface["kind"] == "conical_frustum":
                bottom, top = (
                    float(F(surface["bottom_radius"])),
                    float(F(surface["top_radius"])),
                )
                alpha = math.atan2(top - bottom, float(F(surface["height"])))
                cone = gp_Cone(
                    gp_Ax3(point(low), direction(axis), direction(radial)),
                    alpha,
                    float(F(arcs[0]["curve"]["radius"])),
                )
                builder = BRepBuilderAPI_MakeFace(
                    cone, 0.0, math.pi / 2, 0.0, float(height) / math.cos(alpha)
                )
            else:
                cylinder = gp_Cylinder(
                    gp_Ax3(point(low), direction(axis), direction(radial)),
                    float(F(surface["radius"])),
                )
                builder = BRepBuilderAPI_MakeFace(
                    cylinder, 0.0, math.pi / 2, 0.0, float(height)
                )
            native = builder.Face()
            if surface.get("inward", False):
                native = TopoDS.Face(native.Reversed())
        if not builder.IsDone() or not BRepCheck_Analyzer(native).IsValid():
            raise RuntimeError("Invalid translated shared face")
        converted.append(native)
    parts = []
    for component in topology["components"]:
        sewing = BRepBuilderAPI_Sewing(1e-7)
        for i in component:
            sewing.Add(converted[i])
        sewing.Perform()
        solid = BRepBuilderAPI_MakeSolid()
        explorer = TopExp_Explorer(sewing.SewedShape(), TopAbs_SHELL)
        count = 0
        while explorer.More():
            solid.Add(TopoDS.Shell(explorer.Current()))
            explorer.Next()
            count += 1
        if not count or not solid.IsDone():
            raise RuntimeError("Shared boundary did not produce component shells")
        native = solid.Solid()
        if (
            not BRepLib.OrientClosedSolid_s(native)
            or not BRepCheck_Analyzer(native).IsValid()
        ):
            raise RuntimeError("Shared boundary did not produce a valid solid")
        parts.append(native)
    if len(parts) == 1:
        return parts[0]
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for part in parts:
        builder.Add(compound, part)
    return compound
