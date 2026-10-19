"""Quarter turns preserve exact oriented boundaries and editable world-space intent."""

import copy
from fractions import Fraction as F
from pathlib import Path
import tempfile
import unittest
from store import CadError, Store, evaluate
from test_intersection import rectangle, operations
from test_plane_cuts import tetra
from test_profiles import signed_boundary_volume


def rotated(model, axis="z", turns=1, pivot=(0, 0, 0), id="turned", input=None):
    m = copy.deepcopy(model)
    refs = [id + "." + a for a in "xyz"]
    m["parameters"].update(zip(refs, map(str, pivot)))
    m["features"].append(
        {
            "kind": "rotate_quarter",
            "id": id,
            "input": input or m["features"][-1]["id"],
            "axis": axis,
            "turns": turns,
            "pivot": refs,
        }
    )
    return m


def rodrigues(point, axis, turns, pivot):
    # Independent axis-vector form; sine/cosine at quarter turns are integers.
    a = [F(int(i == "xyz".index(axis))) for i in range(3)]
    v = [F(x) - p for x, p in zip(point, pivot)]
    cross = [
        a[1] * v[2] - a[2] * v[1],
        a[2] * v[0] - a[0] * v[2],
        a[0] * v[1] - a[1] * v[0],
    ]
    c, s = {1: (0, 1), 2: (-1, 0), 3: (0, -1)}[turns]
    dot = sum(x * y for x, y in zip(a, v))
    return tuple(
        p + c * x + s * y + (1 - c) * b * dot for p, x, y, b in zip(pivot, v, cross, a)
    )


class Rotation(unittest.TestCase):
    def test_all_axes_angles_and_fractional_pivots_preserve_exact_boundary(self):
        base = tetra()
        original = evaluate(base)["bodies"][0]
        for axis in "xyz":
            for turns in [1, 2, 3]:
                for pivot in [(0, 0, 0), (F(1, 3), -2, F(5, 7))]:
                    body = evaluate(rotated(base, axis, turns, pivot))["bodies"][0]
                    self.assertEqual(body["volume_mm3"], original["volume_mm3"])
                    self.assertEqual(
                        signed_boundary_volume(body["boundary"]),
                        F(original["volume_mm3"]),
                    )
                    expected = {
                        rodrigues(p, axis, turns, pivot)
                        for p in original["boundary"]["vertices"]
                    }
                    self.assertEqual(
                        {tuple(map(F, p)) for p in body["boundary"]["vertices"]},
                        expected,
                    )
                    for face in body["boundary"]["faces"]:
                        for point in body["boundary"]["vertices"]:
                            self.assertLessEqual(
                                sum(F(n) * F(v) for n, v in zip(face["normal"], point)),
                                F(face["offset"]),
                            )

    def test_inverse_composition_and_simple_profile_boundary(self):
        base = rectangle("stock", 0, 0, 40, 20, 10)
        for axis in "xyz":
            m = rotated(base, axis, 1, (20, 10, 0))
            m = rotated(m, axis, 3, (20, 10, 0), id="inverse")
            result = evaluate(m)["bodies"][0]
            self.assertEqual(result["volume_mm3"], "8000")
            self.assertEqual(
                {tuple(map(F, p)) for p in result["boundary"]["vertices"]},
                {(F(x), F(y), F(z)) for x in [0, 40] for y in [0, 20] for z in [0, 10]},
            )

    def test_invalid_angles_pivots_and_unsupported_reference(self):
        base = rectangle("stock", 0, 0, 10, 10, 10)
        for turns in [0, 4, -1]:
            with self.assertRaises(CadError) as caught:
                evaluate(rotated(base, turns=turns))
            self.assertEqual(caught.exception.detail["code"], "rotation_range")
        with self.assertRaises(CadError) as caught:
            evaluate(rotated(base, pivot=(1000001, 0, 0)))
        self.assertEqual(caught.exception.detail["code"], "rotation_range")
        with self.assertRaises(CadError):
            evaluate(rotated(base, axis="diagonal"))
        with self.assertRaises(CadError) as caught:
            evaluate(rotated(base, input="missing"))
        self.assertEqual(caught.exception.detail["code"], "unsupported_reference")
        from test_round_stock import cylinder

        with self.assertRaises(CadError) as caught:
            evaluate(rotated(cylinder()))
        self.assertEqual(caught.exception.detail["code"], "unsupported_reference")

    def test_replacement_rebuilds_intersection_and_invalid_pivot_is_atomic(self):
        a = rectangle("a", 0, 0, 40, 20, 10)
        b = rotated(rectangle("b", 0, 0, 40, 20, 10), pivot=(20, 10, 0))
        m = {
            "parameters": {**a["parameters"], **b["parameters"]},
            "fixed": {},
            "features": a["features"]
            + b["features"]
            + [
                {"kind": "intersection", "id": "common", "left": "a", "right": "turned"}
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "model.json")
            result = store.execute(
                {
                    "action": "commit",
                    "expected_revision": 0,
                    "transaction_id": "create",
                    "operations": operations(m),
                    "preserve": [],
                }
            )
            self.assertEqual(result["bodies"][0]["volume_mm3"], "4000")
            feature = copy.deepcopy(b["features"][-1])
            feature["turns"] = 2
            command = {
                "action": "commit",
                "expected_revision": 1,
                "transaction_id": "turn",
                "operations": [
                    {"op": "replace_feature", "id": "turned", "feature": feature}
                ],
                "preserve": list(m["parameters"]),
            }
            self.assertEqual(store.execute(command)["bodies"][0]["volume_mm3"], "8000")
            before = store.path.read_bytes()
            with self.assertRaises(CadError) as caught:
                store.execute(
                    {
                        "action": "commit",
                        "expected_revision": 2,
                        "transaction_id": "separate",
                        "operations": [
                            {"op": "set_parameter", "id": "turned.x", "mm": "100"}
                        ],
                        "preserve": [],
                    }
                )
            self.assertEqual(caught.exception.detail["code"], "empty_solid")
            self.assertEqual(store.path.read_bytes(), before)
            undo = Store(store.path).execute(
                {"action": "undo", "expected_revision": 2, "transaction_id": "undo"}
            )
            self.assertEqual(undo["bodies"][0]["volume_mm3"], "4000")
