"""Independent positive-volume common operation and STEP shape comparison."""

import argparse
import json
from pathlib import Path
import tempfile
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakePrism
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from OCP.gp import gp_Pnt, gp_Vec
from store import Store
from step_export import export_step, measure
from verify_intersection import EXAMPLE


def main(write=False):
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        for stage, intercept, exact in [("common", 60, 28000), ("edited", 50, 23000)]:
            body = Store(EXAMPLE / (stage + ".cad.json")).execute(
                {"action": "inspect"}
            )["bodies"][0]
            path = Path(directory) / (stage + ".step")
            export_step(body, path)
            reader = STEPControl_Reader()
            assert reader.ReadFile(str(path)) == IFSelect_RetDone
            assert reader.TransferRoots()
            imported = reader.OneShape()
            assert BRepCheck_Analyzer(imported).IsValid()
            polygon = BRepBuilderAPI_MakePolygon()
            for x, y in [(0, 0), (intercept, 0), (0, intercept)]:
                polygon.Add(gp_Pnt(x, y, 0))
            polygon.Close()
            triangle = BRepPrimAPI_MakePrism(
                BRepBuilderAPI_MakeFace(polygon.Wire()).Face(), gp_Vec(0, 0, 30)
            ).Shape()
            common = BRepAlgoAPI_Common(
                BRepPrimAPI_MakeBox(40, 40, 20).Shape(), triangle
            )
            assert common.IsDone()
            oracle = common.Shape()
            assert BRepCheck_Analyzer(oracle).IsValid()
            actual, reference = measure(imported), measure(oracle)
            assert abs(actual - reference) < 1e-6 and abs(actual - exact) < 1e-6
            rows.append(
                {
                    "stage": stage,
                    "exact_volume_mm3": exact,
                    "step_volume_mm3": actual,
                    "oracle_volume_mm3": reference,
                    "difference_mm3": abs(actual - reference),
                }
            )
            if write:
                (EXAMPLE / path.name).write_bytes(path.read_bytes())
    if write:
        (EXAMPLE / "step-comparison.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps(rows, indent=2))
    print(
        "PASS: exported intersection STEP validity/volume vs independent box/triangular-prism Boolean"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
