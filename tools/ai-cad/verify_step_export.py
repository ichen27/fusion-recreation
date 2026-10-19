"""Independent OCCT reference subtraction and STEP surface/location checks."""

import argparse
from fractions import Fraction
import json
import math
from pathlib import Path
import tempfile
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.GeomAbs import GeomAbs_Cylinder
from OCP.STEPControl import STEPControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.TopAbs import TopAbs_OUT, TopAbs_IN
from OCP.gp import gp_Pnt, gp_Ax2, gp_Dir
from exports import export_stl
from step_export import export_step, faces, measure
from store import ROOT, Store, evaluate, EMPTY
from test_holes import perforated
from test_profiles import model_for
from test_contract import CREATE
from test_holes import read_stl, audit_triangles


def verify(path, expected, params):
    reader = STEPControl_Reader()
    assert reader.ReadFile(str(path)) == IFSelect_RetDone
    assert reader.TransferRoots()
    imported = reader.OneShape()
    p = {k: float(Fraction(v)) for k, v in params.items()}
    expected_circles = [
        (p["margin"], p["margin"], p["radius"]),
        (p["right_x"], p["margin"], p["radius"]),
        (p["center_x"], p["top_y"], p["radius"]),
    ]
    actual = []
    for face in faces(imported):
        surface = BRepAdaptor_Surface(face)
        if surface.GetType() == GeomAbs_Cylinder:
            cylinder = surface.Cylinder()
            point = cylinder.Location()
            direction = cylinder.Axis().Direction()
            assert abs(direction.Z()) > 1 - 1e-12
            actual.append((point.X(), point.Y(), cylinder.Radius()))
    assert len(actual) == 3
    for actual_circle, expected_circle in zip(sorted(actual), sorted(expected_circles)):
        assert max(abs(a - b) for a, b in zip(actual_circle, expected_circle)) < 1e-9
    # Oracle modeling operations are used only here, never in the exporter.
    oracle = BRepPrimAPI_MakeBox(p["width"], p["depth"], p["thickness"]).Shape()
    for x, y, r in expected_circles:
        tool = BRepPrimAPI_MakeCylinder(
            gp_Ax2(gp_Pnt(x, y, 0), gp_Dir(0, 0, 1)), r, p["thickness"]
        ).Shape()
        cut = BRepAlgoAPI_Cut(oracle, tool)
        cut.Build()
        assert cut.IsDone()
        oracle = cut.Shape()
        assert (
            BRepClass3d_SolidClassifier(
                imported, gp_Pnt(x, y, p["thickness"] / 2), 1e-7
            ).State()
            == TopAbs_OUT
        )
    assert (
        BRepClass3d_SolidClassifier(
            imported, gp_Pnt(p["width"] / 2, p["depth"] / 2, p["thickness"] / 2), 1e-7
        ).State()
        == TopAbs_IN
    )
    volume = measure(imported)
    reference = measure(oracle)
    assert abs(volume - reference) < 1e-6
    assert abs(volume - expected) < 1e-6
    return {
        "volume_mm3": volume,
        "oracle_volume_mm3": reference,
        "volume_error_mm3": abs(volume - reference),
        "cylinders": actual,
        "hole_centers_outside_solid": True,
        "material_point_inside": True,
    }


def main(write=False):
    example = ROOT / "examples/ai-cad/bracket"
    rows = []
    with tempfile.TemporaryDirectory() as d:
        store = Store(Path(d) / "part.json")
        for name in ("create", "widen"):
            state = store.execute(json.loads((example / f"{name}.json").read_text()))
            body = state["bodies"][0]
            v = body["analytic"]["volume"]
            expected = float(Fraction(v["constant_mm3"])) - math.pi * float(
                Fraction(v["pi_subtract_mm3"])
            )
            path = Path(d) / f"{name}.step"
            export_step(body, path)
            result = verify(path, expected, state["model"]["parameters"])
            data, mesh = export_stl(store, state["revision"], "bracket")
            result.update(
                stage=name,
                stl_volume_mm3=audit_triangles(read_stl(data), 3),
                stl_triangles=len(mesh["triangles"]),
                max_radial_error_mm=mesh["max_radial_error_mm"],
            )
            rows.append(result)
            try:
                export_step(body, path)
            except FileExistsError:
                pass
            else:
                raise AssertionError("Export overwrote existing file")
        # Other advertised families: old planar corner-cut, sloped outer walls,
        # and a precision case accepted by Rust but refused by this adapter.
        planar = evaluate(EMPTY, CREATE["operations"])["bodies"][0]
        export_step(planar, Path(d) / "corner.step")
        m = model_for([(0, 20), (20, 0), (40, 20), (20, 40)], "3")
        m["parameters"].update(x="10", x2="30", y="20", r="3")
        m["features"].append(perforated()["features"][-1])
        diamond = evaluate(m)["bodies"][0]
        export_step(diamond, Path(d) / "diamond.step")
        m["parameters"]["r"] = "1/100000000"
        tiny = evaluate(m)["bodies"][0]
        try:
            export_step(tiny, Path(d) / "tiny.step")
        except RuntimeError:
            assert not (Path(d) / "tiny.step").exists()
        else:
            raise AssertionError("Sub-tolerance STEP radius was accepted")
        verify(example / "bracket.step", expected, state["model"]["parameters"])
        archived_triangles = read_stl((example / "bracket.stl").read_bytes())
        # libm trig rounding can differ across macOS/Linux. Verify the delivered
        # artifact geometrically rather than requiring platform-specific bytes.
        assert len(archived_triangles) == len(mesh["triangles"])
        assert (
            abs(audit_triangles(archived_triangles, 3) - result["stl_volume_mm3"])
            < 1e-6
        )
    report = {
        "cases": rows,
        "step_adapter": "cadquery-ocp 8.0.1.1.0; analytic boundary translation only",
        "stl": "128 inscribed chords per circle; mm; float64 ASCII",
        "limits": "This corpus covers the published flat bracket. It is not proof of all geometric inputs or a fabrication certification.",
    }
    if write:
        (example / "export-validation.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
