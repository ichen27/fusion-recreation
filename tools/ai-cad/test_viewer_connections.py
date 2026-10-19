"""Real sockets reproduce browser preconnection starvation and bounded recovery."""

import http.client
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from store import Store
from viewer import handler
from viewer_server import ViewerServer
from test_contract import CREATE


class Connections(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.directory.name) / "part.json")

        class SmallServer(ViewerServer):
            max_connections = 4

        self.server = SmallServer(("127.0.0.1", 0), handler(self.store, 0))
        self.port = self.server.server_port
        self.server.RequestHandlerClass = handler(self.store, self.port)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.sockets = []

    def tearDown(self):
        for s in self.sockets:
            s.close()
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.server.RequestHandlerClass.preview_jobs.close()
        self.directory.cleanup()

    def request(self, path="/stock-model.mjs", command=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=1)
        try:
            c.request(
                "GET" if command is None else "POST",
                path,
                body=None if command is None else json.dumps(command),
                headers={} if command is None else {"Content-Type": "application/json"},
            )
            reply = c.getresponse()
            return reply.status, reply.read()
        finally:
            c.close()

    def test_idle_preconnection_and_partial_header_do_not_starve_modules(self):
        for payload in (b"", b"GET / HTTP/1.1\r\nHost:"):
            s = socket.create_connection(("127.0.0.1", self.port))
            self.sockets.append(s)
            if payload:
                s.sendall(payload)
            time.sleep(0.03)
            status, data = self.request()
            self.assertEqual(status, 200)
            self.assertIn(b"stockProposal", data)
        self.assertEqual(self.request("/api/model")[0], 200)

    def test_connection_budget_recovers_after_idle_timeout(self):
        self.server.socket_timeout = 0.3
        for _ in range(self.server.max_connections):
            self.sockets.append(socket.create_connection(("127.0.0.1", self.port)))
            time.sleep(0.02)
        self.assertEqual(self.request()[0], 503)
        time.sleep(0.35)
        self.assertEqual(self.request()[0], 200)
        self.assertEqual(self.store.load()["revision"], 0)

    def test_simultaneous_commits_keep_revision_conflict_and_receipt_semantics(self):
        barrier = threading.Barrier(3)
        results = []

        def save(name):
            barrier.wait()
            results.append(
                self.request("/api/command", {**CREATE, "transaction_id": name})
            )

        threads = [
            threading.Thread(target=save, args=(name,)) for name in ("left", "right")
        ]
        for t in threads:
            t.start()
        barrier.wait()
        for t in threads:
            t.join()
        self.assertEqual(sorted(status for status, _ in results), [200, 400])
        failure = next(json.loads(data) for status, data in results if status == 400)
        self.assertEqual(failure["error"]["code"], "revision_conflict")
        self.assertEqual(self.store.load()["revision"], 1)


if __name__ == "__main__":
    unittest.main()
