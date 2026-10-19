"""Replay real browser/MCP transforms, history and world-space STL coordinates."""

import json
from pathlib import Path
import tempfile
from store import ROOT, Store, dispatch
from test_holes import read_stl, audit_triangles

EXAMPLE = ROOT / "examples/ai-cad/planar-transforms"


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "browser.json"
        path.write_bytes(
            (EXAMPLE.parent / "planar-booleans/browser-through.cad.json").read_bytes()
        )
        store = Store(path)
        stages = {3: "moved", 4: "turned", 5: "widened", 6: "undo"}
        jobs = {}
        rejected = 0
        rows = json.loads((EXAMPLE / "browser-recording.json").read_text())["calls"]
        assert len(rows) == 12
        for row in rows:
            before = path.read_bytes()
            command = row["command"]
            if row["path"] == "/api/command":
                reply = dispatch(store, command)
                assert reply == row["reply"]
                stage = stages[reply["result"]["revision"]]
                assert json.loads(path.read_text()) == json.loads(
                    (EXAMPLE / ("browser-" + stage + ".cad.json")).read_text()
                )
                assert reply["result"]["bodies"][0]["volume_mm3"] == (
                    "1080" if stage == "widened" else "640"
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
                        assert reply["error"]["code"] == "translation_range"
                        rejected += 1
            if row["path"] != "/api/command":
                assert path.read_bytes() == before
        assert rejected == 1
        assert (
            Store(path).execute({"action": "inspect"})["bodies"][0]["volume_mm3"]
            == "640"
        )
        triangles = read_stl((EXAMPLE / "browser-turned.stl").read_bytes())
        assert abs(audit_triangles(triangles, holes=1) - 640) < 1e-7
        vertices = [p for t in triangles for p in t]
        assert [min(p[i] for p in vertices) for i in range(3)] == [10, -15, 3]
        assert [max(p[i] for p in vertices) for i in range(3)] == [20, -5, 13]
        path = Path(directory) / "mcp.json"
        store = Store(path)
        rows = json.loads((EXAMPLE / "mcp-recording.json").read_text())["calls"]
        assert len(rows) == 7
        for row in rows:
            command = {"action": row["tool"].removeprefix("cad_"), **row["arguments"]}
            before = path.read_bytes() if path.exists() else None
            reply = dispatch(store, command)
            assert reply == row["reply"]
            if "error" in reply or command["action"] == "preview":
                assert (path.read_bytes() if path.exists() else None) == before
            else:
                name = {1: "through", 2: "moved", 3: "turned"}[
                    reply["result"]["revision"]
                ]
                assert json.loads(path.read_text()) == json.loads(
                    (EXAMPLE / ("mcp-" + name + ".cad.json")).read_text()
                )
    print(
        "PASS: twelve browser HTTP and seven MCP calls, transformed hole/upstream rebuild, range rejection, undo and world-space STL"
    )


if __name__ == "__main__":
    main()
