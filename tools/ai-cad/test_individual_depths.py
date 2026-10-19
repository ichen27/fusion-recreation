"""Named blind depths preserve exact per-hole floors, moments and transactions."""

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
from test_blind_holes import blind
from test_holes import perforated, audit_triangles
from test_round_stock import flange
from test_intersection import operations
from test_analytic_measurements import exact_value
from test_polyhedral_transforms import moved, turned


def individual(model=None, depth="4"):
    model = blind(perforated() if model is None else model)
    model["parameters"]["individual_depth"] = depth
    feature = model["features"][-1]
    feature["depth_overrides"] = {feature["holes"][-1]["id"]: "individual_depth"}
    return model


class IndividualDepths(unittest.TestCase):
    def test_exact_volume_mesh_floors_and_world_supports(self):
        for model in [
            individual(),
            individual(perforated(True), "1/3"),
            individual(flange()),
        ]:
            body = evaluate(model)["bodies"][0]
            shape = body["analytic"]
            depths = [F(c.get("depth", shape["hole_depth"])) for c in shape["holes"]]
            coefficient = sum(
                F(c["radius"]) ** 2 * d for c, d in zip(shape["holes"], depths)
            )
            if "outer_circle" in shape:
                coefficient -= F(shape["outer_circle"]["radius"]) ** 2 * F(
                    shape["height"]
                )
            self.assertEqual(F(shape["volume"]["pi_subtract_mm3"]), coefficient)
            self.assertNotIn("depth", shape["holes"][0])
            self.assertEqual(
                shape["holes"][-1]["depth"], model["parameters"]["individual_depth"]
            )
            for segments in (16, 64, 256):
                mesh = tessellate(model, body["feature_id"], segments, True)
                triangles = [
                    [tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]
                ]
                self.assertAlmostEqual(
                    audit_triangles(triangles, 0),
                    float(F(shape["volume"]["constant_mm3"]))
                    - float(coefficient) * segments * math.sin(math.tau / segments) / 2,
                    places=6,
                )
                for d in depths:
                    floor = float(F(shape["height"]) - d)
                    self.assertTrue(
                        any(
                            all(abs(p[2] - floor) < 1e-12 for p in t) for t in triangles
                        )
                    )
        for axis in "xyz":
            for turns in (1, 2, 3):
                model = turned(
                    moved(individual(), (F(1, 3), F(-2, 5), F(7, 11))), axis, turns
                )
                topology = topology_model(model, "turned")
                mesh = tessellate(model, "turned", 32, True)
                self.assertEqual(
                    set(mesh["triangle_surfaces"]), set(topology["surfaces"])
                )
                for triangle, name in zip(mesh["triangles"], mesh["triangle_surfaces"]):
                    support = topology["surfaces"][name]
                    if support["kind"] == "plane":
                        for index in triangle:
                            self.assertAlmostEqual(
                                sum(
                                    float(F(n)) * p
                                    for n, p in zip(
                                        support["normal"], mesh["vertices"][index]
                                    )
                                ),
                                float(F(support["offset"])),
                                places=9,
                            )

    def test_maximum_group_with_distinct_depths(self):
        model = individual()
        model["parameters"]["c2"] = "100"
        feature = model["features"][-1]
        feature["holes"] = []
        feature["depth_overrides"] = {}
        for i in range(4):
            model["parameters"][f"grid{i}"] = str(20 + 20 * i)
        for i in range(16):
            id = f"h{i}"
            model["parameters"][f"d{i}"] = str(F(i + 1, 4))
            feature["holes"].append(
                dict(id=id, x=f"grid{i % 4}", y=f"grid{i // 4}", radius="r")
            )
            feature["depth_overrides"][id] = f"d{i}"
        self.assertEqual(evaluate(model)["bodies"][0]["volume_mm3"], "60000 - (306)*pi")
        mesh = tessellate(model, "part", 256, True)
        triangles = [[tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]]
        self.assertAlmostEqual(
            audit_triangles(triangles, 0),
            60000 - 306 * 256 * math.sin(math.tau / 256) / 2,
            places=5,
        )
        self.assertEqual(
            set(mesh["triangle_surfaces"]),
            set(topology_model(model, "part")["surfaces"]),
        )

    def test_exact_centroid_and_dependency_rebuild(self):
        model = individual()
        values = measure_model(model, "part")
        for pi in [F(1), F(2), F(3), F(22, 7)]:
            volume = 36000 - 54 * pi
            self.assertEqual(
                [exact_value(c, pi) for c in values["centroid_mm"]],
                [
                    (1800000 - 3384 * pi) / volume,
                    (1080000 - 648 * pi) / volume,
                    (108000 - 234 * pi) / volume,
                ],
            )
        model["relations"] = {
            "individual_depth": dict(offset_mm="0", terms={"depth": "2"})
        }
        changed = evaluate(model, [dict(op="set_parameter", id="depth", mm="1")])
        self.assertEqual(changed["model"]["parameters"]["individual_depth"], "2")
        self.assertEqual(changed["bodies"][0]["volume_mm3"], "36000 - (27)*pi")
        with self.assertRaises(CadError):
            evaluate(model, [dict(op="remove_parameter", id="individual_depth")])
        model["fixed"]["individual_depth"] = "4"
        with self.assertRaises(CadError):
            evaluate(model, [dict(op="set_parameter", id="depth", mm="1")])

    def test_invalid_override_and_exact_tiny_remaining_floor(self):
        for value, code in [
            ("0", "dimension_range"),
            ("-1", "dimension_range"),
            ("6", "hole_depth"),
            ("7", "hole_depth"),
        ]:
            with self.assertRaises(CadError) as caught:
                evaluate(individual(depth=value))
            self.assertEqual(caught.exception.detail["code"], code)
        model = individual()
        model["features"][-1]["depth_overrides"]["missing"] = "depth"
        with self.assertRaises(CadError) as caught:
            evaluate(model)
        self.assertEqual(caught.exception.detail["code"], "unknown_hole_depth")
        model = individual(depth=str(F(6) - F(1, 10**30)))
        evaluate(model)
        topology_model(model, "part")
        with self.assertRaises(CadError):
            tessellate(model, "part")
        model = blind(perforated())
        result = evaluate(model)
        model["features"][-1]["depth_overrides"] = {}
        self.assertEqual(evaluate(model), result)

    def test_native_mapping_edits_rejection_reopen_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.json"
            store = Store(path)
            first = store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations(individual()),
                    preserve=[],
                )
            )
            before = path.read_bytes()
            feature = copy.deepcopy(first["model"]["features"][-1])
            feature["depth_overrides"] = {"left": "individual_depth"}
            edit = dict(
                expected_revision=1,
                operations=[dict(op="replace_feature", id="part", feature=feature)],
                preserve=[],
            )
            preview = store.execute(dict(action="preview", **edit))
            self.assertEqual(preview["bodies"][0]["volume_mm3"], "36000 - (54)*pi")
            self.assertEqual(preview["bodies"][0]["analytic"]["holes"][0]["depth"], "4")
            self.assertEqual(path.read_bytes(), before)
            store.execute(dict(action="commit", transaction_id="swap", **edit))
            saved = path.read_bytes()
            feature["holes"].pop(0)
            with self.assertRaises(CadError):
                store.execute(
                    dict(
                        action="commit",
                        expected_revision=2,
                        transaction_id="bad",
                        operations=[
                            dict(op="replace_feature", id="part", feature=feature)
                        ],
                        preserve=[],
                    )
                )
            self.assertEqual(path.read_bytes(), saved)
            restored = Store(path).execute(
                dict(action="undo", expected_revision=2, transaction_id="undo")
            )
            self.assertEqual(restored["bodies"], first["bodies"])
            redone = Store(path).execute(
                dict(action="redo", expected_revision=3, transaction_id="redo")
            )
            self.assertEqual(redone["bodies"], preview["bodies"])


if __name__ == "__main__":
    unittest.main()
