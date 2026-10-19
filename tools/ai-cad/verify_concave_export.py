"""Compare concave STEP exports with an independently constructed solid."""

import argparse
from fractions import Fraction
import json
import math
from pathlib import Path
import tempfile

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.GeomAbs import GeomAbs_Cylinder
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_IN, TopAbs_OUT
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

from exports import export_stl
from step_export import export_step, faces, measure
from store import ROOT, Store, evaluate
from test_holes import audit_triangles, read_stl
from test_planar_profiles import drill, planar

EXAMPLE = ROOT / "examples/ai-cad/concave-profile"


def verify(path, parameters):
    p = {k: float(Fraction(v)) for k, v in parameters.items()}
    w, d, leg, h, r = (p[k] for k in ("width", "depth", "leg", "thickness", "radius"))
    reader = STEPControl_Reader()
    assert reader.ReadFile(str(path)) == IFSelect_RetDone
    assert reader.TransferRoots()
    imported = reader.OneShape()
    # Boolean operations belong only to the independent verification oracle.
    fuse = BRepAlgoAPI_Fuse(
        BRepPrimAPI_MakeBox(w, leg, h).Shape(),
        BRepPrimAPI_MakeBox(leg, d, h).Shape(),
    )
    fuse.Build()
    assert fuse.IsDone()
    oracle = fuse.Shape()
    circles = [(p["right_x"], p["margin"], r), (p["margin"], p["top_y"], r)]
    for x, y, radius in circles:
        tool = BRepPrimAPI_MakeCylinder(
            gp_Ax2(gp_Pnt(x, y, 0), gp_Dir(0, 0, 1)), radius, h
        ).Shape()
        cut = BRepAlgoAPI_Cut(oracle, tool)
        cut.Build()
        assert cut.IsDone()
        oracle = cut.Shape()
        assert (
            BRepClass3d_SolidClassifier(imported, gp_Pnt(x, y, h / 2), 1e-7).State()
            == TopAbs_OUT
        )
    assert (
        BRepClass3d_SolidClassifier(imported, gp_Pnt(w / 2, d / 2, h / 2), 1e-7).State()
        == TopAbs_OUT
    )
    assert (
        BRepClass3d_SolidClassifier(
            imported, gp_Pnt(leg / 2, leg / 2, h / 2), 1e-7
        ).State()
        == TopAbs_IN
    )
    actual = []
    for face in faces(imported):
        surface = BRepAdaptor_Surface(face)
        if surface.GetType() == GeomAbs_Cylinder:
            cylinder = surface.Cylinder()
            center = cylinder.Location()
            assert abs(cylinder.Axis().Direction().Z()) > 1 - 1e-12
            actual.append((center.X(), center.Y(), cylinder.Radius()))
    assert len(actual) == len(circles)
    for a, b in zip(sorted(actual), sorted(circles)):
        assert max(abs(x - y) for x, y in zip(a, b)) < 1e-9
    expected = (w * leg + (d - leg) * leg) * h - 2 * math.pi * r * r * h
    volume, reference = measure(imported), measure(oracle)
    assert abs(volume - reference) < 1e-6
    assert abs(volume - expected) < 1e-6
    return dict(
        volume_mm3=volume,
        oracle_volume_mm3=reference,
        error_mm3=abs(volume - reference),
        cylinders=actual,
        notch_and_holes_outside=True,
        material_point_inside=True,
    )


def main(write=False):
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory) / "part.json")
        for name in ("create", "widen"):
            state = store.execute(json.loads((EXAMPLE / f"{name}.json").read_text()))
            path = Path(directory) / f"{name}.step"
            export_step(state["bodies"][0], path)
            row = verify(path, state["model"]["parameters"])
            stl, mesh = export_stl(store, state["revision"], "mount")
            row.update(
                stage=name,
                stl_volume_mm3=audit_triangles(read_stl(stl), 2),
                triangles=len(mesh["triangles"]),
                max_radial_error_mm=mesh["max_radial_error_mm"],
            )
            rows.append(row)
        if write:
            (EXAMPLE / "mount.step").write_bytes(path.read_bytes())
            (EXAMPLE / "mount.stl").write_bytes(stl)
        else:
            verify(EXAMPLE / "mount.step", state["model"]["parameters"])
            assert (
                abs(
                    audit_triangles(read_stl((EXAMPLE / "mount.stl").read_bytes()), 2)
                    - row["stl_volume_mm3"]
                )
                < 1e-6
            )
        # Also translate a no-hole concave prism and a circle near an inward corner.
        for name, model in (
            ("plain", planar()),
            ("reflex", drill(planar(), "15", "15", "7")),
        ):
            body = evaluate(model)["bodies"][0]
            export_step(body, Path(directory) / f"{name}.step")
        # Exact positive clearance can still be below the floating adapter limit.
        tiny = drill(planar(), "17", "16", str(Fraction(5) - Fraction(1, 10**10)))
        target = Path(directory) / "too-close.step"
        try:
            export_step(evaluate(tiny)["bodies"][0], target)
        except RuntimeError:
            assert not target.exists()
        else:
            raise AssertionError("Sub-tolerance inward-corner clearance accepted")
    report = dict(
        cases=rows,
        step_adapter="cadquery-ocp 8.0.1.1.0; boundary translation",
        oracle="Union of two boxes minus two cylinders; verification only",
        limits="Bounded L-shaped plate corpus, not general Boolean or manufacturing certification",
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
