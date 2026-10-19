"""Native files preserve history; imported models are isolated undoable edits."""

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from store import CadError, Store, encode
from test_contract import CREATE


def envelope(state):
    return {"state": state, "sha256": hashlib.sha256(encode(state)).hexdigest()}


class NativeFiles(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.store = Store(root / "workspace.json")
        self.source = Store(root / "source.json")
        self.source.execute(CREATE)
        self.source.execute(
            {
                "action": "commit",
                "expected_revision": 1,
                "transaction_id": "source-edit",
                "preserve": [],
                "operations": [{"op": "set_parameter", "id": "width", "mm": "140"}],
            }
        )
        self.document = json.loads(self.source.native_snapshot(2))
        self.proposal = {
            "action": "preview_import",
            "expected_revision": 0,
            "document": self.document,
        }

    def test_download_reopens_complete_document_without_writing(self):
        original = self.source.path.read_bytes()
        downloaded = self.source.native_snapshot(2)
        reopened = Store(Path(self.directory.name) / "download.json")
        reopened.path.write_bytes(downloaded)
        self.assertEqual(reopened.load(), self.source.load())
        self.assertEqual(self.source.path.read_bytes(), original)
        undone = reopened.execute(
            {
                "action": "undo",
                "expected_revision": 2,
                "transaction_id": "undo-download",
            }
        )
        self.assertEqual(undone["bodies"][0]["volume_mm3"], "71400")
        for revision in [0, True, "2"]:
            with self.assertRaises(CadError) as caught:
                self.source.native_snapshot(revision)
            self.assertEqual(caught.exception.detail["code"], "revision_conflict")
        empty = self.store.native_snapshot(0)
        self.assertEqual(json.loads(empty)["state"]["revision"], 0)
        self.assertFalse(self.store.path.exists())

    def test_preview_import_retry_and_history_remain_local(self):
        source_bytes = self.source.path.read_bytes()
        preview = self.store.execute(self.proposal)
        self.assertTrue(preview["preview"])
        self.assertFalse(self.store.path.exists())
        command = {**self.proposal, "action": "import", "transaction_id": "import-one"}
        committed = self.store.execute(command)
        self.assertEqual(committed["model"], preview["model"])
        self.assertEqual(committed["revision"], 1)
        state = self.store.load()
        self.assertEqual(list(state["receipts"]), ["import-one"])
        self.assertEqual(len(state["undo"]), 1)
        original = self.store.path.read_bytes()
        replayed = self.store.execute(command)
        self.assertTrue(replayed["replayed"])
        self.assertEqual(replayed["committed_revision"], 1)
        self.assertEqual(self.store.path.read_bytes(), original)
        with self.assertRaises(CadError) as caught:
            self.store.execute({**command, "expected_revision": 1})
        self.assertEqual(caught.exception.detail["code"], "transaction_conflict")
        undone = self.store.execute(
            {"action": "undo", "expected_revision": 1, "transaction_id": "undo-import"}
        )
        self.assertEqual(undone["model"]["features"], [])
        redone = Store(self.store.path).execute(
            {"action": "redo", "expected_revision": 2, "transaction_id": "redo-import"}
        )
        self.assertEqual(redone["model"], preview["model"])
        self.assertEqual(self.source.path.read_bytes(), source_bytes)

    def test_replace_existing_model_clears_redo_but_keeps_undo(self):
        self.store.execute(CREATE)
        previous = self.store.load()["model"]
        command = {
            **self.proposal,
            "expected_revision": 1,
            "action": "import",
            "transaction_id": "replace",
        }
        self.store.execute(command)
        self.assertEqual(self.store.load()["undo"][-1], previous)
        self.assertEqual(len(self.store.load()["receipts"]), 2)
        self.store.execute(
            {"action": "undo", "expected_revision": 2, "transaction_id": "undo-replace"}
        )
        self.store.execute(
            {**command, "expected_revision": 3, "transaction_id": "replace-again"}
        )
        self.assertEqual(self.store.load()["redo"], [])
        before = self.store.path.read_bytes()
        with self.assertRaises(CadError) as caught:
            self.store.execute(
                {**command, "expected_revision": 4, "transaction_id": "same"}
            )
        self.assertEqual(caught.exception.detail["code"], "no_change")
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_corrupt_or_invalid_history_rejects_atomically(self):
        self.store.execute(CREATE)
        before = self.store.path.read_bytes()
        bad = copy.deepcopy(self.document)
        bad["state"]["revision"] += 1
        cases = [bad, {}, [], None]
        for field, value in [
            ("schema_version", 2),
            ("revision", -1),
            ("undo", [None]),
            ("redo", [None]),
            ("receipts", {"x": {"request": "x", "revision": 999}}),
        ]:
            state = copy.deepcopy(self.document["state"])
            state[field] = value
            cases.append(envelope(state))
        for document in cases:
            for action in ["preview_import", "import"]:
                command = {
                    **self.proposal,
                    "action": action,
                    "expected_revision": 1,
                    "document": document,
                }
                if action == "import":
                    command["transaction_id"] = "invalid"
                with self.assertRaises(CadError) as caught:
                    self.store.execute(command)
                self.assertEqual(caught.exception.detail["code"], "invalid_document")
                self.assertEqual(self.store.path.read_bytes(), before)

    def test_stale_and_oversized_imports_do_not_write(self):
        self.store.execute(CREATE)
        before = self.store.path.read_bytes()
        with self.assertRaises(CadError) as caught:
            self.store.execute(self.proposal)
        self.assertEqual(caught.exception.detail["code"], "revision_conflict")
        with patch("store.MAX_BYTES", 1):
            with self.assertRaises(CadError) as caught:
                self.store.execute({**self.proposal, "expected_revision": 1})
            self.assertIn(
                caught.exception.detail["code"], ["request_limit", "invalid_document"]
            )
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_cli_accepts_native_envelope_beyond_ordinary_command_limit(self):
        import subprocess
        import sys

        state = copy.deepcopy(self.document["state"])
        state["receipts"]["large"] = {"request": "a" * 300000, "revision": 1}
        command = {**self.proposal, "document": envelope(state)}
        cli = Path(__file__).with_name("cad.py")
        result = subprocess.run(
            [sys.executable, str(cli), "--store", str(self.store.path)],
            input=encode(command),
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(json.loads(result.stdout)["result"]["preview"])
        self.assertFalse(self.store.path.exists())
