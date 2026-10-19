"""Replay linked-copy browser/MCP recordings and verify independently placed STLs."""

import json
from pathlib import Path
import tempfile
import zipfile
from store import ROOT, Store, dispatch
from test_holes import read_stl, audit_triangles

EXAMPLE = ROOT / "examples/ai-cad/linked-instances"


def checkpoint(path, name):
    assert json.loads(path.read_text()) == json.loads(
        (EXAMPLE / (name + ".cad.json")).read_text()
    )


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "browser.json"
        path.write_bytes((EXAMPLE / "mcp-input.cad.json").read_bytes())
        store = Store(path)
        stages = {2: "pair", 3: "edited", 4: "moved", 5: "undo"}
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
                checkpoint(path, "browser-" + stage)
                assert [b["volume_mm3"] for b in reply["result"]["bodies"]] == (
                    ["204", "204"] if stage == "pair" else ["306", "306"]
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
                        assert reply["error"]["code"] == "dimension_range"
                        rejected += 1
            if row["path"] != "/api/command":
                assert path.read_bytes() == before
        assert rejected == 1
        assert [
            b["volume_mm3"]
            for b in Store(path).execute({"action": "inspect"})["bodies"]
        ] == ["306", "306"]
        with zipfile.ZipFile(EXAMPLE / "browser-parts.zip") as archive:
            assert set(archive.namelist()) == {
                "01-instance1.stl",
                "02-l.stl",
                "manifest.json",
            }
            for name, xmin in [("01-instance1.stl", 30), ("02-l.stl", 0)]:
                triangles = read_stl(archive.read(name))
                assert abs(audit_triangles(triangles, holes=0) - 306) < 1e-7
                points = [p for t in triangles for p in t]
                assert [min(p[i] for p in points) for i in range(3)] == [xmin, 0, 0]
                assert [max(p[i] for p in points) for i in range(3)] == [
                    xmin + 10,
                    10,
                    6,
                ]
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
                name = {1: "input", 2: "pair", 3: "edited"}[reply["result"]["revision"]]
                checkpoint(path, "mcp-" + name)
    print(
        "PASS: twelve browser HTTP/seven MCP calls, linked parts/source edits/independent offsets, rejection, undo and separate world-space STLs"
    )


if __name__ == "__main__":
    main()
