"""Replay retained browser reads and audit actual GPU/lifecycle acceptance evidence."""

import hashlib
import json
from pathlib import Path
import tempfile
from store import ROOT, Store
from edge_measurements import dispatch_edge_measure
from topology import dispatch_topology
from selection import dispatch_selection

EXAMPLE = ROOT / "examples/ai-cad/edge-highlight"


def main():
    source = (ROOT / "examples/ai-cad/edge-measurements/source.cad.json").read_bytes()
    runtime = json.loads((EXAMPLE / "browser-runtime.json").read_text())
    assert (
        runtime["native_sha256_before"]
        == runtime["native_sha256_after"]
        == hashlib.sha256(source).hexdigest()
    )
    recorded = json.loads((EXAMPLE / "browser-recording.json").read_text())
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.json"
        path.write_bytes(source)
        store = Store(path)
        functions = {
            "/api/selection": dispatch_selection,
            "/api/topology": dispatch_topology,
            "/api/measure-edge": dispatch_edge_measure,
        }
        for call in recorded["calls"]:
            assert functions[call["url"]](store, call["command"]) == call["reply"]
            assert path.read_bytes() == source
    checks = {c["name"]: c for c in recorded["checks"]}
    assert all(c["error"] == 0 for c in checks.values())
    assert checks["arc"]["uploads"] == [dict(bytes=33 * 24)]
    assert checks["arc"]["edgeDraws"] == [dict(first=0, count=33)]
    assert checks["seam"]["uploads"] == [dict(bytes=2 * 24)]
    assert checks["seam"]["edgeDraws"][-1] == dict(first=0, count=2)
    assert checks["orbit"]["uploads"] == [] and checks["orbit"]["edgeDraws"]
    restored = checks["context_recovery"]
    assert len(restored["uploads"]) == 2 and restored["uploads"][-1]["bytes"] == 48
    assert restored["edgeDraws"] == [dict(first=0, count=2)]
    for name in ("stale_reply_after_clear", "draft_edit"):
        assert checks[name]["uploads"] == [] and checks[name]["edgeDraws"] == []
    assert checks["stale_reply_after_clear"]["inspector"] == ""
    assert checks["draft_edit"]["measurement"] == ""
    reselection = json.loads((EXAMPLE / "reselection-recording.json").read_text())
    checks = {c["name"]: c for c in reselection["checks"]}
    stale = checks["same_body_reselection"]
    assert stale["uploads"] == [] and stale["edgeDraws"] == [] and stale["error"] == 0
    assert stale["message"] == "Selection changed; refresh before measuring."
    fresh = checks["fresh_measurement"]
    assert fresh["uploads"] == [dict(bytes=792)] and fresh["error"] == 0
    runtime = json.loads((EXAMPLE / "reselection-runtime.json").read_text())
    assert (
        runtime["native_sha256_before"]
        == runtime["native_sha256_after"]
        == hashlib.sha256(source).hexdigest()
    )
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.json"
        path.write_bytes(source)
        store = Store(path)
        for call in reselection["calls"]:
            assert functions[call["url"]](store, call["command"]) == call["reply"]
            assert path.read_bytes() == source
    print(
        f"PASS: {len(recorded['calls'])} browser reads replayed; retained GPU evidence covers bounded uploads, orbit, recovery, stale replies and draft clearing"
    )


if __name__ == "__main__":
    main()
