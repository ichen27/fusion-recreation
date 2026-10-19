"""Replay actual browser/MCP analytic placement, depth edits, rejection, history and STL."""

import json
import math
from pathlib import Path
import tempfile
from store import ROOT, Store, dispatch
from test_holes import read_stl, audit_triangles

EXAMPLE = ROOT / "examples/ai-cad/analytic-placement"


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "browser.json"
        path.write_bytes((EXAMPLE / "mcp-input.cad.json").read_bytes())
        store = Store(path)
        stages = {2: "moved", 3: "turned", 4: "deeper", 5: "undo"}
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
                    "7646*pi" if stage == "deeper" else "7764*pi"
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
                        assert reply["error"]["code"] == "hole_depth"
                        rejected += 1
            if row["path"] != "/api/command":
                assert path.read_bytes() == before
        assert rejected == 1
        assert (
            Store(path).execute({"action": "inspect"})["bodies"][0]["volume_mm3"]
            == "7764*pi"
        )
        triangles = read_stl((EXAMPLE / "browser-deeper.stl").read_bytes())
        polygon_volume = 7646 * 128 * math.sin(2 * math.pi / 128) / 2
        assert abs(audit_triangles(triangles, holes=0) - polygon_volume) < 1e-6
        points = [p for t in triangles for p in t]
        for expected, actual in zip(
            [-30, -8, -45], [min(p[i] for p in points) for i in range(3)]
        ):
            assert abs(expected - actual) <= 40 * (1 - math.cos(math.pi / 128)) + 1e-8
        for expected, actual in zip(
            [50, -3, 35], [max(p[i] for p in points) for i in range(3)]
        ):
            assert abs(expected - actual) <= 40 * (1 - math.cos(math.pi / 128)) + 1e-8
        floors = [t for t in triangles if all(abs(p[1] + 5) < 1e-10 for p in t)]
        assert floors
        assert all(
            any(
                all(math.hypot(p[0] - x, p[2] + 5) <= r + 1e-7 for p in triangle)
                for x, r in [(-20, 3), (40, 3), (10, 10)]
            )
            for triangle in floors
        )
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
                name = {1: "input", 2: "moved", 3: "turned"}[
                    reply["result"]["revision"]
                ]
                assert json.loads(path.read_text()) == json.loads(
                    (EXAMPLE / ("mcp-" + name + ".cad.json")).read_text()
                )
    print(
        "PASS: twelve browser HTTP/seven MCP calls, analytic placement/depth edit/rejection/undo and world-space STL with blind floors"
    )


if __name__ == "__main__":
    main()
