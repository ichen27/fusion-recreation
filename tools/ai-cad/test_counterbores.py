"""Exact stepped holes, shoulder topology, derived edits and placed moments."""

import copy
from fractions import Fraction as F
import math
from pathlib import Path
import tempfile
import unittest
from store import CadError, Store, evaluate
from exports import tessellate
from measurements import measure_model
from test_holes import perforated, audit_triangles
from test_round_stock import flange
from test_instances import instance
from test_polyhedral_transforms import turned
from test_analytic_measurements import exact_value
from intent import explain_model


def counterbored(model=None, radius="5", depth="2"):
    model = copy.deepcopy(model or perforated())
    model["parameters"].update(recess_radius=radius, recess_depth=depth)
    model["features"][-1].update(
        kind="counterbore_holes", bore_radius="recess_radius", depth="recess_depth"
    )
    return model


def round_counterbored():
    model = flange()
    model["features"][-1]["holes"].pop()
    return counterbored(model)


class Counterbores(unittest.TestCase):
    def test_exact_volume_mesh_shoulders_and_both_profile_windings(self):
        for model, constant, coefficient in [
            (counterbored(), 36000, 172),
            (counterbored(perforated(True)), 36000, 172),
            (round_counterbored(), 0, -7846),
            (counterbored(depth="1/3"), 36000, F(356, 3)),
        ]:
            body = evaluate(model)["bodies"][0]
            shape = body["analytic"]
            self.assertEqual(
                shape["counterbore"],
                dict(radius="5", depth=model["parameters"]["recess_depth"]),
            )
            self.assertEqual(
                shape["volume"],
                dict(constant_mm3=str(constant), pi_subtract_mm3=str(coefficient)),
            )
            self.assertNotIn("hole_depth", shape)
            for segments in (16, 64, 128):
                mesh = tessellate(model, body["feature_id"], segments)
                triangles = [
                    [tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]
                ]
                volume = audit_triangles(triangles, len(shape["holes"]))
                self.assertAlmostEqual(
                    volume,
                    constant
                    - float(coefficient)
                    * segments
                    * math.sin(2 * math.pi / segments)
                    / 2,
                    places=6,
                )
                floor = float(F(shape["height"]) - F(shape["counterbore"]["depth"]))
                shoulders = [
                    t for t in triangles if all(abs(p[2] - floor) < 1e-12 for p in t)
                ]
                self.assertEqual(len(shoulders), len(shape["holes"]) * segments * 2)
                for t in shoulders:
                    # No shoulder triangle closes the lower through aperture.
                    center = [sum(p[i] for p in t) / 3 for i in (0, 1)]
                    self.assertTrue(
                        any(
                            float(F(h["radius"])) * math.cos(math.pi / segments)
                            < math.hypot(
                                center[0] - float(F(h["center"][0])),
                                center[1] - float(F(h["center"][1])),
                            )
                            < 5
                            for h in shape["holes"]
                        )
                    )

    def test_limits_exact_narrow_shoulders_and_parameter_dependencies(self):
        for key, value, code in [
            ("recess_radius", "3", "counterbore_radius"),
            ("recess_radius", "12", "hole_clearance"),
            ("recess_depth", "6", "hole_depth"),
            ("recess_depth", "0", "dimension_range"),
            ("x2", "22", "hole_overlap"),
        ]:
            model = counterbored()
            model["parameters"][key] = value
            with self.assertRaises(CadError) as caught:
                evaluate(model)
            self.assertEqual(caught.exception.detail["code"], code)
        model = counterbored(radius=str(F(3) + F(1, 10**30)))
        evaluate(model)
        with self.assertRaises(CadError):
            tessellate(model, "part", 64)
        model = counterbored()
        info = explain_model(model, "part")
        self.assertIn("recess_radius", info["parameters"])
        self.assertIn("recess_depth", info["parameters"])
        model["relations"] = {"recess_radius": {"offset_mm": "2", "terms": {"r": "1"}}}
        changed = evaluate(model, [dict(op="set_parameter", id="r", mm="4")])
        self.assertEqual(changed["model"]["parameters"]["recess_radius"], "6")
        self.assertEqual(changed["bodies"][0]["analytic"]["counterbore"]["radius"], "6")

    def test_maximum_hole_group_and_display_resolution(self):
        model = counterbored()
        model["parameters"]["c2"] = "100"
        for i, coordinate in enumerate((20, 40, 60, 80)):
            model["parameters"][f"grid{i}"] = str(coordinate)
        holes = [
            dict(id=f"h{i}_{j}", x=f"grid{i}", y=f"grid{j}", radius="r")
            for i in range(4)
            for j in range(4)
        ]
        model["features"][-1]["holes"] = holes
        self.assertEqual(
            evaluate(model)["bodies"][0]["volume_mm3"], "60000 - (1376)*pi"
        )
        mesh = tessellate(model, "part", 256)
        triangles = [[tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]]
        volume = audit_triangles(triangles, 16)
        self.assertAlmostEqual(
            volume, 60000 - 1376 * 256 * math.sin(2 * math.pi / 256) / 2, places=5
        )
        self.assertEqual(len(mesh["vertices"]), 4 * 16 * 256 + 8)
        model["features"][-1]["holes"].append(
            dict(id="overflow", x="x", y="y", radius="r")
        )
        with self.assertRaises(CadError) as caught:
            evaluate(model)
        self.assertEqual(caught.exception.detail["code"], "hole_limit")

    def test_exact_moments_placements_and_reversible_native_edits(self):
        model = counterbored()
        measurement = measure_model(model, "part")
        # Subtract full through cylinders and only the extra upper annuli.
        volume = 36000 - 172 * math.pi
        self.assertAlmostEqual(
            exact_value(measurement["centroid_mm"][2]),
            (108000 - 644 * math.pi) / volume,
            places=12,
        )
        placed = turned(instance(model, offset=(F(1, 3), -2, 5)), "x", 1)
        bodies = evaluate(placed)["bodies"]
        self.assertEqual(len(bodies), 2)
        mesh = tessellate(placed, "turned", 64)
        audit_triangles(
            [[tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]], 2
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.cad.json"
            store = Store(path)
            operations = [
                dict(op="define_parameter", id=k, mm=v)
                for k, v in model["parameters"].items()
            ] + [dict(op="add_feature", feature=f) for f in model["features"]]
            store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations,
                    preserve=[],
                )
            )
            before = path.read_bytes()
            command = dict(
                expected_revision=1,
                preserve=[],
                operations=[dict(op="set_parameter", id="recess_depth", mm="3")],
            )
            preview = store.execute(dict(action="preview", **command))
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(preview["bodies"][0]["volume_mm3"], "36000 - (204)*pi")
            store.execute(dict(action="commit", transaction_id="deeper", **command))
            reopened = Store(path)
            self.assertEqual(
                reopened.execute(dict(action="inspect"))["model"]["parameters"][
                    "recess_depth"
                ],
                "3",
            )
            restored = reopened.execute(
                dict(action="undo", expected_revision=2, transaction_id="undo")
            )
            self.assertEqual(restored["bodies"][0]["volume_mm3"], "36000 - (172)*pi")


if __name__ == "__main__":
    unittest.main()
