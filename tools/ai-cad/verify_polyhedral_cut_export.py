"""Nonconvex half-space STEP results versus independent Boolean/half-space cuts."""

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
from test_booleans import cases, boolean, box
from test_polyhedral_cuts import cut
from test_polyhedral_transforms import moved, turned

EXAMPLE = ROOT / "examples/ai-cad/nonconvex-plane-cuts"


def scenarios():
    bridge = boolean(
        box("a", [0, 0, 0], [10, 10, 10]),
        box("b", [3, 3, -1], [7, 11, 11]),
        "difference",
    )
    return {
        "split_bridge": (cut(bridge, (0, -1, 0), -5), 300, 2),
        "open_cavity": (cut(cases()["cavity"][0]), 392, 1),
        "oblique_cavity": (cut(cases()["cavity"][0], (1, 1, 1), 15), 392, 1),
        "trim_hole": (cut(cases()["through"][0]), 320, 1),
        "open_hole": (cut(cases()["through"][0], (1, 0, 0), 5), 320, 1),
        "remove_piece": (cut(cases()["split"][0], (1, 0, 0), 5), 400, 1),
        "trim_pieces": (cut(cases()["split"][0]), 400, 2),
        "placed_hole": (
            cut(
                turned(moved(cases()["through"][0], (10, -5, 3)), "x", 1, (10, -5, 3)),
                (0, 1, 0),
                -10,
            ),
            320,
            1,
        ),
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
        "PASS: eight nonconvex cut STEP cases match independent half-space results, areas, component counts and directed residual volumes"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
