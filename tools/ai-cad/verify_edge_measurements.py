"""Replay actual browser edge reads and verify unchanged native documents."""

import hashlib
import json
from pathlib import Path
import tempfile
from store import ROOT, Store
from edge_measurements import dispatch_edge_measure
from selection import dispatch_selection
from topology import dispatch_topology

EXAMPLE = ROOT / "examples/ai-cad/edge-measurements"


def main():
    source = (EXAMPLE / "source.cad.json").read_bytes()
    runtime = json.loads((EXAMPLE / "browser-runtime.json").read_text())
    digest = hashlib.sha256(source).hexdigest()
    assert runtime["native_sha256_before"] == runtime["native_sha256_after"] == digest
    functions = {
        "/api/selection": dispatch_selection,
        "/api/topology": dispatch_topology,
        "/api/measure-edge": dispatch_edge_measure,
    }
    rows = json.loads((EXAMPLE / "browser-recording.json").read_text())["calls"]
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.json"
        path.write_bytes(source)
        store = Store(path)
        for row in rows:
            assert functions[row["url"]](store, row["command"]) == row["reply"]
            assert path.read_bytes() == source
    measured = [r["reply"]["result"] for r in rows if r["url"] == "/api/measure-edge"]
    assert {r["length_mm"] for r in measured} == {"5", "5*pi"}
    assert {r["patch_seam"] for r in measured} == {True, False}
    print(
        f"PASS: {len(rows)} actual browser calls, arc/chord/seam results and unchanged native bytes"
    )


if __name__ == "__main__":
    main()
