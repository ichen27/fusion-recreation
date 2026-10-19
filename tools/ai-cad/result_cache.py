"""Bounded process-local reuse. The document and Rust evaluator remain authoritative."""

from collections import OrderedDict
import hashlib
import json


def engine_token(binary):
    try:
        stat = binary.stat()
        return (
            stat.st_dev,
            stat.st_ino,
            stat.st_size,
            stat.st_mtime_ns,
            stat.st_ctime_ns,
        )
    except OSError:
        return None


class ResultCache:
    def __init__(self, max_entries=128, max_bytes=8 * 1024 * 1024):
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self.entries = OrderedDict()
        self.bytes = 0
        self.hits = 0
        self.misses = 0

    def get(self, binary, request, compute):
        token = engine_token(binary)
        # A missing/replaced engine cannot reuse a result from a prior executable.
        key = hashlib.sha256(
            json.dumps(
                [token, request], sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).digest()
        if token is not None and key in self.entries:
            self.hits += 1
            data = self.entries.pop(key)
            self.entries[key] = data
            return json.loads(data)
        self.misses += 1
        result = compute()
        # Do not associate a computation with an executable changed mid-request.
        if token is not None and token == engine_token(binary):
            data = json.dumps(result, separators=(",", ":"), allow_nan=False).encode()
            size = len(key) + len(data)
            if size <= self.max_bytes and self.max_entries > 0:
                while self.entries and (
                    len(self.entries) >= self.max_entries
                    or self.bytes + size > self.max_bytes
                ):
                    old_key, old_data = self.entries.popitem(last=False)
                    self.bytes -= len(old_key) + len(old_data)
                self.entries[key] = data
                self.bytes += size
        # Store encoded bytes, not a mutable object shared with the caller.
        return result
