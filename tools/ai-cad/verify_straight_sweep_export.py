"""Independent straight sweeps, planar STEP boundaries and exact moments."""

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
from measurements import measure_model
from topology import topology_model
from topology_step import translate as shared_boundary
from verify_boolean_export import oracle, area
from verify_measurements_reference import reference_moments
from test_analytic_measurements import exact_value
from test_straight_sweep import swept
from test_instances import instance
from test_polyhedral_transforms import moved, turned

EXAMPLE = ROOT / "examples/ai-cad/straight-sweep"


def scenarios():
    concave = [(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)]
    cut = swept(concave)
    cut["parameters"]["half"] = "6"
    cut["features"].append(
        dict(
            kind="plane_cut",
            id="cut",
            input="part",
            normal=["0", "0", "1"],
            offset="half",
        )
    )
    return {
        "slanted": swept(),
        "reverse": swept(reverse=True),
        "negative": swept(offset=(7, -3, -12)),
        "vertical": swept(offset=(0, 0, 12)),
        "concave": swept(concave),
        "triangle": swept([(0, 0), (20, 0), (0, 20)]),
        "fractional": swept(offset=("1/3", "-2/7", "3/5")),
        "cut": cut,
        "turned": turned(moved(swept(), (5, -2, 3)), "x", 1),
        "linked": instance(swept(), offset=(100, 0, 0)),
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
            shared = shared_boundary(topology_model(model, id))
            assert BRepCheck_Analyzer(shared).IsValid()
            assert abs(measure(shared) - measure(reference)) < 1e-6
            shared_residual = []
            for a, b in [(shared, reference), (reference, shared)]:
                diff = BRepAlgoAPI_Cut(a, b)
                assert diff.IsDone()
                shared_residual.append(abs(measure(diff.Shape())))
            shared_area_error = abs(area(shared) - area(reference))
            assert max([shared_area_error, *shared_residual]) < 1e-6
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
                    shared_boundary_residual_mm3=shared_residual,
                    shared_boundary_area_error_mm2=shared_area_error,
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
        "PASS: ten independent straight sweeps, STEP planar solids, bidirectional residuals and exact moments"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
