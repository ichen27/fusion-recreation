"""Workspace picks cannot silently retarget changed, consumed or replaced bodies."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from selection import Selection, dispatch_selection
from store import Store, CadError
from test_contract import CREATE


class SelectionContext(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "model.json")
        self.created = self.store.execute(copy.deepcopy(CREATE))
        self.body = self.created["bodies"][0]["feature_id"]
        self.selection = Selection(self.store)

    def select(self, feature=None, revision=1):
        return self.selection.execute(
            {"action": "select", "expected_revision": revision, "feature_id": feature}
        )

    def test_cross_instance_context_never_changes_native_history(self):
        before = self.store.path.read_bytes()
        self.assertEqual(
            self.selection.execute({"action": "context"})["selection_status"], "empty"
        )
        current = self.select(self.body)
        other = Selection(Store(self.store.path)).execute({"action": "context"})
        self.assertEqual(current, other)
        self.assertEqual(other["selected_body"], self.created["bodies"][0])
        self.assertEqual(other["model"], self.created["model"])
        self.assertEqual(self.select()["selection_status"], "empty")
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertNotIn(
            "selection", json.loads(self.store.native_snapshot(1))["state"]
        )

    def test_edit_undo_and_same_revision_replacement_invalidate_selection(self):
        self.select(self.body)
        original = self.store.load()
        result = self.store.execute(
            {
                "action": "commit",
                "expected_revision": 1,
                "transaction_id": "wider",
                "operations": [
                    {"op": "adjust_parameter", "id": "width", "delta_mm": "20"}
                ],
                "preserve": [],
            }
        )
        self.assertEqual(result["revision"], 2)
        stale = self.selection.execute({"action": "context"})
        self.assertEqual(stale["selection_status"], "stale")
        self.assertIsNone(stale["selected_body"])
        self.store.execute(
            {"action": "undo", "expected_revision": 2, "transaction_id": "back"}
        )
        self.assertEqual(
            self.selection.execute({"action": "context"})["selection_status"], "stale"
        )
        self.select(self.body, revision=3)
        self.assertEqual(
            self.selection.execute({"action": "context"})["selection_status"], "current"
        )
        # A file externally replaced with equal revision but different content is stale too.
        original["revision"] = 3
        original["model"]["parameters"]["width"] = "140"
        self.store.save(original)
        self.assertEqual(
            self.selection.execute({"action": "context"})["selection_status"], "stale"
        )

    def test_invalid_picks_are_atomic_and_damage_is_recoverable(self):
        self.select(self.body)
        before = self.selection.path.read_bytes()
        for feature, revision, code in [
            ("missing", 1, "missing_body"),
            ("stock", 1, "missing_body"),
            ([], 1, "missing_body"),
            (self.body, 0, "revision_conflict"),
            (self.body, True, "revision_conflict"),
        ]:
            with self.assertRaises(CadError) as caught:
                self.select(feature, revision)
            self.assertEqual(caught.exception.detail["code"], code)
            self.assertEqual(self.selection.path.read_bytes(), before)
        self.selection.path.write_text("{broken")
        self.assertEqual(
            dispatch_selection(self.store, {"action": "context"})["error"]["code"],
            "invalid_selection",
        )
        self.assertEqual(self.select()["selection_status"], "empty")
        self.assertEqual(self.store.execute({"action": "inspect"})["revision"], 1)

    def test_strict_bounded_context_commands(self):
        for command in [
            [],
            {"action": "context", "extra": 1},
            {"action": "select"},
            {"action": "commit"},
        ]:
            self.assertEqual(
                dispatch_selection(self.store, command)["error"]["code"],
                "invalid_command",
            )
        self.selection.path.write_text(" " * 4097)
        self.assertEqual(
            dispatch_selection(self.store, {"action": "context"})["error"]["code"],
            "invalid_selection",
        )
