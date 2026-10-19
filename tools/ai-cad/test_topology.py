"""Exact shared boundaries, placement, revision gating and content cache freshness."""

import copy
from fractions import Fraction as F
from pathlib import Path
import tempfile
import unittest
from topology import topology_model, dispatch_topology
from store import Store
from test_counterbores import counterbored
from test_intersection import operations
from test_polyhedral_transforms import turned, moved


def inspect(model):
    return topology_model(model, model["features"][-1]["id"])


class Topology(unittest.TestCase):
    def test_all_quarter_turns_transform_exact_vertices_without_renaming(self):
        model = counterbored()
        source = inspect(model)
        points = [list(map(F, p)) for p in source["vertices"]]
        for axis, i in [("x", 0), ("y", 1), ("z", 2)]:
            for n in (1, 2, 3):
                expected = copy.deepcopy(points)
                for _ in range(n):
                    for p in expected:
                        a, b = (i + 1) % 3, (i + 2) % 3
                        p[a], p[b] = -p[b], p[a]
                actual = inspect(turned(model, axis, n))
                self.assertEqual(
                    actual["vertices"], [[str(v) for v in p] for p in expected]
                )
                self.assertEqual(list(actual["surfaces"]), list(source["surfaces"]))
                self.assertEqual(actual["shell_euler"], [-2])
        delta = (F(1, 3), F(-2, 7), F(5, 11))
        actual = inspect(moved(model, delta))
        self.assertEqual(
            actual["vertices"],
            [[str(p[i] + delta[i]) for i in range(3)] for p in points],
        )

    def test_thin_exact_shoulders_do_not_depend_on_display_tolerance(self):
        model = counterbored()
        model["parameters"]["recess_radius"] = (
            "3000000000000000000001/1000000000000000000000"
        )
        model["parameters"]["recess_depth"] = "1/1000000000000000000000"
        actual = inspect(model)
        self.assertEqual(actual["shell_euler"], [-2])
        shoulders = [
            s for name, s in actual["surfaces"].items() if name.endswith("/shoulder")
        ]
        self.assertEqual(len(shoulders), 2)
        self.assertEqual(
            F(shoulders[0]["offset"]), 6 - F(model["parameters"]["recess_depth"])
        )

    def test_read_only_revision_and_content_cache(self):
        model = counterbored()
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
            command = dict(expected_revision=1, feature_id="part")
            reply = dispatch_topology(store, command)
            self.assertEqual(reply["result"]["naming"], "authored_surfaces")
            self.assertEqual(dispatch_topology(store, command), reply)
            for args, code in [
                (dict(expected_revision=0, feature_id="part"), "revision_conflict"),
                (dict(expected_revision=True, feature_id="part"), "revision_conflict"),
                (dict(expected_revision=1, feature_id="missing"), "missing_body"),
                ([], "invalid_command"),
            ]:
                self.assertEqual(dispatch_topology(store, args)["error"]["code"], code)
            self.assertEqual(store.path.read_bytes(), before)
            store.execute(
                dict(
                    action="commit",
                    expected_revision=1,
                    transaction_id="deeper",
                    operations=[dict(op="set_parameter", id="recess_depth", mm="3")],
                    preserve=[],
                )
            )
            after = dispatch_topology(
                store, dict(expected_revision=2, feature_id="part")
            )["result"]
            self.assertNotEqual(after["vertices"], reply["result"]["vertices"])
            self.assertEqual(list(after["surfaces"]), list(reply["result"]["surfaces"]))
            self.assertEqual(
                dispatch_topology(store, command)["error"]["code"], "revision_conflict"
            )


if __name__ == "__main__":
    unittest.main()
