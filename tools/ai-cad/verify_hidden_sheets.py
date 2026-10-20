"""Replay planar visibility exports and verify retained browser/native evidence."""

import hashlib
import json
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET
from fractions import Fraction
from drawings import NS, dispatch_drawing
from store import ROOT, Store, dispatch

EXAMPLE = ROOT / "examples/ai-cad/hidden-line-sheets"


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
                action = {"cad_commit": "commit"}.get(call["tool"])
                reply = dispatch(store, {**args, "action": action} if action else args)
            assert reply == call["reply"]
            if index in (0, 4, 6):
                name = {0: "source", 4: "edited", 6: "undo"}[index]
                assert store.load() == Store(EXAMPLE / f"{name}.cad.json").load()
            if index in (1, 2, 5, 7):
                name = {1: "source", 2: "all-edges", 5: "edited", 7: "undo"}[index]
                assert reply["result"]["svg"] == (EXAMPLE / f"{name}.svg").read_text()
    exports = json.loads((EXAMPLE / "browser-export.json").read_text())["exports"]
    assert len(exports) == 2
    for record, name, download in zip(
        exports, ["source", "all-edges"], ["browser-download", "browser-all-edges"]
    ):
        data = (EXAMPLE / f"{name}.svg").read_bytes()
        assert record["status"] == 200 and record["svg"].encode() == data
        assert (EXAMPLE / f"{download}.svg").read_bytes() == data
    runtime = json.loads((EXAMPLE / "browser-runtime.json").read_text())
    assert (
        runtime["native_sha256_before"]
        == runtime["native_sha256_after"]
        == hashlib.sha256((EXAMPLE / "source.cad.json").read_bytes()).hexdigest()
    )
    for name in ["source", "edited", "undo"]:
        root = ET.fromstring((EXAMPLE / f"{name}.svg").read_bytes())
        metadata = json.loads(root.find(f"{{{NS}}}metadata").text)
        assert metadata["extents_mm"] == ["10"] * 3
        for view in metadata["views"]:
            assert view["hidden_segments"] == view["visible_segments"] == 4
            group = root.find(f"{{{NS}}}g[@id='view-{view['name']}']")
            assert [p.attrib["data-visibility"] for p in group] == ["hidden"] * 4 + [
                "visible"
            ] * 4
            for path in group:
                assert (
                    0
                    <= Fraction(path.attrib["data-t-start"])
                    < Fraction(path.attrib["data-t-end"])
                    <= 1
                )
                assert ("stroke-dasharray" in path.attrib) == (
                    path.attrib["data-visibility"] == "hidden"
                )
    print(
        f"PASS: {len(calls)} MCP calls, exact hidden-line source/edit/undo sheets, two browser downloads and unchanged native bytes"
    )


if __name__ == "__main__":
    main()
