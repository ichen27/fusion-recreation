"""Exact movement preserves dimensions/volume and rebuilds world-space operations."""

import copy
from fractions import Fraction as F
from pathlib import Path
import tempfile
import unittest
from store import CadError, Store, evaluate
from test_intersection import rectangle, operations
from test_profiles import signed_boundary_volume
from test_plane_cuts import tetra


def moved(model, offset, id="moved", input=None):
    m = copy.deepcopy(model)
    names = [id + "." + axis for axis in "xyz"]
    m["parameters"].update(zip(names, map(str, offset)))
    m["features"].append(
        {
            "kind": "translate",
            "id": id,
            "input": input or m["features"][-1]["id"],
            "offset": names,
        }
    )
    return m


class Translation(unittest.TestCase):
    def test_exact_vertices_normals_planes_and_volume_at_signed_offsets(self):
        for base in [tetra(), rectangle("stock", -4, -3, 10, 8, 6)]:
            original = evaluate(base)["bodies"][0]
            # Use a zero move to materialize the simple-profile's convex boundary.
            boundary = evaluate(moved(base, [0, 0, 0]))["bodies"][0]["boundary"]
            for delta in [
                [F(1, 3), F(-7, 2), F(5, 4)],
                [1000000, -1000000, 1000000],
                [0, 0, 0],
            ]:
                actual = evaluate(moved(base, delta))["bodies"][0]
                self.assertEqual(actual["volume_mm3"], original["volume_mm3"])
                self.assertEqual(
                    signed_boundary_volume(actual["boundary"]), F(actual["volume_mm3"])
                )
                expected = {
                    tuple(F(v) + d for v, d in zip(point, delta))
                    for point in boundary["vertices"]
                }
                self.assertEqual(
                    {tuple(map(F, p)) for p in actual["boundary"]["vertices"]}, expected
                )
                for face in actual["boundary"]["faces"]:
                    for point in actual["boundary"]["vertices"]:
                        self.assertLessEqual(
                            sum(F(n) * F(v) for n, v in zip(face["normal"], point)),
                            F(face["offset"]),
                        )

    def test_translation_composes_and_can_feed_global_plane_cut(self):
        m = moved(rectangle("stock", 0, 0, 10, 10, 10), [2, -3, 5])
        m = moved(m, [1, 2, -1], "again")
        direct = moved(rectangle("stock", 0, 0, 10, 10, 10), [3, -1, 4])
        a = evaluate(m)["bodies"][0]["boundary"]
        b = evaluate(direct)["bodies"][0]["boundary"]
        self.assertEqual(a, b)
        m["parameters"]["world_z"] = "9"
        m["features"].append(
            {
                "kind": "plane_cut",
                "id": "cut",
                "input": "again",
                "normal": ["0", "0", "1"],
                "offset": "world_z",
            }
        )
        self.assertEqual(evaluate(m)["bodies"][0]["volume_mm3"], "500")

    def test_wide_computed_coefficients_remain_valid(self):
        tiny = F(1, 2**110 + 3)
        base = rectangle("stock", tiny, tiny, tiny, 2 * tiny, 3 * tiny)
        result = evaluate(moved(base, [F(1, 3), F(1, 7), F(-1, 11)]))["bodies"][0]
        self.assertEqual(F(result["volume_mm3"]), 6 * tiny**3)
        self.assertEqual(signed_boundary_volume(result["boundary"]), 6 * tiny**3)

    def test_invalid_offsets_references_and_unsupported_stock(self):
        base = rectangle("stock", 0, 0, 10, 10, 10)
        for delta, code in [
            ([1000001, 0, 0], "translation_range"),
            ([0, "1.5", 0], "invalid_number"),
        ]:
            with self.assertRaises(CadError) as caught:
                evaluate(moved(base, delta))
            self.assertEqual(caught.exception.detail["code"], code)
        with self.assertRaises(CadError) as caught:
            evaluate(moved(base, [0, 0, 0], input="missing"))
        self.assertEqual(caught.exception.detail["code"], "unsupported_reference")
        from test_round_stock import cylinder

        with self.assertRaises(CadError) as caught:
            evaluate(moved(cylinder(), [1, 2, 3]))
        self.assertEqual(caught.exception.detail["code"], "unsupported_reference")
        m = moved(base, [1, 2, 3])
        m = moved(m, [1, 2, 3], "fork", input="stock")
        with self.assertRaises(CadError) as caught:
            evaluate(m)
        self.assertEqual(caught.exception.detail["code"], "unsupported_branch")

    def test_move_intersection_edit_reopen_undo_and_failure_are_atomic(self):
        a = rectangle("a", 0, 0, 40, 30, 20)
        b = moved(rectangle("b", 0, 0, 40, 30, 20), [20, 5, 5])
        m = {
            "parameters": {**a["parameters"], **b["parameters"]},
            "fixed": {},
            "features": a["features"]
            + b["features"]
            + [{"kind": "intersection", "id": "common", "left": "a", "right": "moved"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            s = Store(Path(directory) / "model.json")
            created = s.execute(
                {
                    "action": "commit",
                    "expected_revision": 0,
                    "transaction_id": "create",
                    "operations": operations(m),
                    "preserve": [],
                }
            )
            self.assertEqual(created["bodies"][0]["volume_mm3"], "7500")
            edit = {
                "action": "commit",
                "expected_revision": 1,
                "transaction_id": "move",
                "operations": [{"op": "set_parameter", "id": "moved.x", "mm": "25"}],
                "preserve": [],
            }
            self.assertEqual(s.execute(edit)["bodies"][0]["volume_mm3"], "5625")
            before = s.path.read_bytes()
            edit.update(expected_revision=2, transaction_id="separate")
            edit["operations"][0]["mm"] = "40"
            with self.assertRaises(CadError) as caught:
                s.execute(edit)
            self.assertEqual(caught.exception.detail["code"], "empty_solid")
            self.assertEqual(s.path.read_bytes(), before)
            undo = Store(s.path).execute(
                {"action": "undo", "expected_revision": 2, "transaction_id": "undo"}
            )
            self.assertEqual(undo["bodies"][0]["volume_mm3"], "7500")
