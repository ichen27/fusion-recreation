"""Original exact half-space cuts: 3D volume, sequential edits and atomic failures."""

from fractions import Fraction as F
from pathlib import Path
import random
import tempfile
import unittest
from store import evaluate, Store, CadError
from exports import tessellate
from test_holes import audit_triangles
from test_round_stock import cylinder
from test_profiles import model_for


def block():
    return {
        "parameters": {"size": "60", "diagonal": "60", "side": "-10"},
        "fixed": {},
        "features": [
            {
                "kind": "block",
                "id": "stock",
                "width": "size",
                "depth": "size",
                "height": "size",
            }
        ],
    }


def cut(id="diagonal_cut", input="stock", normal=None, offset="diagonal"):
    return {
        "kind": "plane_cut",
        "id": id,
        "input": input,
        "normal": normal or ["1", "1", "1"],
        "offset": offset,
    }


def tetra():
    m = block()
    m["features"] += [cut(), cut("side_cut", "diagonal_cut", ["-1", "0", "0"], "side")]
    return m


class PlaneCuts(unittest.TestCase):
    def check_mesh(self, m, volume):
        result = evaluate(m)
        self.assertEqual(len(result["bodies"]), 1)
        body = result["bodies"][0]
        self.assertEqual(F(body["volume_mm3"]), volume)
        self.assertIn("boundary", body)
        self.assertNotIn("analytic", body)
        mesh = tessellate(m, body["feature_id"], 64)
        measured = audit_triangles(
            [[tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]], 0
        )
        self.assertAlmostEqual(measured, float(volume), places=7)
        for f in m["features"]:
            if f["kind"] == "plane_cut":
                for p in body["boundary"]["vertices"]:
                    self.assertLessEqual(
                        sum(F(n) * F(v) for n, v in zip(f["normal"], p)),
                        F(m["parameters"][f["offset"]]),
                    )
        return body

    def test_oblique_tetrahedron_repeated_cut_and_rescaled_plane(self):
        m = tetra()
        b = self.check_mesh(m, F(62500, 3))
        self.assertEqual(b["feature_id"], "side_cut")
        self.assertEqual(len(b["boundary"]["faces"]), 4)
        m["features"][1]["normal"] = ["2", "2", "2"]
        m["parameters"]["diagonal"] = "120"
        self.assertEqual(
            self.check_mesh(m, F(62500, 3))["boundary"]["vertices"],
            b["boundary"]["vertices"],
        )
        m["features"][1]["normal"] = ["1/2", "1/2", "1/2"]
        m["parameters"]["diagonal"] = "30"
        self.check_mesh(m, F(62500, 3))

    def test_cut_after_corner_cut_and_convex_profile_extrusion(self):
        m = block()
        m["parameters"].update(setback="10", diagonal="30")
        m["features"].extend(
            [
                {
                    "kind": "corner_cut",
                    "id": "corner",
                    "input": "stock",
                    "size": "setback",
                },
                cut(input="corner", normal=["0", "0", "1"]),
            ]
        )
        self.check_mesh(m, F(106500))
        m = model_for([(0, 0), (3, 0), (3, 4), (0, 4)], "5")
        m["parameters"]["diagonal"] = "2"
        m["features"].append(cut(input="solid", normal=["0", "0", "1"]))
        self.check_mesh(m, F(24))

    def test_seeded_positive_normal_exact_volume(self):
        rng = random.Random(14)
        for _ in range(30):
            m = block()
            normal = [rng.randint(1, 5) for _ in range(3)]
            s = rng.randint(1, 60)
            m["parameters"]["diagonal"] = str(s)
            m["features"].append(cut(normal=list(map(str, normal))))
            self.check_mesh(m, F(s**3, 6 * normal[0] * normal[1] * normal[2]))

    def test_noop_coplanar_and_empty_or_degenerate_refusal(self):
        for n, offset in [
            (["0", "0", "1"], "60"),
            (["0", "0", "1"], "70"),
            (["0", "0", "-1"], "0"),
        ]:
            m = block()
            m["parameters"]["diagonal"] = offset
            m["features"].append(cut(normal=n))
            self.check_mesh(m, F(216000))
        for n, offset, code in [
            (["0", "0", "1"], "0", "empty_solid"),
            (["0", "0", "1"], "-1", "empty_solid"),
            (["0", "0", "0"], "1", "plane_normal"),
            (["1.5", "0", "0"], "1", "invalid_number"),
        ]:
            m = block()
            m["parameters"]["diagonal"] = offset
            m["features"].append(cut(normal=n))
            with self.assertRaises(CadError) as caught:
                evaluate(m)
            self.assertEqual(caught.exception.detail["code"], code)

    def test_bad_references_branches_and_analytic_stock(self):
        for m, code in [
            (block(), "unsupported_reference"),
            (tetra(), "unsupported_branch"),
            (cylinder(), "unsupported_reference"),
        ]:
            if m["features"][0]["kind"] == "cylinder":
                m["parameters"]["diagonal"] = "20"
            m["features"].append(
                cut(
                    "extra",
                    "missing"
                    if len(m["features"]) == 1 and m["features"][0]["kind"] == "block"
                    else "stock",
                )
            )
            with self.assertRaises(CadError) as caught:
                evaluate(m)
            self.assertEqual(caught.exception.detail["code"], code)

    def test_edit_preview_reopen_undo_and_empty_rollback(self):
        m = tetra()
        ops = [
            {"op": "define_parameter", "id": k, "mm": v}
            for k, v in m["parameters"].items()
        ] + [{"op": "add_feature", "feature": f} for f in m["features"]]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "part.json"
            s = Store(path)
            s.execute(
                {
                    "action": "commit",
                    "expected_revision": 0,
                    "transaction_id": "create",
                    "preserve": [],
                    "operations": ops,
                }
            )
            c = {
                "action": "preview",
                "expected_revision": 1,
                "preserve": ["size", "side"],
                "operations": [{"op": "set_parameter", "id": "diagonal", "mm": "54"}],
            }
            before = path.read_bytes()
            self.assertEqual(s.execute(c)["bodies"][0]["volume_mm3"], "42592/3")
            self.assertEqual(path.read_bytes(), before)
            s.execute({**c, "action": "commit", "transaction_id": "resize"})
            self.assertEqual(
                Store(path).execute({"action": "inspect"})["bodies"][0]["volume_mm3"],
                "42592/3",
            )
            before = path.read_bytes()
            with self.assertRaises(CadError):
                s.execute(
                    {
                        **c,
                        "expected_revision": 2,
                        "action": "commit",
                        "transaction_id": "empty",
                        "operations": [
                            {"op": "set_parameter", "id": "diagonal", "mm": "10"}
                        ],
                    }
                )
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(
                s.execute(
                    {"action": "undo", "expected_revision": 2, "transaction_id": "undo"}
                )["bodies"][0]["volume_mm3"],
                "62500/3",
            )
