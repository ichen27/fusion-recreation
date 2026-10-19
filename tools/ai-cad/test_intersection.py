"""Convex solid intersections: exact independent volumes and safe model history."""

import copy
from fractions import Fraction as F
from pathlib import Path
import random
import tempfile
import unittest
from store import CadError, Store, evaluate
from exports import tessellate
from test_holes import audit_triangles
from test_profiles import model_for, signed_boundary_volume


def prism(name, points, height):
    m = model_for(points, str(height))
    params = {name + "." + k: v for k, v in m["parameters"].items()}
    profile = m["features"][0]
    profile.update(kind="planar_profile", id=name + ".profile")
    for vertex in profile["vertices"]:
        for axis in ["x", "y"]:
            vertex[axis] = name + "." + vertex[axis]
    m["features"][1].update(id=name, profile=profile["id"], height=name + ".height")
    m["parameters"] = params
    return m


def combined(a, b):
    return {
        "parameters": {**a["parameters"], **b["parameters"]},
        "fixed": {},
        "features": a["features"]
        + b["features"]
        + [
            {
                "kind": "intersection",
                "id": "common",
                "left": a["features"][-1]["id"],
                "right": b["features"][-1]["id"],
            }
        ],
    }


def rectangle(name, x, y, w, d, h):
    return prism(name, [(x, y), (x + w, y), (x + w, y + d), (x, y + d)], h)


def operations(m):
    return [
        {"op": "define_parameter", "id": k, "mm": v} for k, v in m["parameters"].items()
    ] + [{"op": "add_feature", "feature": f} for f in m["features"]]


