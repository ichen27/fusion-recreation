"""Exact circular stock and holes; independent float-mesh volume/topology checks."""

import copy
from fractions import Fraction as F
import math
import itertools
import unittest

from store import evaluate, CadError
from exports import tessellate
from test_holes import audit_triangles


def cylinder(cx="0", cy="0", radius="40", height="5"):
    return {
        "parameters": {"cx": cx, "cy": cy, "radius": radius, "height": height},
        "fixed": {},
        "features": [
            {
                "kind": "cylinder",
                "id": "stock",
                "x": "cx",
                "y": "cy",
                "radius": "radius",
                "height": "height",
            }
        ],
    }


def flange(cx="0", cy="0"):
    m = cylinder(cx, cy)
    m["parameters"].update(
        left=str(F(cx) - 30), right=str(F(cx) + 30), mount_r="3", bore_r="10"
    )
    m["features"].append(
        {
            "kind": "through_holes",
            "id": "flange",
            "input": "stock",
            "holes": [
                {"id": "left", "x": "left", "y": "cy", "radius": "mount_r"},
                {"id": "right", "x": "right", "y": "cy", "radius": "mount_r"},
                {"id": "bore", "x": "cx", "y": "cy", "radius": "bore_r"},
            ],
        }
    )
    return m


class RoundStock(unittest.TestCase):
    def invalid(self, m, code):
        with self.assertRaises(CadError) as caught:
            evaluate(m)
        self.assertEqual(caught.exception.detail["code"], code, caught.exception.detail)

    def mesh(self, m, feature, holes, coefficient):
        mesh = tessellate(m, feature, 128)
        volume = audit_triangles(
            [[tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]], holes
        )
        self.assertAlmostEqual(
            volume, float(coefficient) * 128 * math.sin(2 * math.pi / 128) / 2, places=6
        )
        return mesh

    def test_cylinder_exact_fractional_parameters_and_mesh(self):
        m = cylinder("3/7", "-5/11", "17/3", "7/5")
        b = evaluate(m)["bodies"][0]
        self.assertEqual(b["volume_mm3"], "2023/45*pi")
        self.assertEqual(
            b["analytic"]["outer_circle"],
            {"center": ["3/7", "-5/11"], "radius": "17/3"},
        )
        self.assertNotIn("outer", b["analytic"])
        self.assertNotIn("boundary", b)
        mesh = self.mesh(m, "stock", 0, F(2023, 45))
        self.assertAlmostEqual(
            mesh["max_radial_error_mm"],
            float(F(17, 3)) * (1 - math.cos(math.pi / 128)),
            places=12,
        )

    def test_flange_holes_translations_and_exact_volume(self):
        for x, y in [("0", "0"), ("1/3", "-2/7"), ("-5000", "7000")]:
            m = flange(x, y)
            b = evaluate(m)["bodies"][0]
            self.assertEqual(b["volume_mm3"], "7410*pi")
            self.assertEqual(
                b["analytic"]["volume"],
                {"constant_mm3": "0", "pi_subtract_mm3": "-7410"},
            )
            self.mesh(m, "flange", 3, 7410)

    def test_exact_outer_tangency_breakout_and_overlap(self):
        for value in ("37", "38", "40"):
            m = flange()
            m["parameters"]["right"] = value
            self.invalid(m, "hole_clearance")
        m = flange()
        m["parameters"]["right"] = "13"
        self.invalid(m, "hole_overlap")
        m = flange()
        m["parameters"]["bore_r"] = "40"
        self.invalid(m, "hole_clearance")
        m = flange()
        m["parameters"]["right"] = str(F(37) - F(1, 10**30))
        self.assertEqual(evaluate(m)["bodies"][0]["volume_mm3"], "7410*pi")
        # A native gap smaller than outer chord sagitta refuses this mesh resolution.
        with self.assertRaises(CadError) as caught:
            tessellate(m, "flange", 256)
        self.assertEqual(caught.exception.detail["code"], "tessellation_failed")

    def test_aligned_circle_bridge_degeneracy_and_hole_orders(self):
        m = flange()
        m["parameters"]["bore_r"] = "12"
        for holes in itertools.permutations(m["features"][-1]["holes"]):
            candidate = copy.deepcopy(m)
            candidate["features"][-1]["holes"] = list(holes)
            for segments in (16, 64, 128):
                mesh = tessellate(candidate, "flange", segments)
                volume = audit_triangles(
                    [
                        [tuple(mesh["vertices"][i]) for i in t]
                        for t in mesh["triangles"]
                    ],
                    3,
                )
                self.assertAlmostEqual(
                    volume,
                    7190 * segments * math.sin(2 * math.pi / segments) / 2,
                    places=6,
                )

    def test_parameter_bounds_and_invalid_edit_are_explicit(self):
        for key, value, code in [
            ("radius", "0", "dimension_range"),
            ("height", "-1", "dimension_range"),
            ("cx", "1000001", "coordinate_range"),
            ("radius", "1000001", "dimension_range"),
        ]:
            m = cylinder()
            m["parameters"][key] = value
            self.invalid(m, code)
        m = flange()
        before = copy.deepcopy(m)
        with self.assertRaises(CadError):
            evaluate(m, [{"op": "set_parameter", "id": "radius", "mm": "20"}])
        self.assertEqual(m, before)

    def test_removed_group_reveals_stock_and_duplicate_groups_reject(self):
        m = flange()
        state = evaluate(m, [{"op": "remove_feature", "id": "flange"}])
        self.assertEqual(state["bodies"][0]["volume_mm3"], "8000*pi")
        second = copy.deepcopy(m["features"][-1])
        second["id"] = "other"
        m["features"].append(second)
        self.invalid(m, "unsupported_branch")


if __name__ == "__main__":
    unittest.main()
