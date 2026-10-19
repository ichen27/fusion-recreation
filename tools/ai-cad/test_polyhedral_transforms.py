"""Rigid operations preserve exact nonconvex topology and later Boolean editing."""

import copy
from fractions import Fraction as F
from pathlib import Path
import tempfile
import unittest
from store import CadError, Store, evaluate
from exports import tessellate
from test_booleans import cases, boolean, box
from test_holes import audit_triangles
from test_intersection import operations


def moved(model, offset=(10, 0, 0)):
    m = copy.deepcopy(model)
    input = m["features"][-1]["id"]
    ids = ["move." + axis for axis in "xyz"]
    m["parameters"].update({k: str(v) for k, v in zip(ids, offset)})
    m["features"].append(dict(kind="translate", id="moved", input=input, offset=ids))
    return m


def turned(model, axis="x", turns=1, pivot=(0, 0, 0)):
    m = copy.deepcopy(model)
    input = m["features"][-1]["id"]
    ids = ["turn." + axis for axis in "xyz"]
    m["parameters"].update({k: str(v) for k, v in zip(ids, pivot)})
    m["features"].append(
        dict(
            kind="rotate_quarter",
            id="turned",
            input=input,
            axis=axis,
            turns=turns,
            pivot=ids,
        )
    )
    return m


def points(body):
    return {tuple(map(F, p)) for p in body["boundary"]["vertices"]}


def rotated(p, axis, turns, pivot):
    x, y, z = [a - b for a, b in zip(p, pivot)]
    for _ in range(turns):
        if axis == "x":
            x, y, z = x, -z, y
        elif axis == "y":
            x, y, z = z, y, -x
        else:
            x, y, z = -y, x, z
    return tuple(a + b for a, b in zip((x, y, z), pivot))


class PolyhedralTransforms(unittest.TestCase):
    def test_every_axis_turn_and_fractional_translation_preserves_boundary(self):
        delta = (F(7, 3), F(-2, 5), F(9, 7))
        pivot = (F(-1, 3), F(5, 4), F(2, 7))
        for name in ["through", "cavity", "split"]:
            m, volume, count = cases()[name]
            original = evaluate(m)["bodies"][0]
            translated = moved(m, delta)
            a = evaluate(translated)["bodies"][0]
            expected = {
                tuple(x + d for x, d in zip(p, delta)) for p in points(original)
            }
            self.assertEqual(points(a), expected)
            for axis in "xyz":
                for turns in (1, 2, 3):
                    model = turned(translated, axis, turns, pivot)
                    b = evaluate(model)["bodies"][0]
                    self.assertEqual(
                        points(b), {rotated(p, axis, turns, pivot) for p in expected}
                    )
                    self.assertEqual(F(b["volume_mm3"]), volume)
                    self.assertEqual(len(b["components"]), count)
                    self.assertEqual(
                        sorted(len(f["loops"]) for f in b["boundary"]["faces"]),
                        sorted(len(f["loops"]) for f in original["boundary"]["faces"]),
                    )
                    mesh = tessellate(model, "turned")
                    triangles = [
                        [tuple(mesh["vertices"][i]) for i in t]
                        for t in mesh["triangles"]
                    ]
                    actual = audit_triangles(
                        triangles,
                        holes=int(name == "through"),
                        shells=2 if name == "cavity" else count,
                    )
                    self.assertAlmostEqual(actual, volume, places=7)

    def test_transform_result_feeds_later_boolean_and_inverse_restores_shape(self):
        m, _, _ = cases()["through"]
        translated = moved(m)
        sliced = boolean(
            translated, box("c", [10, 0, 0], [15, 10, 10]), "intersection", "half"
        )
        self.assertEqual(evaluate(sliced)["bodies"][0]["volume_mm3"], "320")
        first = turned(translated, "y", 1)
        inverse = {
            **first["features"][-1],
            "id": "inverse",
            "input": "turned",
            "turns": 3,
        }
        first["features"].append(inverse)
        self.assertEqual(
            points(evaluate(first)["bodies"][0]),
            points(evaluate(translated)["bodies"][0]),
        )

    def test_upstream_edit_limits_undo_and_invalid_branch_are_atomic(self):
        m = turned(moved(cases()["split"][0]), "z", 1)
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "model.json")
            store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations(m),
                    preserve=[],
                )
            )
            initial = store.execute({"action": "inspect"})
            edit = dict(
                action="commit",
                expected_revision=1,
                transaction_id="shift",
                operations=[dict(op="set_parameter", id="move.x", mm="20")],
                preserve=[],
            )
            changed = store.execute(edit)
            self.assertEqual(changed["bodies"][0]["volume_mm3"], "800")
            self.assertNotEqual(
                points(changed["bodies"][0]), points(initial["bodies"][0])
            )
            before = store.path.read_bytes()
            edit.update(expected_revision=2, transaction_id="overflow")
            edit["operations"][0]["mm"] = "1000001"
            with self.assertRaises(CadError) as error:
                store.execute(edit)
            self.assertEqual(error.exception.detail["code"], "translation_range")
            self.assertEqual(store.path.read_bytes(), before)
            undo = store.execute(
                dict(action="undo", expected_revision=2, transaction_id="undo")
            )
            self.assertEqual(undo["bodies"], initial["bodies"])
            self.assertEqual(
                Store(store.path).execute({"action": "inspect"})["bodies"],
                initial["bodies"],
            )
        branched = copy.deepcopy(m)
        branched["features"].append({**m["features"][-2], "id": "again"})
        with self.assertRaises(CadError) as error:
            evaluate(branched)
        self.assertEqual(error.exception.detail["code"], "unsupported_branch")


if __name__ == "__main__":
    unittest.main()
