"""One bounded, serial native worker per host process; no geometry state is cached.

Frames: request mode byte + big-endian u32 byte count + JSON; reply u32 + JSON.
A deadline covers lock acquisition and all pipe I/O. Failed calls are never retried.
"""

import atexit
import json
import os
from pathlib import Path
import select
import struct
import subprocess
import threading
import time

MAX_REQUEST = 1_048_576
MAX_RESPONSE = 16 * MAX_REQUEST
MODES = {
    None: 0,
    "--mesh": 1,
    "--explain": 2,
    "--measure": 3,
    "--topology": 4,
    "--edge": 5,
    "--interference": 6,
    "--clearance": 7,
}


class NativeWorker:
    def __init__(self):
        self.lock = threading.Lock()
        self.process = None
        self.identity = None
        self.owner = os.getpid()
        self.starts = 0
        self.requests = 0

    def _fork_check(self):
        if self.owner != os.getpid():
            # A fork must never share a parent's stream or kill its worker.
            if self.process:
                self.process.stdin.close()
                self.process.stdout.close()
            self.process = None
            self.identity = None
            self.lock = threading.Lock()
            self.owner = os.getpid()
            self.starts = self.requests = 0

    def _close(self):
        process, self.process = self.process, None
        self.identity = None
        if process:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdin.close()
            process.stdout.close()

    def close(self):
        self._fork_check()
        with self.lock:
            self._close()

    def _ready(self, stream, write, deadline, args, timeout):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(args, timeout)
        ready = select.select(
            [] if write else [stream], [stream] if write else [], [], remaining
        )
        if not (ready[1] if write else ready[0]):
            raise subprocess.TimeoutExpired(args, timeout)

    def _write(self, data, deadline, args, timeout):
        stream = self.process.stdin
        view = memoryview(data)
        while view:
            self._ready(stream, True, deadline, args, timeout)
            try:
                written = os.write(stream.fileno(), view)
            except BlockingIOError:
                continue
            view = view[written:]

    def _read(self, size, deadline, args, timeout):
        stream = self.process.stdout
        data = bytearray()
        while len(data) < size:
            self._ready(stream, False, deadline, args, timeout)
            try:
                chunk = os.read(stream.fileno(), min(65536, size - len(data)))
            except BlockingIOError:
                continue
            if not chunk:
                raise ValueError("Native worker ended before completing its reply")
            data.extend(chunk)
        return bytes(data)

    def run(self, binary, mode, data, timeout=20):
        if mode not in MODES:
            raise ValueError("Unknown native worker mode")
        if len(data) > MAX_REQUEST:
            raise ValueError("Native request exceeds 1 MiB")
        self._fork_check()
        args = [str(binary), "--worker"]
        deadline = time.monotonic() + timeout
        if not self.lock.acquire(timeout=max(0, timeout)):
            raise subprocess.TimeoutExpired(args, timeout)
        try:
            path = Path(binary).resolve()
            stat = path.stat()
            identity = (
                str(path),
                stat.st_dev,
                stat.st_ino,
                stat.st_size,
                stat.st_mtime_ns,
            )
            if self.process and (
                identity != self.identity or self.process.poll() is not None
            ):
                self._close()
            if self.process is None:
                self.process = subprocess.Popen(
                    args,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=0,
                )
                os.set_blocking(self.process.stdin.fileno(), False)
                os.set_blocking(self.process.stdout.fileno(), False)
                self.identity = identity
                self.starts += 1
            self._write(
                bytes([MODES[mode]]) + struct.pack(">I", len(data)) + data,
                deadline,
                args,
                timeout,
            )
            size = struct.unpack(">I", self._read(4, deadline, args, timeout))[0]
            if size > MAX_RESPONSE:
                raise ValueError("Native response exceeds 16 MiB")
            output = self._read(size, deadline, args, timeout)
            reply = json.loads(output)
            if not isinstance(reply, dict) or ("result" in reply) == ("error" in reply):
                raise ValueError("Invalid native worker reply envelope")
            self.requests += 1
            return subprocess.CompletedProcess(args, int("error" in reply), output, b"")
        except FileNotFoundError:
            self._close()
            raise
        except subprocess.TimeoutExpired:
            self._close()
            raise
        except (OSError, ValueError) as exc:
            self._close()
            raise ValueError(f"Native worker transport failed: {exc}") from exc
        finally:
            self.lock.release()


WORKER = NativeWorker()
atexit.register(WORKER.close)


def run(binary, mode, data, timeout=20):
    return WORKER.run(binary, mode, data, timeout)
