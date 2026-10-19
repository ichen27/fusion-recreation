"""Exact acceptance predicates and independent exported-mesh topology/integrals."""

import copy
from collections import defaultdict
from fractions import Fraction as F
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from exports import export_stl, tessellate, display
from store import CadError, ROOT, Store, evaluate
from test_profiles import model_for

EXAMPLE = ROOT / "examples/ai-cad/bracket"


def perforated(reverse=False):
    model = model_for([(0, 0), (100, 0), (100, 60), (0, 60)], "6", reverse)
    model["parameters"].update(x="12", y="12", r="3", x2="88")
    model["features"].append(
        {
            "kind": "through_holes",
            "id": "part",
            "input": "solid",
            "holes": [
                {"id": "left", "x": "x", "y": "y", "radius": "r"},
                {"id": "right", "x": "x2", "y": "y", "radius": "r"},
            ],
        }
    )
    return model


def read_stl(data):
    # Independent text reader; intentionally does not consume mesh indices.
    vertices = [
        tuple(map(float, line.split()[1:]))
        for line in data.decode().splitlines()
        if line.startswith("vertex ")
    ]
    assert len(vertices) % 3 == 0
    return [vertices[i : i + 3] for i in range(0, len(vertices), 3)]


def audit_triangles(triangles, holes):
    edges = defaultdict(list)
    points = set()
    volume = 0.0
    for a, b, c in triangles:
        assert len({a, b, c}) == 3
        points.update((a, b, c))
        for p, q in ((a, b), (b, c), (c, a)):
            edges[tuple(sorted((p, q)))].append(p < q)
        volume += (
            a[0] * (b[1] * c[2] - b[2] * c[1])
            - a[1] * (b[0] * c[2] - b[2] * c[0])
            + a[2] * (b[0] * c[1] - b[1] * c[0])
        ) / 6
    assert all(sorted(v) == [False, True] for v in edges.values())
    assert len(points) - len(edges) + len(triangles) == 2 - 2 * holes
    return volume


