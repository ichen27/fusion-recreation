"""Exact conical recesses join cylindrical apertures and retain editable context."""

import copy
from fractions import Fraction as F
import math
from pathlib import Path
import tempfile
import unittest
from store import CadError, Store, evaluate
from exports import tessellate
from topology import topology_model
from measurements import measure_model
from test_counterbores import counterbored, round_counterbored
from test_holes import audit_triangles, perforated
from test_intersection import operations
from test_polyhedral_transforms import moved, turned
from test_instances import instance
from test_analytic_measurements import exact_value


def countersunk(model=None, radius="5", depth="2"):
    model = counterbored(model, radius, depth)
    feature = model["features"][-1]
    feature["kind"] = "countersink_holes"
    feature["rim_radius"] = feature.pop("bore_radius")
    return model


class Countersinks(unittest.TestCase):
    def test_exact_volume_closed_conical_mesh_and_world_supports(self):
        for model in [
            countersunk(),
            countersunk(perforated(True)),
            countersunk(round_counterbored()),
            countersunk(depth="1/3"),
        ]:
            body = evaluate(model)["bodies"][0]
            shape = body["analytic"]
            self.assertNotIn("counterbore", shape)
            d = F(shape["countersink"]["depth"])
            R = F(shape["countersink"]["radius"])
            h = F(shape["height"])
            coefficient = sum(
                F(hole["radius"]) ** 2 * (h - d)
                + d * (F(hole["radius"]) ** 2 + F(hole["radius"]) * R + R * R) / 3
                for hole in shape["holes"]
            )
            if "outer_circle" in shape:
                coefficient -= F(shape["outer_circle"]["radius"]) ** 2 * h
            constant = F(shape["volume"]["constant_mm3"])
            self.assertEqual(F(shape["volume"]["pi_subtract_mm3"]), coefficient)
            for segments in (16, 64, 256):
                mesh = tessellate(model, body["feature_id"], segments, True)
                triangles = [
                    [tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]
                ]
                self.assertAlmostEqual(
                    audit_triangles(triangles, len(shape["holes"])),
                    float(constant)
                    - float(coefficient) * segments * math.sin(math.tau / segments) / 2,
                    places=6,
                )
                topology = topology_model(model, body["feature_id"])
                self.assertEqual(
                    set(mesh["triangle_surfaces"]), set(topology["surfaces"])
                )
                tapers = [
                    s
                    for s in topology["surfaces"].values()
                    if s["kind"] == "conical_frustum"
                ]
                self.assertEqual(len(tapers), len(shape["holes"]))
                self.assertTrue(all(s["inward"] for s in tapers))
                self.assertFalse(
                    any("shoulder" in s for s in mesh["triangle_surfaces"])
                )
        # All proper coordinate frames preserve inward conical support and references.
        for axis in "xyz":
            for turns in (1, 2, 3):
                model = turned(
                    moved(countersunk(), (F(1, 3), F(-2, 5), F(7, 11))), axis, turns
                )
                topology = topology_model(model, "turned")
                mesh = tessellate(model, "turned", 32, True)
                for triangle, name in zip(mesh["triangles"], mesh["triangle_surfaces"]):
                    s = topology["surfaces"][name]
                    if s["kind"] != "conical_frustum":
                        continue
                    for index in triangle:
                        v = [
                            p - float(F(o))
                            for p, o in zip(mesh["vertices"][index], s["origin"])
                        ]
                        z = sum(a * b for a, b in zip(v, s["axis"]))
                        radius = math.hypot(*[a - z * b for a, b in zip(v, s["axis"])])
                        expected = float(F(s["bottom_radius"])) + float(
                            F(s["top_radius"]) - F(s["bottom_radius"])
                        ) * z / float(F(s["height"]))
                        self.assertAlmostEqual(radius, expected, places=9)

    def test_maximum_group_retains_closed_tapers(self):
        model = countersunk()
        model["parameters"]["c2"] = "100"
        for i, x in enumerate((20, 40, 60, 80)):
            model["parameters"][f"grid{i}"] = str(x)
        model["features"][-1]["holes"] = [
            dict(id=f"h{i}_{j}", x=f"grid{i}", y=f"grid{j}", radius="r")
            for i in range(4)
            for j in range(4)
        ]
        self.assertEqual(
            evaluate(model)["bodies"][0]["volume_mm3"], "60000 - (3296/3)*pi"
        )
        mesh = tessellate(model, "part", 256, True)
        triangles = [[tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]]
        self.assertAlmostEqual(
            audit_triangles(triangles, 16),
            60000 - float(F(3296, 3)) * 256 * math.sin(math.tau / 256) / 2,
            places=5,
        )
        self.assertEqual(len(mesh["vertices"]), 3 * 16 * 256 + 8)
        self.assertEqual(
            len(
                [
                    k
                    for k in topology_model(model, "part")["surfaces"]
                    if k.endswith("/taper")
                ]
            ),
            16,
        )

    def test_exact_first_moments_and_shared_driver_rebuild(self):
        model = countersunk()
        values = measure_model(model, "part")
        for pi in [F(1), F(2), F(3), F(22, 7)]:
            volume = 36000 - F(412, 3) * pi
            self.assertEqual(
                [exact_value(c, pi) for c in values["centroid_mm"]],
                [
                    F(50),
                    (1080000 - 1648 * pi) / volume,
                    (108000 - F(1444, 3) * pi) / volume,
                ],
            )
        model["relations"] = {"recess_radius": dict(offset_mm="2", terms={"r": "1"})}
        changed = evaluate(model, [dict(op="set_parameter", id="r", mm="4")])
        self.assertEqual(changed["model"]["parameters"]["recess_radius"], "6")
        linked = instance(model, offset=(100, 0, 0))
        self.assertEqual(len(evaluate(linked)["bodies"]), 2)
        self.assertEqual(
            measure_model(linked, "copy")["centroidal_volume_inertia_mm5"],
            measure_model(model, "part")["centroidal_volume_inertia_mm5"],
        )

    def test_invalid_recesses_and_subdisplay_precision_are_explicit(self):
        for key, value, code in [
            ("recess_radius", "3", "countersink_radius"),
            ("recess_radius", "12", "hole_clearance"),
            ("recess_depth", "6", "hole_depth"),
            ("recess_depth", "0", "dimension_range"),
            ("x2", "22", "hole_overlap"),
        ]:
            model = countersunk()
            model["parameters"][key] = value
            with self.assertRaises(CadError) as caught:
                evaluate(model)
            self.assertEqual(caught.exception.detail["code"], code)
        tiny = countersunk(radius=str(F(3) + F(1, 10**30)))
        evaluate(tiny)
        topology_model(tiny, "part")
        measure_model(tiny, "part")
        with self.assertRaises(CadError):
            tessellate(tiny, "part")

    def test_native_preview_save_rejection_undo_and_shape_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.json"
            store = Store(path)
            created = store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations(countersunk()),
                    preserve=[],
                )
            )
            before = path.read_bytes()
            proposal = dict(
                expected_revision=1,
                operations=[dict(op="set_parameter", id="recess_depth", mm="3")],
                preserve=[],
            )
            self.assertEqual(
                store.execute(dict(action="preview", **proposal))["bodies"][0][
                    "volume_mm3"
                ],
                "36000 - (152)*pi",
            )
            self.assertEqual(path.read_bytes(), before)
            store.execute(dict(action="commit", transaction_id="deeper", **proposal))
            self.assertEqual(
                Store(path).execute(dict(action="inspect"))["bodies"][0]["analytic"][
                    "countersink"
                ]["depth"],
                "3",
            )
            saved = path.read_bytes()
            bad = copy.deepcopy(proposal)
            bad.update(expected_revision=2)
            bad["operations"][0]["mm"] = "7"
            with self.assertRaises(CadError):
                store.execute(dict(action="commit", transaction_id="bad", **bad))
            self.assertEqual(path.read_bytes(), saved)
            undo = store.execute(
                dict(action="undo", expected_revision=2, transaction_id="undo")
            )
            self.assertEqual(undo["bodies"], created["bodies"])


if __name__ == "__main__":
    unittest.main()
