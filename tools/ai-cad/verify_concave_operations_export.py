"""Independent STEP comparisons for solid operations on initial concave profiles."""

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
from test_polyhedral_transforms import moved, turned
from test_polyhedral_cuts import cut
from test_booleans import boolean
from test_intersection import rectangle, prism

EXAMPLE = ROOT / "examples/ai-cad/concave-operations"


def scenarios():
    model = l_shape()
    tool = rectangle("b", 2, 2, 4, 4, 4)
    u = prism(
        "u", [(0, 0), (10, 0), (10, 10), (7, 10), (7, 3), (3, 3), (3, 10), (0, 10)], 2
    )
    return {
        "moved": (moved(model, (5, -2, 3)), 204, 1),
        "turned": (turned(model, "y", 1), 204, 1),
        "trimmed": (cut(model, (1, 0, 0), 5), 144, 1),
        "intersection": (boolean(model, tool, "intersection"), 28, 1),
        "difference": (boolean(model, tool, "difference"), 176, 1),
        "union": (boolean(model, tool, "union"), 240, 1),
        "split_profile": (cut(u, (0, -1, 0), -5), 60, 2),
    }


def main(write=False):
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        for name, (model, expected, count) in scenarios().items():
            body = evaluate(model)["bodies"][0]
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
        "PASS: seven initial-concave-profile STEP operations match independent Boolean/cut/transform geometry"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
