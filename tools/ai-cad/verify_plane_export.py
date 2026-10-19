"""Independent sequential half-space intersection and exported boundary checks."""

import argparse
from fractions import Fraction as F
import json
from pathlib import Path
import tempfile
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepPrimAPI import BRepPrimAPI_MakeHalfSpace, BRepPrimAPI_MakeBox
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.GeomAbs import GeomAbs_Plane
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_IN, TopAbs_OUT
from OCP.gp import gp_Pnt, gp_Dir, gp_Pln
from store import ROOT, Store
from step_export import export_step, faces, measure
from exports import export_stl
from test_holes import audit_triangles, read_stl

EXAMPLE = ROOT / "examples/ai-cad/plane-cuts"


def main(write=False):
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store = Store(root / "part.json")
        for name in ["create", "resize"]:
            result = store.execute(json.loads((EXAMPLE / f"{name}.json").read_text()))
            model = result["model"]
            body = result["bodies"][0]
            path = root / f"{name}.step"
            export_step(body, path)
            reader = STEPControl_Reader()
            assert reader.ReadFile(str(path)) == IFSelect_RetDone
            assert reader.TransferRoots()
            imported = reader.OneShape()
            size = float(F(model["parameters"]["size"]))
            oracle = BRepPrimAPI_MakeBox(size, size, size).Shape()
            planes = []
            for feature in model["features"]:
                if feature["kind"] != "plane_cut":
                    continue
                n = list(map(lambda v: float(F(v)), feature["normal"]))
                offset = float(F(model["parameters"][feature["offset"]]))
                nn = sum(x * x for x in n)
                point = [offset * x / nn for x in n]
                face = BRepBuilderAPI_MakeFace(
                    gp_Pln(gp_Pnt(*point), gp_Dir(*n))
                ).Face()
                half = BRepPrimAPI_MakeHalfSpace(
                    face, gp_Pnt(*(p - x / nn**0.5 for p, x in zip(point, n)))
                ).Solid()
                intersection = BRepAlgoAPI_Common(oracle, half)
                assert intersection.IsDone()
                oracle = intersection.Shape()
                assert BRepCheck_Analyzer(oracle).IsValid()
                planes.append((n, offset))
            v, reference = measure(imported), measure(oracle)
            exact = float(F(body["volume_mm3"]))
            assert abs(v - reference) < 1e-6 and abs(v - exact) < 1e-6
            actual = []
            for face in faces(imported):
                surface = BRepAdaptor_Surface(face)
                assert surface.GetType() == GeomAbs_Plane
                plane = surface.Plane()
                p = plane.Location()
                n = plane.Axis().Direction()
                actual.append(([n.X(), n.Y(), n.Z()], [p.X(), p.Y(), p.Z()]))
            assert len(actual) == 4
            for n, offset in planes:
                assert any(
                    abs(sum(a * b for a, b in zip(n, p)) - offset) < 1e-8
                    and abs(
                        abs(sum(a * b for a, b in zip(n, d)))
                        / sum(a * a for a in n) ** 0.5
                        - 1
                    )
                    < 1e-8
                    for d, p in actual
                )
            for point, state in [
                ((20, 5, 5), TopAbs_IN),
                ((5, 5, 5), TopAbs_OUT),
                ((50, 20, 20), TopAbs_OUT),
            ]:
                assert (
                    BRepClass3d_SolidClassifier(imported, gp_Pnt(*point), 1e-7).State()
                    == state
                )
            data, mesh = export_stl(store, result["revision"], "side_cut", 64)
            stl_volume = audit_triangles(read_stl(data), 0)
            assert abs(stl_volume - exact) < 1e-7
            rows.append(
                dict(
                    stage=name,
                    volume_mm3=v,
                    oracle_volume_mm3=reference,
                    error_mm3=abs(v - reference),
                    planes=len(actual),
                    material_and_removed_regions_checked=True,
                    stl_volume_mm3=stl_volume,
                    stl_triangles=len(mesh["triangles"]),
                )
            )
            if write and name == "resize":
                (EXAMPLE / "part.step").write_bytes(path.read_bytes())
                (EXAMPLE / "part.stl").write_bytes(data)
        if write:
            (EXAMPLE / "export-validation.json").write_text(
                json.dumps(rows, indent=2) + "\n"
            )
    print(
        "PASS: sequential independent half-space oracle, STEP plane/volume/containment, closed STL"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--write", action="store_true")
    main(p.parse_args().write)
