"""Persistent native calls preserve replies, bounded failure and process isolation."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from engine_transport import NativeWorker, MAX_REQUEST, MAX_RESPONSE
from store import BINARY, encode
from test_planar_loft import loft
from test_individual_depths import individual


class EngineTransport(unittest.TestCase):
    def setUp(self):
        self.worker = NativeWorker()
        self.addCleanup(self.worker.close)

    def payload(self, mode=None, model=None):
        model = model or loft()
        return encode(
            dict(schema_version=1, model=model, operations=[], preserve=[])
            if mode is None
            else dict(
                model=model,
                feature_id="part",
                **(
                    dict(segments=32, include_surfaces=True)
                    if mode == "--mesh"
                    else dict(edge_index=0)
                    if mode == "--edge"
                    else {}
                ),
            )
        )

    def test_all_modes_match_cli_and_errors_do_not_poison_next_request(self):
        for model in (loft(), individual()):
            for mode in (
                None,
                "--mesh",
                "--explain",
                "--measure",
                "--topology",
                "--edge",
            ):
                data = self.payload(mode, model)
                fresh = subprocess.run(
                    [str(BINARY)] + ([mode] if mode else []),
                    input=data,
                    capture_output=True,
                    check=True,
                )
                result = self.worker.run(BINARY, mode, data)
                self.assertEqual(json.loads(result.stdout), json.loads(fresh.stdout))
        for data in (b"{", b"\xff"):
            self.assertEqual(self.worker.run(BINARY, None, data).returncode, 1)
        self.assertEqual(self.worker.run(BINARY, None, self.payload()).returncode, 0)
        self.assertEqual(self.worker.starts, 1)
        self.assertEqual(self.worker.requests, 15)

    def test_threads_serialize_distinct_requests_and_killed_worker_restarts(self):
        requests = [self.payload(model=loft(height=str(i + 1))) for i in range(12)]
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(
                pool.map(lambda data: self.worker.run(BINARY, None, data), requests)
            )
        for i, result in enumerate(results):
            self.assertEqual(
                json.loads(result.stdout)["result"]["model"]["parameters"]["height"],
                str(i + 1),
            )
        self.assertEqual(self.worker.starts, 1)
        self.worker.process.kill()
        self.worker.process.wait()
        self.worker.run(BINARY, None, self.payload())
        self.assertEqual(self.worker.starts, 2)

    def fake(self, directory, code):
        path = Path(directory) / "fake-engine"
        path.write_text(f"#!{sys.executable}\n" + code)
        path.chmod(0o755)
        return path

    def test_deadlines_eof_invalid_and_oversized_replies_close_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            for code, exception in [
                ("import time; time.sleep(30)\n", subprocess.TimeoutExpired),
                ("pass\n", ValueError),
                ("import os; os.write(1,b'\\x00\\x00\\x00\\x01x')\n", ValueError),
                (
                    f"import os,struct; os.write(1,struct.pack('>I',{MAX_RESPONSE + 1}))\n",
                    ValueError,
                ),
            ]:
                path = self.fake(directory, code)
                start = time.monotonic()
                with self.assertRaises(exception):
                    self.worker.run(path, None, self.payload(), timeout=0.2)
                self.assertLess(time.monotonic() - start, 2)
                self.assertIsNone(self.worker.process)
            # Request-side backpressure is also bounded, including an engine that never reads.
            path = self.fake(directory, "import time; time.sleep(30)\n")
            with self.assertRaises(subprocess.TimeoutExpired):
                self.worker.run(path, None, b" " * MAX_REQUEST, timeout=0.2)
            self.assertIsNone(self.worker.process)
        self.assertEqual(self.worker.run(BINARY, None, self.payload()).returncode, 0)

    def test_queue_deadline_and_request_limit_do_not_kill_active_worker(self):
        self.worker.run(BINARY, None, self.payload())
        process = self.worker.process
        self.worker.lock.acquire()
        try:
            with self.assertRaises(subprocess.TimeoutExpired):
                self.worker.run(BINARY, None, self.payload(), timeout=0.01)
        finally:
            self.worker.lock.release()
        self.assertIs(self.worker.process, process)
        with self.assertRaises(ValueError):
            self.worker.run(BINARY, None, b" " * (MAX_REQUEST + 1))
        self.assertIs(self.worker.process, process)

    def test_binary_replacement_invalidates_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "engine"
            shutil.copy2(BINARY, binary)
            self.worker.run(binary, None, self.payload())
            first = self.worker.process
            replacement = Path(directory) / "replacement"
            shutil.copy2(BINARY, replacement)
            os.replace(replacement, binary)
            self.worker.run(binary, None, self.payload())
            self.assertIsNot(self.worker.process, first)
            self.assertIsNotNone(first.poll())
            self.assertEqual(self.worker.starts, 2)

    def test_native_protocol_rejects_oversize_and_truncated_frames(self):
        for frame in (
            b"\x00" + struct.pack(">I", MAX_REQUEST + 1),
            b"\x00\x00",
            b"\x00" + struct.pack(">I", 10) + b"{}",
        ):
            result = subprocess.run(
                [str(BINARY), "--worker"], input=frame, capture_output=True, timeout=2
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"")
        result = subprocess.run(
            [str(BINARY), "--worker"],
            input=b"\xff" + struct.pack(">I", 2) + b"{}",
            capture_output=True,
            check=True,
        )
        self.assertEqual(
            json.loads(result.stdout[4:])["error"]["code"], "invalid_request"
        )

    @unittest.skipUnless(hasattr(os, "fork"), "POSIX host")
    def test_fork_does_not_share_or_kill_parent_worker(self):
        self.worker.run(BINARY, None, self.payload())
        parent = self.worker.process
        pid = os.fork()
        if pid == 0:
            try:
                result = self.worker.run(BINARY, None, self.payload())
                self.worker.close()
                os._exit(result.returncode)
            except BaseException:
                os._exit(1)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(status, 0)
        self.assertIsNone(parent.poll())
        self.assertEqual(self.worker.run(BINARY, None, self.payload()).returncode, 0)
