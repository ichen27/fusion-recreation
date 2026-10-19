"""Replay actual browser/MCP cavity cuts, rejection, history and pocket STL."""

import json
from pathlib import Path
import tempfile
from store import ROOT, Store, dispatch
from test_holes import read_stl, audit_triangles

EXAMPLE = ROOT / "examples/ai-cad/nonconvex-plane-cuts"


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "browser.json"
        path.write_bytes((EXAMPLE / "mcp-input.cad.json").read_bytes())
        store = Store(path)
        stages = {2: "opened", 3: "lowered", 4: "undo"}
        jobs = {}
        rejected = 0
        rows = json.loads((EXAMPLE / "browser-recording.json").read_text())["calls"]
        assert len(rows) == 9
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
                    "328" if stage == "lowered" else "392"
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
        assert (
            Store(path).execute({"action": "inspect"})["bodies"][0]["volume_mm3"]
            == "392"
        )
        triangles = read_stl((EXAMPLE / "browser-lowered.stl").read_bytes())
        assert abs(audit_triangles(triangles, holes=0) - 328) < 1e-7
        # Pocket has a floor at z=2 and the trimmed exterior top at z=4.
        floors = [t for t in triangles if all(p[2] == 2 for p in t)]
        assert floors and all(
            2 <= p[0] <= 8 and 2 <= p[1] <= 8 for t in floors for p in t
        )
        assert max(p[2] for t in triangles for p in t) == 4
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
                name = {1: "input", 2: "opened", 3: "lowered"}[
                    reply["result"]["revision"]
                ]
                assert json.loads(path.read_text()) == json.loads(
                    (EXAMPLE / ("mcp-" + name + ".cad.json")).read_text()
                )
    print(
        "PASS: nine browser HTTP/seven MCP calls, cavity opening/depth edit, empty rejection, undo and pocket STL floor"
    )


if __name__ == "__main__":
    main()
