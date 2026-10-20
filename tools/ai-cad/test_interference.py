"""Read-only exact overlap volumes, hollow material, contact and unsupported bodies."""

import copy
from fractions import Fraction as F
from pathlib import Path
import random
import tempfile
import unittest
from interference import inspect_interference, dispatch_interference
from store import Store, CadError
from test_intersection import combined, rectangle, prism, operations
from test_booleans import box, cases
from test_instances import instance
from test_frustum import frustum


def pair(a, b):
    model = combined(a, b)
    model["features"].pop()
    return model


def check(model, left, right):
    return inspect_interference(model, left, right)


def examples():
    cavity = cases()["cavity"][0]
    return {
        "overlap": (
            instance(rectangle("part", 0, 0, 10, 4, 2), offset=(5, 0, 0)),
            "part",
            "copy",
            "40",
        ),
        "face_contact": (
            instance(rectangle("part", 0, 0, 10, 4, 2), offset=(10, 0, 0)),
            "part",
            "copy",
            "0",
        ),
        "edge_contact": (
            instance(rectangle("part", 0, 0, 10, 4, 2), offset=(10, 4, 0)),
            "part",
            "copy",
            "0",
        ),
        "point_contact": (
            instance(rectangle("part", 0, 0, 10, 4, 2), offset=(10, 4, 2)),
            "part",
            "copy",
            "0",
        ),
        "inside_cavity": (
            pair(cavity, box("probe", [3, 3, 3], [7, 7, 7])),
            "result",
            "probe.placed",
            "0",
        ),
        "cavity_contact": (
            pair(cavity, box("probe", [2, 2, 2], [8, 8, 8])),
            "result",
            "probe.placed",
            "0",
        ),
        "cavity_wall": (
            pair(cavity, box("probe", [1, 1, 1], [3, 3, 3])),
            "result",
            "probe.placed",
            "7",
        ),
        "separate_pieces": (
            pair(cases()["separate"][0], box("probe", [5, 0, 0], [25, 10, 10])),
            "result",
            "probe",
            "1000",
        ),
        "concave": (
            pair(
                prism("left", [(0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4)], 2),
                rectangle("right", F(1, 2), F(1, 2), 3, 3, 2),
            ),
            "left",
            "right",
            "11/2",
        ),
        "disjoint_with_overlapping_bounds": (
            pair(
                prism("left", [(0, 0), (2, 0), (0, 2)], 2),
                prism("right", [(2, 2), (F(1, 2), 2), (2, F(1, 2))], 2),
            ),
            "left",
            "right",
            "0",
        ),
    }


class Interference(unittest.TestCase):
    def test_cavity_contact_nonconvex_and_disconnected_material(self):
        for name, (model, left, right, expected) in examples().items():
            with self.subTest(name=name):
                for a, b in [(left, right), (right, left)]:
                    result = check(model, a, b)
                    self.assertEqual(result["overlap_volume_mm3"], expected)
                    self.assertEqual(result["positive_volume_overlap"], F(expected) > 0)
                    self.assertEqual((result["left"], result["right"]), (a, b))

    def test_seeded_fractional_boxes_and_tiny_positive_overlap(self):
        rng = random.Random(731)
        for _ in range(25):
            offset = [F(rng.randint(-25, 25), 3) for _ in range(3)]
            model = instance(rectangle("part", 0, 0, 10, 4, 2), offset=offset)
            expected = F(1)
            for size, delta in zip([10, 4, 2], offset):
                expected *= max(F(0), size - abs(delta))
            result = check(model, "part", "copy")
            self.assertEqual(F(result["overlap_volume_mm3"]), expected)
        tiny = F(1, 10**30)
        model = instance(rectangle("part", 0, 0, 10, 4, 2), offset=(10 - tiny, 0, 0))
        result = check(model, "part", "copy")
        self.assertEqual(F(result["overlap_volume_mm3"]), 8 * tiny)
        self.assertTrue(result["positive_volume_overlap"])
        identical = instance(rectangle("part", 0, 0, 10, 4, 2), offset=(0, 0, 0))
        self.assertEqual(check(identical, "part", "copy")["overlap_volume_mm3"], "80")

    def test_unsupported_and_missing_bodies_do_not_report_clearance(self):
        model = instance(frustum(), offset=(100, 0, 0))
        with self.assertRaises(CadError) as caught:
            check(model, "taper", "copy")
        self.assertEqual(caught.exception.detail["code"], "unsupported_interference")
        m, left, right, _ = examples()["cavity_wall"]
        for a, b, code in [
            (left, left, "invalid_pair"),
            ("missing", right, "missing_body"),
            ("a", right, "missing_body"),
        ]:
            with self.assertRaises(CadError) as caught:
                check(m, a, b)
            self.assertEqual(caught.exception.detail["code"], code)

    def test_read_only_stale_revision_and_content_cache(self):
        model, left, right, _ = examples()["overlap"]
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
            args = dict(expected_revision=1, left=left, right=right)
            result = dispatch_interference(store, args)
            self.assertEqual(result["result"]["overlap_volume_mm3"], "40")
            self.assertEqual(dispatch_interference(store, args), result)
            for change, code in [
                ({"expected_revision": 0}, "revision_conflict"),
                ({"expected_revision": True}, "revision_conflict"),
                ({"right": left}, "invalid_pair"),
                ({"left": False}, "invalid_command"),
                ({"extra": 0}, "invalid_command"),
            ]:
                self.assertEqual(
                    dispatch_interference(store, {**args, **change})["error"]["code"],
                    code,
                )
            self.assertEqual(store.path.read_bytes(), before)
            store.execute(
                dict(
                    action="commit",
                    expected_revision=1,
                    transaction_id="separate",
                    operations=[dict(op="set_parameter", id="copy.x", mm="20")],
                    preserve=[],
                )
            )
            self.assertEqual(
                dispatch_interference(store, args)["error"]["code"], "revision_conflict"
            )
            self.assertFalse(
                dispatch_interference(store, {**args, "expected_revision": 2})[
                    "result"
                ]["positive_volume_overlap"]
            )
            other = Store(Path(directory) / "other.json")
            changed = copy.deepcopy(model)
            changed["parameters"]["copy.x"] = "0"
            other.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="different",
                    operations=operations(changed),
                    preserve=[],
                )
            )
            store.path.write_bytes(other.path.read_bytes())
            self.assertEqual(
                dispatch_interference(store, args)["result"]["overlap_volume_mm3"], "80"
            )


if __name__ == "__main__":
    unittest.main()
