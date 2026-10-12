"""Independent OCCT comparisons of edited/reloaded shared documents."""
import json
from pathlib import Path
from document import Document
from fractions import Fraction
from OCP.gp import gp_Pnt, gp_Ax2, gp_Dir
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse, BRepAlgoAPI_Common
from OCP.BRepCheck import BRepCheck_Analyzer
import compare_boundary as helper


def reference(document):
    shapes = {}
    for feature in document.features:
        p = feature.parameters
        if feature.operation == "box":
            lo, hi = [[float(Fraction(x)) for x in p[key]] for key in ("lo", "hi")]
            shape = BRepPrimAPI_MakeBox(gp_Pnt(*lo), *(b - a for a, b in zip(lo, hi))).Shape()
        elif feature.operation == "rectangle":
            x0, y0, x1, y1 = p["bounds"]
            z0, z1 = p["z"]
            shape = BRepPrimAPI_MakeBox(gp_Pnt(x0, y0, z0), x1-x0, y1-y0, z1-z0).Shape()
        elif feature.operation == "cylinder":
            x, y = p["center"]
            z0, z1 = p["z"]
            shape = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x, y, z0), gp_Dir(0, 0, 1)),
                                            p["radius"], z1-z0).Shape()
        else:
            operation = {"cut": BRepAlgoAPI_Cut, "union": BRepAlgoAPI_Fuse,
                         "intersection": BRepAlgoAPI_Common}[feature.operation]
            builder = operation(shapes[p["left"]], shapes[p["right"]])
            if not builder.IsDone():
                raise RuntimeError("OCCT reference failed")
            shape = builder.Shape()
        shapes[feature.id] = shape
    return shapes


def demo():
    return (Document()
            .append("plate", "rectangle", bounds=[-8, -5, 8, 5], z=[0, 4])
            .append("drill", "cylinder", center=[-3, 0], radius=1.5, z=[-1, 5])
            .append("drilled", "cut", left="plate", right="drill")
            .append("bore", "cylinder", center=[-3, 0], radius=2.5, z=[3, 5])
            .append("counterbored", "cut", left="drilled", right="bore")
            .append("block", "box", lo=[20, -5, 0], hi=[30, 5, 4])
            .append("slot", "box", lo=[22, -1, -1], hi=[24, 1, 5])
            .append("slotted", "cut", left="block", right="slot"))


def run():
    original = demo()
    edited = original.replace("drill", center=[-3, 0], radius=1, z=[-1, 5])
    edited = edited.replace("block", lo=[20, -5, 0], hi=[32, 5, 4])
    edited.save("shared-demo.json")
    restored = Document.load("shared-demo.json")
    assert edited == restored
    rows = []
    for name, document in (("original", original), ("edited", edited), ("reloaded", restored)):
        native = reference(document)
        for feature_id, model in document.evaluate().items():
            shape = native[feature_id]
            volume_error = abs(float(model.volume) - helper.measure(shape, "volume"))
            area_error = abs(model.area - helper.measure(shape, "area"))
            valid = BRepCheck_Analyzer(shape).IsValid() and not model.validate()
            assert valid and volume_error < 1e-7 and area_error < 1e-7
            rows.append({"stage": name, "feature": feature_id, **model.summary(),
                         "occt_valid": bool(valid), "volume_error_mm3": volume_error,
                         "area_error_mm2": area_error})
    report = {"model_states": len(rows), "rows": rows,
              "max_volume_error_mm3": max(r["volume_error_mm3"] for r in rows),
              "max_area_error_mm2": max(r["area_error_mm2"] for r in rows),
              "scope": "Editing/replay and area/volume comparisons, not full surface equivalence"}
    Path("document-comparison.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    run()
