"""Independent explicit inner solids versus exact native shells and exported STEP."""

import argparse
import copy
from fractions import Fraction as F
import json
from pathlib import Path
import tempfile
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from OCP.gp import gp_Pnt, gp_Trsf, gp_Vec
from store import ROOT, evaluate
from step_export import export_step, measure
from measurements import measure_model
from topology import topology_model
from topology_step import translate
from verify_boolean_export import oracle, area
from verify_measurements_reference import reference_moments
from test_analytic_measurements import exact_value
from test_planar_shell import shell
from test_planar_loft import loft
from test_intersection import prism
from test_polyhedral_transforms import moved

EXAMPLE = ROOT / "examples/ai-cad/planar-shell"


def box_reference(opening, t=F(2)):
    lo, hi = [t] * 3, [F(size) - t for size in (40, 30, 20)]
    if opening:
        axis = next(i for i, v in enumerate(opening) if v)
        if opening[axis] > 0:
            hi[axis] = F((40, 30, 20)[axis])
        else:
            lo[axis] = F(0)
    outer = BRepPrimAPI_MakeBox(40, 30, 20).Shape()
    inner = BRepPrimAPI_MakeBox(
        gp_Pnt(*map(float, lo)), gp_Pnt(*map(float, hi))
    ).Shape()
    return BRepAlgoAPI_Cut(outer, inner).Shape()


def scenarios():
    for name, opening in [
        ("closed", None),
        ("top", (0, 0, 1)),
        ("bottom", (0, 0, -1)),
        ("right", (1, 0, 0)),
        ("left", (-1, 0, 0)),
        ("back", (0, 1, 0)),
        ("front", (0, -1, 0)),
    ]:
        yield name, shell(opening=opening), box_reference(opening)
    yield "fractional", shell(thickness="3/7"), box_reference((0, 0, 1), F(3, 7))
    # Independent analytic section positions for a 5-12-13 tapered wall.
    for name, opening, top_z in [
        ("tapered_closed", None, F(11)),
        ("tapered_open", (0, 0, 1), F(12)),
    ]:
        bottom_inset = F(3, 2)
        top_inset = (5 * top_z + 13) / 12

        def section(inset):
            return [
                (inset, inset),
                (40 - inset, inset),
                (40 - inset, 20 - inset),
                (inset, 20 - inset),
            ]

        inner = oracle(
            moved(
                loft(section(bottom_inset), section(top_inset), str(top_z - 1)),
                (0, 0, 1),
            )
        )
        reference = BRepAlgoAPI_Cut(oracle(loft()), inner).Shape()
        yield name, shell(loft(), "1", opening), reference
    source = prism("part", [(0, 0), (40, 0), (0, 30)], 20)
    inner = moved(prism("inner", [(2, 2), (34, 2), (2, 26)], 16), (0, 0, 2))
    yield (
        "triangle",
        shell(copy.deepcopy(source), "2", None),
        BRepAlgoAPI_Cut(oracle(source), oracle(inner)).Shape(),
    )
    shift = gp_Trsf()
    shift.SetTranslation(gp_Vec(7, -3, 5))
    yield (
        "moved",
        moved(shell(), (7, -3, 5)),
        BRepBuilderAPI_Transform(box_reference((0, 0, 1)), shift, True).Shape(),
    )


def main(write=False):
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        for name, model, reference in scenarios():
            id = model["features"][-1]["id"]
            body = evaluate(model)["bodies"][0]
            path = Path(directory) / (name + ".step")
            assert export_step(body, path)["solid_count"] == 1
            reader = STEPControl_Reader()
            assert (
                reader.ReadFile(str(path)) == IFSelect_RetDone
                and reader.TransferRoots()
            )
            actual = reader.OneShape()
            shared = translate(topology_model(model, id))
            errors = []
            for shape in [actual, shared]:
                assert (
                    BRepCheck_Analyzer(shape).IsValid()
                    and BRepCheck_Analyzer(reference).IsValid()
                )
                errors.append(abs(area(shape) - area(reference)))
                for a, b in [(shape, reference), (reference, shape)]:
                    diff = BRepAlgoAPI_Cut(a, b)
                    assert diff.IsDone()
                    errors.append(abs(measure(diff.Shape())))
            assert max(errors) < 1e-6, (name, errors)
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
                abs(float(F(body["volume_mm3"])) - volume) < 1e-6
                and center_error < 1e-8
                and inertia_error < 1e-5
            ), (name, inertia_error)
            rows.append(
                dict(
                    case=name,
                    volume_mm3=volume,
                    exact_measurements=values,
                    step_and_topology_errors=errors,
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
        "PASS: twelve source-built explicit cavities, STEP/shared topology, residuals and exact moments"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
