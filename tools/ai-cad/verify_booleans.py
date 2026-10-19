"""Replay recorded browser/MCP Booleans and audit the actual downloaded STL."""

import json
from pathlib import Path
import tempfile
from store import ROOT, Store, dispatch
from test_holes import read_stl, audit_triangles

EXAMPLE = ROOT / "examples/ai-cad/planar-booleans"


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "model.json"
        path.write_bytes((EXAMPLE / "browser-inputs.cad.json").read_bytes())
        store = Store(path)
        jobs = {}
        stages = {2: "through", 3: "union", 4: "common", 6: "undo"}
        rows = json.loads((EXAMPLE / "browser-recording.json").read_text())["calls"]
        assert len(rows) == 15
        rejected = 0
        for row in rows:
            before = path.read_bytes()
            command = row["command"]
            if row["path"] == "/api/command":
                reply = dispatch(store, command)
                assert reply == row["reply"], command
                revision = reply["result"]["revision"]
                if revision in stages:
                    expected = EXAMPLE / ("browser-" + stages[revision] + ".cad.json")
                    assert json.loads(path.read_text()) == json.loads(
                        expected.read_text()
                    )
            elif command:
                assert command["action"] == "preview"
                jobs[row["reply"]["result"]["job_id"]] = command
            else:
                job = row["reply"]["result"]
                if "reply" in job:
                    reply = dispatch(store, jobs[job["job_id"]])
                    assert reply == job["reply"]
                    if "error" in reply:
                        assert reply["error"]["code"] == "empty_solid"
                        rejected += 1
            if row["path"] != "/api/command":
                assert path.read_bytes() == before
        assert rejected == 1
        state = Store(path).execute({"action": "inspect"})
        assert state["revision"] == 6 and state["bodies"][0]["volume_mm3"] == "640"
        triangles = read_stl((EXAMPLE / "browser-through.stl").read_bytes())
        assert abs(audit_triangles(triangles, holes=1) - 640) < 1e-7
        # Recorded typed tool calls use a separate, originally empty document.
        path = Path(directory) / "mcp.json"
        store = Store(path)
        for row in json.loads((EXAMPLE / "mcp-recording.json").read_text())["calls"]:
            command = {"action": row["tool"].removeprefix("cad_"), **row["arguments"]}
            before = path.read_bytes() if path.exists() else None
            reply = dispatch(store, command)
            assert reply == row["reply"]
            if "error" in reply or command["action"] == "preview":
                assert (path.read_bytes() if path.exists() else None) == before
        assert json.loads(path.read_text()) == json.loads(
            (EXAMPLE / "mcp-intersection.cad.json").read_text()
        )
    print(
        "PASS: fifteen browser HTTP calls, five MCP calls, Boolean edits, discarded preview, empty rejection, undo/reopen and holed STL"
    )


if __name__ == "__main__":
    main()
