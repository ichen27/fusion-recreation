"""Selection changes between preview and save cannot silently retarget a guarded edit."""

import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from store import Store, CadError, dispatch
from selection import Selection
from preview_jobs import PreviewJobs
from test_preview_jobs import until
from test_counterbores import counterbored
from test_intersection import operations


class SelectionGuard(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = Store(Path(temp.name) / "part.json")
        self.store.execute(
            dict(
                action="commit",
                expected_revision=0,
                transaction_id="seed",
                operations=operations(counterbored()),
                preserve=[],
            )
        )
        self.select("left")
        self.command = dict(
            action="preview",
            expected_revision=1,
            operations=[dict(op="set_parameter", id="recess_radius", mm="6")],
            preserve=[],
            selection_guard=dict(
                feature_id="part", surface_id="feature/part/hole/left/upper"
            ),
        )

    def select(self, hole):
        return Selection(Store(self.store.path)).execute(
            dict(
                action="select_surface",
                expected_revision=1,
                feature_id="part",
                surface_id=f"feature/part/hole/{hole}/upper",
            )
        )

    def test_same_revision_selection_change_rejects_then_explicit_reselection_succeeds(
        self,
    ):
        before = self.store.path.read_bytes()
        preview = self.store.execute(self.command)
        self.assertEqual(preview["model"]["parameters"]["recess_radius"], "6")
        self.select("right")
        commit = {**self.command, "action": "commit", "transaction_id": "larger"}
        self.assertEqual(
            dispatch(self.store, commit)["error"]["code"], "selection_conflict"
        )
        self.assertEqual(self.store.path.read_bytes(), before)
        self.select("left")
        saved = self.store.execute(commit)
        self.assertEqual(saved["revision"], 2)
        after = self.store.path.read_bytes()
        # A lost acknowledgement remains safely replayable after commit invalidates selection.
        Selection(self.store).execute(
            dict(action="select", expected_revision=2, feature_id=None)
        )
        replay = self.store.execute(commit)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["committed_revision"], 2)
        self.assertEqual(self.store.path.read_bytes(), after)
        changed = copy.deepcopy(commit)
        changed["selection_guard"]["surface_id"] = "feature/part/hole/right/upper"
        self.assertEqual(
            dispatch(self.store, changed)["error"]["code"], "transaction_conflict"
        )

    def test_body_only_guard_and_missing_corrupted_or_replaced_context(self):
        selection = Selection(self.store)
        command = copy.deepcopy(self.command)
        command["selection_guard"]["surface_id"] = None
        self.assertEqual(
            dispatch(self.store, command)["error"]["code"], "selection_conflict"
        )
        selection.execute(dict(action="select", expected_revision=1, feature_id="part"))
        self.assertIn("result", dispatch(self.store, command))
        selection.execute(dict(action="select", expected_revision=1, feature_id=None))
        self.assertEqual(
            dispatch(self.store, command)["error"]["code"], "selection_conflict"
        )
        selection.path.unlink()
        self.assertEqual(
            dispatch(self.store, command)["error"]["code"], "selection_conflict"
        )
        selection.path.write_text("{bad")
        self.assertEqual(
            dispatch(self.store, command)["error"]["code"], "invalid_selection"
        )
        self.select("left")
        state = self.store.load()
        state["model"]["parameters"]["recess_depth"] = "1"
        self.store.save(state)
        self.assertEqual(
            dispatch(self.store, self.command)["error"]["code"], "selection_conflict"
        )

    def test_guard_fields_are_strict_and_failure_is_atomic(self):
        before = self.store.path.read_bytes()
        for guard in [
            None,
            [],
            {},
            dict(feature_id="part"),
            dict(feature_id="part", surface_id=""),
            dict(feature_id=True, surface_id=None),
            dict(feature_id="part", surface_id=None, extra=True),
        ]:
            reply = dispatch(self.store, {**self.command, "selection_guard": guard})
            self.assertEqual(reply["error"]["code"], "invalid_command", guard)
            self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(
            dispatch(
                self.store,
                dict(action="inspect", selection_guard=self.command["selection_guard"]),
            )["error"]["code"],
            "invalid_command",
        )

    def test_snapshot_preview_checks_guard_and_commit_checks_it_again(self):
        entered, release = threading.Event(), threading.Event()

        def run(snapshot, cancel):
            entered.set()
            assert release.wait(5)
            # Only immutable geometry/metadata crosses the process boundary.
            self.assertNotIn("selection_guard", json.loads(snapshot))
            return jobs._process(snapshot, cancel)

        jobs = PreviewJobs(self.store, runner=run)
        self.addCleanup(jobs.close)
        self.addCleanup(release.set)
        before = self.store.path.read_bytes()
        id = jobs.start(self.command)["job_id"]
        self.assertTrue(entered.wait(2))
        self.select("right")
        with self.assertRaises(CadError) as caught:
            jobs.start(self.command)
        self.assertEqual(caught.exception.detail["code"], "selection_conflict")
        release.set()
        result = until(
            lambda: (job if (job := jobs.get(id))["status"] == "succeeded" else None)
        )
        self.assertEqual(result["reply"]["result"]["revision"], 1)
        reply = dispatch(
            self.store,
            {**self.command, "action": "commit", "transaction_id": "blocked"},
        )
        self.assertEqual(reply["error"]["code"], "selection_conflict")
        self.assertEqual(self.store.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
