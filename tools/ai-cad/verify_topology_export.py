"""Translate explicit shared topology, then compare against independent solid operations."""

import argparse
import json
from pathlib import Path
import tempfile
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder
from OCP.STEPControl import STEPControl_Writer, STEPControl_Reader, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from topology import topology_model
from topology_step import translate
from step_export import measure, faces
from verify_boolean_export import oracle, area
from store import ROOT

EXAMPLE = ROOT / "examples/ai-cad/shared-topology"
CASES = {
    "counterbored": "counterbores/plate",
    "turned_counterbored": "counterbores/turned",
    "concave_counterbored": "counterbores/concave",
    "round_counterbored": "counterbores/linked_round",
    "blind_plate": "analytic-measurements/blind_plate",
    "cavity": "planar-booleans/cavity",
    "separate": "planar-booleans/separate",
    "through": "planar-booleans/through",
}


def main(write=False):
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        for name, source in CASES.items():
            model = json.loads(
                (ROOT / "examples/ai-cad" / (source + ".model.json")).read_text()
            )
            topology = topology_model(model, model["features"][-1]["id"])
            shape = translate(topology)
            reference = oracle(model)
            assert BRepCheck_Analyzer(shape).IsValid()
            path = Path(directory) / (name + ".step")
            Interface_Static.SetCVal_s("write.step.unit", "MM")
            writer = STEPControl_Writer()
            assert writer.Transfer(shape, STEPControl_AsIs) == IFSelect_RetDone
            assert writer.Write(str(path)) == IFSelect_RetDone
            reader = STEPControl_Reader()
            assert (
                reader.ReadFile(str(path)) == IFSelect_RetDone
                and reader.TransferRoots()
            )
            actual = reader.OneShape()
            assert BRepCheck_Analyzer(actual).IsValid()
            residuals = []
            for a, b in [(actual, reference), (reference, actual)]:
                cut = BRepAlgoAPI_Cut(a, b)
                assert cut.IsDone()
                residuals.append(abs(measure(cut.Shape())))
            volume_error = abs(measure(actual) - measure(reference))
            area_error = abs(area(actual) - area(reference))
            assert max([volume_error, area_error, *residuals]) < 1e-6, (
                name,
                residuals,
                volume_error,
                area_error,
            )
            cylinder_patches = sum(
                BRepAdaptor_Surface(f).GetType() == GeomAbs_Cylinder
                for f in faces(actual)
            )
            assert cylinder_patches == 4 * sum(
                s["kind"] == "cylinder" for s in topology["surfaces"].values()
            )
            rows.append(
                dict(
                    case=name,
                    vertices=len(topology["vertices"]),
                    edges=len(topology["edges"]),
                    faces=len(topology["faces"]),
                    surfaces=len(topology["surfaces"]),
                    shell_euler=topology["shell_euler"],
                    components=len(topology["components"]),
                    volume_error_mm3=volume_error,
                    area_error_mm2=area_error,
                    directed_residual_mm3=residuals,
                    cylinder_patches=cylinder_patches,
                )
            )
            if write:
                EXAMPLE.mkdir(parents=True, exist_ok=True)
                (EXAMPLE / path.name).write_bytes(path.read_bytes())
                for suffix, data in [("model", model), ("topology", topology)]:
                    (EXAMPLE / f"{name}.{suffix}.json").write_text(
                        json.dumps(data, indent=2) + "\n"
                    )
            else:
                assert topology == json.loads(
                    (EXAMPLE / f"{name}.topology.json").read_text()
                )
    if write:
        (EXAMPLE / "independent-comparison.json").write_text(
            json.dumps(rows, indent=2) + "\n"
        )
    print(
        f"PASS: {len(rows)} explicit shared boundaries, STEP readback, independent volume/area and directed residuals"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
