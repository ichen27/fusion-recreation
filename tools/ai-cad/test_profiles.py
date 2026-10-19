"""Exercise profile editing and exact solids through the real Rust process."""

import copy
from fractions import Fraction as F
import json
from pathlib import Path
import random
import tempfile
import unittest

from store import CadError, ROOT, Store, evaluate


def model_for(points, height="3", reverse=False):
    parameters = {"height": height}
    vertices = []
    # Reuse equal coordinate values, as a real parameterized model can.
    names = {}
    for i, point in enumerate(points):
        refs = []
        for q in point:
            value = str(q)
            if value not in names:
                name = f"c{len(names)}"
                names[value] = name
                parameters[name] = value
            refs.append(names[value])
        vertices.append({"id": f"v{i}", "x": refs[0], "y": refs[1]})
    return {
        "parameters": parameters,
        "fixed": {},
        "features": [
            {
                "kind": "polygon_profile",
                "id": "outline",
                "vertices": vertices[::-1] if reverse else vertices,
            },
            {
                "kind": "extrude",
                "id": "solid",
                "profile": "outline",
                "height": "height",
            },
        ],
    }


def signed_boundary_volume(boundary):
    """Independent tetrahedron sum checks the returned face orientations/geometry."""
    points = [list(map(F, p)) for p in boundary["vertices"]]
    volume = F(0)
    for face in boundary["faces"]:
        loop = [
            points[boundary["edges"][u["edge"]]["vertices"][0 if u["forward"] else 1]]
            for u in face["loops"][0]
        ]
        a = loop[0]
        for b, c in zip(loop[1:], loop[2:]):
            volume += (
                a[0] * (b[1] * c[2] - b[2] * c[1])
                - a[1] * (b[0] * c[2] - b[2] * c[0])
                + a[2] * (b[0] * c[1] - b[1] * c[0])
            ) / 6
    return volume


