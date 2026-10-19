"""Analytic circles/holes survive exact placements, native edits and world-space meshes."""

import copy
import math
from fractions import Fraction as F
from pathlib import Path
import tempfile
import unittest
from store import CadError, Store, evaluate
from exports import tessellate
from test_round_stock import cylinder, flange
from test_holes import perforated, audit_triangles
from test_blind_holes import blind
from test_polyhedral_transforms import moved, turned, rotated
from test_instances import instance
from test_intersection import operations
from test_polyhedral_cuts import cut


def scenarios():
    return dict(
        cylinder=(cylinder(), 0),
        flange=(flange(), 3),
        blind_flange=(blind(flange()), 0),
        plate=(perforated(), 2),
        blind_plate=(blind(perforated()), 0),
    )


class AnalyticPlacement(unittest.TestCase):
    def test_all_axis_turns_and_fractional_placements_preserve_analytic_geometry_and_mesh(
        self,
    ):
        delta = (F(7, 3), F(-2, 5), F(9, 7))
        pivot = (F(1, 3), F(-3, 4), F(2, 7))
        for name, (model, holes) in scenarios().items():
            original = evaluate(model)["bodies"][0]
            mesh = tessellate(model, original["feature_id"], 32)
            base_volume = audit_triangles(
                [[tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]],
                holes,
            )
            placed = moved(model, delta)
            for axis in "xyz":
                for turns in (1, 2, 3):
                    m = turned(placed, axis, turns, pivot)
                    body = evaluate(m)["bodies"][0]
                    shape = copy.deepcopy(body["analytic"])
                    frame = shape.pop("placement")
                    self.assertEqual(shape, original["analytic"])
                    self.assertEqual(body["volume_mm3"], original["volume_mm3"])
                    self.assertNotIn("boundary", body)
                    self.assertEqual(
                        list(map(F, frame["origin"])),
                        list(rotated(delta, axis, turns, pivot)),
                    )
                    actual = tessellate(m, "turned", 32)
                    self.assertEqual(actual["triangles"], mesh["triangles"])
                    self.assertEqual(
                        actual["max_radial_error_mm"], mesh["max_radial_error_mm"]
                    )
                    for a, p in zip(actual["vertices"], mesh["vertices"]):
                        expected = rotated(
                            tuple(F(v) + d for v, d in zip(p, delta)),
                            axis,
                            turns,
                            pivot,
                        )
                        for x, y in zip(a, expected):
                            self.assertAlmostEqual(x, float(y), places=10)
                    volume = audit_triangles(
                        [
                            [tuple(actual["vertices"][i]) for i in t]
                            for t in actual["triangles"]
                        ],
                        holes,
                    )
                    self.assertAlmostEqual(volume, base_volume, places=6)

    def test_inverse_and_linked_copy_follow_source_depth_without_curved_boolean_fallback(
        self,
    ):
        source = blind(flange())
        linked = instance(source, offset=(10, 2, 3))
        a = evaluate(linked)["bodies"]
        self.assertEqual(len(a), 2)
        self.assertEqual({b["volume_mm3"] for b in a}, {"7764*pi"})
        linked["parameters"]["depth"] = "3"
        self.assertEqual(
            {b["volume_mm3"] for b in evaluate(linked)["bodies"]}, {"7646*pi"}
        )
        rotated_model = turned(source, "x", 1)
        rotated_model["features"].append(
            {
                **rotated_model["features"][-1],
                "id": "inverse",
                "input": "turned",
                "turns": 3,
            }
        )
        self.assertEqual(
            evaluate(rotated_model)["bodies"][0]["analytic"]["placement"],
            dict(axes=[[1, 0, 0], [0, 1, 0], [0, 0, 1]], origin=["0", "0", "0"]),
        )
        with self.assertRaises(CadError) as error:
            evaluate(cut(moved(source), (0, 0, 1), 3))
        self.assertEqual(error.exception.detail["code"], "unsupported_reference")

    def test_computed_placement_rational_budget_is_enforced(self):
        model = cylinder()
        denominators = []
        candidate = 2**100 + 1
        while len(denominators) < 12:
            if all(math.gcd(candidate, d) == 1 for d in denominators):
                denominators.append(candidate)
            candidate += 2
        previous = "stock"
        for i, d in enumerate(denominators):
            parameter = f"d{i}"
            feature = f"move{i}"
            model["parameters"][parameter] = f"1/{d}"
            model["features"].append(
                dict(
                    kind="translate",
                    id=feature,
                    input=previous,
                    offset=[parameter, "cx", "cy"],
                )
            )
            previous = feature
        with self.assertRaises(CadError) as error:
            evaluate(model)
        self.assertEqual(error.exception.detail["code"], "placement_limit")

    def test_invalid_source_and_placement_edits_preserve_history(self):
        model = turned(moved(blind(flange())), "y", 1)
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "part.json")
            original = store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations(model),
                    preserve=[],
                )
            )
            before = store.path.read_bytes()
            for key, value in [
                ("depth", "5"),
                ("move.x", "1000001"),
                ("turn.x", "-1000001"),
            ]:
                with self.assertRaises(CadError):
                    store.execute(
                        dict(
                            action="commit",
                            expected_revision=1,
                            transaction_id="invalid",
                            operations=[dict(op="set_parameter", id=key, mm=value)],
                            preserve=[],
                        )
                    )
                self.assertEqual(store.path.read_bytes(), before)
            changed = store.execute(
                dict(
                    action="commit",
                    expected_revision=1,
                    transaction_id="depth",
                    operations=[dict(op="set_parameter", id="depth", mm="3")],
                    preserve=[],
                )
            )
            self.assertEqual(changed["bodies"][0]["volume_mm3"], "7646*pi")
            restored = store.execute(
                dict(action="undo", expected_revision=2, transaction_id="undo")
            )
            self.assertEqual(restored["bodies"], original["bodies"])
            self.assertEqual(
                Store(store.path).execute(dict(action="inspect"))["bodies"],
                original["bodies"],
            )


if __name__ == "__main__":
    unittest.main()
