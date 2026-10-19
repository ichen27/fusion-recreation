"""Independent solid subtraction, STEP surfaces/shoulders and exact moments."""

import argparse
from fractions import Fraction as F
import json
from pathlib import Path
import tempfile
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_IN, TopAbs_OUT
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from store import ROOT, evaluate
from step_export import export_step, measure, faces
from measurements import measure_model
from verify_boolean_export import oracle, area
from verify_measurements_reference import reference_moments
from test_analytic_measurements import exact_value
from test_counterbores import counterbored, round_counterbored
from test_holes import perforated
from test_profiles import model_for
from test_instances import instance
from test_polyhedral_transforms import moved, turned

EXAMPLE = ROOT / "examples/ai-cad/counterbores"


def scenarios():
    asymmetric = counterbored()
    asymmetric["parameters"]["r2"] = "2"
    asymmetric["features"][-1]["holes"][1]["radius"] = "r2"
    concave = model_for([(0, 0), (100, 0), (100, 20), (20, 20), (20, 60), (0, 60)], "6")
    concave["features"][0]["kind"] = "planar_profile"
    concave["parameters"].update(x="12", y="12", r="3", x2="88")
    concave["features"].append(perforated()["features"][-1])
    return {
        "asymmetric": asymmetric,
        "concave": counterbored(concave),
        "plate": counterbored(),
        "reverse_plate": counterbored(perforated(True)),
        "round": round_counterbored(),
        "fractional_depth": counterbored(depth="1/3"),
        "turned": turned(moved(counterbored(), (5, -2, 3)), "x", 1),
        "linked_round": instance(round_counterbored(), offset=(100, 0, 0)),
    }


def main(write=False):
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        for name, model in scenarios().items():
            id = model["features"][-1]["id"]
            body = next(b for b in evaluate(model)["bodies"] if b["feature_id"] == id)
            path = Path(directory) / (name + ".step")
            assert export_step(body, path)["solid_count"] == 1
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
            residual = []
            for a, b in [(actual, reference), (reference, actual)]:
                diff = BRepAlgoAPI_Cut(a, b)
                assert diff.IsDone()
                residual.append(abs(measure(diff.Shape())))
            assert max(residual) < 1e-6 and abs(area(actual) - area(reference)) < 1e-6
            analytic = body["analytic"]
            cylinders = [
                BRepAdaptor_Surface(f).Cylinder()
                for f in faces(actual)
                if BRepAdaptor_Surface(f).GetType() == GeomAbs_Cylinder
            ]
            assert len(cylinders) == 2 * len(analytic["holes"]) + int(
                "outer_circle" in analytic
            )
            frame = analytic.get(
                "placement",
                dict(axes=[[1, 0, 0], [0, 1, 0], [0, 0, 1]], origin=["0", "0", "0"]),
            )

            def world(point):
                return gp_Pnt(
                    *[
                        float(F(frame["origin"][i]))
                        + sum(frame["axes"][i][j] * point[j] for j in range(3))
                        for i in range(3)
                    ]
                )

            floor = float(F(analytic["height"]) - F(analytic["counterbore"]["depth"]))
            classified = 0
            for hole in analytic["holes"]:
                x, y = map(lambda v: float(F(v)), hole["center"])
                radius = (
                    float(F(hole["radius"]))
                    + float(F(analytic["counterbore"]["radius"]))
                ) / 2
                for z, state in [(floor - 1e-4, TopAbs_IN), (floor + 1e-4, TopAbs_OUT)]:
                    assert (
                        BRepClass3d_SolidClassifier(
                            actual, world([x + radius, y, z]), 1e-7
                        ).State()
                        == state
                    )
                    classified += 1
                assert (
                    BRepClass3d_SolidClassifier(
                        actual, world([x, y, floor / 2]), 1e-7
                    ).State()
                    == TopAbs_OUT
                )
                classified += 1
            values = measure_model(model, id)
            volume, centroid, tensor = reference_moments(reference)
            center_error = max(
                abs(exact_value(v) - r) for v, r in zip(values["centroid_mm"], centroid)
            )
            inertia_error = max(
                abs(
                    exact_value(values["centroidal_volume_inertia_mm5"][i][j])
                    - tensor[i][j]
                )
                for i in range(3)
                for j in range(3)
            )
            assert (
                abs(measure(actual) - volume) < 1e-6
                and center_error < 1e-8
                and inertia_error < 1e-6
            )
            rows.append(
                dict(
                    case=name,
                    volume_mm3=volume,
                    step_volume_mm3=measure(actual),
                    directed_residual_mm3=residual,
                    area_error_mm2=abs(area(actual) - area(reference)),
                    cylinder_count=len(cylinders),
                    classified_shoulder_and_aperture_points=classified,
                    exact_measurements=values,
                    centroid_error_mm=center_error,
                    inertia_error_mm5=inertia_error,
                )
            )
            if write:
                EXAMPLE.mkdir(parents=True, exist_ok=True)
                (EXAMPLE / path.name).write_bytes(path.read_bytes())
                (EXAMPLE / (name + ".model.json")).write_text(
                    json.dumps(model, indent=2) + "\n"
                )
    if write:
        (EXAMPLE / "independent-comparison.json").write_text(
            json.dumps(rows, indent=2) + "\n"
        )
    print(
        "PASS: eight independent counterbored solids, STEP validity/cylinders/shoulders, bidirectional residuals and exact moments"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
