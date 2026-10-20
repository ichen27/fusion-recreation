"""Replay retained browser reads and check native-worker evidence without timing gates."""

import hashlib
import json
from pathlib import Path
import tempfile
from store import ROOT, Store
from intent import dispatch_explain
from measurements import dispatch_measure
from selection import dispatch_selection
from topology import dispatch_topology
from engine_transport import WORKER

EXAMPLE = ROOT / "examples/ai-cad/native-worker"


def main():
    source = ROOT / "examples/ai-cad/planar-loft/browser-deeper.cad.json"
    recorded = json.loads((EXAMPLE / "browser-runtime.json").read_text())
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert recorded["native_sha256_before"] == recorded["native_sha256_after"] == digest
    assert recorded["worker_starts"] == 1 and recorded["worker_requests"] >= 4
    functions = {
        "/api/selection": dispatch_selection,
        "/api/explain": dispatch_explain,
        "/api/measure": dispatch_measure,
        "/api/topology": dispatch_topology,
    }
    WORKER.close()
    starts, requests = WORKER.starts, WORKER.requests
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.json"
        path.write_bytes(source.read_bytes())
        store = Store(path)
        rows = json.loads((EXAMPLE / "browser-recording.json").read_text())["calls"]
        for row in rows:
            assert functions[row["url"]](store, row["command"]) == row["reply"]
            assert path.read_bytes() == source.read_bytes()
    assert WORKER.starts - starts == 1 and WORKER.requests - requests >= 4
    benchmark = json.loads((EXAMPLE / "benchmark.json").read_text())
    assert benchmark["worker_starts"] == 1 and len(benchmark["results"]) == 10
    assert all(r["exact_replies_equal"] for r in benchmark["results"])
    print(
        f"PASS: four actual browser reads, unchanged native bytes; {WORKER.requests - requests} current calls share one native worker"
    )


if __name__ == "__main__":
    main()
