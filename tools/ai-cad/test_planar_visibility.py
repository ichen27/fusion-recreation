"""Exact occlusion against closed planar faces, holes and rational split points."""

from fractions import Fraction as F
import unittest
from planar_visibility import intervals, Budget
from topology import topology_model
from store import CadError
from test_intersection import rectangle
from test_booleans import box, boolean, cases
from test_polyhedral_transforms import moved
from test_round_stock import cylinder


def segments(topology, view=(0, 1, 1)):
    result = []
    for edge, pieces in zip(topology["edges"], intervals(topology, *view)):
        a, b = [[F(v) for v in topology["vertices"][i]] for i in edge["vertices"]]
        for lo, hi, hidden in pieces:
            result.append(
                (
                    [a[i] + lo * (b[i] - a[i]) for i in range(3)],
                    [a[i] + hi * (b[i] - a[i]) for i in range(3)],
                    hidden,
                )
            )
    return result


class PlanarVisibility(unittest.TestCase):
    def topology(self, model):
        return topology_model(model, model["features"][-1]["id"])

    def test_box_near_rim_visible_far_rim_hidden_in_all_views(self):
        topology = self.topology(rectangle("box", 0, 0, 10, 4, 2))
        for view, axis, near, far in [
            ((0, 1, 1), 2, 2, 0),
            ((0, 2, -1), 1, 0, 4),
            ((1, 2, 1), 0, 10, 0),
        ]:
            result = segments(topology, view)
            self.assertEqual(len(result), 8)
            self.assertEqual(sum(hidden for a, b, hidden in result), 4)
            for a, b, hidden in result:
                self.assertEqual(a[axis], far if hidden else near)
                self.assertEqual(b[axis], far if hidden else near)

    def test_partial_occlusion_splits_at_exact_projected_boundary(self):
        for cut in [F(5), F(5) + F(1, 10**30)]:
            model = boolean(
                box("lower", [0, 0, 0], [10, 4, 2]),
                box("upper", [cut, -1, 4], [15, 5, 6]),
                "union",
            )
            result = segments(self.topology(model))
            target = [
                (a, b, h)
                for a, b, h in result
                if a[1] == b[1] == 0 and a[2] == b[2] == 2
            ]
            self.assertEqual(len(target), 2)
            ranges = sorted((min(a[0], b[0]), max(a[0], b[0]), h) for a, b, h in target)
            self.assertEqual(ranges, [(F(0), cut, False), (cut, F(10), True)])

    def test_hole_does_not_occlude_material_seen_through_it(self):
        ring = cases()["through"][0]
        model = boolean(
            ring, box("probe", [3, 3, -3], [7, 7, -2]), "union", id="assembly"
        )
        result = segments(self.topology(model))
        probe = [
            (a, b, h)
            for a, b, h in result
            if a[2] == b[2] == -2
            and all(3 <= a[i] <= 7 and 3 <= b[i] <= 7 for i in (0, 1))
        ]
        self.assertEqual(len(probe), 4)
        self.assertFalse(any(h for a, b, h in probe))

    def test_enclosed_cavity_edges_hidden_and_translation_invariant(self):
        model = cases()["cavity"][0]
        result = segments(self.topology(model))
        interior = [
            h for a, b, h in result if all(0 < v < 10 for p in (a, b) for v in p)
        ]
        self.assertTrue(interior)
        self.assertTrue(all(interior))
        shifted = segments(self.topology(moved(model, (10000, -20000, 30000))))
        recovered = [
            (
                [p[i] - [10000, -20000, 30000][i] for i in range(3)],
                [q[i] - [10000, -20000, 30000][i] for i in range(3)],
                hidden,
            )
            for p, q, hidden in shifted
        ]
        self.assertEqual(result, recovered)

    def test_curves_reject_and_work_is_bounded(self):
        with self.assertRaises(CadError) as caught:
            intervals(self.topology(cylinder()), 0, 1, 1)
        self.assertEqual(caught.exception.detail["code"], "unsupported_drawing")
        with self.assertRaises(CadError) as caught:
            intervals(
                self.topology(rectangle("box", 0, 0, 10, 4, 2)), 0, 1, 1, Budget(1)
            )
        self.assertEqual(caught.exception.detail["code"], "drawing_limit")
        with self.assertRaises(CadError) as caught:
            intervals(
                self.topology(rectangle("box", 0, 0, 10, 4, 2)),
                0,
                1,
                1,
                Budget(seconds=0),
            )
        self.assertEqual(caught.exception.detail["code"], "drawing_timeout")
