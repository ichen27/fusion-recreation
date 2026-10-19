"""Cache reuse cannot weaken document validation, revision checks or isolation."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from result_cache import ResultCache
from store import Store, CadError, evaluate
from test_contract import CREATE
from test_holes import EXAMPLE
from exports import display


class Cache(unittest.TestCase):
    def test_bounds_mutation_isolation_and_engine_replacement(self):
        with tempfile.TemporaryDirectory() as d:
            binary = Path(d) / "engine"
            binary.write_bytes(b"v1")
            cache = ResultCache(max_entries=2, max_bytes=180)
            calls = []

            def compute():
                calls.append(1)
                return {"nested": {"value": "valid"}}

            result = cache.get(binary, {"model": 1}, compute)
            result["nested"]["value"] = "changed"
            self.assertEqual(
                cache.get(binary, {"model": 1}, compute)["nested"]["value"], "valid"
            )
            self.assertEqual(len(calls), 1)
            for i in (2, 3):
                cache.get(binary, {"model": i}, compute)
            self.assertLessEqual(cache.bytes, 180)
            self.assertLessEqual(len(cache.entries), 2)
            cache.get(binary, {"model": 1}, compute)
            self.assertEqual(len(calls), 4)
            replacement = Path(d) / "new"
            replacement.write_bytes(b"v2")
            replacement.replace(binary)
            cache.get(binary, {"model": 1}, compute)
            self.assertEqual(len(calls), 5)
            binary.unlink()
            cache.get(binary, {"model": 1}, compute)
            self.assertEqual(len(calls), 6)

    def test_failure_and_oversize_not_cached(self):
        with tempfile.TemporaryDirectory() as d:
            binary = Path(d) / "engine"
            binary.touch()
            cache = ResultCache(max_bytes=40)

            def fail():
                raise RuntimeError("failed")

            for _ in range(2):
                with self.assertRaises(RuntimeError):
                    cache.get(binary, {}, fail)
            cache.get(binary, {}, lambda: {"data": "x" * 100})
            self.assertEqual(len(cache.entries), 0)
            self.assertEqual(cache.bytes, 0)

    def test_repeated_inspect_reuses_but_external_edits_are_seen(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "part.json"
            store = Store(path)
            store.execute(CREATE)
            with patch("store.evaluate", wraps=evaluate) as called:
                first = store.execute({"action": "inspect"})
                count = called.call_count
                first["model"]["parameters"]["width"] = "bad"
                self.assertEqual(
                    store.execute({"action": "inspect"})["model"]["parameters"][
                        "width"
                    ],
                    "100",
                )
                self.assertEqual(called.call_count, count)
                other = Store(path)
                other.execute(
                    {
                        "action": "commit",
                        "expected_revision": 1,
                        "transaction_id": "other",
                        "operations": [
                            {"op": "set_parameter", "id": "width", "mm": "120"}
                        ],
                        "preserve": [],
                    }
                )
                updated = store.execute({"action": "inspect"})
                self.assertEqual(updated["revision"], 2)
                self.assertEqual(updated["model"]["parameters"]["width"], "120")
                with self.assertRaises(CadError):
                    store.execute(
                        {
                            "action": "preview",
                            "expected_revision": 1,
                            "operations": [],
                            "preserve": [],
                        }
                    )

    def test_changed_checksum_valid_history_is_still_validated(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "part.json")
            store.execute(CREATE)
            store.execute({"action": "inspect"})
            state = store.load()
            state["undo"][0]["parameters"] = {"invalid": "0/0"}
            store.save(state)  # Deliberately valid envelope containing invalid history.
            with self.assertRaises(CadError) as caught:
                store.execute({"action": "inspect"})
            self.assertEqual(caught.exception.detail["code"], "invalid_document")

    def test_preview_preserve_validation_and_mesh_copy_isolation(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "part.json")
            state = store.execute(json.loads((EXAMPLE / "create.json").read_text()))
            cache = ResultCache()
            with patch(
                "exports.tessellate", return_value={"vertices": [[1, 2, 3]]}
            ) as called:
                first = display({"result": state}, cache)
                first["result"]["bodies"][0]["display_mesh"]["vertices"][0][0] = 999
                second = display(
                    {"result": store.execute({"action": "inspect"})}, cache
                )
                self.assertEqual(
                    second["result"]["bodies"][0]["display_mesh"]["vertices"][0][0], 1
                )
                self.assertEqual(called.call_count, 1)
            with self.assertRaises(CadError):
                store.execute(
                    {
                        "action": "preview",
                        "expected_revision": 1,
                        "operations": [],
                        "preserve": ["missing"],
                    }
                )


if __name__ == "__main__":
    unittest.main()