class Intersection(unittest.TestCase):
    def verify(self, m, volume):
        result = evaluate(m)
        self.assertEqual(len(result["bodies"]), 1)
        body = result["bodies"][0]
        self.assertEqual(F(body["volume_mm3"]), volume)
        self.assertEqual(signed_boundary_volume(body["boundary"]), volume)
        mesh = tessellate(m, body["feature_id"], 64)
        self.assertAlmostEqual(
            audit_triangles(
                [[tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]], 0
            ),
            float(volume),
            places=7,
        )
        return result

    def test_seeded_offset_boxes_commute_with_exact_overlap_volume(self):
        rng = random.Random(31)
        for _ in range(25):
            ax, ay, bx, by = [F(rng.randint(-6, 6), 3) for _ in range(4)]
            aw, ad, bw, bd = [F(rng.randint(6, 15)) for _ in range(4)]
            ah, bh = [F(rng.randint(1, 10)) for _ in range(2)]
            expected = (
                (min(ax + aw, bx + bw) - max(ax, bx))
                * (min(ay + ad, by + bd) - max(ay, by))
                * min(ah, bh)
            )
            a, b = (
                rectangle("a", ax, ay, aw, ad, ah),
                rectangle("b", bx, by, bw, bd, bh),
            )
            self.verify(combined(a, b), expected)
            self.verify(combined(b, a), expected)

    def test_triangle_overlap_identical_contained_and_thin_volume(self):
        a = rectangle("a", 0, 0, 40, 40, 20)
        b = prism("b", [(0, 0), (60, 0), (0, 60)], 30)
        self.verify(combined(a, b), F(28000))
        self.verify(combined(a, rectangle("b", 0, 0, 40, 40, 20)), F(32000))
        self.verify(combined(a, rectangle("b", 5, 5, 10, 10, 5)), F(500))
        # Positive rational overlap must not be mistaken for contact by a tolerance.
        m = combined(
            rectangle("a", 0, 0, 1, 1, 1),
            rectangle("b", F(1) - F(1, 10**12), 0, 1, 1, 1),
        )
        body = evaluate(m)["bodies"][0]
        self.assertEqual(F(body["volume_mm3"]), F(1, 10**12))
        self.assertEqual(signed_boundary_volume(body["boundary"]), F(1, 10**12))

    def test_disjoint_and_face_edge_contact_are_empty(self):
        a = rectangle("a", 0, 0, 1, 1, 1)
        for x, y in [(2, 0), (1, 0), (1, 1)]:
            with self.assertRaises(CadError) as caught:
                evaluate(combined(a, rectangle("b", x, y, 1, 1, 1)))
            self.assertEqual(caught.exception.detail["code"], "empty_solid")

    def test_reference_branch_and_unsupported_geometry_errors(self):
        m = combined(rectangle("a", 0, 0, 10, 10, 10), rectangle("b", 2, 2, 10, 10, 10))
        for key, value, code in [
            ("left", "missing", "unsupported_reference"),
            ("right", "a", "invalid_intersection"),
        ]:
            bad = copy.deepcopy(m)
            bad["features"][-1][key] = value
            with self.assertRaises(CadError) as caught:
                evaluate(bad)
            self.assertEqual(caught.exception.detail["code"], code)
        branched = copy.deepcopy(m)
        branched["features"].append(
            {
                "kind": "plane_cut",
                "id": "fork",
                "input": "a",
                "normal": ["0", "0", "1"],
                "offset": "a.height",
            }
        )
        with self.assertRaises(CadError) as caught:
            evaluate(branched)
        self.assertEqual(caught.exception.detail["code"], "unsupported_branch")
        concave = prism("b", [(0, 0), (10, 0), (2, 2), (0, 10)], 10)
        with self.assertRaises(CadError) as caught:
            evaluate(combined(rectangle("a", 0, 0, 10, 10, 10), concave))
        self.assertEqual(caught.exception.detail["code"], "unsupported_reference")
        from test_round_stock import cylinder

        with self.assertRaises(CadError) as caught:
            evaluate(combined(rectangle("a", 0, 0, 10, 10, 10), cylinder()))
        self.assertEqual(caught.exception.detail["code"], "unsupported_reference")

    def test_chained_intersection_plane_and_atomic_upstream_edit(self):
        m = combined(
            rectangle("a", 0, 0, 40, 40, 20), prism("b", [(0, 0), (60, 0), (0, 60)], 30)
        )
        m["parameters"]["top"] = "10"
        m["features"].append(
            {
                "kind": "plane_cut",
                "id": "low",
                "input": "common",
                "normal": ["0", "0", "1"],
                "offset": "top",
            }
        )
        self.verify(m, F(14000))
        with tempfile.TemporaryDirectory() as directory:
            s = Store(Path(directory) / "model.json")
            s.execute(
                {
                    "action": "commit",
                    "expected_revision": 0,
                    "transaction_id": "create",
                    "operations": operations(m),
                    "preserve": [],
                }
            )
            before = s.path.read_bytes()
            # Changing the triangle coordinate shared by its two intercepts to -60 separates it.
            key = next(
                k
                for k, v in m["parameters"].items()
                if k.startswith("b.") and v == "60"
            )
            command = {
                "action": "commit",
                "expected_revision": 1,
                "transaction_id": "move",
                "operations": [{"op": "set_parameter", "id": key, "mm": "-60"}],
                "preserve": [],
            }
            with self.assertRaises(CadError) as caught:
                s.execute(command)
            self.assertEqual(caught.exception.detail["code"], "empty_solid")
            self.assertEqual(s.path.read_bytes(), before)
            command["operations"][0]["mm"] = "50"
            self.assertEqual(s.execute(command)["bodies"][0]["volume_mm3"], "11500")
            undone = Store(s.path).execute(
                {"action": "undo", "expected_revision": 2, "transaction_id": "undo"}
            )
            self.assertEqual(undone["bodies"][0]["volume_mm3"], "14000")

    def test_intersections_chain_and_accept_oblique_boundaries(self):
        from test_plane_cuts import tetra

        a = tetra()
        b = rectangle("b", 0, 0, 60, 60, 20)
        m = combined(a, b)
        # Tetra x>=10,x+y+z<=60 truncated to z<=20:
        # integral (50-z)^2/2 dz from 0 to 20 = 49000/3.
        self.verify(m, F(49000, 3))
        c = rectangle("c", 0, 0, 60, 60, 10)
        m["parameters"].update(c["parameters"])
        m["features"] += c["features"] + [
            {"kind": "intersection", "id": "common2", "left": "common", "right": "c"}
        ]
        self.verify(m, F(30500, 3))
