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
        self.server.RequestHandlerClass.preview_jobs.close()
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

    def test_revision_bound_selection_shared_with_separate_client(self):
        from selection import Selection

        result = self.store.execute(CREATE)
        feature = result["bodies"][0]["feature_id"]
        before = self.store.path.read_bytes()
        status, payload = self.request(
            "POST",
            "/api/selection",
            json.dumps(
                {"action": "select", "expected_revision": 1, "feature_id": feature}
            ),
            {"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        selected = json.loads(payload)["result"]
        self.assertEqual(
            selected, Selection(Store(self.store.path)).execute({"action": "context"})
        )
        status, payload = self.request("GET", "/api/context")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload)["result"], selected)
        status, _ = self.request(
            "POST", "/api/selection", "x" * 4097, {"Content-Type": "application/json"}
        )
        self.assertEqual(status, 413)
        status, _ = self.request(
            "GET", "/api/context", headers={"Origin": "https://example.com"}
        )
        self.assertEqual(status, 403)
        status, _ = self.request(
            "POST",
            "/api/selection",
            json.dumps(
                {"action": "select", "expected_revision": 0, "feature_id": feature}
            ),
            {"Content-Type": "application/json"},
        )
        self.assertEqual(status, 400)
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_explanation_http_is_read_only_and_revision_bound(self):
        result = self.store.execute(CREATE)
        before = self.store.path.read_bytes()
        feature = result["bodies"][0]["feature_id"]
        for revision, expected_status in [(1, 200), (0, 400)]:
            status, payload = self.request(
                "POST",
                "/api/explain",
                json.dumps({"expected_revision": revision, "feature_id": feature}),
                {"Content-Type": "application/json"},
            )
            self.assertEqual(status, expected_status)
            if status == 200:
                info = json.loads(payload)["result"]
                self.assertEqual(
                    info["parameters"]["width"]["affected_bodies"], [feature]
                )
                self.assertFalse(info["parameters"]["thickness"]["directly_editable"])
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_measurement_http_is_read_only_and_revision_bound(self):
        result = self.store.execute(CREATE)
        before = self.store.path.read_bytes()
        feature = result["bodies"][0]["feature_id"]
        for revision, expected_status in [(1, 200), (0, 400)]:
            status, payload = self.request(
                "POST",
                "/api/measure",
                json.dumps({"expected_revision": revision, "feature_id": feature}),
                {"Content-Type": "application/json"},
            )
            self.assertEqual(status, expected_status)
            if status == 200:
                self.assertEqual(
                    json.loads(payload)["result"]["volume_mm3"],
                    result["bodies"][0]["volume_mm3"],
                )
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_surface_selection_http_is_shared_with_other_client(self):
        from test_counterbores import counterbored
        from test_intersection import operations
        from selection import Selection

        self.store.execute(
            dict(
                action="commit",
                expected_revision=0,
                transaction_id="seed",
                operations=operations(counterbored()),
                preserve=[],
            )
        )
        before = self.store.path.read_bytes()
        command = dict(
            action="select_surface",
            expected_revision=1,
            feature_id="part",
            surface_id="feature/part/hole/left/shoulder",
        )
        status, payload = self.request(
            "POST",
            "/api/selection",
            json.dumps(command),
            {"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        context = json.loads(payload)["result"]
        self.assertEqual(
            context, Selection(Store(self.store.path)).execute(dict(action="context"))
        )
        self.assertEqual(context["selected_surface"]["support"]["offset"], "4")
        status, payload = self.request("GET", "/api/context")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload)["result"], context)
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_topology_http_revision_origin_and_limits(self):
        result = self.store.execute(CREATE)
        before = self.store.path.read_bytes()
        feature = result["bodies"][0]["feature_id"]
        for revision, expected in [(1, 200), (0, 400)]:
            status, payload = self.request(
                "POST",
                "/api/topology",
                json.dumps(dict(expected_revision=revision, feature_id=feature)),
                {"Content-Type": "application/json"},
            )
            self.assertEqual(status, expected)
            if status == 200:
                self.assertEqual(json.loads(payload)["result"]["shell_euler"], [2])
        self.assertEqual(
            self.request(
                "POST",
                "/api/topology",
                "x" * 4097,
                {"Content-Type": "application/json"},
            )[0],
            413,
        )
        self.assertEqual(
            self.request(
                "POST",
                "/api/topology",
                "{}",
                {"Content-Type": "application/json", "Origin": "https://example.com"},
            )[0],
            403,
        )
        self.assertEqual(self.request("GET", "/topology-view.mjs")[0], 200)
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_preview_job_http_stays_responsive_and_cancel_preserves_model(self):
        from store import CadError
        from test_preview_jobs import until

        self.store.execute(CREATE)
        before = self.store.path.read_bytes()
        entered = threading.Event()

        def runner(snapshot, cancel):
            entered.set()
            if not cancel.wait(3):
                raise AssertionError("Expected cancellation")
            raise CadError("preview_cancelled", "Cancelled")

        jobs = self.server.RequestHandlerClass.preview_jobs
        jobs.runner = runner
        command = {
            "action": "preview",
            "expected_revision": 1,
            "operations": [{"op": "set_parameter", "id": "width", "mm": "120"}],
            "preserve": [],
        }
        status, payload = self.request(
            "POST",
            "/api/preview-jobs",
            json.dumps(command),
            {"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        id = json.loads(payload)["result"]["job_id"]
        self.assertTrue(entered.wait(2))
        status, payload = self.request("GET", "/api/model")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload)["result"]["revision"], 1)
        status, payload = self.request(
            "POST",
            "/api/preview-jobs",
            json.dumps({"action": "cancel", "job_id": id}),
            {"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)

        def finished():
            status, payload = self.request("GET", "/api/preview-jobs?id=" + id)
            self.assertEqual(status, 200)
            result = json.loads(payload)["result"]
            return result if result["status"] == "cancelled" else None

        self.assertEqual(until(finished)["reply"]["error"]["code"], "preview_cancelled")
        self.assertEqual(self.store.path.read_bytes(), before)
        status, _ = self.request(
            "GET",
            "/api/preview-jobs?id=" + id,
            headers={"Origin": "https://example.com"},
        )
        self.assertEqual(status, 403)

    def test_render_and_edit_share_store(self):
        status, html = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"viewport", html)
        for asset in (
            "/display-data.mjs",
            "/preview-client.mjs",
            "/picking.mjs",
            "/rotation-model.mjs",
            "/rotation-editor.mjs",
            "/vector-parameters.mjs",
            "/translate-model.mjs",
            "/translate-editor.mjs",
            "/boolean-model.mjs",
            "/boolean-editor.mjs",
            "/intersection-model.mjs",
            "/intersection-editor.mjs",
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
            self.assertRegex(source, rb"export (async )?function")
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

    def test_native_download_and_import_over_http(self):
        self.store.execute(CREATE)
        before = self.store.path.read_bytes()
        status, native = self.request("GET", "/api/export.cad?revision=1")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(native), json.loads(before))
        for query in [
            "",
            "revision=0",
            "revision=1&revision=1",
            "revision=x",
            "revision=1&body=x",
        ]:
            self.assertEqual(self.request("GET", "/api/export.cad?" + query)[0], 400)
        self.assertEqual(
            self.request(
                "GET",
                "/api/export.cad?revision=1",
                headers={"Origin": "https://example.com"},
            )[0],
            403,
        )
        from test_native_files import envelope

        document = json.loads(native)
        document["state"]["model"]["parameters"]["width"] = "140"
        # A valid historical receipt can make a native file exceed the ordinary command limit.
        document["state"]["receipts"]["historical"] = {
            "request": "a" * 300000,
            "revision": 1,
        }
        document = envelope(document["state"])
        command = {
            "action": "preview_import",
            "expected_revision": 1,
            "document": document,
        }
        headers = {"Content-Type": "application/json"}
        status, raw = self.request("POST", "/api/command", json.dumps(command), headers)
        self.assertEqual(status, 200, raw)
        self.assertTrue(json.loads(raw)["result"]["preview"])
        self.assertEqual(self.store.path.read_bytes(), before)
        command.update(action="import", transaction_id="http-import")
        status, raw = self.request("POST", "/api/command", json.dumps(command), headers)
        self.assertEqual(status, 200, raw)
        self.assertEqual(json.loads(raw)["result"]["revision"], 2)
        self.assertNotIn("historical", self.store.load()["receipts"])
        document["sha256"] = "bad"
        command.update(action="preview_import", expected_revision=2)
        del command["transaction_id"]
        status, raw = self.request("POST", "/api/command", json.dumps(command), headers)
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(raw)["error"]["code"], "invalid_document")
        self.assertEqual(self.store.load()["revision"], 2)


if __name__ == "__main__":
    unittest.main()
