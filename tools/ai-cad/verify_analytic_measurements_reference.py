"""Compare original exact moments against independently constructed OCCT solids."""

import argparse
from fractions import Fraction as F
import json
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID
from store import ROOT
from measurements import measure_model
from verify_boolean_export import oracle
from test_round_stock import cylinder, flange
from test_holes import perforated
from test_blind_holes import blind
from test_analytic_measurements import exact_value
from test_polyhedral_transforms import moved, turned
from test_instances import instance

EXAMPLE = ROOT / "examples/ai-cad/analytic-measurements"


def scenarios():
    base = {
        "cylinder": cylinder(),
        "flange": flange(),
        "blind_flange": blind(flange()),
        "plate": perforated(),
        "blind_plate": blind(perforated()),
    }
    result = dict(base)
    for name, model in base.items():
        result[name + "_placed"] = instance(model, offset=(F(7, 3), -2, 5))
        result[name + "_turned"] = turned(moved(model, (5, -2, 3)), "y", 1)
    return result


def reference_moments(shape):
    # Integrate each connected solid independently, then use the parallel-axis
    # theorem. Preserve whole-compound output separately as diagnostic evidence.
    solids = []
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    while explorer.More():
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(explorer.Current(), props)
        center, tensor = props.CentreOfMass(), props.MatrixOfInertia()
        solids.append(
            (
                props.Mass(),
                list(center.Coord()),
                [[tensor.Value(i + 1, j + 1) for j in range(3)] for i in range(3)],
            )
        )
        explorer.Next()
    assert solids
    volume = sum(v for v, _, _ in solids)
    centroid = [sum(v * c[i] for v, c, _ in solids) / volume for i in range(3)]
    inertia = [[0.0] * 3 for _ in range(3)]
    for v, c, t in solids:
        d = [c[i] - centroid[i] for i in range(3)]
        radius2 = sum(x * x for x in d)
        for i in range(3):
            for j in range(3):
                inertia[i][j] += t[i][j] + v * (
                    (radius2 if i == j else 0) - d[i] * d[j]
                )
    return volume, centroid, inertia


def main(write=False):
    rows = []
    for name, model in scenarios().items():
        actual = measure_model(model, model["features"][-1]["id"])
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(oracle(model), props)
        reference_volume, reference_center, reference_tensor = reference_moments(
            oracle(model)
        )
        compound_center = list(props.CentreOfMass().Coord())
        center_error = max(
            abs(float(exact_value(v)) - r)
            for v, r in zip(actual["centroid_mm"], reference_center)
        )
        tensor_error = max(
            abs(
                float(exact_value(actual["centroidal_volume_inertia_mm5"][i][j]))
                - reference_tensor[i][j]
            )
            for i in range(3)
            for j in range(3)
        )
        volume_error = abs(float(exact_value(actual["volume_mm3"])) - reference_volume)
        assert center_error < 1e-8 and tensor_error < 1e-6 and volume_error < 1e-7
        rows.append(
            dict(
                case=name,
                exact=actual,
                reference_centroid_mm=reference_center,
                whole_compound_centroid_mm=compound_center,
                reference_method="per-solid integration plus parallel-axis aggregation",
                reference_centroidal_volume_inertia_mm5=reference_tensor,
                centroid_error_mm=center_error,
                inertia_error_mm5=tensor_error,
                volume_error_mm3=volume_error,
            )
        )
        if write:
            EXAMPLE.mkdir(parents=True, exist_ok=True)
            (EXAMPLE / (name + ".model.json")).write_text(
                json.dumps(model, indent=2) + "\n"
            )
    if write:
        (EXAMPLE / "independent-comparison.json").write_text(
            json.dumps(rows, indent=2) + "\n"
        )
    print(
        f"PASS: {len(rows)} independent analytic reference solids match symbolic pi centroids and all inertia components"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
