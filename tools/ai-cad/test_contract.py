"""Integration checks exercise the actual Rust executable and durable host."""

import copy
import json
import multiprocessing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from store import ROOT, Store, dispatch

CREATE = json.loads((ROOT / "examples/ai-cad/create.json").read_text())
WIDEN = json.loads((ROOT / "examples/ai-cad/widen.json").read_text())


def concurrent_writer(path, tx, queue):
    command = {**WIDEN, "transaction_id": tx}
    queue.put(dispatch(Store(path), command))


class Contract(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "model.cad.json"
        self.store = Store(self.path)

    def initial(self):
        return self.store.execute(copy.deepcopy(CREATE))

    def assert_error(self, command, code):
        before = self.path.read_bytes() if self.path.exists() else None
        reply = dispatch(self.store, command)
        self.assertEqual(reply["error"]["code"], code, reply)
        self.assertEqual(self.path.read_bytes() if self.path.exists() else None, before)

    def test_two_turn_geometry_and_reopen(self):
        first = self.initial()
        self.assertEqual(first["bodies"][0]["volume_mm3"], "71400")
        second = Store(self.path).execute(WIDEN)
        self.assertEqual(second["bodies"][0]["volume_mm3"], "85800")
        self.assertEqual(second["changed_parameters"], ["width"])
        self.assertEqual(
            second["model"]["fixed"], {"corner_size": "10", "thickness": "12"}
        )
        boundary = second["bodies"][0]["boundary"]
        self.assertIn(["110", "60", "12"], boundary["vertices"])
        self.assertIn(["120", "50", "12"], boundary["vertices"])
        self.assertEqual(
            Store(self.path).execute({"action": "inspect"})["model"], second["model"]
        )

    def test_preview_has_no_persistent_effect(self):
        self.initial()
        before = self.path.read_bytes()
        command = {k: v for k, v in WIDEN.items() if k != "transaction_id"}
        command["action"] = "preview"
        result = self.store.execute(command)
        self.assertEqual(result["bodies"][0]["volume_mm3"], "85800")
        self.assertEqual(result["revision"], 1)
        self.assertEqual(self.path.read_bytes(), before)

    def test_undo_redo_survive_restart_and_increment_revision(self):
        self.initial()
        self.store.execute(WIDEN)
        undo = Store(self.path).execute(
            {"action": "undo", "expected_revision": 2, "transaction_id": "undo"}
        )
        self.assertEqual(
            (undo["revision"], undo["model"]["parameters"]["width"]), (3, "100")
        )
        redo = Store(self.path).execute(
            {"action": "redo", "expected_revision": 3, "transaction_id": "redo"}
        )
        self.assertEqual(
            (redo["revision"], redo["model"]["parameters"]["width"]), (4, "120")
        )

    def test_invalid_batch_rolls_back(self):
        self.initial()
        self.assert_error(
            {
                **WIDEN,
                "preserve": [],
                "operations": [
                    {"op": "set_parameter", "id": "width", "mm": "200"},
                    {"op": "set_parameter", "id": "thickness", "mm": "13"},
                ],
            },
            "constraint_conflict",
        )

    def test_fix_again_cannot_overwrite_invariant(self):
        self.initial()
        self.assert_error(
            {
                **WIDEN,
                "preserve": [],
                "operations": [
                    {"op": "set_parameter", "id": "thickness", "mm": "13"},
                    {"op": "fix_parameter", "id": "thickness"},
                ],
            },
            "constraint_conflict",
        )

    def test_explicit_constraint_release(self):
        self.initial()
        result = self.store.execute(
            {
                **WIDEN,
                "preserve": [],
                "operations": [
                    {"op": "release_parameter", "id": "thickness"},
                    {"op": "set_parameter", "id": "thickness", "mm": "13"},
                ],
            }
        )
        self.assertEqual(result["model"]["parameters"]["thickness"], "13")

    def test_preserve_and_stale_revision(self):
        self.initial()
        self.assert_error({**WIDEN, "preserve": ["width"]}, "preserve_conflict")
        self.assert_error({**WIDEN, "expected_revision": 0}, "revision_conflict")
        self.assert_error({**WIDEN, "expected_revision": True}, "revision_conflict")

    def test_retry_is_idempotent_after_restart_and_later_edits(self):
        self.initial()
        self.store.execute(WIDEN)
        again = Store(self.path).execute(CREATE)
        self.assertEqual(
            (again["replayed"], again["committed_revision"], again["revision"]),
            (True, 1, 2),
        )
        self.assertEqual(again["model"]["parameters"]["width"], "120")
        self.assert_error(
            {**WIDEN, "transaction_id": CREATE["transaction_id"]},
            "transaction_conflict",
        )

    def test_bad_numeric_values_and_unknown_fields(self):
        for mm in ["NaN", "1.2.3", "1/0", "1e9", "9" * 81]:
            self.assert_error(
                {
                    **CREATE,
                    "operations": [{"op": "define_parameter", "id": "x", "mm": mm}],
                },
                "invalid_number",
            )
        self.assert_error({**CREATE, "unexpected": True}, "invalid_command")
        self.assert_error(
            {
                **CREATE,
                "operations": [
                    {"op": "define_parameter", "id": "x", "mm": "2", "ignored": True}
                ],
            },
            "invalid_request",
        )

    def test_invalid_references_and_cut_range(self):
        self.initial()
        self.assert_error(
            {
                **WIDEN,
                "operations": [{"op": "set_parameter", "id": "width", "mm": "5"}],
            },
            "cut_range",
        )
        self.assert_error(
            {
                **WIDEN,
                "operations": [{"op": "set_parameter", "id": "missing", "mm": "5"}],
            },
            "missing_parameter",
        )
        self.assert_error(
            {
                **WIDEN,
                "operations": [
                    {
                        "op": "add_feature",
                        "feature": {
                            "kind": "corner_cut",
                            "id": "bad",
                            "input": "corner",
                            "size": "corner_size",
                        },
                    }
                ],
            },
            "unsupported_reference",
        )

    def test_unrelated_body_unchanged(self):
        initial = copy.deepcopy(CREATE)
        initial["operations"] += [
            {"op": "define_parameter", "id": "other_size", "mm": "3"},
            {
                "op": "add_feature",
                "feature": {
                    "kind": "block",
                    "id": "other",
                    "width": "other_size",
                    "depth": "other_size",
                    "height": "other_size",
                },
            },
        ]
        first = self.store.execute(initial)
        second = self.store.execute(WIDEN)
        self.assertEqual(first["bodies"][1], second["bodies"][1])

    def test_branch_discards_redo(self):
        self.initial()
        self.store.execute(WIDEN)
        self.store.execute(
            {"action": "undo", "expected_revision": 2, "transaction_id": "u"}
        )
        self.store.execute(
            {**WIDEN, "expected_revision": 3, "transaction_id": "branch"}
        )
        self.assert_error(
            {"action": "redo", "expected_revision": 4, "transaction_id": "r"},
            "empty_history",
        )

    def test_corrupt_document_is_not_overwritten(self):
        self.initial()
        envelope = json.loads(self.path.read_text())
        envelope["state"]["model"]["parameters"]["width"] = "999"
        self.path.write_text(json.dumps(envelope))
        self.assert_error(WIDEN, "invalid_document")

    def test_failed_save_before_publication(self):
        self.initial()
        with patch("store.os.replace", side_effect=OSError("injected")):
            self.assert_error(WIDEN, "save_failed")

    def test_uncertain_save_can_be_resolved_by_same_retry(self):
        self.initial()
        import os

        original = os.fsync
        calls = []

        def fail_directory(fd):
            calls.append(fd)
            if len(calls) == 2:
                raise OSError("injected directory sync failure")
            original(fd)

        with patch("store.os.fsync", side_effect=fail_directory):
            self.assertEqual(
                dispatch(self.store, WIDEN)["error"]["code"], "commit_uncertain"
            )
        retry = Store(self.path).execute(WIDEN)
        self.assertTrue(retry["replayed"])
        self.assertEqual(retry["revision"], 2)

    def test_two_processes_cannot_commit_same_revision(self):
        self.initial()
        context = multiprocessing.get_context("spawn")
        queue = context.Queue()
        processes = [
            context.Process(target=concurrent_writer, args=(self.path, str(i), queue))
            for i in range(2)
        ]
        for process in processes:
            process.start()
        results = [queue.get(timeout=30) for _ in processes]
        for process in processes:
            process.join(30)
            self.assertEqual(process.exitcode, 0)
        self.assertEqual(sum("result" in r for r in results), 1)
        self.assertEqual(
            [r["error"]["code"] for r in results if "error" in r], ["revision_conflict"]
        )


if __name__ == "__main__":
    unittest.main()
