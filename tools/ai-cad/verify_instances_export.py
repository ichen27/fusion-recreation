"""Independent world-space STEP comparisons for linked part placements."""

import argparse
import json
from pathlib import Path
import tempfile
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from store import ROOT, evaluate
from step_export import export_step, measure
from verify_boolean_export import oracle, area
from test_concave_operations import l_shape
from test_instances import instance
from test_booleans import cases
from test_polyhedral_transforms import turned

EXAMPLE = ROOT / "examples/ai-cad/linked-instances"


def scenarios():
    profile = l_shape()
    cavity, volume, count = cases()["cavity"]
    split, split_volume, split_count = cases()["split"]
    return {
        "concave_copy": (instance(profile), 204, 1),
        "nested_copy": (
            instance(instance(profile), name="nested", offset=(0, 15, 0)),
            204,
            1,
        ),
        "cavity_copy": (instance(cavity), volume, count),
        "split_copy": (instance(split), split_volume, split_count),
        "turned_copy": (turned(instance(profile), "x", 1), 204, 1),
    }


def main(write=False):
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        for name, (model, expected, count) in scenarios().items():
            body = next(
                b
                for b in evaluate(model)["bodies"]
                if b["feature_id"] == model["features"][-1]["id"]
            )
            path = Path(directory) / (name + ".step")
            result = export_step(body, path)
            assert result["solid_count"] == count
            reader = STEPControl_Reader()
            assert (
                reader.ReadFile(str(path)) == IFSelect_RetDone
                and reader.TransferRoots()
            )
            actual, reference = reader.OneShape(), oracle(model)
            assert (
                BRepCheck_Analyzer(actual).IsValid()
                and BRepCheck_Analyzer(reference).IsValid()
            )
            residues = []
            for a, b in [(actual, reference), (reference, actual)]:
                difference = BRepAlgoAPI_Cut(a, b)
                assert difference.IsDone()
                residues.append(abs(measure(difference.Shape())))
            assert max(residues) < 1e-7 and abs(measure(actual) - expected) < 1e-7
            assert abs(area(actual) - area(reference)) < 1e-7
            rows.append(
                dict(
                    case=name,
                    expected_volume_mm3=expected,
                    step_volume_mm3=measure(actual),
                    material_components=count,
                    directed_residue_mm3=residues,
                    surface_difference_mm2=abs(area(actual) - area(reference)),
                )
            )
            if write:
                EXAMPLE.mkdir(parents=True, exist_ok=True)
                (EXAMPLE / path.name).write_bytes(path.read_bytes())
                (EXAMPLE / (name + ".model.json")).write_text(
                    json.dumps(model, indent=2) + "\n"
                )
    if write:
        (EXAMPLE / "step-comparison.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps(rows, indent=2))
    print(
        "PASS: five linked-instance STEP exports match independently placed source geometry"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
