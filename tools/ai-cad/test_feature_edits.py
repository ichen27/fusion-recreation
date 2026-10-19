"""Feature replacement/removal, topology changes and atomic document recovery."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from store import ROOT, Store, evaluate, CadError, dispatch

EXAMPLE = ROOT / "examples/ai-cad/concave-profile"


def model():
    return json.loads((EXAMPLE / "create.reply.json").read_text())["result"]["model"]


def replace(feature):
    return {"op": "replace_feature", "id": feature["id"], "feature": feature}


class Features(unittest.TestCase):
    def invalid(self, m, operations, code):
        original = copy.deepcopy(m)
        with self.assertRaises(CadError) as caught:
            evaluate(m, operations)
        self.assertEqual(caught.exception.detail["code"], code, caught.exception.detail)
        self.assertEqual(m, original)

    def test_add_remove_holes_retains_other_ids_and_exact_volume(self):
        m = model()
        feature = copy.deepcopy(m["features"][-1])
        feature["holes"].append(
            {"id": "corner_mount", "x": "margin", "y": "margin", "radius": "radius"}
        )
        state = evaluate(m, [replace(feature)])
        self.assertEqual(state["bodies"][0]["volume_mm3"], "12000 - (135)*pi")
        self.assertEqual(state["model"]["features"][:2], m["features"][:2])
        self.assertEqual(state["changed_parameters"], [])
        feature["holes"].pop(0)
        state = evaluate(state["model"], [replace(feature)])
        self.assertEqual(
            [h["id"] for h in state["bodies"][0]["analytic"]["holes"]],
            ["top_mount", "corner_mount"],
        )
        self.assertEqual(state["bodies"][0]["volume_mm3"], "12000 - (90)*pi")

    def test_replace_profile_rebuilds_dependents_and_rejects_invalid_topology(self):
        m = model()
        profile = copy.deepcopy(m["features"][0])
        # Replace the L-shaped outline with a rectangle using existing vertex IDs.
        profile["vertices"] = [profile["vertices"][i] for i in (0, 1, 4, 5)]
        profile["vertices"][2]["x"] = "width"
        result = evaluate(m, [replace(profile)])
        self.assertEqual(result["bodies"][0]["volume_mm3"], "24000 - (90)*pi")
        self.assertEqual(result["model"]["features"][1:], m["features"][1:])
        profile["vertices"][1]["x"] = "zero"
        self.invalid(m, [replace(profile)], "invalid_profile")

    def test_replacement_identity_missing_and_forward_references_reject(self):
        m = model()
        feature = copy.deepcopy(m["features"][0])
        feature["id"] = "new_outline"
        self.invalid(
            m,
            [{"op": "replace_feature", "id": "outline", "feature": feature}],
            "feature_identity",
        )
        feature["id"] = "outline"
        feature["kind"] = "polygon_profile"
        self.invalid(m, [replace(feature)], "feature_identity")
        self.invalid(
            m,
            [{"op": "replace_feature", "id": "unknown", "feature": feature}],
            "missing_feature",
        )
        self.invalid(m, [{"op": "remove_feature", "id": "unknown"}], "missing_feature")
        extrusion = copy.deepcopy(m["features"][1])
        extrusion["profile"] = "later"
        later = copy.deepcopy(m["features"][0])
        later["id"] = "later"
        self.invalid(
            m,
            [replace(extrusion), {"op": "add_feature", "feature": later}],
            "unsupported_reference",
        )

    def test_removal_has_no_implicit_cascade_and_batch_can_remove_dependencies(self):
        m = model()
        self.invalid(
            m, [{"op": "remove_feature", "id": "outline"}], "unsupported_reference"
        )
        self.invalid(
            m, [{"op": "remove_feature", "id": "plate"}], "unsupported_reference"
        )
        result = evaluate(m, [{"op": "remove_feature", "id": "mount"}])
        self.assertEqual(result["bodies"][0]["feature_id"], "plate")
        self.assertEqual(result["bodies"][0]["volume_mm3"], "12000")
        for ids in [("outline", "plate", "mount"), ("mount", "plate", "outline")]:
            result = evaluate(m, [{"op": "remove_feature", "id": i} for i in ids])
            self.assertEqual(result["bodies"], [])
            self.assertEqual(result["model"]["parameters"], m["parameters"])

    def test_unused_parameter_cleanup_is_explicit_and_constraints_are_not_deleted(self):
        m = model()
        self.invalid(
            m, [{"op": "remove_parameter", "id": "width"}], "missing_parameter"
        )
        self.invalid(
            m, [{"op": "remove_parameter", "id": "radius"}], "parameter_in_use"
        )
        self.invalid(
            m, [{"op": "remove_parameter", "id": "right_x"}], "parameter_in_use"
        )
        self.invalid(
            m, [{"op": "remove_parameter", "id": "unknown"}], "missing_parameter"
        )
        ops = [
            {"op": "remove_feature", "id": "mount"},
            {"op": "release_parameter", "id": "radius"},
            {"op": "remove_parameter", "id": "radius"},
        ]
        result = evaluate(m, ops)
        self.assertEqual(result["changed_parameters"], ["radius"])
        self.assertNotIn("radius", result["model"]["parameters"])
        self.invalid(
            m,
            ops + [{"op": "define_parameter", "id": "margin", "mm": "1"}],
            "duplicate_id",
        )
        with self.assertRaises(CadError) as caught:
            evaluate(m, ops, ["radius"])
        self.assertEqual(caught.exception.detail["code"], "missing_parameter")

    def test_store_preview_commit_retry_reopen_undo_and_failure_are_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.json"
            store = Store(path)
            store.execute(json.loads((EXAMPLE / "create.json").read_text()))
            before = path.read_bytes()
            op = {"op": "remove_feature", "id": "mount"}
            command = {
                "action": "preview",
                "expected_revision": 1,
                "operations": [op],
                "preserve": [],
            }
            preview = store.execute(command)
            self.assertEqual(path.read_bytes(), before)
            command.update(action="commit", transaction_id="remove-holes")
            committed = store.execute(command)
            self.assertEqual(committed["bodies"], preview["bodies"])
            self.assertTrue(store.execute(command)["replayed"])
            current = path.read_bytes()
            bad = {
                **command,
                "expected_revision": 2,
                "transaction_id": "bad-parent",
                "operations": [{"op": "remove_feature", "id": "outline"}],
            }
            self.assertEqual(
                dispatch(store, bad)["error"]["code"], "unsupported_reference"
            )
            self.assertEqual(path.read_bytes(), current)
            undone = Store(path).execute(
                {
                    "action": "undo",
                    "expected_revision": 2,
                    "transaction_id": "undo-remove",
                }
            )
            self.assertEqual(undone["model"], model())
            redone = Store(path).execute(
                {
                    "action": "redo",
                    "expected_revision": 3,
                    "transaction_id": "redo-remove",
                }
            )
            self.assertEqual(redone["model"], committed["model"])


if __name__ == "__main__":
    unittest.main()
