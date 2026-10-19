"""Bounded single-worker preview queue with process-group cancellation.

Snapshots are captured under the document lock; worker processes receive no
store path. Polling/cancellation never acquire that lock or evaluate geometry.
"""

from collections import OrderedDict
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import threading
import time
import uuid
from store import CadError, encode
from selection import require_selection


class PreviewJobs:
    def __init__(
        self,
        store,
        *,
        capacity=4,
        history=32,
        result_bytes=8 * 1024 * 1024,
        timeout=30,
        runner=None,
    ):
        self.store = store
        self.capacity, self.history, self.result_limit = capacity, history, result_bytes
        self.timeout = timeout
        self.runner = runner or self._process
        self.lock = threading.Lock()
        self.queue = queue.Queue()
        self.jobs = OrderedDict()
        self.pending, self.bytes = 0, 0
        self.closed = False
        self.thread = None

    def start(self, command):
        if (
            not isinstance(command, dict)
            or set(command)
            not in (
                {"action", "expected_revision", "operations", "preserve"},
                {
                    "action",
                    "expected_revision",
                    "operations",
                    "preserve",
                    "selection_guard",
                },
            )
            or command["action"] != "preview"
            or not isinstance(command["operations"], list)
            or not isinstance(command["preserve"], list)
        ):
            raise CadError(
                "invalid_command", "Preview jobs accept only explicit preview commands"
            )
        if len(encode(command)) > 262144:
            raise CadError("request_limit", "Preview command exceeds 256 KiB")
        with self.lock:
            if self.closed:
                raise CadError("queue_closed", "Preview worker is shutting down")
            if self.pending >= self.capacity:
                raise CadError(
                    "queue_full", "Preview queue is full; cancel or wait for a job"
                )
            with self.store.locked():
                state = self.store.load()
                if (
                    type(command["expected_revision"]) is not int
                    or command["expected_revision"] != state["revision"]
                ):
                    raise CadError(
                        "revision_conflict", "Refresh before starting a preview"
                    )
                if "selection_guard" in command:
                    require_selection(self.store, state, command["selection_guard"])
                snapshot = encode(
                    {
                        "model": state["model"],
                        "operations": command["operations"],
                        "preserve": command["preserve"],
                        "metadata": {
                            "revision": state["revision"],
                            "can_undo": bool(state["undo"]),
                            "can_redo": bool(state["redo"]),
                        },
                    }
                )
            if len(snapshot) > 1_048_576:
                raise CadError("request_limit", "Preview snapshot exceeds 1 MiB")
            id = str(uuid.uuid4())
            self.jobs[id] = {
                "status": "queued",
                "revision": state["revision"],
                "cancel": threading.Event(),
                "pending": True,
                "reply": None,
            }
            self.pending += 1
            self.queue.put((id, snapshot))
            if self.thread is None:
                self.thread = threading.Thread(
                    target=self._work, name="cad-preview", daemon=True
                )
                self.thread.start()
            return self._view(id)

    def _view(self, id):
        if not isinstance(id, str) or id not in self.jobs:
            raise CadError("missing_job", "Preview job expired or does not exist")
        job = self.jobs[id]
        result = {"job_id": id, "status": job["status"], "revision": job["revision"]}
        if job["reply"] is not None:
            result["reply"] = json.loads(job["reply"])
        return result

    def get(self, id):
        with self.lock:
            return self._view(id)

    def cancel(self, id):
        with self.lock:
            self._view(id)
            job = self.jobs[id]
            if job["pending"]:
                job["cancel"].set()
                job["status"] = "cancelling"
            return self._view(id)

    def _trim(self):
        while len(self.jobs) > self.history or self.bytes > self.result_limit:
            victim = next(
                (id for id, job in self.jobs.items() if not job["pending"]), None
            )
            if victim is None:
                break
            job = self.jobs.pop(victim)
            self.bytes -= len(job["reply"] or b"")

    def _work(self):
        while True:
            try:
                id, snapshot = self.queue.get(timeout=0.1)
            except queue.Empty:
                with self.lock:
                    if self.closed:
                        return
                continue
            with self.lock:
                job = self.jobs[id]
                cancel = job["cancel"]
                if not cancel.is_set():
                    job["status"] = "running"
            try:
                if cancel.is_set():
                    raise CadError("preview_cancelled", "Preview cancelled")
                reply = self.runner(snapshot, cancel)
            except CadError as exc:
                reply = {"error": exc.detail}
            except Exception as exc:
                reply = {
                    "error": {
                        "code": "preview_failed",
                        "entity": "preview",
                        "message": str(exc),
                    }
                }
            try:
                data = encode(reply)
            except (ValueError, TypeError):
                data = encode(
                    {
                        "error": {
                            "code": "preview_failed",
                            "entity": "preview",
                            "message": "Preview returned invalid JSON data",
                        }
                    }
                )
            with self.lock:
                if cancel.is_set():
                    data = encode(
                        {
                            "error": {
                                "code": "preview_cancelled",
                                "entity": "preview",
                                "message": "Preview cancelled; saved model is unchanged",
                            }
                        }
                    )
                if len(data) > self.result_limit:
                    data = encode(
                        {
                            "error": {
                                "code": "preview_limit",
                                "entity": "preview",
                                "message": "Preview result exceeds the retained memory limit",
                            }
                        }
                    )
                job["reply"] = data
                job["status"] = (
                    "cancelled"
                    if cancel.is_set()
                    else "failed"
                    if "error" in json.loads(data)
                    else "succeeded"
                )
                job["pending"] = False
                self.pending -= 1
                self.bytes += len(data)
                self._trim()
            self.queue.task_done()

    def _process(self, snapshot, cancel):
        command = [sys.executable, str(Path(__file__).with_name("preview_worker.py"))]
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        start = time.monotonic()
        first = True
        try:
            while True:
                if cancel.is_set():
                    raise CadError("preview_cancelled", "Preview cancelled")
                if time.monotonic() - start > self.timeout:
                    raise CadError(
                        "preview_timeout", "Preview exceeded its total time budget"
                    )
                try:
                    output, _ = process.communicate(
                        input=snapshot if first else None, timeout=0.05
                    )
                    break
                except subprocess.TimeoutExpired:
                    first = False
            if process.returncode:
                raise CadError(
                    "preview_failed", "Preview process exited unsuccessfully"
                )
            reply = json.loads(output)
            if not isinstance(reply, dict) or set(reply) not in ({"result"}, {"error"}):
                raise CadError(
                    "preview_failed", "Preview process returned an invalid reply"
                )
            return reply
        finally:
            # A cancelled worker may have a live Rust evaluator/tessellator child.
            # Kill the entire isolated group and reap the worker before freeing a slot.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()

    def close(self):
        with self.lock:
            self.closed = True
            for job in self.jobs.values():
                if job["pending"]:
                    job["cancel"].set()
        if self.thread is not None:
            self.thread.join(timeout=2)
