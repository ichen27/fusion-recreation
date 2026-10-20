"""Exact benchmark reply hashes and native/MCP history replay."""

import hashlib
import json
from pathlib import Path
import tempfile
from store import BINARY, ROOT, Store, dispatch, encode
from engine_transport import NativeWorker

EXAMPLE = ROOT / "examples/ai-cad/independent-rebuild"


def main():
    report = json.loads((EXAMPLE / "benchmark.json").read_text())
    worker = NativeWorker()
    try:
        for row in report["results"]:
            request = json.loads((EXAMPLE / f"{row['case']}.request.json").read_text())
            data = encode(request)
            reply = worker.run(BINARY, None, data)
            assert reply.returncode == 0, reply.stdout
            checksum = hashlib.sha256(encode(json.loads(reply.stdout))).hexdigest()
            assert (
                checksum
                == row["baseline"]["reply_sha256"]
                == row["current"]["reply_sha256"]
            )
            assert (
                hashlib.sha256(data).hexdigest()
                == row["baseline"]["request_sha256"]
                == row["current"]["request_sha256"]
            )
    finally:
        worker.close()
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory) / "part.cad.json")
        calls = json.loads((EXAMPLE / "mcp-recording.json").read_text())["calls"]
        checkpoints = {0: "source", 2: "edited", 4: "undo"}
        for index, call in enumerate(calls):
            args = call["arguments"]
            action = {"cad_commit": "commit", "cad_preview": "preview"}.get(
                call["tool"]
            )
            command = {**args, "action": action} if action else args
            before = store.path.read_bytes() if store.path.exists() else None
            assert dispatch(store, command) == call["reply"]
            if index in checkpoints:
                assert (
                    store.load()
                    == Store(EXAMPLE / f"{checkpoints[index]}.cad.json").load()
                )
            else:
                assert store.path.read_bytes() == before
    print(
        f"PASS: {len(report['results'])} exact baseline/current benchmark replies and {len(calls)} MCP history requests"
    )


if __name__ == "__main__":
    main()
