"""Replay retained browser and MCP surface inspection without changing history on reads."""

import json
from pathlib import Path
import tempfile
from store import ROOT, Store, dispatch
from topology import dispatch_topology

EXAMPLE = ROOT / "examples/ai-cad/shared-topology"


def main():
    counts = {}
    with tempfile.TemporaryDirectory() as directory:
        for transport in ("browser", "mcp"):
            path = Path(directory) / (transport + ".json")
            source = (
                "browser-input.cad.json" if transport == "browser" else "input.cad.json"
            )
            path.write_bytes((EXAMPLE / source).read_bytes())
            store = Store(path)
            jobs = {}
            inspections = []
            rows = json.loads((EXAMPLE / (transport + "-recording.json")).read_text())[
                "calls"
            ]
            counts[transport] = len(rows)
            for row in rows:
                before = path.read_bytes()
                command = (
                    row.get("command") if transport == "browser" else row["arguments"]
                )
                name = row.get("url", row.get("tool"))
                if name in ("/api/topology", "cad_topology"):
                    reply = dispatch_topology(store, command)
                    assert reply == row["reply"]
                    if "result" in reply:
                        inspections.append(reply["result"])
                elif name.startswith("/api/preview-jobs"):
                    if command:
                        jobs[row["reply"]["result"]["job_id"]] = command
                    else:
                        job = row["reply"]["result"]
                        if "reply" in job:
                            assert dispatch(store, jobs[job["job_id"]]) == job["reply"]
                else:
                    if transport == "mcp":
                        command = {"action": name.removeprefix("cad_"), **command}
                    assert dispatch(store, command) == row["reply"]
                    if command["action"] == "commit":
                        assert json.loads(path.read_text()) == json.loads(
                            (EXAMPLE / (transport + "-deeper.cad.json")).read_text()
                        )
                        continue
                assert path.read_bytes() == before
            assert len(inspections) >= 2
            assert list(inspections[0]["surfaces"]) == list(inspections[-1]["surfaces"])
            assert inspections[0]["vertices"] != inspections[-1]["vertices"]
    print(
        f"PASS: {counts} actual browser/MCP requests replay with exact shared surfaces and read-only inspection"
    )


if __name__ == "__main__":
    main()
