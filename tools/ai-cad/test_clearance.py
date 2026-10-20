"""Exact material distance, contact classification, witnesses and read isolation."""

from fractions import Fraction as F
from pathlib import Path
import random
import tempfile
import unittest
from clearance import inspect_clearance, dispatch_clearance
from store import CadError, Store
from test_interference import examples, pair
from test_booleans import box
from test_intersection import rectangle, operations
from test_instances import instance
from test_frustum import frustum


def check(model, left="part", right="copy"):
    return inspect_clearance(model, left, right)


def witness_squared(result):
    a, b = [list(map(F, p)) for p in result["closest_points_mm"]]
    return sum((x - y) ** 2 for x, y in zip(a, b))


class Clearance(unittest.TestCase):
    def test_hollow_material_and_contact_classification(self):
        for name, (model, left, right, volume) in examples().items():
            with self.subTest(name=name):
                result = check(model, left, right)
                if F(volume) > 0:
                    self.assertEqual(result["relation"], "overlapping")
                    self.assertEqual(result["distance_mm"], "0")
                    self.assertIsNone(result["closest_points_mm"])
                else:
                    expected = (
                        F(1)
                        if name == "inside_cavity"
                        else F(1, 8)
                        if name == "disjoint_with_overlapping_bounds"
                        else F(0)
                    )
                    self.assertEqual(F(result["distance_squared_mm2"]), expected)
                    self.assertEqual(witness_squared(result), expected)
                    self.assertEqual(
                        result["relation"], "separated" if expected else "touching"
                    )
                    reverse = check(model, right, left)
                    self.assertEqual(
                        reverse["distance_squared_mm2"], result["distance_squared_mm2"]
                    )
                    self.assertEqual(witness_squared(reverse), expected)

    def test_fractional_boxes_known_3d_distances_and_witness_membership(self):
        rng = random.Random(827)
        for offset in [
            (F(13), F(8), F(2)),
            (F(11), F(5), F(3)),
            (F(10) + F(1, 10**30), F(0), F(0)),
        ] + [tuple(F(rng.randint(-60, 60), 3) for _ in range(3)) for _ in range(30)]:
            model = instance(rectangle("part", 0, 0, 10, 4, 2), offset=offset)
            result = check(model)
            expected = sum(
                max(F(0), abs(delta) - size) ** 2
                for size, delta in zip([10, 4, 2], offset)
            )
            self.assertEqual(F(result["distance_squared_mm2"]), expected)
            overlap = all(abs(delta) < size for size, delta in zip([10, 4, 2], offset))
            self.assertEqual(
                result["relation"],
                "overlapping" if overlap else "separated" if expected else "touching",
            )
            if not overlap:
                self.assertEqual(witness_squared(result), expected)
                a, b = [list(map(F, p)) for p in result["closest_points_mm"]]
                for i, size in enumerate([10, 4, 2]):
                    self.assertTrue(0 <= a[i] <= size)
                    self.assertTrue(offset[i] <= b[i] <= offset[i] + size)
        self.assertEqual(
            check(instance(rectangle("part", 0, 0, 10, 4, 2), offset=(13, 8, 2)))[
                "distance_mm"
            ],
            "5",
        )
        self.assertEqual(
            check(instance(rectangle("part", 0, 0, 10, 4, 2), offset=(11, 5, 3)))[
                "distance_mm"
            ],
            "sqrt(3)",
        )

    def test_contained_material_has_zero_separation_not_boundary_gap(self):
        model = pair(
            box("outer", [0, 0, 0], [10, 10, 10]), box("inner", [3, 3, 3], [7, 7, 7])
        )
        result = check(model, "outer", "inner.placed")
        self.assertEqual(result["relation"], "overlapping")
        self.assertEqual(result["distance_squared_mm2"], "0")
        self.assertIsNone(result["closest_points_mm"])

    def test_read_only_revision_cache_and_explicit_unsupported(self):
        model = instance(rectangle("part", 0, 0, 10, 4, 2), offset=(13, 8, 2))
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "part.json")
            store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations(model),
                    preserve=[],
                )
            )
            before = store.path.read_bytes()
            args = dict(expected_revision=1, left="part", right="copy")
            result = dispatch_clearance(store, args)
            self.assertEqual(result["result"]["distance_mm"], "5")
            self.assertEqual(dispatch_clearance(store, args), result)
            for change, code in [
                ({"expected_revision": False}, "revision_conflict"),
                ({"expected_revision": 0}, "revision_conflict"),
                ({"right": "part"}, "invalid_pair"),
                ({"right": "gone"}, "missing_body"),
                ({"right": 0}, "invalid_command"),
            ]:
                self.assertEqual(
                    dispatch_clearance(store, {**args, **change})["error"]["code"], code
                )
            self.assertEqual(store.path.read_bytes(), before)
            store.execute(
                dict(
                    action="commit",
                    expected_revision=1,
                    transaction_id="move",
                    operations=[dict(op="set_parameter", id="copy.x", mm="10")],
                    preserve=[],
                )
            )
            self.assertEqual(
                dispatch_clearance(store, args)["error"]["code"], "revision_conflict"
            )
            self.assertEqual(
                dispatch_clearance(store, {**args, "expected_revision": 2})["result"][
                    "distance_mm"
                ],
                "4",
            )
        with self.assertRaises(CadError) as caught:
            check(instance(frustum()), "taper", "copy")
        self.assertEqual(caught.exception.detail["code"], "unsupported_clearance")


if __name__ == "__main__":
    unittest.main()