class Holes(unittest.TestCase):
    def assert_code(self, model, code):
        with self.assertRaises(CadError) as caught:
            evaluate(model)
        self.assertEqual(caught.exception.detail["code"], code)

    def test_exact_volume_both_windings_and_small_clearance(self):
        for reverse in (False, True):
            m = perforated(reverse)
            b = evaluate(m)["bodies"][0]
            self.assertNotIn("boundary", b)
            self.assertEqual(b["volume_mm3"], "36000 - (108)*pi")
            self.assertEqual(b["analytic"]["holes"][0]["radius"], "3")
            # Positive exact clearance smaller than float resolution remains valid.
            m["parameters"]["x"] = str(F(3) + F(1, 10**30))
            self.assertEqual(evaluate(m)["bodies"][0]["volume_mm3"], b["volume_mm3"])

    def test_edges_tangencies_overlap_and_duplicates(self):
        for key, value, code in [
            ("x", "3", "hole_clearance"),
            ("y", "2", "hole_clearance"),
            ("x", "-12", "hole_clearance"),
            ("x2", "18", "hole_overlap"),
            ("x2", "17", "hole_overlap"),
            ("r", "0", "dimension_range"),
            ("r", "-1", "dimension_range"),
        ]:
            m = perforated()
            m["parameters"][key] = value
            self.assert_code(m, code)
        m = perforated()
        m["features"][-1]["holes"][1]["id"] = "left"
        self.assert_code(m, "duplicate_id")
        m = perforated()
        m["features"][-1]["holes"][0]["radius"] = "missing"
        self.assert_code(m, "missing_parameter")
        for count in (0, 17):
            m = perforated()
            m["features"][-1]["holes"] = [m["features"][-1]["holes"][0]] * count
            self.assert_code(m, "hole_limit")
        m = perforated()
        m["features"].append({**m["features"][-1], "id": "branch"})
        self.assert_code(m, "unsupported_branch")
        for reference in ("part", "outline", "missing"):
            m = perforated()
            m["features"][-1]["input"] = reference
            self.assert_code(m, "unsupported_reference")

    def test_diagonal_clearance_and_seeded_scaled_translated_parts(self):
        rng = random.Random(5512)
        for _ in range(24):
            scale = F(rng.randint(1, 10), rng.randint(1, 7))
            tx = F(rng.randint(-100, 100), 7)
            ty = F(rng.randint(-100, 100), 11)
            # 3-4-5 hypotenuse, x/40+y/30<1. At (10,10), distance is 10.
            m = model_for(
                [(tx, ty), (tx + 40 * scale, ty), (tx, ty + 30 * scale)], "7/3"
            )
            m["parameters"].update(
                x=str(tx + 10 * scale), y=str(ty + 10 * scale), r=str(10 * scale)
            )
            m["features"].append(
                {
                    "kind": "through_holes",
                    "id": "part",
                    "input": "solid",
                    "holes": [{"id": "h", "x": "x", "y": "y", "radius": "r"}],
                }
            )
            # Distance to slope is 10, as are distances to both coordinate edges.
            self.assert_code(m, "hole_clearance")
            m["parameters"]["r"] = str(9 * scale)
            self.assertEqual(
                evaluate(m)["bodies"][0]["analytic"]["volume"]["pi_subtract_mm3"],
                str(81 * scale * scale * F(7, 3)),
            )

    def test_mesh_manifold_volume_convergence_and_hole_caps(self):
        m = perforated()
        exact = 36000 - 108 * math.pi
        last = float("inf")
        for segments in (16, 32, 64, 128, 256):
            mesh = tessellate(m, "part", segments)
            triangles = [
                [tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]
            ]
            volume = audit_triangles(triangles, 2)
            polygon_expected = (
                36000 - 108 * segments * math.sin(2 * math.pi / segments) / 2
            )
            self.assertAlmostEqual(volume, polygon_expected, places=7)
            self.assertGreater(volume, exact)
            self.assertLess(volume - exact, last)
            last = volume - exact
            self.assertAlmostEqual(
                mesh["max_radial_error_mm"], 3 * (1 - math.cos(math.pi / segments))
            )
            # Each cap triangle's interior excludes both hole centers.
            for tri in triangles:
                if len({p[2] for p in tri}) != 1:
                    continue
                for x, y in ((12, 12), (88, 12)):
                    crosses = [
                        (b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0])
                        for a, b in zip(tri, tri[1:] + tri[:1])
                    ]
                    self.assertFalse(
                        all(v > 0 for v in crosses) or all(v < 0 for v in crosses)
                    )
        for segments in (15, 257):
            with self.assertRaises(CadError):
                tessellate(m, "part", segments)

    def test_diamond_and_sixteen_hole_meshes(self):
        m = model_for([(0, 20), (20, 0), (40, 20), (20, 40)], "3")
        m["parameters"].update(x="10", x2="30", y="20", r="3")
        m["features"].append(perforated()["features"][-1])
        mesh = tessellate(m, "part", 64)
        triangles = [[tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]]
        self.assertAlmostEqual(
            audit_triangles(triangles, 2),
            2400 - 54 * 64 * math.sin(2 * math.pi / 64) / 2,
            places=7,
        )
        m = model_for([(0, 0), (100, 0), (100, 100), (0, 100)], "5")
        m["parameters"].update(r="2", a="10", b="30", c="50", d="70")
        holes = [
            {"id": x + y, "x": x, "y": y, "radius": "r"} for x in "abcd" for y in "abcd"
        ]
        m["features"].append(
            {"kind": "through_holes", "id": "part", "input": "solid", "holes": holes}
        )
        mesh = tessellate(m, "part", 256)
        triangles = [[tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]]
        self.assertAlmostEqual(
            audit_triangles(triangles, 16),
            50000 - 320 * 256 * math.sin(2 * math.pi / 256) / 2,
            places=6,
        )

    def test_export_cli_protects_existing_files_and_stale_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.cad.json"
            Store(path).execute(json.loads((EXAMPLE / "create.json").read_text()))
            output = Path(directory) / "part.stl"
            command = [
                sys.executable,
                str(ROOT / "tools/ai-cad/exports.py"),
                "--store",
                str(path),
                "--revision",
                "1",
                "--body",
                "bracket",
                "--format",
                "stl",
                "--output",
                str(output),
            ]
            first = subprocess.run(command, capture_output=True, check=True)
            self.assertIn("result", json.loads(first.stdout))
            data = output.read_bytes()
            second = subprocess.run(command, capture_output=True)
            self.assertEqual(second.returncode, 1)
            self.assertEqual(output.read_bytes(), data)
            command[command.index("--revision") + 1] = "0"
            command[-1] = str(Path(directory) / "stale.stl")
            stale = subprocess.run(command, capture_output=True)
            self.assertEqual(
                json.loads(stale.stdout)["error"]["code"], "revision_conflict"
            )
            self.assertFalse(Path(command[-1]).exists())

    def test_old_planar_solid_exports(self):
        from test_contract import CREATE
        from store import EMPTY
        from exports import stl_bytes

        state = evaluate(EMPTY, CREATE["operations"])
        mesh = tessellate(state["model"], state["bodies"][0]["feature_id"])
        self.assertAlmostEqual(
            audit_triangles(read_stl(stl_bytes(mesh)), 0), 71400, places=7
        )

    def test_unrenderable_exact_model_remains_valid(self):
        m = perforated()
        m["parameters"]["r"] = "1/1000000000000000000000000000000"
        state = evaluate(m)
        self.assertIn(
            "display_error", display({"result": state})["result"]["bodies"][0]
        )
        self.assertEqual(state["model"], m)

    def test_bracket_transaction_reopen_undo_and_revision_bound_stl(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "part.json"
            store = Store(path)
            create = json.loads((EXAMPLE / "create.json").read_text())
            widen = json.loads((EXAMPLE / "widen.json").read_text())
            original = store.execute(create)
            before = path.read_bytes()
            preview = store.execute(
                {
                    k: v
                    for k, v in {**widen, "action": "preview"}.items()
                    if k != "transaction_id"
                }
            )
            self.assertEqual(path.read_bytes(), before)
            edited = store.execute(widen)
            self.assertEqual(preview["bodies"], edited["bodies"])
            self.assertEqual(
                edited["changed_parameters"], ["center_x", "right_x", "width"]
            )
            self.assertEqual(
                Store(path).execute({"action": "inspect"})["bodies"], edited["bodies"]
            )
            data, _ = export_stl(store, 2, "bracket")
            volume = audit_triangles(read_stl(data), 3)
            self.assertAlmostEqual(
                volume, 43200 - 162 * 128 * math.sin(2 * math.pi / 128) / 2, places=7
            )
            before = path.read_bytes()
            for value in ("20", "10"):
                bad = copy.deepcopy(widen)
                bad.update(expected_revision=2, transaction_id="invalid")
                bad["operations"][0]["mm"] = value
                with self.assertRaises(CadError):
                    store.execute(bad)
                self.assertEqual(path.read_bytes(), before)
            with self.assertRaises(CadError):
                export_stl(store, 1, "bracket")
            self.assertEqual(path.read_bytes(), before)
            undone = store.execute(
                {"action": "undo", "expected_revision": 2, "transaction_id": "undo"}
            )
            self.assertEqual(undone["bodies"], original["bodies"])
            redone = store.execute(
                {"action": "redo", "expected_revision": 3, "transaction_id": "redo"}
            )
            self.assertEqual(redone["bodies"], edited["bodies"])


if __name__ == "__main__":
    unittest.main()
