"""Exact coaxial clipping, opposing axes, contacts and editable dependencies."""

import copy
from fractions import Fraction as F
import math
import random
from pathlib import Path
import tempfile
import unittest
from store import CadError, Store, evaluate
from exports import tessellate
from topology import topology_model
from measurements import measure_model
from test_holes import audit_triangles
from test_intersection import combined, operations
from test_revolution import revolved
from test_round_stock import cylinder, flange
from test_frustum import frustum
from test_polyhedral_transforms import moved, turned


def prefixed(m, prefix):
    m = copy.deepcopy(m)
    names = {k: prefix + "." + k for k in m["parameters"]}
    names.update({f["id"]: prefix + "." + f["id"] for f in m["features"]})

    def feature(v, key=""):
        if isinstance(v, dict):
            return {k: feature(x, k) for k, x in v.items()}
        if isinstance(v, list):
            return [feature(x, key) for x in v]
        if isinstance(v, str) and key not in ("kind", "axis"):
            return names.get(v, v)
        return v

    m["features"] = feature(m["features"])
    m["parameters"] = {names[k]: v for k, v in m["parameters"].items()}
    m["fixed"] = {names[k]: v for k, v in m["fixed"].items()}
    assert not m.get("relations"), "Fixture helper needs explicit relation renaming"
    return m


def intersect(a=None, b=None):
    a = a or cylinder(radius="10", height="12")
    b = b or moved(cylinder(radius="5", height="8"), (0, 0, 6))
    m = combined(prefixed(a, "left"), prefixed(b, "right"))
    m["features"][-1]["kind"] = "coaxial_intersection"
    return m


