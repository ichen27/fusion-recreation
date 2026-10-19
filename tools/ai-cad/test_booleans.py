"""Original planar Booleans: independent volumes, topology, history and meshes."""

import copy
from fractions import Fraction as F
from pathlib import Path
import random
import tempfile
import unittest
from store import CadError, Store, evaluate
from exports import tessellate
from test_holes import audit_triangles
from test_intersection import rectangle, combined, operations, prism


def box(name, lo, hi):
    m = rectangle(name, lo[0], lo[1], hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])
    if lo[2]:
        m["parameters"].update({name + ".zero": "0", name + ".z": str(lo[2])})
        m["features"].append(
            {
                "kind": "translate",
                "id": name + ".placed",
                "input": name,
                "offset": [name + ".zero", name + ".zero", name + ".z"],
            }
        )
    return m


def boolean(a, b, operation, id="result"):
    m = combined(a, b)
    m["features"][-1].update(kind="boolean", id=id, operation=operation)
    return m


def cases():
    outer = box("a", [0, 0, 0], [10, 10, 10])
    return {
        "overlap": (
            boolean(outer, box("b", [5, 5, 5], [15, 15, 15]), "union"),
            1875,
            1,
        ),
        "cavity": (
            boolean(outer, box("b", [2, 2, 2], [8, 8, 8]), "difference"),
            784,
            1,
        ),
        "through": (
            boolean(outer, box("b", [2, 2, -1], [8, 8, 11]), "difference"),
            640,
            1,
        ),
        "split": (
            boolean(outer, box("b", [4, -1, -1], [6, 11, 11]), "difference"),
            800,
            2,
        ),
        "separate": (
            boolean(outer, box("b", [20, 0, 0], [30, 10, 10]), "union"),
            2000,
            2,
        ),
        "l_shape": (
            boolean(
                box("a", [0, 0, 0], [2, 1, 1]), box("b", [0, 1, 0], [1, 2, 1]), "union"
            ),
            3,
            1,
        ),
    }


class Booleans(unittest.TestCase):
    def verify(self, m, volume, components=None, holes=0, shells=1):
        body = evaluate(m)["bodies"][0]
        self.assertEqual(F(body["volume_mm3"]), volume)
        if components is not None:
            self.assertEqual(len(body["components"]), components)
        self.assertEqual(
            sorted(i for group in body["components"] for i in group),
            list(range(len(body["boundary"]["faces"]))),
        )
        mesh = tessellate(m, body["feature_id"])
        actual = audit_triangles(
            [[tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]],
            holes,
            shells,
        )
        self.assertAlmostEqual(actual, float(volume), places=7)
        return body

    def test_cavity_holes_components_and_concave_faces_render(self):
        for name, (model, volume, count) in cases().items():
            with self.subTest(name=name):
                body = self.verify(
                    model,
                    volume,
                    count,
                    holes=int(name == "through"),
                    shells=2 if name == "cavity" else count,
                )
                if name == "through":
                    self.assertEqual(
                        sum(len(f["loops"]) == 2 for f in body["boundary"]["faces"]), 2
                    )

    def test_seeded_fractional_boxes_match_independent_overlap_formula(self):
        rng = random.Random(73)
        for _ in range(12):
            lo = [F(rng.randint(1, 8), 3) for _ in range(3)]
            hi = [x + F(rng.randint(5, 15), 3) for x in lo]
            overlap = F(1)
            v = F(1)
            for a, b in zip(lo, hi):
                overlap *= min(4, b) - a
                v *= b - a
            a, b = box("a", [0, 0, 0], [4, 4, 4]), box("b", lo, hi)
            for op, expected in [
                ("union", 64 + v - overlap),
                ("difference", 64 - overlap),
                ("intersection", overlap),
            ]:
                self.verify(boolean(a, b, op), expected)

    def test_repeated_nonconvex_operations_and_plane_consumers(self):
        hole, _, _ = cases()["through"]
        refill = boolean(hole, box("c", [2, 2, 0], [8, 8, 10]), "union", "filled")
        body = self.verify(refill, 1000, 1)
        self.assertEqual(len(body["boundary"]["faces"]), 6)
        refill["features"].append(
            {
                "kind": "plane_cut",
                "id": "top",
                "input": "filled",
                "normal": ["0", "0", "1"],
                "offset": "a.height",
            }
        )
        self.assertEqual(evaluate(refill)["bodies"][0]["volume_mm3"], "1000")
        hole["features"].append(
            {
                "kind": "plane_cut",
                "id": "top",
                "input": "result",
                "normal": ["0", "0", "1"],
                "offset": "a.height",
            }
        )
        unchanged = evaluate(hole)["bodies"][0]
        self.assertEqual(unchanged["volume_mm3"], "640")
        self.assertEqual(
            sum(len(f["loops"]) == 2 for f in unchanged["boundary"]["faces"]), 2
        )

    def test_atomic_operation_edit_empty_rejection_and_undo(self):
        m, _, _ = cases()["overlap"]
        with tempfile.TemporaryDirectory() as directory:
            s = Store(Path(directory) / "model.json")
            s.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations(m),
                    preserve=[],
                )
            )
            feature = {**m["features"][-1], "operation": "difference"}
            command = dict(
                action="commit",
                expected_revision=1,
                transaction_id="cut",
                operations=[dict(op="replace_feature", id="result", feature=feature)],
                preserve=list(m["parameters"]),
            )
            self.assertEqual(s.execute(command)["bodies"][0]["volume_mm3"], "875")
            before = s.path.read_bytes()
            command.update(expected_revision=2, transaction_id="invalid")
            command["operations"][0]["feature"]["right"] = "a"
            with self.assertRaises(CadError):
                s.execute(command)
            self.assertEqual(s.path.read_bytes(), before)
            restored = s.execute(
                dict(action="undo", expected_revision=2, transaction_id="undo")
            )
            self.assertEqual(restored["bodies"][0]["volume_mm3"], "1875")
            self.assertEqual(
                Store(s.path).execute({"action": "inspect"})["bodies"],
                restored["bodies"],
            )

    def test_contacts_empty_unsupported_and_consumed_references_reject(self):
        a = box("a", [0, 0, 0], [1, 1, 1])
        for lo, hi, op, code in [
            ([1, 1, 0], [2, 2, 1], "union", "invalid_polyhedron"),
            ([1, 1, 1], [2, 2, 2], "union", "invalid_polyhedron"),
            ([1, 0, 0], [2, 1, 1], "intersection", "empty_solid"),
            ([0, 0, 0], [1, 1, 1], "difference", "empty_solid"),
        ]:
            with self.assertRaises(CadError) as e:
                evaluate(boolean(a, box("b", lo, hi), op))
            self.assertEqual(e.exception.detail["code"], code)
            self.assertEqual(e.exception.detail["entity"], "result")
        bad = boolean(a, prism("b", [(0, 0), (2, 0), (1, 1), (0, 2)], 1), "union")
        with self.assertRaises(CadError):
            evaluate(bad)
        bad = copy.deepcopy(cases()["overlap"][0])
        bad["features"].append({**bad["features"][-1], "id": "again"})
        with self.assertRaises(CadError) as e:
            evaluate(bad)
        self.assertEqual(e.exception.detail["code"], "unsupported_branch")


if __name__ == "__main__":
    unittest.main()
