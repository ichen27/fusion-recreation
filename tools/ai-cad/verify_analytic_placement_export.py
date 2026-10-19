"""Independent analytic surfaces and world-space STEP comparisons for exact placements."""

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
from test_instances import instance
from test_polyhedral_transforms import moved, turned
from test_round_stock import cylinder, flange
from test_holes import perforated
from test_blind_holes import blind
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder
from step_export import faces

EXAMPLE = ROOT / "examples/ai-cad/analytic-placement"


def scenarios():
    return {
        "moved_cylinder": moved(cylinder(), (5, -2, 3)),
        "turned_flange": turned(moved(flange(), (5, -2, 3)), "x", 1),
        "turned_blind_flange": turned(moved(blind(flange()), (5, -2, 3)), "y", 1),
        "turned_plate": turned(moved(perforated(), (5, -2, 3)), "z", 1),
        "turned_blind_plate": turned(moved(blind(perforated()), (5, -2, 3)), "x", 1),
        "linked_flange": instance(flange(), offset=(100, 0, 0)),
    }


def main(write=False):
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        for name, model in scenarios().items():
            body = next(
                b
                for b in evaluate(model)["bodies"]
                if b["feature_id"] == model["features"][-1]["id"]
            )
            expected = measure(oracle(model))
            count = 1
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
            assert max(residues) < 1e-6 and abs(measure(actual) - expected) < 1e-6
            assert abs(area(actual) - area(reference)) < 1e-6
            cylinders = [
                BRepAdaptor_Surface(f).Cylinder()
                for f in faces(actual)
                if BRepAdaptor_Surface(f).GetType() == GeomAbs_Cylinder
            ]
            analytic = body["analytic"]
            assert len(cylinders) == len(analytic["holes"]) + int(
                "outer_circle" in analytic
            )
            axis = [row[2] for row in analytic["placement"]["axes"]]
            for cylinder_surface in cylinders:
                direction = cylinder_surface.Axis().Direction().Coord()
                assert abs(abs(sum(a * b for a, b in zip(axis, direction))) - 1) < 1e-10
            rows.append(
                dict(
                    case=name,
                    expected_volume_mm3=expected,
                    step_volume_mm3=measure(actual),
                    material_components=count,
                    analytic_cylinder_count=len(cylinders),
                    cylinder_axis=axis,
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
        "PASS: six analytic placement STEP exports preserve cylinders and match independent world-space solids"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
