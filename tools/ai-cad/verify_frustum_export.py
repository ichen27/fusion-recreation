"""Independent conical solids versus both STEP adapters, exact moments and supports."""

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
from test_frustum import frustum
from test_instances import instance
from test_polyhedral_transforms import moved, turned

EXAMPLE = ROOT / "examples/ai-cad/tapered-stock"


def scenarios():
    return dict(
        narrowing=frustum(),
        widening=frustum(top="15"),
        fractional=frustum("7/3", "2/5", "11/7"),
        translated=moved(frustum(), (F(1, 3), F(-2, 5), F(7, 11))),
        turned_x=turned(frustum(top="15"), "x", 1),
        turned_y=turned(frustum(), "y", 3, (1, 2, 3)),
        linked=instance(frustum(), offset=(50, 0, 0)),
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
                assert cones == (1 if adapter == "stock" else 4)
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
        tiny = evaluate(frustum(top="1000000001/100000000"))["bodies"][0]
        try:
            export_step(tiny, Path(directory) / "tiny.step")
            raise AssertionError("Sub-tolerance taper must reject")
        except RuntimeError as exc:
            assert "1e-6" in str(exc)
    if write:
        (EXAMPLE / "independent-comparison.json").write_text(
            json.dumps(rows, indent=2) + "\n"
        )
    print(
        "PASS: seven independent conical solids, fourteen STEP readbacks, directed residuals, analytic supports and exact moments"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
