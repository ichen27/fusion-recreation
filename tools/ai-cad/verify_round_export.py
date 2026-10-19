"""Independent circular-stock STEP surface, containment and subtraction oracle."""

import argparse
from fractions import Fraction
import json
import math
from pathlib import Path
import tempfile

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCP.GeomAbs import GeomAbs_Cylinder
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_IN, TopAbs_OUT
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

from exports import export_stl
from step_export import export_step, faces, measure
from store import ROOT, Store, evaluate
from test_holes import audit_triangles, read_stl
from test_round_stock import cylinder, flange

EXAMPLE = ROOT / "examples/ai-cad/round-flange"


def verify(path, body):
    shape = body["analytic"]
    outer = shape["outer_circle"]
    x, y = (float(Fraction(v)) for v in outer["center"])
    r, h = (float(Fraction(v)) for v in (outer["radius"], shape["height"]))
    circles = [(x, y, r)] + [
        (
            float(Fraction(c["center"][0])),
            float(Fraction(c["center"][1])),
            float(Fraction(c["radius"])),
        )
        for c in shape["holes"]
    ]
    reader = STEPControl_Reader()
    assert reader.ReadFile(str(path)) == IFSelect_RetDone
    assert reader.TransferRoots()
    imported = reader.OneShape()
    actual = []
    for face in faces(imported):
        surface = BRepAdaptor_Surface(face)
        if surface.GetType() == GeomAbs_Cylinder:
            c = surface.Cylinder()
            center = c.Location()
            assert abs(c.Axis().Direction().Z()) > 1 - 1e-12
            actual.append((center.X(), center.Y(), c.Radius()))
    assert len(actual) == len(circles)
    for a, b in zip(sorted(actual), sorted(circles)):
        assert max(abs(u - v) for u, v in zip(a, b)) < 1e-9
    # Solid subtraction is used only in this independent verification oracle.
    oracle = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(x, y, 0), gp_Dir(0, 0, 1)), r, h
    ).Shape()
    for hx, hy, hr in circles[1:]:
        tool = BRepPrimAPI_MakeCylinder(
            gp_Ax2(gp_Pnt(hx, hy, 0), gp_Dir(0, 0, 1)), hr, h
        ).Shape()
        cut = BRepAlgoAPI_Cut(oracle, tool)
        cut.Build()
        assert cut.IsDone()
        oracle = cut.Shape()
        assert (
            BRepClass3d_SolidClassifier(imported, gp_Pnt(hx, hy, h / 2), 1e-7).State()
            == TopAbs_OUT
        )
    assert (
        BRepClass3d_SolidClassifier(imported, gp_Pnt(x, y + r / 2, h / 2), 1e-7).State()
        == TopAbs_IN
    )
    assert (
        BRepClass3d_SolidClassifier(imported, gp_Pnt(x + r + 1, y, h / 2), 1e-7).State()
        == TopAbs_OUT
    )
    expected = -float(Fraction(shape["volume"]["pi_subtract_mm3"])) * math.pi
    volume, reference = measure(imported), measure(oracle)
    assert abs(volume - reference) < 1e-6
    assert abs(volume - expected) < 1e-6
    return dict(
        volume_mm3=volume,
        oracle_volume_mm3=reference,
        error_mm3=abs(volume - reference),
        cylinders=actual,
        holes_outside=True,
        material_inside=True,
        outside_stock_empty=True,
    )


def main(write=False):
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory) / "part.json")
        for name in ("create", "grow"):
            state = store.execute(json.loads((EXAMPLE / f"{name}.json").read_text()))
            body = state["bodies"][0]
            path = Path(directory) / f"{name}.step"
            export_step(body, path)
            row = verify(path, body)
            stl, mesh = export_stl(store, state["revision"], "flange")
            volume = audit_triangles(read_stl(stl), 3)
            coefficient = -float(
                Fraction(body["analytic"]["volume"]["pi_subtract_mm3"])
            )
            assert (
                abs(volume - coefficient * 128 * math.sin(2 * math.pi / 128) / 2) < 1e-6
            )
            row.update(
                stage=name,
                stl_volume_mm3=volume,
                triangles=len(mesh["triangles"]),
                max_radial_error_mm=mesh["max_radial_error_mm"],
            )
            rows.append(row)
        if write:
            (EXAMPLE / "flange.step").write_bytes(path.read_bytes())
            (EXAMPLE / "flange.stl").write_bytes(stl)
        else:
            verify(EXAMPLE / "flange.step", body)
            assert (
                abs(
                    audit_triangles(read_stl((EXAMPLE / "flange.stl").read_bytes()), 3)
                    - volume
                )
                < 1e-6
            )
        # Offset stock without holes exercises the independent circular outer wire.
        plain = evaluate(cylinder("10", "-20"))["bodies"][0]
        target = Path(directory) / "plain.step"
        export_step(plain, target)
        verify(target, plain)
        tiny = flange()
        tiny["parameters"]["right"] = str(Fraction(37) - Fraction(1, 10**10))
        target = Path(directory) / "too-close.step"
        try:
            export_step(evaluate(tiny)["bodies"][0], target)
        except RuntimeError:
            assert not target.exists()
        else:
            raise AssertionError("Sub-tolerance outer-circle gap accepted")
    report = dict(
        cases=rows,
        step_adapter="cadquery-ocp 8.0.1.1.0; boundary translation only",
        oracle="Independent solid cylinder minus hole cylinders; verification only",
        limits="Bounded axial round-prism corpus, not general curved Boolean operations or fabrication certification",
    )
    if write:
        (EXAMPLE / "export-validation.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
