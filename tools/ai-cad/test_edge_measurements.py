"""Exact lengths, arc/chord distinction, seams and revision-bound read isolation."""

import copy
from fractions import Fraction as F
import math
from pathlib import Path
import tempfile
import unittest
from edge_measurements import measure_edge, dispatch_edge_measure
from topology import topology_model
from store import Store, CadError
from test_frustum import frustum
from test_planar_loft import loft
from test_intersection import operations
from test_polyhedral_transforms import moved, turned


def measurements(model):
    feature = model["features"][-1]["id"]
    topology = topology_model(model, feature)
    return [measure_edge(model, feature, i) for i in range(len(topology["edges"]))]


class EdgeMeasurements(unittest.TestCase):
    def test_arc_chord_and_smooth_seams_have_independent_closed_forms(self):
        rows = measurements(frustum("10", "7", "4"))
        lines = [r for r in rows if r["curve"]["kind"] == "line"]
        arcs = [r for r in rows if r["curve"]["kind"] == "quarter_circle"]
        self.assertEqual(len(lines), 4)
        self.assertEqual(len(arcs), 8)
        for row in lines:
            self.assertEqual((row["length_mm"], row["chord_squared_mm2"]), ("5", "25"))
            self.assertTrue(row["patch_seam"])
            self.assertEqual(len(row["incident_surfaces"]), 1)
        for row in arcs:
            r = F(row["curve"]["radius"])
            self.assertEqual(row["length_mm"], f"{r / 2}*pi")
            self.assertEqual(row["chord_squared_mm2"], str(2 * r * r))
            self.assertEqual(row["chord_mm"], f"sqrt({2 * r * r})")
            self.assertAlmostEqual(row["length_approx_mm"], float(r) * math.pi / 2)
            self.assertFalse(row["patch_seam"])
            self.assertEqual(len(row["incident_surfaces"]), 2)

    def test_irrational_and_fractional_lengths_survive_placements(self):
        for model, expected in [
            (frustum("10", "7", "5"), "sqrt(34)"),
            (frustum("10", "17/2", "2"), "5/2"),
        ]:
            original = measurements(model)
            for axis in "xyz":
                for turns in (1, 2, 3):
                    placed = measurements(
                        turned(moved(model, (F(1, 7), F(-2, 3), F(4, 9))), axis, turns)
                    )
                    for a, b in zip(original, placed):
                        for key in (
                            "length_mm",
                            "chord_mm",
                            "chord_squared_mm2",
                            "incident_surfaces",
                            "patch_seam",
                        ):
                            self.assertEqual(a[key], b[key])
                    self.assertEqual(
                        {
                            r["length_mm"]
                            for r in placed
                            if r["curve"]["kind"] == "line"
                        },
                        {expected},
                    )

    def test_planar_edges_and_tiny_lengths(self):
        # Triangle sides independently form a 3-4-5 triangle. Vertical edges are 2 mm.
        triangle = [(0, 0), (3, 0), (0, 4)]
        rows = measurements(loft(bottom=triangle, top=triangle, height="2"))
        self.assertEqual(
            sorted(r["length_mm"] for r in rows),
            ["2", "2", "2", "3", "3", "4", "4", "5", "5"],
        )
        self.assertFalse(any(r["patch_seam"] for r in rows))
        tiny = str(F(1, 10**30))
        rows = measurements(loft(bottom=triangle, top=triangle, height=tiny))
        self.assertEqual(sum(r["length_mm"] == tiny for r in rows), 3)
        self.assertTrue(all(r["length_approx_mm"] > 0 for r in rows))

    def test_invalid_references_do_not_retarget_or_write_and_cache_is_content_bound(
        self,
    ):
        model = frustum("10", "7", "4")
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
            args = dict(expected_revision=1, feature_id="taper", edge_index=0)
            first = dispatch_edge_measure(store, args)
            self.assertIn("result", first)
            self.assertEqual(first, dispatch_edge_measure(store, args))
            for change, code in [
                ({"expected_revision": 0}, "revision_conflict"),
                ({"expected_revision": True}, "revision_conflict"),
                ({"edge_index": -1}, "invalid_command"),
                ({"edge_index": True}, "invalid_command"),
                ({"edge_index": "0"}, "invalid_command"),
                ({"edge_index": 10000}, "missing_edge"),
                ({"feature_id": "gone"}, "missing_body"),
                ({"extra": 0}, "invalid_command"),
            ]:
                self.assertEqual(
                    dispatch_edge_measure(store, {**args, **change})["error"]["code"],
                    code,
                )
            self.assertEqual(store.path.read_bytes(), before)
            store.execute(
                dict(
                    action="commit",
                    expected_revision=1,
                    transaction_id="taller",
                    operations=[dict(op="set_parameter", id="height", mm="12")],
                    preserve=[],
                )
            )
            self.assertEqual(
                dispatch_edge_measure(store, args)["error"]["code"], "revision_conflict"
            )
            now = dispatch_edge_measure(store, {**args, "expected_revision": 2})
            self.assertEqual(now["result"]["revision"], 2)
            # Same revision from another valid native document must not reuse old geometry.
            other = Store(Path(directory) / "other.json")
            different = copy.deepcopy(model)
            different["parameters"]["bottom"] = "20"
            other.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create-other",
                    operations=operations(different),
                    preserve=[],
                )
            )
            store.path.write_bytes(other.path.read_bytes())
            self.assertNotEqual(dispatch_edge_measure(store, args), first)
        with self.assertRaises(CadError) as caught:
            measure_edge(turned(model, "x", 1), "taper", 0)
        self.assertEqual(caught.exception.detail["code"], "missing_body")


if __name__ == "__main__":
    unittest.main()
