"""Compare original planar Booleans with independent OCCT operations and STEP."""

import argparse
import json
from pathlib import Path
import tempfile
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut, BRepAlgoAPI_Common
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakePolygon,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_Transform,
)
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from OCP.gp import gp_Pnt, gp_Vec, gp_Trsf
from store import ROOT, evaluate
from step_export import export_step, measure, number
from test_booleans import cases, boolean, box
from test_intersection import prism

EXAMPLE = ROOT / "examples/ai-cad/planar-booleans"


def oracle(model):
    """Construct independently from typed profile coordinates, not Rust boundaries."""
    values = {k: number(v) for k, v in model["parameters"].items()}
    shapes = {}
    for f in model["features"]:
        if f["kind"] in ["planar_profile", "polygon_profile"]:
            polygon = BRepBuilderAPI_MakePolygon()
            for p in f["vertices"]:
                polygon.Add(gp_Pnt(values[p["x"]], values[p["y"]], 0))
            polygon.Close()
            shape = BRepBuilderAPI_MakeFace(polygon.Wire(), True).Face()
        elif f["kind"] == "extrude":
            shape = BRepPrimAPI_MakePrism(
                shapes[f["profile"]], gp_Vec(0, 0, values[f["height"]])
            ).Shape()
        elif f["kind"] == "translate":
            transform = gp_Trsf()
            transform.SetTranslation(gp_Vec(*[values[v] for v in f["offset"]]))
            shape = BRepBuilderAPI_Transform(
                shapes[f["input"]], transform, True
            ).Shape()
        elif f["kind"] == "boolean":
            operation = {
                "union": BRepAlgoAPI_Fuse,
                "difference": BRepAlgoAPI_Cut,
                "intersection": BRepAlgoAPI_Common,
            }[f["operation"]]
            result = operation(shapes[f["left"]], shapes[f["right"]])
            assert result.IsDone()
            shape = result.Shape()
        else:
            raise AssertionError(f["kind"])
        shapes[f["id"]] = shape
    return shape


def area(shape):
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, props)
    return props.Mass()


def main(write=False):
    models = cases()
    refill = boolean(
        models["cavity"][0], box("c", [2, 2, 2], [8, 8, 8]), "union", "filled"
    )
    models["refilled"] = (refill, 1000, 1)
    models["oblique"] = (
        boolean(
            box("a", [0, 0, 0], [10, 10, 10]),
            prism("b", [(0, 0), (12, 0), (0, 12)], 12),
            "difference",
        ),
        320,
        1,
    )
    models["repeated_intersection"] = (
        boolean(
            models["through"][0],
            box("c", [0, 0, 0], [5, 10, 10]),
            "intersection",
            "half",
        ),
        320,
        1,
    )
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        for name, (model, expected, components) in models.items():
            body = evaluate(model)["bodies"][0]
            path = Path(directory) / (name + ".step")
            exported = export_step(body, path)
            assert exported["solid_count"] == components
            reader = STEPControl_Reader()
            assert (
                reader.ReadFile(str(path)) == IFSelect_RetDone
                and reader.TransferRoots()
            )
            imported = reader.OneShape()
            reference = oracle(model)
            assert (
                BRepCheck_Analyzer(imported).IsValid()
                and BRepCheck_Analyzer(reference).IsValid()
            )
            volume_error = abs(measure(imported) - measure(reference))
            area_error = abs(area(imported) - area(reference))
            # Equal volume/area can hide a wrong position or missing cavity. Test
            # both directed differences independently against the reference shape.
            residues = []
            for a, b in [(imported, reference), (reference, imported)]:
                difference = BRepAlgoAPI_Cut(a, b)
                assert difference.IsDone()
                residues.append(abs(measure(difference.Shape())))
            assert volume_error < 1e-7 and area_error < 1e-7 and max(residues) < 1e-7
            assert abs(measure(imported) - expected) < 1e-7
            rows.append(
                dict(
                    case=name,
                    expected_volume_mm3=expected,
                    step_volume_mm3=measure(imported),
                    solid_count=components,
                    volume_difference_mm3=volume_error,
                    surface_difference_mm2=area_error,
                    directed_residue_mm3=residues,
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
        "PASS: nine independent Boolean/STEP cases, component counts, areas and bidirectional residual volumes"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
