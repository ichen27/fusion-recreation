"""OCCT is an independent reference/export adapter, never the Rust modeling path."""
from fractions import Fraction as F
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import sys

from bridge import HERE, clip, request, volume
from adapters import from_planar
from boundary import Body
from kernel import Solid
from compare_topology import compare, helper
from OCP.BRepPrimAPI import BRepPrimAPI_MakeHalfSpace
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.gp import gp_Pnt, gp_Dir, gp_Pln
import OCP


def fixtures():
    cube = Solid.box((0, 0, 0), (2, 2, 2))
    for name, normal, offset in [
        ("axis", (1, 0, 0), F(1, 3)),
        ("corner", (1, 1, 1), 1),
        ("edge", (1, 1, 0), 2),
        ("vertex", (1, 1, 1), 2),
        ("center", (1, 1, 1), 3),
        ("existing-edge", (1, -1, 0), 0),
        ("negative", (-2, 1, 3), F(7, 3)),
    ]:
        yield name, cube, normal, F(offset)
    prism = Solid.extrude(((0, 0), (3, 0), (0, 2)), 4)
    yield "triangle-prism", prism, (1, -1, 1), F(3, 2)
    for i in range(8):
        skewed = cube.affine(((F(3, 5), F(-4, 5), F(1, 7)),
                             (F(4, 5), F(3, 5), 0), (0, 0, -1 if i % 2 else 1)),
                            (F(i, 7), F(-i, 11), F(i, 13)))
        normal = (F(i+1), F(2-i), F(3))
        values = [sum(n*x for n, x in zip(normal, p)) for face in skewed.faces for p in face]
        yield "skewed-%d" % i, skewed, normal, (min(values)+max(values))/2


def native_clip(shape, normal, offset):
    n = tuple(map(float, normal))
    nn = sum(x*x for x in n)
    point = tuple(float(offset)*x/nn for x in n)
    face = BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(*point), gp_Dir(*n))).Face()
    reference_point = gp_Pnt(*(p-x/(nn**.5) for p, x in zip(point, n)))
    half = BRepPrimAPI_MakeHalfSpace(face, reference_point).Solid()
    op = BRepAlgoAPI_Common(shape, half)
    if not op.IsDone() or not BRepCheck_Analyzer(op.Shape()).IsValid():
        raise RuntimeError("OCCT half-space reference failed")
    return op.Shape()


def run(binary):
    rows = []
    fixture_inputs = []
    for name, solid, normal, offset in fixtures():
        boundary = from_planar(Body.from_solid(solid))
        original = helper.simple_solid(solid)
        for sign in (1, -1):
            n, d = tuple(sign*x for x in normal), sign*offset
            payload = request(boundary, n, d)
            fixture_inputs.append(payload)
            reply, own = clip(binary, boundary, n, d)
            ref = native_clip(original, n, d)
            row = compare(name, sign, own, ref)
            row["exact_volume_mm3"] = reply["volume"]
            rows.append(row)
            if not row["passed"]: raise AssertionError(row)
        # Sequential clipping must work on the returned representation too.
        _, own = clip(binary, boundary, normal, offset)
        ref = native_clip(original, normal, offset)
        n, d = (0, 1, 0), F(1, 2)
        _, own = clip(binary, own, n, d)
        ref = native_clip(ref, n, d)
        # All fixtures retain a full-dimensional region for this second cut.
        row = compare(name, "repeat-y", own, ref)
        row["exact_volume_mm3"] = str(volume(own))
        rows.append(row)
        if not row["passed"]: raise AssertionError(row)
    root = HERE.parents[1]
    source_paths = [HERE / "Cargo.toml", HERE / "Cargo.lock", HERE / "rust-toolchain.toml",
                    *sorted((HERE / "src").glob("*.rs")), HERE / "bridge.py", Path(__file__),
                    HERE / "verify.py", HERE.parent / "2026-10-12-shared-topology/topology.py",
                    HERE.parent / "2026-10-12-shared-topology/compare_topology.py"]
    report = {
        "schema_version": 1,
        "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True)),
        "platform": platform.platform(), "python": platform.python_version(),
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "source_hashes": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in source_paths},
        "fixture_input_sha256": hashlib.sha256(json.dumps(fixture_inputs, sort_keys=True).encode()).hexdigest(),
        "ocp_version": OCP.__version__, "comparisons": len(rows), "passed": all(r["passed"] for r in rows),
        "surface_samples": sum(r["surface_samples"] for r in rows),
        "max_volume_error_mm3": max(r["volume_error_mm3"] for r in rows),
        "max_area_error_mm2": max(r["area_error_mm2"] for r in rows),
        "max_surface_distance_mm": max(max(r["forward_distance_mm"], r["reverse_distance_mm"]) for r in rows),
        "rows": rows,
        "limits": "Bounded convex planar fixtures. Sampled surface agreement is not a global proof. "
                  "No OCCT comparison claimed for 1e-30 thickness or 1e30 translation.",
    }
    (HERE / "occt-comparison.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("rows", "source_hashes")}, indent=2))


if __name__ == "__main__":
    binary = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE / "target/release/boundary-clip"
    run(binary)
