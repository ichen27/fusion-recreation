#!/usr/bin/env python3
"""Loopback-only CAD viewer. Forward this port over SSH for a remote browser."""

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
from store import MAX_BYTES, CadError, Store, dispatch
from exports import display, export_stl, export_stl_archive
from result_cache import ResultCache
from urllib.parse import urlsplit, parse_qs


def handler(store, port):
    meshes = ResultCache(max_entries=32, max_bytes=16 * 1024 * 1024)

    class Handler(BaseHTTPRequestHandler):
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
            if not self.allowed():
                return self.reply(403, b"{}")
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
                "/intersection-model.mjs": (
                    "intersection-model.mjs",
                    "text/javascript",
                ),
                "/intersection-editor.mjs": (
                    "intersection-editor.mjs",
                    "text/javascript",
                ),
                "/stock-model.mjs": ("stock-model.mjs", "text/javascript"),
                "/stock-editor.mjs": ("stock-editor.mjs", "text/javascript"),
                "/plane-model.mjs": ("plane-model.mjs", "text/javascript"),
                "/plane-editor.mjs": ("plane-editor.mjs", "text/javascript"),
                "/translate-model.mjs": ("translate-model.mjs", "text/javascript"),
                "/translate-editor.mjs": ("translate-editor.mjs", "text/javascript"),
                "/picking.mjs": ("picking.mjs", "text/javascript"),
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
            if (
                not self.allowed()
                or self.headers.get("Content-Type") != "application/json"
            ):
                return self.reply(403, b"{}")
            if self.path != "/api/command":
                return self.reply(404, b"{}")
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BYTES + 1024:
                    return self.reply(413, b"{}")
                self.connection.settimeout(5)
                command = json.loads(self.rfile.read(length))
                reply = display(dispatch(store, command), meshes)
                self.reply(400 if "error" in reply else 200, json.dumps(reply).encode())
            except (ValueError, TimeoutError):
                self.reply(400, b'{"error":{"message":"Invalid JSON request"}}')

    return Handler


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = HTTPServer(("127.0.0.1", args.port), handler(Store(args.store), args.port))
    print(f"CAD viewer: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
