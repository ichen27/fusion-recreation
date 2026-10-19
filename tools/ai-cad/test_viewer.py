"""The loopback HTTP adapter must preserve the same document contract."""

import http.client
import io
import zipfile
from http.server import HTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from store import Store
from test_contract import CREATE
from viewer import handler


class Viewer(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.directory.name) / "model.json")
        self.server = HTTPServer(("127.0.0.1", 0), handler(self.store, 0))
        self.port = self.server.server_port
        self.server.RequestHandlerClass = handler(self.store, self.port)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.directory.cleanup()

    def request(self, method, path, data=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path, body=data, headers=headers or {})
            reply = connection.getresponse()
            return reply.status, reply.read()
        finally:
            connection.close()

    def test_render_and_edit_share_store(self):
        status, html = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"viewport", html)
        for asset in (
            "/display-data.mjs",
            "/stock-model.mjs",
            "/stock-editor.mjs",
            "/plane-model.mjs",
            "/plane-editor.mjs",
            "/sketch-model.mjs",
            "/sketch-editor.mjs",
            "/hole-model.mjs",
            "/hole-editor.mjs",
        ):
            status, source = self.request("GET", asset)
            self.assertEqual(status, 200)
            self.assertIn(b"export function", source)
        status, raw = self.request(
            "POST",
            "/api/command",
            json.dumps(CREATE),
            {"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["result"]["revision"], 1)
        status, raw = self.request("GET", "/api/model")
        self.assertEqual(json.loads(raw)["result"]["bodies"][0]["volume_mm3"], "71400")
        self.assertEqual(self.store.execute({"action": "inspect"})["revision"], 1)

    def test_analytic_display_and_revision_bound_download(self):
        from test_holes import EXAMPLE, read_stl, audit_triangles

        self.store.execute(json.loads((EXAMPLE / "create.json").read_text()))
        status, raw = self.request("GET", "/api/model")
        self.assertEqual(status, 200)
        self.assertIn("display_mesh", json.loads(raw)["result"]["bodies"][0])
        status, raw = self.request(
            "GET", "/api/export.stl?revision=1&body=bracket&segments=128"
        )
        self.assertEqual(status, 200)
        self.assertGreater(audit_triangles(read_stl(raw), 3), 35000)
        for query in (
            "revision=0&body=bracket&segments=128",
            "revision=1&body=bracket&segments=999",
            "revision=1&body=plate&segments=128",
            "revision=1&body=bracket&segments=128&body=plate",
        ):
            self.assertEqual(self.request("GET", "/api/export.stl?" + query)[0], 400)
        self.assertEqual(
            self.request(
                "GET",
                "/api/export.stl?revision=1&body=bracket&segments=128",
                headers={"Origin": "https://example.com"},
            )[0],
            403,
        )
        self.assertEqual(self.store.execute({"action": "inspect"})["revision"], 1)

    def test_reject_cross_origin_wrong_host_and_path(self):
        for headers in [
            {"Origin": "https://example.com", "Content-Type": "application/json"},
            {"Host": "example.com", "Content-Type": "application/json"},
            {"Content-Type": "text/plain"},
        ]:
            self.assertEqual(
                self.request("POST", "/api/command", json.dumps(CREATE), headers)[0],
                403,
            )
        self.assertEqual(self.request("GET", "/../store.py")[0], 404)
        self.assertEqual(
            self.request(
                "POST", "/api/command", "{", {"Content-Type": "application/json"}
            )[0],
            400,
        )
        self.assertEqual(self.store.execute({"action": "inspect"})["revision"], 0)

    def test_revision_bound_archive_endpoint(self):
        self.store.execute(CREATE)
        status, data = self.request("GET", "/api/export.zip?revision=1&segments=64")
        self.assertEqual(status, 200)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["revision"], 1)
            self.assertEqual(len(manifest["bodies"]), 1)
            self.assertTrue(
                archive.read(manifest["bodies"][0]["file"]).startswith(b"solid cad_mm")
            )
        for query in [
            "revision=0&segments=64",
            "revision=1&segments=64&body=anything",
            "revision=1&revision=1&segments=64",
        ]:
            self.assertEqual(self.request("GET", "/api/export.zip?" + query)[0], 400)


if __name__ == "__main__":
    unittest.main()
