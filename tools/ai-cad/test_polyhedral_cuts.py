"""Nonconvex half-space cuts rebuild holes, cavity shells and material components."""

import copy
from fractions import Fraction as F
from pathlib import Path
import random
import tempfile
import unittest
from store import CadError, Store, evaluate
from exports import tessellate
from test_booleans import cases, boolean, box
from test_holes import audit_triangles
from test_intersection import operations
from test_polyhedral_transforms import moved, turned


def cut(model, normal=(0, 0, 1), offset=5, id="trimmed"):
    m = copy.deepcopy(model)
    input = m["features"][-1]["id"]
    parameter = id + ".offset"
    m["parameters"][parameter] = str(offset)
    m["features"].append(
        dict(
            kind="plane_cut",
            id=id,
            input=input,
            normal=list(map(str, normal)),
            offset=parameter,
        )
    )
    return m


class PolyhedralCuts(unittest.TestCase):
    def verify(self, model, volume, components=1, holes=0):
        body = evaluate(model)["bodies"][0]
        self.assertEqual(F(body["volume_mm3"]), volume)
        self.assertEqual(len(body["components"]), components)
        mesh = tessellate(model, body["feature_id"])
        triangles = [[tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]]
        self.assertAlmostEqual(
            audit_triangles(triangles, holes, shells=components),
            float(volume),
            places=7,
        )
        return body

    def test_open_cavity_through_hole_and_removed_component(self):
        for name, normal, offset, volume, components, holes in [
            ("cavity", (0, 0, 1), 5, 392, 1, 0),
            ("cavity", (1, 1, 1), 15, 392, 1, 0),
            ("through", (0, 0, 1), 5, 320, 1, 1),
            ("through", (1, 0, 0), 5, 320, 1, 0),
            ("split", (1, 0, 0), 5, 400, 1, 0),
            ("split", (0, 0, 1), 5, 400, 2, 0),
        ]:
            with self.subTest(name=name, normal=normal):
                self.verify(
                    cut(cases()[name][0], normal, offset), volume, components, holes
                )

    def test_removing_bridge_splits_one_material_component_into_two(self):
        u = boolean(
            box("a", [0, 0, 0], [10, 10, 10]),
            box("b", [3, 3, -1], [7, 11, 11]),
            "difference",
        )
        self.assertEqual(len(evaluate(u)["bodies"][0]["components"]), 1)
        self.verify(cut(u, (0, -1, 0), -5), 300, components=2)

    def test_seeded_oblique_planes_split_symmetric_cavity_exactly_in_half(self):
        rng = random.Random(109)
        model = cases()["cavity"][0]
        for _ in range(12):
            normal = [rng.randint(1, 7) for _ in range(3)]
            offset = 5 * sum(normal)
            self.verify(cut(model, normal, offset), 392)
            self.verify(cut(model, [-n for n in normal], -offset), 392)

    def test_cut_result_transforms_and_feeds_later_boolean(self):
        model = cut(cases()["through"][0], (0, 0, 1), 5)
        shifted = moved(model, (10, 0, 0))
        reoriented = turned(shifted, "z", 1, (10, 0, 0))
        self.verify(reoriented, 320, holes=1)
        filled = boolean(model, box("c", [2, 2, 0], [8, 8, 5]), "union", "filled")
        self.verify(filled, 500)
        self.verify(cut(model, (1, 0, 0), 5, "side"), 160)

    def test_noop_preserves_cavity_and_empty_zero_normal_edits_are_atomic(self):
        model = cases()["cavity"][0]
        before = evaluate(model)["bodies"][0]
        after = evaluate(cut(model, offset=10))["bodies"][0]
        self.assertEqual(after["boundary"], before["boundary"])
        self.assertEqual(after["components"], before["components"])
        model = cut(model)
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "part.json")
            store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations(model),
                    preserve=[],
                )
            )
            before = store.path.read_bytes()
            for value in ["0", "-1"]:
                with self.assertRaises(CadError) as e:
                    store.execute(
                        dict(
                            action="commit",
                            expected_revision=1,
                            transaction_id="empty" + value,
                            operations=[
                                dict(op="set_parameter", id="trimmed.offset", mm=value)
                            ],
                            preserve=[],
                        )
                    )
                self.assertEqual(e.exception.detail["code"], "empty_solid")
                self.assertEqual(store.path.read_bytes(), before)
            bad = {**model["features"][-1], "normal": ["0", "0", "0"]}
            with self.assertRaises(CadError) as e:
                store.execute(
                    dict(
                        action="commit",
                        expected_revision=1,
                        transaction_id="zero",
                        operations=[
                            dict(op="replace_feature", id="trimmed", feature=bad)
                        ],
                        preserve=[],
                    )
                )
            self.assertEqual(e.exception.detail["code"], "plane_normal")
            self.assertEqual(store.path.read_bytes(), before)
            changed = store.execute(
                dict(
                    action="commit",
                    expected_revision=1,
                    transaction_id="lower",
                    operations=[dict(op="set_parameter", id="trimmed.offset", mm="4")],
                    preserve=[],
                )
            )
            self.assertEqual(changed["bodies"][0]["volume_mm3"], "328")
            restored = store.execute(
                dict(action="undo", expected_revision=2, transaction_id="undo")
            )
            self.assertEqual(restored["bodies"][0]["volume_mm3"], "392")
            self.assertEqual(
                Store(store.path).execute({"action": "inspect"})["bodies"],
                restored["bodies"],
            )


if __name__ == "__main__":
    unittest.main()
