"""Replay actual browser picks and MCP context/edit responses across instances."""

import json
from pathlib import Path
import tempfile
from store import ROOT, Store, dispatch
from selection import dispatch_selection

EXAMPLE = ROOT / "examples/ai-cad/shared-selection"


def main():
    browser = json.loads((EXAMPLE / "browser-recording.json").read_text())["calls"]
    edits = json.loads((EXAMPLE / "edit-mcp.json").read_text())
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "workspace.cad.json"
        path.write_bytes((EXAMPLE / "initial.cad.json").read_bytes())
        store = Store(path)

        def pick(index):
            before = path.read_bytes()
            row = browser[index]
            assert dispatch_selection(store, row["command"]) == row["reply"]
            assert path.read_bytes() == before

        def context(row):
            before = path.read_bytes()
            assert row["tool"] == "cad_context"
            assert (
                dispatch_selection(Store(path), {"action": "context"}) == row["reply"]
            )
            assert path.read_bytes() == before

        pick(0)
        context(edits[0])
        assert edits[0]["reply"]["result"]["selected_body"]["volume_mm3"] == "4000"
        for row in edits[1:3]:
            action = {"cad_preview": "preview", "cad_commit": "commit"}[row["tool"]]
            before = path.read_bytes()
            assert (
                dispatch(Store(path), {"action": action, **row["arguments"]})
                == row["reply"]
            )
            if action == "preview":
                assert path.read_bytes() == before
        assert json.loads(path.read_text()) == json.loads(
            (EXAMPLE / "edited.cad.json").read_text()
        )
        context(edits[3])
        assert edits[3]["reply"]["result"]["selection_status"] == "stale"
        pick(1)
        reselected = json.loads((EXAMPLE / "reselected-mcp.json").read_text())[0]
        context(reselected)
        assert reselected["reply"]["result"]["selected_body"]["volume_mm3"] == "8000"
        pick(2)
        cleared = json.loads((EXAMPLE / "cleared-mcp.json").read_text())[0]
        context(cleared)
        assert cleared["reply"]["result"]["selection_status"] == "empty"
    print(
        "PASS: actual browser selection -> MCP context/edit -> stale -> reselect -> clear; native history unchanged by picks"
    )


if __name__ == "__main__":
    main()
