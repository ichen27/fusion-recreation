"""Replay actual surface selections, shared context and native edits."""

import json
from pathlib import Path
import tempfile
from store import ROOT, Store, dispatch
from topology import dispatch_topology
from selection import dispatch_selection
from intent import dispatch_explain

EXAMPLE = ROOT / "examples/ai-cad/surface-context"


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
                elif name in ("/api/selection", "cad_select_surface"):
                    reply = dispatch_selection(
                        store,
                        command
                        if transport == "browser"
                        else {"action": "select_surface", **command},
                    )
                elif name == "cad_context":
                    reply = dispatch_selection(store, dict(action="context"))
                elif name == "cad_explain":
                    reply = dispatch_explain(store, command)
                elif name.startswith("/api/preview-jobs"):
                    if command:
                        jobs[row["reply"]["result"]["job_id"]] = command
                    else:
                        job = row["reply"]["result"]
                        if "reply" in job:
                            assert dispatch(store, jobs[job["job_id"]]) == job["reply"]
                    continue
                else:
                    if transport == "mcp":
                        command = {"action": name.removeprefix("cad_"), **command}
                    reply = dispatch(store, command)
                    if command["action"] == "commit":
                        assert reply == row["reply"]
                        assert json.loads(path.read_text()) == json.loads(
                            (EXAMPLE / (transport + "-larger.cad.json")).read_text()
                        )
                        continue
                assert reply == row["reply"], name
                if (
                    transport == "browser"
                    and name == "/api/selection"
                    and command["action"] == "select_surface"
                    and command["expected_revision"] == 1
                ):
                    assert dispatch_selection(
                        store, dict(action="context")
                    ) == json.loads((EXAMPLE / "browser-shared-mcp.json").read_text())
                assert path.read_bytes() == before
    print(
        f"PASS: {counts} actual requests replay with read-only surface context and exact model edits"
    )


if __name__ == "__main__":
    main()
