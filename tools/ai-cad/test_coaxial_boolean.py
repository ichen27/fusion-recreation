"""Bounded coaxial material unions/cuts with exact radial-cell boundaries."""

import copy
import math
from pathlib import Path
import tempfile
import unittest
from store import CadError, Store, evaluate
from exports import tessellate
from topology import topology_model
from measurements import measure_model
from test_holes import audit_triangles
from test_coaxial import intersect
from test_intersection import operations
from test_round_stock import cylinder
from test_revolution import revolved
from test_polyhedral_transforms import moved, turned


def boolean(a=None, b=None, operation="difference"):
    m = intersect(a, b)
    m["features"][-1].update(kind="coaxial_boolean", operation=operation)
    return m


class CoaxialBoolean(unittest.TestCase):
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

    def test_union_difference_intersection_face_join_and_full_bore(self):
        for operation, volume in [
            ("union", 1250),
            ("difference", 1050),
            ("intersection", 150),
        ]:
            self.verify(boolean(operation=operation), volume)
        self.verify(
            boolean(
                b=moved(cylinder(radius="5", height="8"), (0, 0, 12)), operation="union"
            ),
            1400,
        )
        self.verify(boolean(b=cylinder(radius="5", height="12")), 900, 1)
        self.verify(
            boolean(
                b=revolved([(10, 0), (12, 0), (12, 12), (10, 12)]), operation="union"
            ),
            1728,
        )

    def test_concave_radial_input_and_repeated_placed_results(self):
        for operation, volume, genus in [
            ("intersection", 572, 0),
            ("union", 948, 0),
            ("difference", 180, 1),
        ]:
            self.verify(
                boolean(revolved(), cylinder(radius="8", height="12"), operation),
                volume,
                genus,
            )
        original = boolean(operation="union")
        self.verify(boolean(original, cylinder(radius="3", height="20")), 1124, 1)
        for axis in "xyz":
            self.verify(turned(moved(boolean(), (2, 3, 4)), axis, 1), 1050)

    def test_disconnected_contour_holes_axis_cavities_empty_and_misaligned_reject(self):
        cases = [
            (
                boolean(
                    b=moved(cylinder(radius="5", height="8"), (0, 0, 20)),
                    operation="union",
                ),
                "unsupported_coaxial_result",
            ),
            (
                boolean(b=revolved([(3, 3), (5, 3), (5, 9), (3, 9)])),
                "unsupported_coaxial_result",
            ),
            (
                boolean(b=moved(cylinder(radius="5", height="6"), (0, 0, 3))),
                "unsupported_coaxial_result",
            ),
            (boolean(b=cylinder(radius="20", height="20")), "empty_solid"),
            (
                boolean(b=cylinder(cx="1", radius="5", height="8")),
                "unsupported_coaxial",
            ),
        ]
        for m, code in cases:
            with self.subTest(code=code), self.assertRaises(CadError) as caught:
                evaluate(m)
            self.assertEqual(caught.exception.detail["code"], code)

    def test_feature_operation_replace_source_edit_and_atomic_history(self):
        m = boolean()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.json"
            store = Store(path)
            original = store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations(m),
                    preserve=[],
                )
            )
            before = path.read_bytes()
            feature = copy.deepcopy(m["features"][-1])
            feature["operation"] = "union"
            edit = dict(
                expected_revision=1,
                operations=[dict(op="replace_feature", id="common", feature=feature)],
                preserve=[],
            )
            self.assertEqual(
                store.execute(dict(action="preview", **edit))["bodies"][0][
                    "volume_mm3"
                ],
                "1250*pi",
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
                            dict(op="set_parameter", id="right.move.x", mm="1")
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
        changed = evaluate(m, [dict(op="set_parameter", id="right.radius", mm="6")])
        self.assertEqual(changed["bodies"][0]["volume_mm3"], "984*pi")
