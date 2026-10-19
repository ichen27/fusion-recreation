"""Translate supplied conical supports and circular caps; no solid Boolean."""

import math
from fractions import Fraction
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeWire,
    BRepBuilderAPI_MakeFace,
)
from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2, gp_Ax3, gp_Circ, gp_Cone
from OCP.TopoDS import TopoDS


def conical_faces(shape):
    circle = shape["outer_circle"]
    x, y = [float(Fraction(v)) for v in circle["center"]]
    bottom, top, height = [
        float(Fraction(v))
        for v in (circle["radius"], shape["top_radius"], shape["height"])
    ]
    if min(bottom, top, height, abs(top - bottom)) <= 1e-6:
        raise RuntimeError(
            "STEP frustum adapter requires radii, height and radius difference above 1e-6 mm"
        )
    alpha = math.atan2(top - bottom, height)
    cone = gp_Cone(gp_Ax3(gp_Pnt(x, y, 0), gp_Dir(0, 0, 1)), alpha, bottom)
    wall = BRepBuilderAPI_MakeFace(cone, 0.0, math.tau, 0.0, height / math.cos(alpha))
    if not wall.IsDone():
        raise RuntimeError("STEP conical wall construction failed")
    result = [wall.Face()]
    for z, radius, up in [(0, bottom, False), (height, top, True)]:
        edge = BRepBuilderAPI_MakeEdge(
            gp_Circ(gp_Ax2(gp_Pnt(x, y, z), gp_Dir(0, 0, 1)), radius)
        ).Edge()
        wire = BRepBuilderAPI_MakeWire(edge).Wire()
        face = BRepBuilderAPI_MakeFace(wire, True)
        if not face.IsDone():
            raise RuntimeError("STEP circular cap construction failed")
        result.append(face.Face() if up else TopoDS.Face(face.Face().Reversed()))
    return result
