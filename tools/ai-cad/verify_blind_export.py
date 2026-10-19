"""Independent blind-hole STEP surfaces, floor containment and solid-cut oracle."""

import argparse
from fractions import Fraction
import json
import math
from pathlib import Path
import tempfile

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeBox
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_IN, TopAbs_OUT
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

from step_export import export_step, faces, measure, translate
from exports import export_stl
from store import ROOT, Store, evaluate
from test_blind_holes import blind, perforated, flange
from test_holes import audit_triangles, read_stl

EXAMPLE = ROOT / "examples/ai-cad/blind-holes"


def num(s):
    return float(Fraction(s))


def verify(path, body):
    shape = body["analytic"]
    h = num(shape["height"])
    d = num(shape["hole_depth"])
    floor = h - d
    reader = STEPControl_Reader()
    assert reader.ReadFile(str(path)) == IFSelect_RetDone
    assert reader.TransferRoots()
    imported = reader.OneShape()
    outer = shape.get("outer_circle")
    if outer:
        x, y = map(num, outer["center"])
        r = num(outer["radius"])
        oracle = BRepPrimAPI_MakeCylinder(
            gp_Ax2(gp_Pnt(x, y, 0), gp_Dir(0, 0, 1)), r, h
        ).Shape()
    else:
        # Independent rectangular fixture, not reconstruction from the exported faces.
        oracle = BRepPrimAPI_MakeBox(100, 60, 6).Shape()
    cylinders = []
    floor_planes = 0
    for face in faces(imported):
        s = BRepAdaptor_Surface(face)
        if s.GetType() == GeomAbs_Cylinder:
            c = s.Cylinder()
            p = c.Location()
            assert abs(c.Axis().Direction().Z()) > 1 - 1e-12
            cylinders.append([p.X(), p.Y(), c.Radius()])
        elif s.GetType() == GeomAbs_Plane:
            p = s.Plane()
            if (
                abs(abs(p.Axis().Direction().Z()) - 1) < 1e-12
                and abs(p.Location().Z() - floor) < 1e-8
            ):
                floor_planes += 1
    circles = [[*map(num, c["center"]), num(c["radius"])] for c in shape["holes"]]
    expected_cylinders = circles + ([[x, y, r]] if outer else [])
    assert len(cylinders) == len(expected_cylinders)
    for a, b in zip(sorted(cylinders), sorted(expected_cylinders)):
        assert max(abs(u - v) for u, v in zip(a, b)) < 1e-8
    assert floor_planes == len(circles)
    for x, y, r in circles:
        tool = BRepPrimAPI_MakeCylinder(
            gp_Ax2(gp_Pnt(x, y, floor), gp_Dir(0, 0, 1)), r, d
        ).Shape()
        cut = BRepAlgoAPI_Cut(oracle, tool)
        cut.Build()
        assert cut.IsDone()
        oracle = cut.Shape()
        for z, state in [
            (floor / 2, TopAbs_IN),
            (floor + d / 2, TopAbs_OUT),
            (-1, TopAbs_OUT),
            (h + 1, TopAbs_OUT),
        ]:
            assert (
                BRepClass3d_SolidClassifier(imported, gp_Pnt(x, y, z), 1e-7).State()
                == state
            )
    exact = (
        num(shape["volume"]["constant_mm3"])
        - num(shape["volume"]["pi_subtract_mm3"]) * math.pi
    )
    volume, reference = measure(imported), measure(oracle)
    assert abs(volume - reference) < 1e-6 and abs(volume - exact) < 1e-6
    return dict(
        volume_mm3=volume,
        oracle_volume_mm3=reference,
        error_mm3=abs(volume - reference),
        hole_depth_mm=d,
        remaining_floor_mm=floor,
        cylinders=cylinders,
        floor_faces=floor_planes,
        material_below_holes=True,
        void_above_floors=True,
    )


def main(write=False):
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for name, m in [
            ("rectangular", blind(perforated())),
            ("round", blind(flange())),
            ("deeper", blind(flange(), "4")),
        ]:
            body = evaluate(m)["bodies"][0]
            path = root / f"{name}.step"
            export_step(body, path)
            row = {"case": name, **verify(path, body)}
            if write and name == "deeper":
                (EXAMPLE / "part.step").write_bytes(path.read_bytes())
            rows.append(row)
        store = Store(root / "part.json")
        for name in ["create", "deeper"]:
            store.execute(json.loads((EXAMPLE / f"{name}.json").read_text()))
        data, mesh = export_stl(store, 2, "flange", 128)
        volume = audit_triangles(read_stl(data), 0)
        expected = 7528 * 128 * math.sin(2 * math.pi / 128) / 2
        assert abs(volume - expected) < 1e-6
        if write:
            (EXAMPLE / "part.stl").write_bytes(data)
            (EXAMPLE / "export-validation.json").write_text(
                json.dumps(
                    {
                        "step": rows,
                        "stl_volume_mm3": volume,
                        "max_radial_error_mm": mesh["max_radial_error_mm"],
                    },
                    indent=2,
                )
                + "\n"
            )
        for depth in ["1/10000000", "49999999/10000000"]:
            try:
                translate(evaluate(blind(flange(), depth))["bodies"][0])
            except RuntimeError as e:
                assert "blind depth" in str(e)
            else:
                raise AssertionError("sub-tolerance depth/floor accepted")
    print(
        "PASS: independent blind STEP floor/wall/volume oracle, material/void classification and closed STL topology"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--write", action="store_true")
    main(p.parse_args().write)
