"""Replay exact native/drawing snapshots and inspect retained browser download."""

import hashlib
import json
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET
from drawings import NS, dispatch_drawing
from store import ROOT, Store, dispatch

EXAMPLE = ROOT / "examples/ai-cad/reference-sheets"


def main():
    calls = json.loads((EXAMPLE / "mcp-recording.json").read_text())["calls"]
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory) / "part.cad.json")
        for index, call in enumerate(calls):
            args = call["arguments"]
            before = store.path.read_bytes() if store.path.exists() else None
            if call["tool"] == "cad_reference_sheet":
                reply = dispatch_drawing(store, args)
                assert store.path.read_bytes() == before
            else:
                action = {"cad_preview": "preview", "cad_commit": "commit"}.get(
                    call["tool"]
                )
                reply = dispatch(store, {**args, "action": action} if action else args)
            assert reply == call["reply"]
            if index in (0, 3, 6):
                name = {0: "source", 3: "edited", 6: "undo"}[index]
                assert store.load() == Store(EXAMPLE / f"{name}.cad.json").load()
            if index in (1, 4, 7):
                name = {1: "source", 4: "edited", 7: "undo"}[index]
                assert reply["result"]["svg"] == (EXAMPLE / f"{name}.svg").read_text()
    source = (EXAMPLE / "source.svg").read_bytes()
    assert (EXAMPLE / "browser-download.svg").read_bytes() == source
    recorded = json.loads((EXAMPLE / "browser-export.json").read_text())["exports"]
    assert len(recorded) == 1 and recorded[0]["status"] == 200
    assert recorded[0]["svg"].encode() == source
    runtime = json.loads((EXAMPLE / "browser-runtime.json").read_text())
    assert (
        runtime["native_sha256_before"]
        == runtime["native_sha256_after"]
        == hashlib.sha256((EXAMPLE / "source.cad.json").read_bytes()).hexdigest()
    )
    for name in ["source", "edited", "undo"]:
        root = ET.fromstring((EXAMPLE / f"{name}.svg").read_bytes())
        metadata = json.loads(root.find(f"{{{NS}}}metadata").text)
        assert metadata["extents_mm"] == [
            "100",
            "60",
            "12" if name == "edited" else "6",
        ]
        assert root.find(f"{{{NS}}}script") is None
        assert all(
            not any(k.endswith("href") for k in node.attrib) for node in root.iter()
        )
        top = root.find(f"{{{NS}}}g[@id='view-top']")
        arcs = [p for p in top if " A " in p.attrib["d"]]
        assert len(arcs) == 16  # Two holes, two end rings, four quarter arcs each.
    print(
        f"PASS: {len(calls)} MCP calls, SVG/native edit/undo snapshots, 16 native hole arcs and exact browser download"
    )


if __name__ == "__main__":
    main()
