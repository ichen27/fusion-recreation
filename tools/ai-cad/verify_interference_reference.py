"""Compare exact material overlap with independent source-built OCCT intersections."""

import argparse
import copy
from fractions import Fraction as F
import json
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepCheck import BRepCheck_Analyzer
from interference import inspect_interference
from store import ROOT
from test_interference import examples
from test_instances import instance
from test_planar_loft import loft
from test_polyhedral_transforms import turned
from verify_boolean_export import oracle
from step_export import measure

EXAMPLE = ROOT / "examples/ai-cad/interference"


def reference(model, id):
    model = copy.deepcopy(model)
    index = next(i for i, f in enumerate(model["features"]) if f["id"] == id)
    model["features"] = model["features"][: index + 1]
    return oracle(model)


def main(write=False):
    scenarios = examples()
    scenarios["loft_copy"] = (instance(loft(), offset=(5, 0, 0)), "part", "copy", None)
    scenarios["turned_loft"] = (
        turned(instance(loft(), offset=(0, 0, 0)), "x", 1),
        "part",
        "turned",
        None,
    )
    rows = []
    for name, (model, left, right, expected) in scenarios.items():
        a, b = reference(model, left), reference(model, right)
        assert BRepCheck_Analyzer(a).IsValid() and BRepCheck_Analyzer(b).IsValid()
        common = BRepAlgoAPI_Common(a, b)
        assert common.IsDone() and BRepCheck_Analyzer(common.Shape()).IsValid()
        volume = measure(common.Shape())
        result = inspect_interference(model, left, right)
        assert abs(float(F(result["overlap_volume_mm3"])) - volume) < 1e-7
        if expected is not None:
            assert result["overlap_volume_mm3"] == expected
        rows.append(
            dict(case=name, native=result, independent_overlap_volume_mm3=volume)
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
        f"PASS: {len(rows)} planar overlaps agree with independently constructed solid intersections"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
