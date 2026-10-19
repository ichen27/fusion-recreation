"""All-body archives use one saved snapshot and contain portable complete files."""

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import exports
from store import Store, CadError
from test_holes import audit_triangles, read_stl


class Archive(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = Store(Path(self.directory.name) / "part.json")
        ops = [
            {"op": "define_parameter", "id": "w", "mm": "2"},
            {"op": "define_parameter", "id": "h", "mm": "3"},
        ]
        ops += [
            {
                "op": "add_feature",
                "feature": {
                    "kind": "block",
                    "id": name,
                    "width": "w",
                    "depth": "w",
                    "height": "h",
                },
            }
            for name in ["Part", "part"]
        ]
        self.store.execute(
            {
                "action": "commit",
                "expected_revision": 0,
                "transaction_id": "create",
                "preserve": [],
                "operations": ops,
            }
        )

    def test_complete_deterministic_archive_with_portable_unique_names(self):
        before = self.store.path.read_bytes()
        data, manifest = exports.export_stl_archive(self.store, 1)
        self.assertEqual(data, exports.export_stl_archive(self.store, 1)[0])
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(manifest["units"], "mm")
        self.assertEqual(manifest["revision"], 1)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertIsNone(archive.testzip())
            names = archive.namelist()
            self.assertEqual(len(names), 3)
            self.assertEqual(len({n.casefold() for n in names}), 3)
            self.assertEqual(json.loads(archive.read("manifest.json")), manifest)
            for row in manifest["bodies"]:
                self.assertAlmostEqual(
                    audit_triangles(read_stl(archive.read(row["file"])), 0), 12
                )

    def test_one_snapshot_survives_interleaved_commit(self):
        original = exports.tessellate
        calls = 0

        def mesh(model, feature_id, segments):
            nonlocal calls
            if calls == 0:
                self.store.execute(
                    {
                        "action": "commit",
                        "expected_revision": 1,
                        "transaction_id": "concurrent",
                        "preserve": [],
                        "operations": [{"op": "set_parameter", "id": "w", "mm": "4"}],
                    }
                )
            calls += 1
            return original(model, feature_id, segments)

        with patch("exports.tessellate", side_effect=mesh):
            data, manifest = exports.export_stl_archive(self.store, 1)
        self.assertEqual(self.store.execute({"action": "inspect"})["revision"], 2)
        self.assertEqual(manifest["revision"], 1)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for row in manifest["bodies"]:
                self.assertAlmostEqual(
                    audit_triangles(read_stl(archive.read(row["file"])), 0), 12
                )

    def test_stale_empty_invalid_resolution_and_size_fail(self):
        for revision, segments, code in [
            (0, 128, "revision_conflict"),
            (1, 1, "mesh_limit"),
        ]:
            with self.assertRaises(CadError) as caught:
                exports.export_stl_archive(self.store, revision, segments)
            self.assertEqual(caught.exception.detail["code"], code)
        with patch("exports.MAX_ARCHIVE_BYTES", 1):
            with self.assertRaises(CadError) as caught:
                exports.export_stl_archive(self.store, 1)
            self.assertEqual(caught.exception.detail["code"], "export_limit")
        with self.assertRaises(CadError) as caught:
            exports.export_stl_archive(
                Store(Path(self.directory.name) / "empty.json"), 0
            )
        self.assertEqual(caught.exception.detail["code"], "missing_body")
