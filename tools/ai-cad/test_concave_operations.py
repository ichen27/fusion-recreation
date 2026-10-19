"""Exact simple-profile decomposition supplies the native solid operation pipeline."""

import copy
from fractions import Fraction as F
import unittest
from store import CadError, evaluate
from test_intersection import prism, rectangle
from test_booleans import boolean
from test_polyhedral_cuts import cut
from test_polyhedral_transforms import moved, turned
from exports import tessellate
from test_holes import audit_triangles


def l_shape(reverse=False):
    points = [(0, 0), (10, 0), (10, 3), (3, 3), (3, 10), (0, 10)]
    return prism("l", list(reversed(points)) if reverse else points, 4)


def signed_area(points):
    return (
        abs(
            sum(
                a[0] * b[1] - b[0] * a[1]
                for a, b in zip(points, points[1:] + points[:1])
            )
        )
        / 2
    )


class ConcaveOperations(unittest.TestCase):
    def check(self, model, expected, components=1):
        body = evaluate(model)["bodies"][0]
        self.assertEqual(F(body["volume_mm3"]), expected)
        self.assertEqual(len(body["components"]), components)
        mesh = tessellate(model, body["feature_id"])
        actual = audit_triangles(
            [[tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]],
            holes=0,
            shells=components,
        )
        self.assertAlmostEqual(actual, float(expected), places=7)
        return body

    def test_both_windings_feed_all_supported_solid_operations(self):
        for reverse in [False, True]:
            model = l_shape(reverse)
            self.assertIn("analytic", evaluate(model)["bodies"][0])
            self.check(moved(model, (5, -2, 3)), 204)
            self.check(turned(model, "y", 1), 204)
            self.check(cut(model, (1, 0, 0), 5), 144)
            cutter = rectangle("b", 2, 2, 4, 4, 4)
            self.check(boolean(model, cutter, "intersection"), 28)
            self.check(boolean(model, cutter, "difference"), 176)
            self.check(boolean(model, cutter, "union"), 240)

    def test_maximum_vertex_comb_and_fractional_scale(self):
        points = [(F(0), F(0)), (F(29, 2), F(0))] + [
            (F(29 - i, 2), F(5 if i % 2 == 0 else 3)) for i in range(30)
        ]
        self.assertEqual(len(points), 32)
        for reverse in [False, True]:
            outline = list(reversed(points)) if reverse else points
            model = prism("comb", outline, 2)
            self.check(cut(model, offset=2), signed_area(points) * 2)
        epsilon = F(1, 2**80)
        small = prism(
            "tiny",
            [
                (F(x) * epsilon, F(y) * epsilon)
                for x, y in [(0, 0), (10, 0), (10, 3), (3, 3), (3, 10), (0, 10)]
            ],
            epsilon,
        )
        result = evaluate(moved(small, (1, 1, 1)))["bodies"][0]
        self.assertEqual(F(result["volume_mm3"]), 51 * epsilon**3)
        # Exact geometry remains valid even if world-space float64 tessellation collapses.
        with self.assertRaises(CadError) as e:
            tessellate(moved(small, (1, 1, 1)), "moved")
        self.assertEqual(e.exception.detail["code"], "tessellation_failed")

    def test_cut_removes_concave_bridge_and_later_operations_keep_components(self):
        u = prism(
            "u",
            [(0, 0), (10, 0), (10, 10), (7, 10), (7, 3), (3, 3), (3, 10), (0, 10)],
            2,
        )
        split = cut(u, (0, -1, 0), -5)
        self.check(split, 60, 2)
        self.check(turned(moved(split), "x", 1), 60, 2)

    def test_invalid_source_remains_rejected_and_legacy_intersection_is_convex(self):
        model = l_shape()
        bad = copy.deepcopy(model)
        # Make one nonadjacent corner coincide with the origin.
        bad["features"][0]["vertices"][3].update(x="l.c0", y="l.c0")
        with self.assertRaises(CadError):
            evaluate(moved(bad))
        legacy = boolean(model, rectangle("b", 2, 2, 4, 4, 4), "intersection")
        legacy["features"][-1].pop("operation")
        legacy["features"][-1]["kind"] = "intersection"
        with self.assertRaises(CadError) as e:
            evaluate(legacy)
        self.assertEqual(e.exception.detail["code"], "unsupported_reference")


if __name__ == "__main__":
    unittest.main()
