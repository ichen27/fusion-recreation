"""Independent coaxial intersections versus supplied-boundary STEP, moments and topology."""

import argparse
from fractions import Fraction as F
import json
from pathlib import Path
import tempfile
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cone
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader, STEPControl_Writer, STEPControl_AsIs
from OCP.Interface import Interface_Static
from store import ROOT, evaluate
from step_export import export_step, measure, faces
from topology import topology_model
from topology_step import translate
from measurements import measure_model
from verify_boolean_export import oracle, area
from verify_measurements_reference import reference_moments
from test_analytic_measurements import exact_value
from test_revolution import revolved
from test_coaxial import intersect
from test_round_stock import cylinder
from test_frustum import frustum
from test_instances import instance
from test_polyhedral_transforms import moved, turned

EXAMPLE = ROOT / "examples/ai-cad/coaxial-intersection"


def scenarios():
    taper = intersect(frustum("10", "4", "12"), cylinder(radius="7", height="12"))
    ring = intersect(
        revolved([(3, 0), (10, 0), (10, 12), (3, 12)]),
        revolved([(5, 2), (12, 2), (12, 10), (5, 10)]),
    )
    return dict(
        cylinders=intersect(),
        taper=taper,
        rings=ring,
        conical_ring=intersect(
            revolved([(3, 0), (10, 0), (5, 12), (2, 12)]),
            cylinder(radius="7", height="10"),
        ),
        opposite=intersect(
            b=moved(turned(cylinder(radius="5", height="8"), "x", 2), (0, 0, 14))
        ),
        fractional=intersect(
            cylinder(radius="1/3", height="7/5"), cylinder(radius="2/7", height="11/13")
        ),
        nested=intersect(intersect(), cylinder(radius="3", height="12")),
        axis_x=intersect(
            turned(cylinder(radius="10", height="12"), "y", 1),
            turned(moved(cylinder(radius="5", height="8"), (0, 0, 6)), "y", 1),
        ),
        axis_y=intersect(
            turned(cylinder(radius="10", height="12"), "x", 1),
            turned(moved(cylinder(radius="5", height="8"), (0, 0, 6)), "x", 1),
        ),
        translated=moved(taper, (F(1, 3), F(-2, 5), F(7, 11))),
        rotated=turned(ring, "x", 1),
        linked=instance(taper, offset=(50, 0, 0)),
    )


def main(write=False):
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        for name, model in scenarios().items():
            id = model["features"][-1]["id"]
            body = next(b for b in evaluate(model)["bodies"] if b["feature_id"] == id)
            topology = topology_model(model, id)
            reference = oracle(model)
            volume, centroid, tensor = reference_moments(reference)
            values = measure_model(model, id)
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
            assert center_error < 1e-8 and inertia_error < 1e-6, (
                name,
                center_error,
                inertia_error,
            )
            for adapter in ("stock", "shared"):
                path = Path(directory) / (name + "-" + adapter + ".step")
                if adapter == "stock":
                    assert export_step(body, path)["solid_count"] == 1
                else:
                    shape = translate(topology)
                    assert BRepCheck_Analyzer(shape).IsValid()
                    Interface_Static.SetCVal_s("write.step.unit", "MM")
                    writer = STEPControl_Writer()
                    assert writer.Transfer(shape, STEPControl_AsIs) == IFSelect_RetDone
                    assert writer.Write(str(path)) == IFSelect_RetDone
                reader = STEPControl_Reader()
                assert (
                    reader.ReadFile(str(path)) == IFSelect_RetDone
                    and reader.TransferRoots()
                )
                actual = reader.OneShape()
                assert (
                    BRepCheck_Analyzer(actual).IsValid()
                    and BRepCheck_Analyzer(reference).IsValid()
                )
                residual = []
                for a, b in [(actual, reference), (reference, actual)]:
                    diff = BRepAlgoAPI_Cut(a, b)
                    assert diff.IsDone()
                    residual.append(abs(measure(diff.Shape())))
                volume_error = abs(measure(actual) - volume)
                area_error = abs(area(actual) - area(reference))
                assert max([volume_error, area_error, *residual]) < 1e-6, (
                    name,
                    adapter,
                    residual,
                    volume_error,
                    area_error,
                )
                cones = sum(
                    BRepAdaptor_Surface(f).GetType() == GeomAbs_Cone
                    for f in faces(actual)
                )
                native_cones = sum(
                    s["kind"] == "conical_frustum"
                    for s in topology["surfaces"].values()
                )
                assert cones == native_cones * (1 if adapter == "stock" else 4)
                rows.append(
                    dict(
                        case=name,
                        adapter=adapter,
                        volume_mm3=volume,
                        volume_error_mm3=volume_error,
                        area_error_mm2=area_error,
                        directed_residual_mm3=residual,
                        cone_patches=cones,
                        centroid_error_mm=center_error,
                        inertia_error_mm5=inertia_error,
                        exact_measurements=values,
                    )
                )
                if write:
                    EXAMPLE.mkdir(parents=True, exist_ok=True)
                    (EXAMPLE / path.name).write_bytes(path.read_bytes())
            if write:
                (EXAMPLE / (name + ".model.json")).write_text(
                    json.dumps(model, indent=2) + "\n"
                )
    if write:
        (EXAMPLE / "independent-comparison.json").write_text(
            json.dumps(rows, indent=2) + "\n"
        )
    print(
        "PASS: twelve independent coaxial intersections, twenty-four STEP readbacks, directed residuals, analytic supports and exact moments"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
