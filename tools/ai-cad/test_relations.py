"""Exact design relationships through the same process/document interface as clients."""

import copy
from fractions import Fraction as F
import json
from pathlib import Path
import random
import tempfile
import unittest

from store import CadError, ROOT, Store, evaluate


def model(values):
    return {
        "parameters": {k: str(v) for k, v in values.items()},
        "features": [],
        "fixed": {},
    }


def relation(id, terms, offset="0"):
    return {
        "op": "set_relation",
        "id": id,
        "relation": {
            "offset_mm": str(offset),
            "terms": {k: str(v) for k, v in terms.items()},
        },
    }


def set_value(id, value):
    return {"op": "set_parameter", "id": id, "mm": str(value)}


class RelationshipTests(unittest.TestCase):
    def assert_error(self, m, ops, code, preserve=None):
        with self.assertRaises(CadError) as caught:
            evaluate(m, ops, preserve)
        self.assertEqual(caught.exception.detail["code"], code)
        return caught.exception.detail

    def centered(self):
        return evaluate(
            model({"width": 100, "center": 50}), [relation("center", {"width": "1/2"})]
        )["model"]

    def test_chain_diamond_and_changed_parameters(self):
        m = model({"width": 100, "left": 10, "center": 0, "right": 0, "span": 0})
        result = evaluate(
            m,
            [
                relation("span", {"right": 1, "left": -1}),
                relation("right", {"width": 1, "left": -1}),
                relation("center", {"width": "1/2"}),
            ],
        )
        self.assertEqual(
            result["model"]["parameters"],
            {"width": "100", "left": "10", "center": "50", "right": "90", "span": "80"},
        )
        edited = evaluate(result["model"], [set_value("width", 120)], ["left"])
        self.assertEqual(
            edited["changed_parameters"], ["center", "right", "span", "width"]
        )
        self.assertEqual(edited["model"]["parameters"]["span"], "100")
        self.assertEqual(edited["model"]["relations"], result["model"]["relations"])

    def test_seeded_exact_affine_relations(self):
        rng = random.Random(20261020)
        for i in range(40):
            a, b, ca, cb, offset = [
                F(rng.randint(-100, 100), rng.randint(1, 19)) for _ in range(5)
            ]
            terms = {name: c for name, c in [("a", ca), ("b", cb)] if c}
            result = evaluate(
                model({"a": a, "b": b, "out": 0}), [relation("out", terms, offset)]
            )
            with self.subTest(case=i):
                self.assertEqual(
                    F(result["model"]["parameters"]["out"]), offset + a * ca + b * cb
                )

    def test_cycles_include_path_and_do_not_mutate_input(self):
        m = model({"a": 1, "b": 2, "c": 3})
        original = copy.deepcopy(m)
        error = self.assert_error(
            m,
            [relation("a", {"b": 1}), relation("b", {"c": 1}), relation("c", {"a": 1})],
            "relation_cycle",
        )
        self.assertIn("a -> b -> c -> a", error["message"])
        self.assertEqual(m, original)
        self.assert_error(m, [relation("a", {"a": 1})], "relation_cycle")

    def test_missing_parameters_and_bad_relation_fields(self):
        m = model({"a": 1, "b": 2})
        for op, code in [
            (relation("absent", {"a": 1}), "missing_parameter"),
            (relation("b", {"absent": 1}), "missing_parameter"),
            (relation("b", {"a": 0}), "invalid_relation"),
            (relation("b", {"a": "1/0"}), "invalid_number"),
            (relation("b", {"a": "0.5"}), "invalid_number"),
            (relation("b", {"a": 1}, "bad"), "invalid_number"),
        ]:
            with self.subTest(op=op):
                self.assert_error(m, [op], code)
        op = relation("b", {"a": 1})
        op["relation"]["executable"] = "forbidden"
        with self.assertRaises(CadError):
            evaluate(m, [op])

    def test_derived_values_require_explicit_relationship_edit(self):
        m = self.centered()
        self.assert_error(m, [set_value("center", 70)], "derived_parameter")
        self.assert_error(
            m,
            [{"op": "adjust_parameter", "id": "center", "delta_mm": "1"}],
            "derived_parameter",
        )
        result = evaluate(m, [relation("center", {"width": "1/4"}, 3)])
        self.assertEqual(result["model"]["parameters"]["center"], "28")

    def test_remove_freezes_current_value_and_allows_free_edit(self):
        m = self.centered()
        result = evaluate(
            m,
            [
                set_value("width", 120),
                {"op": "remove_relation", "id": "center"},
                set_value("width", 140),
            ],
        )
        self.assertNotIn("relations", result["model"])
        self.assertEqual(result["model"]["parameters"]["center"], "60")
        edited = evaluate(result["model"], [set_value("center", 77)])
        self.assertEqual(edited["model"]["parameters"]["center"], "77")
        self.assert_error(
            result["model"],
            [{"op": "remove_relation", "id": "center"}],
            "missing_relation",
        )

    def test_fixed_derived_value_and_preserve_are_enforced(self):
        m = self.centered()
        fixed = evaluate(m, [{"op": "fix_parameter", "id": "center"}])["model"]
        self.assert_error(fixed, [set_value("width", 120)], "constraint_conflict")
        self.assert_error(
            fixed,
            [set_value("width", 120), {"op": "fix_parameter", "id": "center"}],
            "constraint_conflict",
        )
        self.assert_error(
            fixed,
            [{"op": "release_parameter", "id": "center"}, set_value("width", 120)],
            "preserve_conflict",
            ["center"],
        )
        result = evaluate(
            fixed,
            [{"op": "release_parameter", "id": "center"}, set_value("width", 120)],
        )
        self.assertEqual(result["model"]["parameters"]["center"], "60")
        self.assert_error(m, [set_value("width", 120)], "preserve_conflict", ["center"])
        # Fix observes the computed value at this point in the command sequence.
        result = evaluate(
            m, [set_value("width", 120), {"op": "fix_parameter", "id": "center"}]
        )
        self.assertEqual(result["model"]["fixed"]["center"], "60")

    def test_stale_stored_derived_value_rejects_instead_of_repairing(self):
        m = self.centered()
        m["parameters"]["center"] = "49"
        self.assert_error(m, [], "relation_mismatch")

    def test_bounds_and_constant_relationship(self):
        m = model({"source": 2**127, "out": 0})
        self.assert_error(m, [relation("out", {"source": 2})], "relation_overflow")
        m = model({f"p{i}": i for i in range(10)})
        self.assert_error(
            m, [relation("p9", {f"p{i}": 1 for i in range(9)})], "relation_limit"
        )
        result = evaluate(m, [relation("p9", {}, "7/3")])
        self.assertEqual(result["model"]["parameters"]["p9"], "7/3")
        # Exercise the full bounded dependency depth, in reverse ID order.
        m = model({f"p{i:02}": 1 for i in range(64)})
        ops = [relation(f"p{i:02}", {f"p{i + 1:02}": 1}, 1) for i in range(63)]
        self.assertEqual(evaluate(m, ops)["model"]["parameters"]["p00"], "64")
        m["parameters"]["extra"] = "1"
        self.assert_error(m, [], "model_limit")

    def test_profile_rebuild_preview_persistence_undo_and_failed_save(self):
        fixture = ROOT / "examples/ai-cad/relationships"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            store = Store(path)
            created = store.execute(json.loads((fixture / "create.json").read_text()))
            widen = json.loads((fixture / "widen.json").read_text())
            before = path.read_bytes()
            preview = store.execute(
                {
                    **{k: v for k, v in widen.items() if k != "transaction_id"},
                    "action": "preview",
                }
            )
            self.assertEqual(preview["model"]["parameters"]["tip_x"], "60")
            self.assertEqual(preview["changed_parameters"], ["tip_x", "width"])
            self.assertIn(
                ["60", "60", "12"], preview["bodies"][0]["boundary"]["vertices"]
            )
            self.assertEqual(path.read_bytes(), before)
            edited = store.execute(widen)
            self.assertEqual(
                Store(path).execute({"action": "inspect"})["model"], edited["model"]
            )
            self.assertEqual(edited["model"]["features"], created["model"]["features"])
            self.assertTrue(store.execute(widen)["replayed"])
            before = path.read_bytes()
            invalid = {
                **widen,
                "transaction_id": "cycle",
                "expected_revision": 2,
                "preserve": [],
                "operations": [relation("width", {"tip_x": 2})],
            }
            with self.assertRaises(CadError) as caught:
                store.execute(invalid)
            self.assertEqual(caught.exception.detail["code"], "relation_cycle")
            self.assertEqual(path.read_bytes(), before)
            undone = store.execute(
                {"action": "undo", "expected_revision": 2, "transaction_id": "undo"}
            )
            self.assertEqual(undone["model"], created["model"])
            redone = store.execute(
                {"action": "redo", "expected_revision": 3, "transaction_id": "redo"}
            )
            self.assertEqual(redone["bodies"], edited["bodies"])


if __name__ == "__main__":
    unittest.main()