class Coaxial(unittest.TestCase):
    def verify(self, m, coefficient, genus=0):
        result = evaluate(m)
        self.assertEqual(len(result["bodies"]), 1)
        body = result["bodies"][0]
        id = body["feature_id"]
        self.assertEqual(body["volume_mm3"], str(coefficient) + "*pi")
        top = topology_model(m, id)
        self.assertEqual(top["shell_euler"], [2 - 2 * genus])
        self.assertEqual(top["naming"], "revision_only")
        mesh = tessellate(m, id, 64, True)
        volume = audit_triangles(
            [[tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]], genus
        )
        self.assertAlmostEqual(
            volume, float(coefficient) * 64 * math.sin(math.tau / 64) / 2, places=7
        )
        self.assertTrue(all(s in top["surfaces"] for s in mesh["triangle_surfaces"]))
        return measure_model(m, id)

    def test_cylinders_taper_and_ring_sections(self):
        self.assertEqual(self.verify(intersect(), 150)["centroid_mm"], ["0", "0", "9"])
        self.verify(
            intersect(frustum("10", "4", "12"), cylinder(radius="7", height="12")), 480
        )
        a = revolved([(3, 0), (10, 0), (10, 12), (3, 12)])
        b = revolved([(5, 2), (12, 2), (12, 10), (5, 10)], reverse=True)
        self.assertEqual(
            self.verify(intersect(a, b), 600, 1)["centroid_mm"], ["0", "0", "6"]
        )

    def test_antiparallel_axes_and_every_coordinate_orientation(self):
        a = cylinder(radius="10", height="12")
        b = moved(turned(cylinder(radius="5", height="8"), "x", 2), (0, 0, 14))
        self.verify(intersect(a, b), 150)
        for axis in "xyz":
            for turns in (1, 2, 3):
                # Prefix intermediate feature IDs before adding another transform.
                left = turned(prefixed(moved(a, (3, 4, 5)), "a"), axis, turns)
                right = turned(
                    prefixed(moved(prefixed(b, "source"), (3, 4, 5)), "b"), axis, turns
                )
                self.verify(intersect(left, right), 150)

    def test_contact_disjoint_misaligned_nonconvex_and_perforated_rejection(self):
        cases = [
            (
                intersect(b=moved(cylinder(radius="5", height="8"), (0, 0, 12))),
                "empty_solid",
            ),
            (
                intersect(b=moved(cylinder(radius="5", height="8"), (0, 0, 20))),
                "empty_solid",
            ),
            (
                intersect(
                    b=cylinder(
                        cx="1/1000000000000000000000000000000", radius="5", height="8"
                    )
                ),
                "unsupported_coaxial",
            ),
            (
                intersect(b=turned(cylinder(radius="5", height="8"), "x", 1)),
                "unsupported_coaxial",
            ),
            (intersect(b=revolved()), "unsupported_coaxial"),
            (intersect(b=flange()), "unsupported_coaxial"),
            (
                intersect(b=revolved([(10, 0), (12, 0), (12, 12), (10, 12)])),
                "empty_solid",
            ),
        ]
        for m, code in cases:
            with self.subTest(code=code), self.assertRaises(CadError) as caught:
                evaluate(m)
            self.assertEqual(caught.exception.detail["code"], code)
        m = intersect()
        m["features"][-1]["right"] = m["features"][-1]["left"]
        with self.assertRaises(CadError) as caught:
            evaluate(m)
        self.assertEqual(caught.exception.detail["code"], "invalid_operands")

    def test_repeated_intersection_placement_and_atomic_upstream_edit(self):
        initial = intersect()
        chained = intersect(initial, cylinder(radius="3", height="12"))
        self.verify(chained, 54)
        self.verify(turned(moved(initial, (2, 3, 4)), "y", 1), 150)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.json"
            store = Store(path)
            original = store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations(initial),
                    preserve=[],
                )
            )
            before = path.read_bytes()
            edit = dict(
                expected_revision=1,
                operations=[dict(op="set_parameter", id="right.radius", mm="6")],
                preserve=[],
            )
            self.assertEqual(
                store.execute(dict(action="preview", **edit))["bodies"][0][
                    "volume_mm3"
                ],
                "216*pi",
            )
            self.assertEqual(path.read_bytes(), before)
            store.execute(dict(action="commit", transaction_id="edit", **edit))
            saved = path.read_bytes()
            with self.assertRaises(CadError):
                store.execute(
                    dict(
                        action="commit",
                        expected_revision=2,
                        transaction_id="invalid",
                        operations=[
                            dict(op="set_parameter", id="right.move.z", mm="20")
                        ],
                        preserve=[],
                    )
                )
            self.assertEqual(path.read_bytes(), saved)
            self.assertEqual(
                Store(path).execute(
                    dict(action="undo", expected_revision=2, transaction_id="undo")
                )["bodies"],
                original["bodies"],
            )

    def test_exact_fractional_intersection_and_consumed_inputs(self):
        m = intersect(
            cylinder(radius="1/3", height="7/5"), cylinder(radius="2/7", height="11/13")
        )
        self.verify(m, F(44, 637))
        m = intersect()
        m["features"].append(
            dict(
                kind="coaxial_intersection",
                id="again",
                left="left.stock",
                right="right.moved",
            )
        )
        with self.assertRaises(CadError) as caught:
            evaluate(m)
        self.assertEqual(caught.exception.detail["code"], "unsupported_branch")

    def test_seeded_tapers_against_independent_piecewise_disk_integrals(self):
        rng = random.Random(6143)
        for _ in range(40):
            ra, rb, rc, rd = [
                F(rng.randrange(1, 20), rng.randrange(1, 5)) for _ in range(4)
            ]
            h, k = F(rng.randrange(5, 20)), F(rng.randrange(5, 20))
            shift = F(rng.randrange(-3, 4), 2)

            def shape(a, b, height):
                return (
                    cylinder(radius=str(a), height=str(height))
                    if a == b
                    else frustum(str(a), str(b), str(height))
                )

            left = shape(ra, rb, h)
            right = moved(shape(rc, rd, k), (0, 0, shift))
            lo, hi = max(F(0), shift), min(h, shift + k)
            ma, mb = (rb - ra) / h, (rd - rc) / k
            ca, cb = ra, rc - mb * shift
            cuts = [lo, hi]
            if ma != mb:
                z = (cb - ca) / (ma - mb)
                if lo < z < hi:
                    cuts.insert(1, z)
            coefficient = F(0)
            for lower, upper in zip(cuts, cuts[1:]):
                mid = (lower + upper) / 2
                slope, constant = (
                    (ma, ca) if ma * mid + ca < mb * mid + cb else (mb, cb)
                )
                r0, r1 = slope * lower + constant, slope * upper + constant
                coefficient += (upper - lower) * (r0 * r0 + r0 * r1 + r1 * r1) / 3
            for a, b in [(left, right), (right, left)]:
                model = intersect(a, b)
                self.assertEqual(
                    evaluate(model)["bodies"][0]["volume_mm3"], str(coefficient) + "*pi"
                )
