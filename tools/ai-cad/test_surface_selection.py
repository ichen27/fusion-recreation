"""Surface context is scoped to body, exact document content and saved revision."""

import copy
from pathlib import Path
import tempfile
import unittest
from selection import Selection, dispatch_selection
from store import Store
from test_counterbores import counterbored
from test_instances import instance
from test_intersection import operations

REFERENCE = "feature/part/hole/left/shoulder"


class SurfaceSelection(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = Store(Path(temp.name) / "part.json")
        self.model = instance(counterbored(), offset=(130, 0, 0))
        self.store.execute(
            dict(
                action="commit",
                expected_revision=0,
                transaction_id="seed",
                operations=operations(self.model),
                preserve=[],
            )
        )
        self.selection = Selection(self.store)

    def select(self, feature="copy", reference=REFERENCE, revision=1):
        return dispatch_selection(
            self.store,
            dict(
                action="select_surface",
                expected_revision=revision,
                feature_id=feature,
                surface_id=reference,
            ),
        )

    def test_linked_surfaces_share_names_but_retain_world_support_and_source(self):
        before = self.store.path.read_bytes()
        source = self.select("part")["result"]["selected_surface"]
        actual = self.select()["result"]
        self.assertEqual(actual["selected_body"]["feature_id"], "copy")
        self.assertEqual(source["reference"], actual["selected_surface"]["reference"])
        self.assertEqual(
            actual["selected_surface"]["source_feature"], self.model["features"][-2]
        )
        self.assertEqual(actual["selected_surface"]["support"]["offset"], "4")
        other = Selection(Store(self.store.path)).execute(dict(action="context"))
        self.assertEqual(actual, other)
        wall = "feature/part/hole/left/upper"
        source = self.select("part", wall)["result"]["selected_surface"]
        placed = self.select("copy", wall)["result"]["selected_surface"]
        self.assertEqual(len(placed["faces"]), 4)
        self.assertEqual(source["support"]["origin"], ["12", "12", "0"])
        self.assertEqual(placed["support"]["origin"], ["142", "12", "0"])
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_edit_undo_import_and_reselect_invalidate_without_retargeting(self):
        self.select()
        original = self.store.load()
        self.store.execute(
            dict(
                action="commit",
                expected_revision=1,
                transaction_id="deeper",
                operations=[dict(op="set_parameter", id="recess_depth", mm="3")],
                preserve=[],
            )
        )
        stale = self.selection.execute(dict(action="context"))
        self.assertEqual(stale["selection_status"], "stale")
        self.assertIsNone(stale["selected_surface"])
        self.assertEqual(self.select()["error"]["code"], "revision_conflict")
        self.assertEqual(
            self.select(revision=2)["result"]["selected_surface"]["support"]["offset"],
            "3",
        )
        self.store.execute(
            dict(action="undo", expected_revision=2, transaction_id="back")
        )
        self.assertEqual(
            self.selection.execute(dict(action="context"))["selection_status"], "stale"
        )
        self.select(revision=3)
        replaced = copy.deepcopy(original)
        replaced["revision"] = 3
        replaced["model"]["parameters"]["recess_depth"] = "1"
        self.store.save(replaced)
        self.assertEqual(
            self.selection.execute(dict(action="context"))["selection_status"], "stale"
        )
        current = self.select(revision=3)["result"]
        self.assertEqual(current["selected_surface"]["support"]["offset"], "5")
        body_only = self.selection.execute(
            dict(action="select", expected_revision=3, feature_id="copy")
        )
        self.assertNotIn("selected_surface", body_only)
        self.assertEqual(body_only["selection_status"], "current")

    def test_invalid_references_do_not_overwrite_context_or_native_history(self):
        self.select()
        before, selected = (
            self.store.path.read_bytes(),
            self.selection.path.read_bytes(),
        )
        for feature, surface, revision, code in [
            ("copy", "missing", 1, "missing_surface"),
            ("copy", None, 1, "missing_surface"),
            (None, REFERENCE, 1, "missing_surface"),
            ("stock", REFERENCE, 1, "missing_body"),
            ("copy", REFERENCE, True, "revision_conflict"),
        ]:
            self.assertEqual(
                self.select(feature, surface, revision)["error"]["code"], code
            )
            self.assertEqual(self.selection.path.read_bytes(), selected)
        self.assertEqual(self.store.path.read_bytes(), before)
        self.selection.path.write_text('{"schema_version":2}')
        self.assertEqual(
            dispatch_selection(self.store, dict(action="context"))["error"]["code"],
            "invalid_selection",
        )
        self.assertEqual(self.select()["result"]["selection_status"], "current")


if __name__ == "__main__":
    unittest.main()
