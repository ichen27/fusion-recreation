"""Translate supplied revolution boundary into analytic faces; never model by sweep."""

import math
from fractions import Fraction as F
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeWire,
    BRepBuilderAPI_MakeFace,
)
from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2, gp_Ax3, gp_Circ, gp_Cylinder
from OCP.TopoDS import TopoDS
from frustum_export import conical_wall


def faces(shape):
    points = [[F(v) for v in p] for p in shape["revolution"]["points"]]
    result = []

    def ring(radius, z):
        edge = BRepBuilderAPI_MakeEdge(
            gp_Circ(gp_Ax2(gp_Pnt(0, 0, float(z)), gp_Dir(0, 0, 1)), float(radius))
        ).Edge()
        return BRepBuilderAPI_MakeWire(edge).Wire()

    for a, b in zip(points, points[1:] + points[:1]):
        if a[0] == b[0] == 0:
            continue
        if a[1] == b[1]:
            outer, inner = max(a[0], b[0]), min(a[0], b[0])
            if float(outer - inner) <= 1e-6 or (inner and float(inner) <= 1e-6):
                raise RuntimeError(
                    "STEP revolution caps require positive radius/gaps above 1e-6 mm"
                )
            builder = BRepBuilderAPI_MakeFace(ring(outer, a[1]), True)
            if inner:
                builder.Add(TopoDS.Wire(ring(inner, a[1]).Reversed()))
            if not builder.IsDone():
                raise RuntimeError("STEP revolution cap construction failed")
            face = builder.Face()
            result.append(face if a[0] > b[0] else TopoDS.Face(face.Reversed()))
        else:
            inward = b[1] < a[1]
            low, high = (b, a) if inward else (a, b)
            height = high[1] - low[1]
            if min(float(low[0]), float(high[0]), float(height)) <= 1e-6:
                raise RuntimeError(
                    "STEP revolution walls require radii/heights above 1e-6 mm"
                )
            if low[0] != high[0]:
                result.append(
                    conical_wall(
                        0,
                        0,
                        float(low[1]),
                        float(low[0]),
                        float(high[0]),
                        float(height),
                        inward,
                    )
                )
            else:
                cylinder = gp_Cylinder(
                    gp_Ax3(gp_Pnt(0, 0, float(low[1])), gp_Dir(0, 0, 1)), float(low[0])
                )
                builder = BRepBuilderAPI_MakeFace(
                    cylinder, 0, math.tau, 0, float(height)
                )
                if not builder.IsDone():
                    raise RuntimeError("STEP revolution wall construction failed")
                face = builder.Face()
                result.append(TopoDS.Face(face.Reversed()) if inward else face)
    return result
