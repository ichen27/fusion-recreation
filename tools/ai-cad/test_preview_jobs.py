"""Preview work stays bounded, cancellable and isolated from document writes."""

import os
import io
import json
from types import SimpleNamespace
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from exports import display
from preview_jobs import PreviewJobs
from store import Store, CadError
from test_contract import CREATE


def until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for preview state")


class PreviewQueue(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "model.json")
        self.store.execute(CREATE)
        self.command = {
            "action": "preview",
            "expected_revision": 1,
            "operations": [{"op": "set_parameter", "id": "width", "mm": "120"}],
            "preserve": [],
        }

    def queue(self, **kwargs):
        jobs = PreviewJobs(self.store, **kwargs)
        self.addCleanup(jobs.close)
        return jobs

    def done(self, jobs, id):
        return until(
            lambda: (
                value
                if (value := jobs.get(id))["status"]
                in ("succeeded", "failed", "cancelled")
                else None
            )
        )

    def test_real_worker_matches_sync_preview_without_writing_document(self):
        jobs = self.queue()
        before = self.store.path.read_bytes()
        id = jobs.start(self.command)["job_id"]
        result = self.done(jobs, id)
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(
            result["reply"], display({"result": self.store.execute(self.command)})
        )
        result["reply"]["result"]["model"]["parameters"]["width"] = "bad"
        self.assertEqual(
            jobs.get(id)["reply"]["result"]["model"]["parameters"]["width"], "120"
        )
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_bounded_queue_cancellation_and_nonblocking_model_edits(self):
        entered, release = threading.Event(), threading.Event()

        def runner(snapshot, cancel):
            entered.set()
            while not release.wait(0.01):
                if cancel.is_set():
                    raise CadError("preview_cancelled", "cancelled")
            return jobs._process(snapshot, cancel)

        jobs = self.queue(runner=runner)
        first = jobs.start(self.command)["job_id"]
        self.assertTrue(entered.wait(2))
        queued = [jobs.start(self.command)["job_id"] for _ in range(3)]
        with self.assertRaises(CadError) as caught:
            jobs.start(self.command)
        self.assertEqual(caught.exception.detail["code"], "queue_full")
        # Model commit is possible while the worker holds a snapshot, not the lock.
        changed = self.store.execute(
            {**self.command, "action": "commit", "transaction_id": "other"}
        )
        self.assertEqual(changed["revision"], 2)
        before = self.store.path.read_bytes()
        jobs.cancel(queued[0])
        jobs.cancel(first)
        self.assertEqual(self.done(jobs, first)["status"], "cancelled")
        self.assertEqual(self.done(jobs, queued[0])["status"], "cancelled")
        release.set()
        result = self.done(jobs, queued[-1])
        self.assertEqual(result["revision"], 1)
        self.assertEqual(result["status"], "succeeded")
        with self.assertRaises(CadError) as caught:
            self.store.execute(
                {**self.command, "action": "commit", "transaction_id": "stale"}
            )
        self.assertEqual(caught.exception.detail["code"], "revision_conflict")
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_errors_limits_expiry_and_shutdown(self):
        jobs = self.queue(
            history=2,
            result_bytes=1024,
            runner=lambda request, cancel: {"result": {"payload": "x" * 2000}},
        )
        ids = []
        for _ in range(3):
            id = jobs.start(self.command)["job_id"]
            ids.append(id)
            result = self.done(jobs, id)
            self.assertEqual(result["reply"]["error"]["code"], "preview_limit")
        self.assertLessEqual(jobs.bytes, 1024)
        with self.assertRaises(CadError):
            jobs.get(ids[0])
        for command in [
            {**self.command, "action": "commit"},
            {**self.command, "expected_revision": 0},
            {**self.command, "expected_revision": True},
            [],
        ]:
            with self.assertRaises(CadError):
                jobs.start(command)
        jobs.close()
        with self.assertRaises(CadError) as caught:
            jobs.start(self.command)
        self.assertEqual(caught.exception.detail["code"], "queue_closed")
        self.assertFalse(jobs.thread.is_alive())

    def test_process_group_cancel_kills_worker_and_child(self):
        jobs = self.queue()
        pidfile = Path(self.temp.name) / "child.pid"
        script = Path(self.temp.name) / "slow.py"
        script.write_text(
            "import subprocess,sys,time\nfrom pathlib import Path\np=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])\nPath("
            + repr(str(pidfile))
            + ").write_text(str(p.pid))\ntime.sleep(60)\n"
        )
        original = subprocess.Popen
        cancel = threading.Event()
        errors = []

        def run():
            try:
                jobs._process(b"{}", cancel)
            except CadError as exc:
                errors.append(exc.detail["code"])

        with patch(
            "preview_jobs.subprocess.Popen",
            side_effect=lambda command, **kwargs: original(
                [sys.executable, str(script)], **kwargs
            ),
        ):
            thread = threading.Thread(target=run)
            thread.start()
            until(pidfile.exists)
            child = int(pidfile.read_text())
            cancel.set()
            thread.join(2)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, ["preview_cancelled"])

        def gone():
            try:
                os.kill(child, 0)
            except ProcessLookupError:
                return True
            status = subprocess.run(
                ["ps", "-o", "stat=", "-p", str(child)], capture_output=True, text=True
            ).stdout.strip()
            return not status or status.startswith("Z")

        until(gone)

    def test_worker_enforces_own_deadline_and_reaps_calculation_child(self):
        # The worker deadline remains effective if its scheduling host disappears.
        import preview_worker
        from store import encode

        pidfile = Path(self.temp.name) / "deadline.pid"
        child = (
            "import os,time; from pathlib import Path; Path("
            + repr(str(pidfile))
            + ").write_text(str(os.getpid())); time.sleep(60)"
        )

        def calculation(*args):
            subprocess.run([sys.executable, "-c", child], check=True)

        output = io.BytesIO()
        request = encode(
            {"model": {}, "operations": [], "preserve": [], "metadata": {}}
        )
        with (
            patch("preview_worker.evaluate", side_effect=calculation),
            patch(
                "preview_worker.sys.stdin", SimpleNamespace(buffer=io.BytesIO(request))
            ),
            patch("preview_worker.sys.stdout", SimpleNamespace(buffer=output)),
        ):
            preview_worker.main(timeout=0.5)
        self.assertEqual(
            json.loads(output.getvalue())["error"]["code"], "preview_timeout"
        )
        self.assertTrue(pidfile.exists())
        with self.assertRaises(ProcessLookupError):
            os.kill(int(pidfile.read_text()), 0)

    def test_total_timeout_and_failed_geometry_do_not_change_native_file(self):
        before = self.store.path.read_bytes()
        jobs = self.queue(timeout=0)
        result = self.done(jobs, jobs.start(self.command)["job_id"])
        self.assertEqual(result["reply"]["error"]["code"], "preview_timeout")
        normal = self.queue()
        bad = {
            **self.command,
            "operations": [{"op": "set_parameter", "id": "width", "mm": "-1"}],
        }
        result = self.done(normal, normal.start(bad)["job_id"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.store.path.read_bytes(), before)
