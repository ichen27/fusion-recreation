"""Independent solid distances and closest-point membership for native separation."""

import argparse
from fractions import Fraction as F
import json
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
from OCP.gp import gp_Pnt
from clearance import inspect_clearance
from store import ROOT
from test_interference import examples
from test_intersection import rectangle
from test_instances import instance
from test_planar_loft import loft
from verify_interference_reference import reference

EXAMPLE = ROOT / "examples/ai-cad/clearance"


def scenarios():
    result = {
        name: (model, left, right)
        for name, (model, left, right, _) in examples().items()
    }
    for name, offset in [
        ("gap_345", (13, 8, 2)),
        ("irrational_gap", (11, 5, 3)),
        ("fractional_gap", (F(31, 3), F(13, 3), F(7, 3))),
    ]:
        result[name] = (
            instance(rectangle("part", 0, 0, 10, 4, 2), offset=offset),
            "part",
            "copy",
        )
    result["loft_gap"] = (instance(loft(), offset=(50, 0, 0)), "part", "copy")
    return result


def main(write=False):
    rows = []
    for name, (model, left, right) in scenarios().items():
        a, b = reference(model, left), reference(model, right)
        oracle = BRepExtrema_DistShapeShape(a, b)
        assert oracle.IsDone()
        measured = inspect_clearance(model, left, right)
        distance = oracle.Value()
        assert abs(measured["distance_approx_mm"] - distance) < 1e-7
        witness_errors = []
        if measured["closest_points_mm"] is not None:
            for position, shape in zip(measured["closest_points_mm"], [a, b]):
                point = BRepBuilderAPI_MakeVertex(
                    gp_Pnt(*[float(F(v)) for v in position])
                ).Vertex()
                separation = BRepExtrema_DistShapeShape(point, shape)
                assert separation.IsDone()
                witness_errors.append(separation.Value())
            assert max(witness_errors) < 1e-7
            x, y = [list(map(F, p)) for p in measured["closest_points_mm"]]
            assert sum((a - b) ** 2 for a, b in zip(x, y)) == F(
                measured["distance_squared_mm2"]
            )
        rows.append(
            dict(
                case=name,
                native=measured,
                independent_distance_mm=distance,
                witness_membership_error_mm=witness_errors,
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
        f"PASS: {len(rows)} distances and native closest-point witnesses agree with independently built solids"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
