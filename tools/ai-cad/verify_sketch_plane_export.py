"""Compare exported sketch cuts with an independent box/half-space oracle."""

import argparse
import json
from pathlib import Path
import tempfile
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeHalfSpace
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from OCP.gp import gp_Pnt, gp_Dir, gp_Pln
from store import Store
from step_export import export_step, measure
from verify_sketch_plane import EXAMPLE


def main(write=False):
    results = []
    with tempfile.TemporaryDirectory() as directory:
        for stage, exact in [("cut", 108000), ("edited", 104000)]:
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
            oracle = BRepPrimAPI_MakeBox(100, 60, 20).Shape()
            planes = [([1, 0, 1], 100)]
            if stage == "edited":
                planes.append(([3, 1, 0], 300))
            for normal, offset in planes:
                nn = sum(x * x for x in normal)
                point = [offset * x / nn for x in normal]
                face = BRepBuilderAPI_MakeFace(
                    gp_Pln(gp_Pnt(*point), gp_Dir(*normal))
                ).Face()
                half = BRepPrimAPI_MakeHalfSpace(
                    face, gp_Pnt(*(p - x / nn**0.5 for p, x in zip(point, normal)))
                ).Solid()
                common = BRepAlgoAPI_Common(oracle, half)
                assert common.IsDone()
                oracle = common.Shape()
                assert BRepCheck_Analyzer(oracle).IsValid()
            actual, reference = measure(imported), measure(oracle)
            assert abs(actual - reference) < 1e-6 and abs(actual - exact) < 1e-6
            results.append(
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
        (EXAMPLE / "step-comparison.json").write_text(
            json.dumps(results, indent=2) + "\n"
        )
    print(json.dumps(results, indent=2))
    print(
        "PASS: native sketch-cut STEP validity and independent box/half-space volumes"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
