"""Simple nonconvex prism validation, exact circles, and independent mesh integrals."""

import copy
from fractions import Fraction as F
import math
import random
import unittest
from store import evaluate, CadError
from test_profiles import model_for
from test_holes import audit_triangles
from exports import tessellate

L = [(0, 0), (80, 0), (80, 20), (20, 20), (20, 60), (0, 60)]


def planar(points=L, height="5", reverse=False):
    model = model_for(points, height, reverse)
    model["features"][0]["kind"] = "planar_profile"
    return model


def drill(model, x="10", y="40", r="3"):
    model["parameters"].update(hx=x, hy=y, hr=r)
    model["features"].append(
        {
            "kind": "through_holes",
            "id": "drilled",
            "input": "solid",
            "holes": [{"id": "mount", "x": "hx", "y": "hy", "radius": "hr"}],
        }
    )
    return model


class Planar(unittest.TestCase):
    def invalid(self, m, code="invalid_profile"):
        with self.assertRaises(CadError) as caught:
            evaluate(m)
        self.assertEqual(caught.exception.detail["code"], code)

    def mesh_volume(self, m, holes=0):
        body = evaluate(m)["bodies"][0]
        mesh = tessellate(m, body["feature_id"], 128)
        return audit_triangles(
            [[tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]], holes
        )

    def test_l_both_windings_and_old_convex_contract(self):
        for reverse in (False, True):
            m = planar(reverse=reverse)
            body = evaluate(m)["bodies"][0]
            self.assertEqual(body["volume_mm3"], "12000")
            self.assertEqual(body["analytic"]["kind"], "polygon_prism")
            self.assertNotIn("boundary", body)
            self.assertAlmostEqual(self.mesh_volume(m), 12000, places=8)
            m["features"][0]["kind"] = "polygon_profile"
            self.invalid(m)

    def test_transformed_simple_polygons_exact_volume_and_mesh(self):
        rng = random.Random(103)
        for i in range(24):
            a, b, c, d = [F(rng.randint(-5, 5), rng.randint(1, 3)) for _ in range(4)]
            det = a * d - b * c
            if not det:
                continue
            tx, ty = F(i, 7), F(-i, 11)
            m = planar(
                [(a * x + b * y + tx, c * x + d * y + ty) for x, y in L],
                "7/3",
                bool(i % 2),
            )
            expected = F(2400) * abs(det) * F(7, 3)
            self.assertEqual(F(evaluate(m)["bodies"][0]["volume_mm3"]), expected)
            self.assertAlmostEqual(self.mesh_volume(m), float(expected), places=6)

    def test_crossing_touching_repeated_and_overlapping_edges_reject(self):
        cases = [
            [(0, 0), (4, 4), (0, 4), (4, 0)],
            [(0, 0), (4, 0), (4, 4), (2, 0), (0, 4)],
            [(0, 0), (4, 0), (4, 4), (0, 4), (4, 0)],
            [(0, 0), (4, 0), (2, 0), (2, 4), (0, 4)],
            [(0, 0), (2, 0), (4, 0), (0, 4)],
        ]
        for points in cases:
            self.invalid(planar(points))
        self.invalid(planar([(0, 0), (2, 0), (2, 0), (0, 2)]))

    def test_hole_uses_segment_clearance_not_convex_halfplanes(self):
        m = drill(planar())
        b = evaluate(m)["bodies"][0]
        self.assertEqual(b["volume_mm3"], "12000 - (45)*pi")
        self.assertAlmostEqual(
            self.mesh_volume(m, 1),
            12000 - 45 * 128 * math.sin(2 * math.pi / 128) / 2,
            places=7,
        )
        for x, y, r in [
            ("40", "40", "3"),
            ("19", "40", "3"),
            ("10", "40", "10"),
            ("15", "15", "8"),
        ]:
            self.invalid(drill(planar(), x, y, r), "hole_clearance")
        # Closest boundary is the inward corner, not an edge's infinite line.
        accepted = drill(planar(), "15", "15", "7")
        self.assertEqual(
            evaluate(accepted)["bodies"][0]["volume_mm3"], "12000 - (245)*pi"
        )

    def test_exact_near_corner_distance_and_failed_edit(self):
        # At (17,16) the inward corner (20,20) is exactly 5 mm away.
        self.invalid(drill(planar(), "17", "16", "5"), "hole_clearance")
        m = drill(planar(), "17", "16", str(F(5) - F(1, 10**30)))
        state = evaluate(m)
        self.assertEqual(state["model"], m)
        before = copy.deepcopy(m)
        with self.assertRaises(CadError):
            evaluate(m, [{"op": "set_parameter", "id": "hx", "mm": "30"}])
        self.assertEqual(m, before)


if __name__ == "__main__":
    unittest.main()
