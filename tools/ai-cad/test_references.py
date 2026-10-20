"""Saved references must follow dimensions, never guess changed topology."""

import copy
from pathlib import Path
import tempfile
import unittest
from store import CadError, Store, evaluate
from topology import topology_model
from test_counterbores import counterbored
from test_instances import instance
from test_intersection import operations

SHOULDER = "feature/part/hole/left/shoulder"
UPPER = "feature/part/hole/left/upper"


def surface(name="seat", feature="part", surface_id=SHOULDER):
    return dict(
        op="set_reference",
        id=name,
        feature_id=feature,
        target=dict(kind="surface", surface_id=surface_id),
    )


def rim(feature="part"):
    return dict(
        op="set_reference",
        id="rim",
        feature_id=feature,
        target=dict(kind="edge_chain", surfaces=[UPPER, SHOULDER]),
    )


class References(unittest.TestCase):
    def test_surface_and_closed_rim_follow_dimension_changes(self):
        original = evaluate(counterbored())
        self.assertNotIn("references", original["model"])
        bound = evaluate(original["model"], [surface(), rim()])
        self.assertEqual(bound["bodies"], original["bodies"])
        self.assertEqual(len(bound["resolved_references"]["rim"]["edge_indices"]), 4)
        edited = evaluate(
            bound["model"], [dict(op="set_parameter", id="recess_depth", mm="3")]
        )
        self.assertEqual(edited["resolved_references"], bound["resolved_references"])
        topology = topology_model(edited["model"], "part")
        self.assertEqual(topology["surfaces"][SHOULDER]["offset"], "3")
        for i in edited["resolved_references"]["rim"]["edge_indices"]:
            self.assertEqual(topology["edges"][i]["curve"]["radius"], "5")

    def test_instances_are_distinct_and_unrelated_edits_do_not_break_binding(self):
        model = instance(counterbored(), offset=(130, 0, 0))
        bound = evaluate(model, [surface(feature="copy"), rim(feature="copy")])
        self.assertEqual(bound["resolved_references"]["seat"]["feature_id"], "copy")
        edited = evaluate(
            bound["model"], [dict(op="define_parameter", id="unused", mm="9")]
        )
        self.assertEqual(edited["resolved_references"], bound["resolved_references"])
        self.assertNotIn(
            "unused", str(edited["model"]["references"]["seat"]["ancestry"])
        )

    def test_structure_changes_reject_until_explicitly_rebound(self):
        bound = evaluate(counterbored(), [surface()])["model"]
        replacement = copy.deepcopy(bound["features"][-1])
        replacement["holes"] = list(reversed(replacement["holes"]))
        op = dict(op="replace_feature", id="part", feature=replacement)
        with self.assertRaises(CadError) as caught:
            evaluate(bound, [op])
        self.assertEqual(caught.exception.detail["code"], "reference_changed")
        result = evaluate(bound, [op, surface()])
        self.assertEqual(
            result["resolved_references"]["seat"]["target"]["surface_id"], SHOULDER
        )
        self.assertNotEqual(result["model"]["references"], bound["references"])

    def test_missing_nonadjacent_duplicate_and_revision_only_names_reject(self):
        for op, code in [
            (surface(surface_id="evaluated/face/0"), "reference_missing"),
            (
                dict(
                    op="set_reference",
                    id="edge",
                    feature_id="part",
                    target=dict(kind="edge_chain", surfaces=[SHOULDER, SHOULDER]),
                ),
                "invalid_reference",
            ),
            (
                dict(
                    op="set_reference",
                    id="edge",
                    feature_id="part",
                    target=dict(
                        kind="edge_chain",
                        surfaces=[SHOULDER, "feature/part/hole/right/shoulder"],
                    ),
                ),
                "reference_missing",
            ),
        ]:
            with self.assertRaises(CadError) as caught:
                evaluate(counterbored(), [op])
            self.assertEqual(caught.exception.detail["code"], code)
        from test_booleans import boolean, box

        m = boolean(
            box("a", [0, 0, 0], [10, 10, 10]),
            box("b", [5, 0, 0], [15, 10, 10]),
            "union",
        )
        with self.assertRaises(CadError) as caught:
            evaluate(m, [surface(feature="result", surface_id="evaluated/face/0")])
        self.assertEqual(caught.exception.detail["code"], "unsupported_reference")

    def test_consumption_requires_clear_and_history_preserves_names(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "part.cad.json")
            store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations(counterbored()) + [surface(), rim()],
                    preserve=[],
                )
            )
            before = store.path.read_bytes()
            preview = store.execute(
                dict(
                    action="preview",
                    expected_revision=1,
                    operations=[dict(op="set_parameter", id="recess_depth", mm="3")],
                    preserve=[],
                )
            )
            self.assertEqual(store.path.read_bytes(), before)
            self.assertIn("seat", preview["resolved_references"])
            store.execute(
                dict(
                    action="commit",
                    expected_revision=1,
                    transaction_id="clear",
                    operations=[
                        dict(op="remove_reference", id="seat"),
                        dict(op="remove_reference", id="rim"),
                    ],
                    preserve=[],
                )
            )
            self.assertNotIn("references", Store(store.path).load()["model"])
            restored = store.execute(
                dict(action="undo", expected_revision=2, transaction_id="undo")
            )
            self.assertEqual(set(restored["resolved_references"]), {"seat", "rim"})
            model = store.load()["model"]
            model["references"]["seat"]["ancestry"] = []
            with self.assertRaises(CadError):
                evaluate(model)

    def test_consume_referenced_source_requires_explicit_removal(self):
        bound = evaluate(counterbored(), [surface()])["model"]
        ops = [
            dict(op="define_parameter", id="delta", mm="1"),
            dict(
                op="add_feature",
                feature=dict(
                    kind="translate", id="moved", input="part", offset=["delta"] * 3
                ),
            ),
        ]
        with self.assertRaises(CadError) as caught:
            evaluate(bound, ops)
        self.assertEqual(caught.exception.detail["code"], "reference_missing")
        cleared = evaluate(bound, [dict(op="remove_reference", id="seat"), *ops])
        self.assertEqual(cleared["bodies"][0]["feature_id"], "moved")


if __name__ == "__main__":
    unittest.main()
