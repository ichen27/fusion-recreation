"""Runtime provenance and file/platform verification fail before launching code."""

import hashlib
import json
from pathlib import Path
import platform
import tempfile
import unittest
from unittest.mock import patch
from runtime_launcher import verify, mcp_environment


class RuntimeLauncher(unittest.TestCase):
    def fixture(self, root):
        files = {}
        for name in [
            "cad.py",
            "tools/ai-cad/store.py",
            "tools/ai-cad/viewer.py",
            "tools/ai-cad/mcp_server.py",
            "crates/model-engine/target/release/model-engine",
            "samples/materials.cad.json",
        ]:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")
            files[name] = dict(
                bytes=7, sha256=hashlib.sha256(b"fixture").hexdigest(), executable=False
            )
        return dict(
            format_version=1,
            platform=dict(system=platform.system(), machine=platform.machine()),
            source_commit="a" * 40,
            source_dirty=False,
            files=files,
        )

    def test_missing_modified_and_wrong_platform_reject(self):
        with (
            tempfile.TemporaryDirectory() as d,
            patch("runtime_launcher.sys.version_info", (3, 14, 0)),
        ):
            root = Path(d)
            manifest = self.fixture(root)

            def save():
                (root / "manifest.json").write_text(json.dumps(manifest))

            save()
            self.assertEqual(verify(root), manifest)
            (root / "cad.py").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "integrity mismatch"):
                verify(root)
            (root / "cad.py").write_bytes(b"fixture")
            manifest["platform"]["machine"] = "unsupported"
            save()
            with self.assertRaisesRegex(ValueError, "architecture"):
                verify(root)
            manifest["platform"]["machine"] = platform.machine()
            save()
            (root / "cad.py").unlink()
            with self.assertRaisesRegex(ValueError, "Missing or unsafe"):
                verify(root)

    def test_path_escape_and_missing_provenance_reject(self):
        with (
            tempfile.TemporaryDirectory() as d,
            patch("runtime_launcher.sys.version_info", (3, 14, 0)),
        ):
            root = Path(d)
            manifest = self.fixture(root)
            manifest["files"]["../outside"] = manifest["files"]["cad.py"]
            (root / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "unsafe"):
                verify(root)
            del manifest["files"]["../outside"]
            manifest["source_commit"] = "unknown"
            (root / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "provenance"):
                verify(root)
            manifest["source_commit"] = "a" * 40
            manifest["files"] = {}
            (root / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "required files"):
                verify(root)

    def test_optional_mcp_requires_the_pinned_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requirements.lock").write_text("mcp==2.3.0\npydantic==2.14.1\n")
            with patch(
                "runtime_launcher.importlib.metadata.version",
                side_effect=["1.26.0", "2.14.1"],
            ):
                result = mcp_environment(root)
                self.assertFalse(result["ready"])
                self.assertEqual(result["mismatched_packages"], ["mcp"])
            with patch(
                "runtime_launcher.importlib.metadata.version",
                side_effect=["2.3.0", "2.14.1"],
            ):
                self.assertTrue(mcp_environment(root)["ready"])
