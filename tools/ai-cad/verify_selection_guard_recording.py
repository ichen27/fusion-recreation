"""Replay an interleaved browser/MCP guarded-save conflict and explicit recovery."""

import json
from pathlib import Path
import tempfile
from store import ROOT, Store, dispatch
from selection import dispatch_selection
from topology import dispatch_topology

EXAMPLE = ROOT / "examples/ai-cad/selection-guard"


def main():
    rows = json.loads((EXAMPLE / "recording.json").read_text())["calls"]
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.json"
        path.write_bytes((EXAMPLE / "input.cad.json").read_bytes())
        store = Store(path)
        jobs = {}
        rejected = committed = 0
        for row in rows:
            before = path.read_bytes()
            name = row.get("url", row.get("tool"))
            command = row.get("command", row.get("arguments"))
            if name == "cad_select_surface":
                reply = dispatch_selection(
                    store, {"action": "select_surface", **command}
                )
            elif name == "/api/selection":
                reply = dispatch_selection(store, command)
            elif name == "/api/topology":
                reply = dispatch_topology(store, command)
            elif name.startswith("/api/preview-jobs"):
                if command:
                    assert (
                        command["selection_guard"]["surface_id"]
                        == "feature/part/hole/left/upper"
                    )
                    jobs[row["reply"]["result"]["job_id"]] = command
                else:
                    job = row["reply"]["result"]
                    if "reply" in job:
                        assert dispatch(store, jobs[job["job_id"]]) == job["reply"]
                assert path.read_bytes() == before
                continue
            else:
                reply = dispatch(store, command)
                if "error" in reply:
                    assert reply["error"]["code"] == "selection_conflict"
                    rejected += 1
                elif command["action"] == "commit":
                    committed += 1
                    assert reply == row["reply"]
                    assert json.loads(path.read_text()) == json.loads(
                        (EXAMPLE / "saved.cad.json").read_text()
                    )
                    continue
            assert reply == row["reply"]
            assert path.read_bytes() == before
        assert rejected == committed == 1
    print(
        f"PASS: {len(rows)} interleaved browser/MCP requests; guarded preview, unchanged model on conflict, explicit reselection and saved edit"
    )


if __name__ == "__main__":
    main()
