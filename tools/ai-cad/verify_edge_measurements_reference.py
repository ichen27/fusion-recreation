"""Compare native exact lengths with OCCT integration of translated edge supports.

This checks the length algorithm/transport, not independent topology correctness.
Independent source-dimension identities are covered by test_edge_measurements.py.
"""

import argparse
from fractions import Fraction as F
import json
import math
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Ax2, gp_Circ
from topology_step import point, direction, vector
from topology import topology_model
from edge_measurements import measure_edge
from store import ROOT
from test_frustum import frustum
from test_planar_loft import loft
from test_counterbores import counterbored
from test_countersinks import countersunk
from test_individual_depths import individual
from test_polyhedral_transforms import moved, turned

EXAMPLE = ROOT / "examples/ai-cad/edge-measurements"


def main(write=False):
    cases = {
        "frustum": frustum("10", "7", "4"),
        "irrational": frustum("10", "7", "5"),
        "loft": loft(),
        "counterbores": counterbored(),
        "countersinks": countersunk(),
        "individual_depths": individual(),
        "placed": turned(
            moved(frustum("10", "7", "5"), (F(1, 7), F(-2, 3), F(4, 9))), "y", 3
        ),
    }
    results = []
    for name, model in cases.items():
        feature = model["features"][-1]["id"]
        topology = topology_model(model, feature)
        for index, edge in enumerate(topology["edges"]):
            a, b = [vector(topology["vertices"][i]) for i in edge["vertices"]]
            curve = edge["curve"]
            if curve["kind"] == "line":
                reference = BRepBuilderAPI_MakeEdge(point(a), point(b)).Edge()
            else:
                center = vector(curve["center"])
                radial = [x - y for x, y in zip(a, center)]
                circle = gp_Circ(
                    gp_Ax2(point(center), direction(curve["axis"]), direction(radial)),
                    float(F(curve["radius"])),
                )
                reference = BRepBuilderAPI_MakeEdge(circle, 0.0, math.pi / 2).Edge()
            properties = GProp_GProps()
            BRepGProp.LinearProperties_s(reference, properties)
            measured = measure_edge(model, feature, index)
            assert math.isclose(
                measured["length_approx_mm"],
                properties.Mass(),
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
            results.append(
                dict(
                    case=name,
                    edge_index=index,
                    native=measured,
                    reference_length_mm=properties.Mass(),
                )
            )
    if write:
        (EXAMPLE / "reference-comparison.json").write_text(
            json.dumps(
                dict(
                    method="OCCT integration of translated exact supports; not independent topology reconstruction",
                    results=results,
                ),
                indent=2,
            )
            + "\n"
        )
    print(
        f"PASS: {len(results)} edges across {len(cases)} models agree with translated-support integration"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
