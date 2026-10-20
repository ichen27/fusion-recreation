"""Replay actual planar-loft browser/MCP commands and their native checkpoints."""

import json
from pathlib import Path
import tempfile
from store import ROOT, Store, dispatch
from measurements import dispatch_measure
from selection import dispatch_selection
from topology import dispatch_topology
from test_holes import read_stl, audit_triangles

EXAMPLE = ROOT / "examples/ai-cad/planar-loft"


def main():
    counts = {}
    with tempfile.TemporaryDirectory() as directory:
        for transport in ("browser", "mcp"):
            path = Path(directory) / (transport + ".json")
            store = Store(path)
            jobs = {}
            commits = 0
            rejected = 0
            rows = json.loads((EXAMPLE / (transport + "-recording.json")).read_text())[
                "calls"
            ]
            counts[transport] = len(rows)
            for row in rows:
                before = path.read_bytes() if path.exists() else None
                command = (
                    row.get("command") if transport == "browser" else row["arguments"]
                )
                name = row.get("url", row.get("tool"))
                if name in ("/api/selection", "cad_select_surface"):
                    if transport == "mcp":
                        command = {"action": "select_surface", **command}
                    assert dispatch_selection(store, command) == row["reply"]
                elif name in ("/api/topology", "cad_topology"):
                    assert dispatch_topology(store, command) == row["reply"]
                elif name in ("/api/measure", "cad_measure"):
                    assert dispatch_measure(store, command) == row["reply"]
                elif transport == "browser" and name.startswith("/api/preview-jobs"):
                    if command:
                        jobs[row["reply"]["result"]["job_id"]] = command
                    else:
                        job = row["reply"]["result"]
                        if "reply" in job:
                            reply = dispatch(store, jobs[job["job_id"]])
                            assert reply == job["reply"]
                            rejected += int("error" in reply)
                else:
                    if transport == "mcp" and name != "cad_history":
                        command = {"action": name.removeprefix("cad_"), **command}
                    reply = dispatch(store, command)
                    assert reply == row["reply"]
                    rejected += int("error" in reply)
                    if command["action"] in ("commit", "undo") and "result" in reply:
                        if command["action"] == "commit":
                            commits += 1
                            if transport == "browser":
                                stage = [None, "profiles", "created", "deeper"][
                                    commits - 1
                                ]
                            else:
                                stage = ["created", "deeper"][commits - 1]
                            if stage is None:
                                continue
                        else:
                            stage = "undo"
                        assert json.loads(path.read_text()) == json.loads(
                            (
                                EXAMPLE / (transport + "-" + stage + ".cad.json")
                            ).read_text()
                        )
                        continue
                assert (path.read_bytes() if path.exists() else None) == before
            assert commits == (4 if transport == "browser" else 2) and rejected >= 1
            state = store.execute(dict(action="inspect"))
            assert state["bodies"][0]["volume_mm3"] == "6400"

    triangles = read_stl((EXAMPLE / "browser-deeper.stl").read_bytes())
    volume = audit_triangles(triangles, 0)
    assert abs(volume - 12800) < 1e-7
    print(
        f"PASS: {counts} actual calls, native creation/edit/rejection/undo replay and closed planar loft STL"
    )


if __name__ == "__main__":
    main()
