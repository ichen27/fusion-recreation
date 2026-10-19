"""Independent STEP checks for moved/turned holed, cavity and split results."""

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
from test_booleans import cases
from test_polyhedral_transforms import moved, turned

EXAMPLE = ROOT / "examples/ai-cad/planar-transforms"


def main(write=False):
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        for name in ["through", "cavity", "split"]:
            model, expected, count = cases()[name]
            model = turned(moved(model, (10, -5, 3)), "x", 1, (10, -5, 3))
            body = evaluate(model)["bodies"][0]
            path = Path(directory) / (name + ".step")
            result = export_step(body, path)
            assert result["solid_count"] == count
            reader = STEPControl_Reader()
            assert (
                reader.ReadFile(str(path)) == IFSelect_RetDone
                and reader.TransferRoots()
            )
            actual = reader.OneShape()
            reference = oracle(model)
            assert (
                BRepCheck_Analyzer(actual).IsValid()
                and BRepCheck_Analyzer(reference).IsValid()
            )
            residues = []
            for a, b in [(actual, reference), (reference, actual)]:
                cut = BRepAlgoAPI_Cut(a, b)
                assert cut.IsDone()
                residues.append(abs(measure(cut.Shape())))
            assert max(residues) < 1e-7
            assert (
                abs(measure(actual) - expected) < 1e-7
                and abs(area(actual) - area(reference)) < 1e-7
            )
            rows.append(
                dict(
                    case=name,
                    expected_volume_mm3=expected,
                    step_volume_mm3=measure(actual),
                    material_components=count,
                    directed_residue_mm3=residues,
                    area_difference_mm2=abs(area(actual) - area(reference)),
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
        "PASS: moved/turned holed, cavity and split STEP results match independent transforms and Boolean references"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
