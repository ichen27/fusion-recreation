"""STEP positions and volumes match independent positioned boxes/intersections."""

import argparse
import json
from pathlib import Path
import tempfile
from OCP.BRep import BRep_Tool
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Pnt
from store import Store
from step_export import export_step, measure
from verify_rotation import EXAMPLE


def main(write=False):
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        for stage, angle, exact in [
            ("turned", 90, 8000),
            ("common", 90, 4000),
            ("edited", 180, 8000),
        ]:
            bodies = Store(EXAMPLE / (stage + ".cad.json")).execute(
                {"action": "inspect"}
            )["bodies"]
            body = next(
                b
                for b in bodies
                if b["feature_id"]
                == ("turn1" if stage == "turned" else "intersection1")
            )
            path = Path(directory) / (stage + ".step")
            export_step(body, path)
            reader = STEPControl_Reader()
            assert reader.ReadFile(str(path)) == IFSelect_RetDone
            assert reader.TransferRoots()
            imported = reader.OneShape()
            assert BRepCheck_Analyzer(imported).IsValid()
            oracle = (
                BRepPrimAPI_MakeBox(gp_Pnt(10, -10, 0), 20, 40, 10).Shape()
                if angle == 90
                else BRepPrimAPI_MakeBox(40, 20, 10).Shape()
            )
            if stage != "turned":
                common = BRepAlgoAPI_Common(
                    BRepPrimAPI_MakeBox(40, 20, 10).Shape(), oracle
                )
                assert common.IsDone()
                oracle = common.Shape()
            actual, reference = measure(imported), measure(oracle)
            assert abs(actual - reference) < 1e-6 and abs(actual - exact) < 1e-6
            explorer = TopExp_Explorer(imported, TopAbs_VERTEX)
            points = []
            while explorer.More():
                p = BRep_Tool.Pnt_s(TopoDS.Vertex(explorer.Current()))
                points.append([p.X(), p.Y(), p.Z()])
                explorer.Next()
            bounds = [
                [min(p[i] for p in points) for i in range(3)],
                [max(p[i] for p in points) for i in range(3)],
            ]
            expected = {
                "turned": [[10, -10, 0], [30, 30, 10]],
                "common": [[10, 0, 0], [30, 20, 10]],
                "edited": [[0, 0, 0], [40, 20, 10]],
            }[stage]
            assert all(
                abs(a - b) < 1e-8
                for aa, bb in zip(bounds, expected)
                for a, b in zip(aa, bb)
            )
            rows.append(
                {
                    "stage": stage,
                    "exact_volume_mm3": exact,
                    "step_volume_mm3": actual,
                    "oracle_volume_mm3": reference,
                    "difference_mm3": abs(actual - reference),
                    "bounds_mm": bounds,
                }
            )
            if write:
                (EXAMPLE / path.name).write_bytes(path.read_bytes())
    if write:
        (EXAMPLE / "step-comparison.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps(rows, indent=2))
    print("PASS: rotated/intersected STEP positions, validity and independent volumes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
