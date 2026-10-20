#!/usr/bin/env python3
"""Loopback-only CAD viewer. Forward this port over SSH for a remote browser."""

import argparse
from http.server import BaseHTTPRequestHandler
from viewer_server import ViewerServer
import threading
import json
from pathlib import Path
from store import MAX_BYTES, CadError, Store, dispatch
from selection import dispatch_selection
from intent import dispatch_explain
from measurements import dispatch_measure
from topology import dispatch_topology
from edge_measurements import dispatch_edge_measure
from interference import dispatch_interference
from clearance import dispatch_clearance
from exports import display, export_stl, export_stl_archive
from result_cache import ResultCache
from preview_jobs import PreviewJobs
from urllib.parse import urlsplit, parse_qs


def handler(store, port):
    meshes = ResultCache(max_entries=32, max_bytes=16 * 1024 * 1024)
    jobs = PreviewJobs(store)
    requests = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        preview_jobs = jobs

        def reply(self, status, data, content_type="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(data)

        def allowed(self):
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            origin = self.headers.get("Origin")
            return self.headers.get("Host") in hosts and (
                origin is None or origin in {"http://" + h for h in hosts}
            )

        def do_GET(self):
            # Parsing is concurrent; preserve the existing single-request model,
            # cache and export semantics after a complete HTTP header arrives.
            with requests:
                self.get()

        def get(self):
            if not self.allowed():
                return self.reply(403, b"{}")
            if urlsplit(self.path).path == "/api/preview-jobs":
                try:
                    query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
                    if set(query) != {"id"} or len(query["id"]) != 1:
                        raise CadError("invalid_command", "Expected one job ID")
                    return self.reply(
                        200, json.dumps({"result": jobs.get(query["id"][0])}).encode()
                    )
                except (CadError, ValueError) as exc:
                    return self.reply(
                        400,
                        json.dumps(
                            {
                                "error": exc.detail
                                if isinstance(exc, CadError)
                                else {"message": str(exc)}
                            }
                        ).encode(),
                    )
            if self.path == "/api/context":
                reply = dispatch_selection(store, {"action": "context"})
                return self.reply(
                    400 if "error" in reply else 200, json.dumps(reply).encode()
                )
            if self.path == "/api/model":
                return self.reply(
                    200,
                    json.dumps(
                        display(dispatch(store, {"action": "inspect"}), meshes)
                    ).encode(),
                )
            if urlsplit(self.path).path == "/api/export.cad":
                try:
                    query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
                    if set(query) != {"revision"} or len(query["revision"]) != 1:
                        raise ValueError("Expected one revision")
                    return self.reply(
                        200,
                        store.native_snapshot(int(query["revision"][0])),
                        "application/json",
                    )
                except (CadError, ValueError) as exc:
                    return self.reply(
                        400,
                        json.dumps(
                            {
                                "error": exc.detail
                                if isinstance(exc, CadError)
                                else {"message": str(exc)}
                            }
                        ).encode(),
                    )
            if urlsplit(self.path).path in ("/api/export.stl", "/api/export.zip"):
                bundled = urlsplit(self.path).path.endswith(".zip")
                try:
                    query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
                    expected = (
                        {"revision", "segments"}
                        if bundled
                        else {"revision", "body", "segments"}
                    )
                    if set(query) != expected or any(
                        len(v) != 1 for v in query.values()
                    ):
                        raise ValueError("Expected " + ", ".join(sorted(expected)))
                    if bundled:
                        data, _ = export_stl_archive(
                            store, int(query["revision"][0]), int(query["segments"][0])
                        )
                        return self.reply(200, data, "application/zip")
                    data, _ = export_stl(
                        store,
                        int(query["revision"][0]),
                        query["body"][0],
                        int(query["segments"][0]),
                    )
                    return self.reply(200, data, "model/stl")
                except (CadError, ValueError) as exc:
                    return self.reply(
                        400,
                        json.dumps(
                            {
                                "error": exc.detail
                                if isinstance(exc, CadError)
                                else {"message": str(exc)}
                            }
                        ).encode(),
                    )
            files = {
                "/": ("index.html", "text/html; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript"),
                "/startup.js": ("startup.js", "text/javascript"),
                "/preview-client.mjs": ("preview-client.mjs", "text/javascript"),
                "/boolean-model.mjs": ("boolean-model.mjs", "text/javascript"),
                "/boolean-editor.mjs": ("boolean-editor.mjs", "text/javascript"),
                "/intersection-model.mjs": (
                    "intersection-model.mjs",
                    "text/javascript",
                ),
                "/intersection-editor.mjs": (
                    "intersection-editor.mjs",
                    "text/javascript",
                ),
                "/stock-model.mjs": ("stock-model.mjs", "text/javascript"),
                "/loft-model.mjs": ("loft-model.mjs", "text/javascript"),
                "/loft-editor.mjs": ("loft-editor.mjs", "text/javascript"),
                "/stock-editor.mjs": ("stock-editor.mjs", "text/javascript"),
                "/pattern-model.mjs": ("pattern-model.mjs", "text/javascript"),
                "/pattern-editor.mjs": ("pattern-editor.mjs", "text/javascript"),
                "/shell-model.mjs": ("shell-model.mjs", "text/javascript"),
                "/shell-editor.mjs": ("shell-editor.mjs", "text/javascript"),
                "/plane-model.mjs": ("plane-model.mjs", "text/javascript"),
                "/plane-editor.mjs": ("plane-editor.mjs", "text/javascript"),
                "/rotation-model.mjs": ("rotation-model.mjs", "text/javascript"),
                "/rotation-editor.mjs": ("rotation-editor.mjs", "text/javascript"),
                "/vector-parameters.mjs": ("vector-parameters.mjs", "text/javascript"),
                "/translate-model.mjs": ("translate-model.mjs", "text/javascript"),
                "/translate-editor.mjs": ("translate-editor.mjs", "text/javascript"),
                "/picking.mjs": ("picking.mjs", "text/javascript"),
                "/edge-display.mjs": ("edge-display.mjs", "text/javascript"),
                "/topology-view.mjs": ("topology-view.mjs", "text/javascript"),
                "/display-data.mjs": ("display-data.mjs", "text/javascript"),
                "/sketch-editor.mjs": ("sketch-editor.mjs", "text/javascript"),
                "/sketch-model.mjs": ("sketch-model.mjs", "text/javascript"),
                "/hole-model.mjs": ("hole-model.mjs", "text/javascript"),
                "/hole-editor.mjs": ("hole-editor.mjs", "text/javascript"),
                "/style.css": ("style.css", "text/css"),
            }
            if self.path not in files:
                return self.reply(404, b"{}")
            name, kind = files[self.path]
            self.reply(200, (Path(__file__).parent / "web" / name).read_bytes(), kind)

        def do_POST(self):
            with requests:
                self.post()

        def post(self):
            if (
                not self.allowed()
                or self.headers.get("Content-Type") != "application/json"
            ):
                return self.reply(403, b"{}")
            if self.path not in (
                "/api/command",
                "/api/selection",
                "/api/explain",
                "/api/measure",
                "/api/topology",
                "/api/measure-edge",
                "/api/interference",
                "/api/clearance",
                "/api/preview-jobs",
            ):
                return self.reply(404, b"{}")
            try:
                length = int(self.headers.get("Content-Length", "0"))
                limit = (
                    MAX_BYTES + 1024
                    if self.path == "/api/command"
                    else 262144
                    if self.path == "/api/preview-jobs"
                    else 4096
                )
                if not 0 < length <= limit:
                    return self.reply(413, b"{}")
                self.connection.settimeout(5)
                command = json.loads(self.rfile.read(length))
                if self.path == "/api/preview-jobs":
                    try:
                        if (
                            isinstance(command, dict)
                            and set(command) == {"action", "job_id"}
                            and command["action"] == "cancel"
                        ):
                            result = jobs.cancel(command["job_id"])
                        else:
                            result = jobs.start(command)
                        return self.reply(200, json.dumps({"result": result}).encode())
                    except (CadError, OSError, ValueError, TypeError) as exc:
                        error = (
                            exc.detail
                            if isinstance(exc, CadError)
                            else {"code": "preview_failed", "message": str(exc)}
                        )
                        return self.reply(400, json.dumps({"error": error}).encode())
                reply = (
                    dispatch_clearance(store, command)
                    if self.path == "/api/clearance"
                    else dispatch_interference(store, command)
                    if self.path == "/api/interference"
                    else dispatch_edge_measure(store, command)
                    if self.path == "/api/measure-edge"
                    else dispatch_topology(store, command)
                    if self.path == "/api/topology"
                    else dispatch_measure(store, command)
                    if self.path == "/api/measure"
                    else dispatch_explain(store, command)
                    if self.path == "/api/explain"
                    else dispatch_selection(store, command)
                    if self.path == "/api/selection"
                    else display(dispatch(store, command), meshes)
                )
                self.reply(400 if "error" in reply else 200, json.dumps(reply).encode())
            except (ValueError, TimeoutError):
                self.reply(400, b'{"error":{"message":"Invalid JSON request"}}')

    return Handler


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ViewerServer(
        ("127.0.0.1", args.port), handler(Store(args.store), args.port)
    )
    print(f"CAD viewer: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.RequestHandlerClass.preview_jobs.close()