class ProfileTests(unittest.TestCase):
    def assert_invalid(self, model, code):
        with self.assertRaises(CadError) as caught:
            evaluate(model)
        self.assertEqual(caught.exception.detail["code"], code)

    def assert_solid(self, model, expected_area):
        result = evaluate(model)
        body = result["bodies"][0]
        expected_volume = expected_area * F(model["parameters"]["height"])
        self.assertEqual(F(result["profiles"][0]["area_mm2"]), expected_area)
        self.assertEqual(F(body["volume_mm3"]), expected_volume)
        boundary = body["boundary"]
        self.assertEqual(signed_boundary_volume(boundary), expected_volume)
        n = len(model["features"][0]["vertices"])
        self.assertEqual(len(boundary["vertices"]), 2 * n)
        self.assertEqual(len(boundary["edges"]), 3 * n)
        self.assertEqual(len(boundary["faces"]), n + 2)
        expected_points = {
            (F(model["parameters"][v["x"]]), F(model["parameters"][v["y"]]), z)
            for v in model["features"][0]["vertices"]
            for z in (F(0), F(model["parameters"]["height"]))
        }
        self.assertEqual(
            {tuple(map(F, p)) for p in boundary["vertices"]}, expected_points
        )
        uses = [[] for _ in boundary["edges"]]
        for face in boundary["faces"]:
            for use in face["loops"][0]:
                uses[use["edge"]].append(use["forward"])
        self.assertTrue(all(sorted(u) == [False, True] for u in uses))
        return result

    def test_triangle_winding_and_exact_fraction(self):
        points = [(F(-1, 3), F(-2, 5)), (F(8, 3), F(-2, 5)), (F(-1, 3), F(3, 5))]
        for reverse in (False, True):
            model = model_for(points, "7/3", reverse)
            result = self.assert_solid(model, F(3, 2))
            self.assertEqual(result["model"], model)
            self.assertEqual(
                [v["id"] for v in result["profiles"][0]["vertices"]],
                [v["id"] for v in model["features"][0]["vertices"]],
            )

    def test_seeded_affine_triangles_and_rectangles(self):
        rng = random.Random(20261019)
        for i in range(40):
            a, b, c, d = [F(rng.randint(-20, 20), rng.randint(1, 11)) for _ in range(4)]
            determinant = a * d - b * c
            if not determinant:
                continue
            tx, ty = F(rng.randint(-30, 30), 7), F(rng.randint(-30, 30), 11)
            source = (
                [(0, 0), (3, 0), (3, 2), (0, 2)] if i % 2 else [(0, 0), (3, 0), (0, 2)]
            )
            points = [(a * x + b * y + tx, c * x + d * y + ty) for x, y in source]
            with self.subTest(case=i):
                self.assert_solid(
                    model_for(points, "13/7", bool(i % 3)),
                    abs(determinant) * (6 if i % 2 else 3),
                )

    def test_tiny_nonzero_profile_is_not_rounded_away(self):
        self.assert_solid(
            model_for([(0, 0), (F(1, 10**30), 0), (0, 1)], "1/3"), F(1, 2 * 10**30)
        )

    def test_coordinate_limit_and_max_vertex_count(self):
        self.assert_solid(
            model_for(
                [(-1000000, -1000000), (1000000, -1000000), (0, 1000000)], "1000000"
            ),
            F(2 * 10**12),
        )
        points = [(i, i * i) for i in range(32)]
        area = (
            abs(
                sum(
                    F(x) * yy - F(xx) * y
                    for (x, y), (xx, yy) in zip(points, points[1:] + points[:1])
                )
            )
            / 2
        )
        self.assert_solid(model_for(points), area)
        self.assert_invalid(
            model_for([(1000001, 0), (0, 0), (0, 1)]), "coordinate_range"
        )

    def test_invalid_loops_are_rejected(self):
        cases = {
            "too_few": ([(0, 0), (1, 0)], "profile_limit"),
            "collinear": ([(0, 0), (1, 0), (2, 0)], "invalid_profile"),
            "redundant_corner": ([(0, 0), (1, 0), (2, 0), (0, 2)], "invalid_profile"),
            "repeated_closure": ([(0, 0), (2, 0), (0, 2), (0, 0)], "invalid_profile"),
            "collapsed_edge": ([(0, 0), (2, 0), (2, 0), (0, 2)], "invalid_profile"),
            "concave": ([(0, 0), (3, 0), (1, 1), (3, 3), (0, 3)], "invalid_profile"),
            "bow_tie": ([(0, 0), (2, 2), (0, 2), (2, 0)], "invalid_profile"),
            # Same-sign local turns are insufficient: this pentagram still crosses.
            "star": ([(0, 3), (2, -3), (-3, 1), (3, 1), (-2, -3)], "invalid_profile"),
        }
        for label, (points, code) in cases.items():
            with self.subTest(label=label):
                self.assert_invalid(model_for(points), code)
        model = model_for([(0, 0), (2, 0), (0, 2)])
        model["features"][0]["vertices"] *= 11
        self.assert_invalid(model, "profile_limit")

    def test_ids_references_and_height(self):
        base = model_for([(0, 0), (2, 0), (0, 2)])
        for height in ("0", "-1", "1000001"):
            m = copy.deepcopy(base)
            m["parameters"]["height"] = height
            self.assert_invalid(m, "dimension_range")
        for key, value, code in [
            ("id", "v0", "duplicate_id"),
            ("id", "bad id", "invalid_id"),
            ("x", "absent", "missing_parameter"),
        ]:
            m = copy.deepcopy(base)
            m["features"][0]["vertices"][1][key] = value
            self.assert_invalid(m, code)
        for ref in ("solid", "absent"):
            m = copy.deepcopy(base)
            m["features"][1]["profile"] = ref
            self.assert_invalid(m, "unsupported_reference")
        m = copy.deepcopy(base)
        m["features"].reverse()
        self.assert_invalid(m, "unsupported_reference")

    def test_profile_can_exist_alone_and_feed_two_solids(self):
        m = model_for([(0, 0), (2, 0), (0, 2)])
        extrusion = m["features"].pop()
        result = evaluate(m)
        self.assertEqual(result["bodies"], [])
        self.assertEqual(result["profiles"][0]["area_mm2"], "2")
        m["features"] += [extrusion, {**extrusion, "id": "second"}]
        self.assertEqual([b["volume_mm3"] for b in evaluate(m)["bodies"]], ["6", "6"])

    def test_edit_preview_reopen_undo_and_failed_edit_atomicity(self):
        fixture = ROOT / "examples/ai-cad/profile-extrusion"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.json"
            store = Store(path)
            profile = store.execute(json.loads((fixture / "profile.json").read_text()))
            self.assertFalse(profile["bodies"])
            created = store.execute(json.loads((fixture / "extrude.json").read_text()))
            self.assertEqual(created["bodies"][0]["volume_mm3"], "57000")
            widen = json.loads((fixture / "widen.json").read_text())
            preview_command = {k: v for k, v in widen.items() if k != "transaction_id"}
            before = path.read_bytes()
            preview = store.execute({**preview_command, "action": "preview"})
            self.assertEqual(preview["bodies"][0]["volume_mm3"], "68400")
            self.assertEqual(path.read_bytes(), before)
            edited = store.execute(widen)
            self.assertEqual(edited["model"]["features"], created["model"]["features"])
            self.assertEqual(edited["changed_parameters"], ["width"])
            self.assertEqual(
                Store(path).execute({"action": "inspect"})["bodies"], edited["bodies"]
            )
            before = path.read_bytes()
            for parameter, value, code in [
                ("tip_x", "200", "invalid_profile"),
                ("thickness", "20", "constraint_conflict"),
            ]:
                with self.assertRaises(CadError) as caught:
                    store.execute(
                        {
                            **widen,
                            "expected_revision": 3,
                            "transaction_id": "invalid",
                            "preserve": [],
                            "operations": [
                                {"op": "set_parameter", "id": parameter, "mm": value}
                            ],
                        }
                    )
                self.assertEqual(caught.exception.detail["code"], code)
                self.assertEqual(path.read_bytes(), before)
            undone = store.execute(
                {"action": "undo", "expected_revision": 3, "transaction_id": "undo"}
            )
            self.assertEqual(undone["bodies"], created["bodies"])
            redone = store.execute(
                {"action": "redo", "expected_revision": 4, "transaction_id": "redo"}
            )
            self.assertEqual(redone["bodies"], edited["bodies"])


if __name__ == "__main__":
    unittest.main()
