"""Flat-bottom blind holes retain exact depth, floor, topology and reversible edits."""

import copy
from fractions import Fraction as F
import math
from pathlib import Path
import tempfile
import unittest

from store import CadError, Store, evaluate
from exports import tessellate
from test_holes import perforated, audit_triangles
from test_round_stock import flange


def blind(model, depth="2"):
    m = copy.deepcopy(model)
    m["parameters"]["depth"] = depth
    m["features"][-1].update(kind="blind_holes", depth="depth")
    return m


class BlindHoles(unittest.TestCase):
    def test_exact_volume_and_closed_floor_mesh(self):
        for m, constant, coefficient in [
            (blind(perforated()), 36000, 36),
            (blind(perforated(True), "1/3"), 36000, 6),
            (blind(flange()), 0, -7764),
        ]:
            body = evaluate(m)["bodies"][0]
            shape = body["analytic"]
            self.assertEqual(shape["hole_depth"], m["parameters"]["depth"])
            self.assertEqual(
                shape["volume"],
                {"constant_mm3": str(constant), "pi_subtract_mm3": str(coefficient)},
            )
            for segments in [16, 64, 128]:
                mesh = tessellate(m, body["feature_id"], segments)
                triangles = [
                    [tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]
                ]
                volume = audit_triangles(triangles, 0)
                self.assertAlmostEqual(
                    volume,
                    constant
                    - coefficient * segments * math.sin(2 * math.pi / segments) / 2,
                    places=6,
                )
                floor = float(F(shape["height"]) - F(shape["hole_depth"]))
                self.assertTrue(any(all(p[2] == floor for p in t) for t in triangles))
                self.assertTrue(any(all(p[2] == 0 for p in t) for t in triangles))

    def test_computed_coefficients_are_not_restricted_as_input_literals(self):
        scale = F(1, 10**30 + 1)
        m = blind(flange())
        for key, value in list(m["parameters"].items()):
            m["parameters"][key] = str(F(value) * scale)
        result = evaluate(m)["bodies"][0]
        self.assertEqual(result["volume_mm3"], f"{7764 * scale**3}*pi")
        m["features"][-1]["kind"] = "through_holes"
        m["features"][-1].pop("depth")
        self.assertEqual(
            evaluate(m)["bodies"][0]["volume_mm3"], f"{7410 * scale**3}*pi"
        )

    def test_depth_range_and_remaining_floor_precision(self):
        for depth, code in [
            ("0", "dimension_range"),
            ("-1", "dimension_range"),
            ("6", "hole_depth"),
            ("7", "hole_depth"),
        ]:
            with self.assertRaises(CadError) as caught:
                evaluate(blind(perforated(), depth))
            self.assertEqual(caught.exception.detail["code"], code)
        m = blind(perforated(), str(F(6) - F(1, 10**30)))
        self.assertEqual(
            evaluate(m)["bodies"][0]["analytic"]["hole_depth"], m["parameters"]["depth"]
        )
        with self.assertRaises(CadError) as caught:
            tessellate(m, "part", 64)
        self.assertEqual(caught.exception.detail["code"], "tessellation_failed")

    def test_existing_containment_overlap_and_branch_rules(self):
        for key, value, code in [
            ("x", "3", "hole_clearance"),
            ("x2", "18", "hole_overlap"),
        ]:
            m = blind(perforated())
            m["parameters"][key] = value
            with self.assertRaises(CadError) as caught:
                evaluate(m)
            self.assertEqual(caught.exception.detail["code"], code)
        m = blind(perforated())
        other = copy.deepcopy(m["features"][-1])
        other.update(kind="through_holes", id="other")
        other.pop("depth")
        m["features"].append(other)
        with self.assertRaises(CadError) as caught:
            evaluate(m)
        self.assertEqual(caught.exception.detail["code"], "unsupported_branch")

    def test_depth_edit_preview_rollback_reopen_and_undo(self):
        m = blind(perforated())
        operations = [
            {"op": "define_parameter", "id": k, "mm": v}
            for k, v in m["parameters"].items()
        ] + [{"op": "add_feature", "feature": f} for f in m["features"]]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "part.json"
            store = Store(path)
            store.execute(
                {
                    "action": "commit",
                    "expected_revision": 0,
                    "transaction_id": "create",
                    "preserve": [],
                    "operations": operations,
                }
            )
            before = path.read_bytes()
            command = {
                "action": "preview",
                "expected_revision": 1,
                "preserve": [],
                "operations": [{"op": "set_parameter", "id": "depth", "mm": "4"}],
            }
            self.assertEqual(
                store.execute(command)["bodies"][0]["volume_mm3"], "36000 - (72)*pi"
            )
            self.assertEqual(path.read_bytes(), before)
            store.execute({**command, "action": "commit", "transaction_id": "deeper"})
            self.assertEqual(
                Store(path).execute({"action": "inspect"})["model"]["parameters"][
                    "depth"
                ],
                "4",
            )
            before = path.read_bytes()
            with self.assertRaises(CadError):
                store.execute(
                    {
                        **command,
                        "action": "commit",
                        "transaction_id": "invalid",
                        "expected_revision": 2,
                        "operations": [
                            {"op": "set_parameter", "id": "depth", "mm": "6"}
                        ],
                    }
                )
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(
                store.execute(
                    {"action": "undo", "expected_revision": 2, "transaction_id": "undo"}
                )["model"]["parameters"]["depth"],
                "2",
            )
            self.assertEqual(
                store.execute(
                    {"action": "redo", "expected_revision": 3, "transaction_id": "redo"}
                )["model"]["parameters"]["depth"],
                "4",
            )
