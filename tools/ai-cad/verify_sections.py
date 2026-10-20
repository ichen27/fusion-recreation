"""Replay native section history and actual browser failure/recovery evidence."""

import hashlib
import json
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET
from sections import dispatch_section
from drawings import NS
from store import ROOT, Store, dispatch

EXAMPLE = ROOT / "examples/ai-cad/planar-sections"


def main():
    calls = json.loads((EXAMPLE / "mcp-recording.json").read_text())["calls"]
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory) / "part.cad.json")
        for index, call in enumerate(calls):
            args = call["arguments"]
            before = store.path.read_bytes() if store.path.exists() else None
            if call["tool"] == "cad_section":
                reply = dispatch_section(store, args)
                assert store.path.read_bytes() == before
            else:
                command = (
                    {**args, "action": "commit"}
                    if call["tool"] == "cad_commit"
                    else args
                )
                reply = dispatch(store, command)
            assert reply == call["reply"]
            if index in (0, 5, 8):
                name = {0: "source", 5: "edited", 8: "undo"}[index]
                assert store.load() == Store(EXAMPLE / f"{name}.cad.json").load()
            if index in (1, 6, 9):
                name = {1: "source", 6: "edited", 9: "undo"}[index]
                assert reply["result"]["svg"] == (EXAMPLE / f"{name}.svg").read_text()
        store.path.write_bytes((EXAMPLE / "source.cad.json").read_bytes())
        browser = json.loads((EXAMPLE / "browser-recording.json").read_text())["calls"]
        assert len(browser) == 2
        assert [c["status"] for c in browser] == [400, 200]
        for call in browser:
            assert dispatch_section(store, call["command"]) == call["reply"]
    assert (EXAMPLE / "browser-download.svg").read_bytes() == (
        EXAMPLE / "source.svg"
    ).read_bytes()
    runtime = json.loads((EXAMPLE / "browser-runtime.json").read_text())
    assert (
        runtime["native_sha256_before"]
        == runtime["native_sha256_after"]
        == hashlib.sha256((EXAMPLE / "source.cad.json").read_bytes()).hexdigest()
    )
    for name, area, centroid in [
        ("source", "64", "5"),
        ("edited", "76", "101/19"),
        ("undo", "64", "5"),
    ]:
        root = ET.fromstring((EXAMPLE / f"{name}.svg").read_bytes())
        info = json.loads(root.find(f"{{{NS}}}metadata").text)
        assert info["area_mm2"] == area and info["centroid_mm"] == ["5", "5", centroid]
        assert (
            root.find(f"{{{NS}}}path[@id='section-material']").attrib["fill-rule"]
            == "evenodd"
        )
        assert len(info["loops"]) == 2
    print(
        f"PASS: {len(calls)} MCP calls, native/SVG source/edit/undo, browser rejection/recovery/download and unchanged native bytes"
    )


if __name__ == "__main__":
    main()
