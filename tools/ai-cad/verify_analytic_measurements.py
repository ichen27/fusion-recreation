"""Replay recorded symbolic measurement and depth-edit browser/MCP workflows."""

import json
from pathlib import Path
import tempfile
from store import ROOT, Store, dispatch
from measurements import dispatch_measure

EXAMPLE = ROOT / "examples/ai-cad/analytic-measurements"


def main():
    with tempfile.TemporaryDirectory() as directory:
        for transport in ("browser", "mcp"):
            path = Path(directory) / (transport + ".json")
            path.write_bytes((EXAMPLE / "input.cad.json").read_bytes())
            store = Store(path)
            jobs = {}
            commits = 0
            rows = json.loads((EXAMPLE / (transport + "-recording.json")).read_text())[
                "calls"
            ]
            assert len(rows) == 6
            for row in rows:
                before = path.read_bytes()
                command = (
                    row.get("command") if transport == "browser" else row["arguments"]
                )
                name = row.get("path", row.get("tool"))
                if name in ("/api/measure", "cad_measure"):
                    reply = dispatch_measure(store, command)
                    assert reply == row["reply"]
                    assert path.read_bytes() == before
                elif transport == "browser" and name.startswith("/api/preview-jobs"):
                    if command:
                        jobs[row["reply"]["result"]["job_id"]] = command
                    else:
                        job = row["reply"]["result"]
                        if "reply" in job:
                            assert dispatch(store, jobs[job["job_id"]]) == job["reply"]
                    assert path.read_bytes() == before
                else:
                    if transport == "mcp":
                        command = {"action": name.removeprefix("cad_"), **command}
                    reply = dispatch(store, command)
                    assert reply == row["reply"]
                    if command["action"] == "commit":
                        commits += 1
                        assert json.loads(path.read_text()) == json.loads(
                            (EXAMPLE / (transport + "-deeper.cad.json")).read_text()
                        )
                    else:
                        assert path.read_bytes() == before
            assert commits == 1
    print(
        "PASS: six browser/six MCP calls, symbolic placed/source measurements, shared depth edit, unchanged reads and exact native checkpoints"
    )


if __name__ == "__main__":
    main()
