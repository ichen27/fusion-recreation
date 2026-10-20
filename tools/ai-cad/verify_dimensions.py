"""Replay unit-entry transport evidence and check canonical saved models/exports."""

import json
from pathlib import Path
import tempfile
import zipfile
from fractions import Fraction as F
from store import ROOT, Store, dispatch
from exports import display
from measurements import dispatch_measure
from selection import dispatch_selection
from topology import dispatch_topology
from test_holes import read_stl, audit_triangles

EXAMPLE = ROOT / "examples/ai-cad/dimensions"


def main():
    counts = {}
    with tempfile.TemporaryDirectory() as directory:
        for transport in ("browser", "mcp"):
            path = Path(directory) / (transport + ".json")
            if transport == "browser":
                path.write_bytes((EXAMPLE / "browser-source.cad.json").read_bytes())
            store = Store(path)
            commits = 0
            rejected = 0
            rows = json.loads((EXAMPLE / (transport + "-recording.json")).read_text())[
                "calls"
            ]
            counts[transport] = len(rows)
            # The browser recording retains queued replies and later reads of the
            # completed job records. Compare each job against its submission state.
            finished = {
                row["reply"]["result"]["job_id"]: row["reply"]["result"]
                for row in rows
                if row.get("url", "").startswith("/api/preview-jobs?")
                and "reply" in row["reply"]["result"]
            }
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
                        job = finished[row["reply"]["result"]["job_id"]]
                        reply = dispatch(store, command)
                        reply = display(reply) if transport == "browser" else reply
                        assert reply == job["reply"]
                        rejected += int("error" in reply)
                    else:
                        assert row["reply"]["result"]["status"] in (
                            "queued",
                            "running",
                            "succeeded",
                            "failed",
                        )
                else:
                    if transport == "mcp" and name != "cad_history":
                        command = {"action": name.removeprefix("cad_"), **command}
                    reply = dispatch(store, command)
                    reply = display(reply) if transport == "browser" else reply
                    assert reply == row["reply"]
                    rejected += int("error" in reply)
                    if command["action"] in ("commit", "undo") and "result" in reply:
                        if command["action"] == "commit":
                            commits += 1
                            if transport == "browser":
                                stage = ["created", "edited"][commits - 1]
                            else:
                                stage = ["created", "edited"][commits - 1]
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
            assert commits == 2 and rejected >= 1
            state = store.execute(dict(action="inspect"))
            parameter = "stock1.width" if transport == "browser" else "width"
            assert state["model"]["parameters"][parameter] == "127/10"

    downloaded = json.loads((EXAMPLE / "browser-download.cad.json").read_text())
    assert downloaded == json.loads((EXAMPLE / "browser-edited.cad.json").read_text())
    with zipfile.ZipFile(EXAMPLE / "browser-solids.zip") as archive:
        triangles = read_stl(archive.read("04-stock1.stl"))
    volume = audit_triangles(triangles, 0)
    expected = F(381, 20) * F(127, 5) * 10
    assert abs(volume - float(expected)) < 1e-7
    audit = json.loads((EXAMPLE / "browser-audit.json").read_text())
    assert audit["invalid"]["invalidText"] == "1 yd"
    assert audit["invalid"]["diagnostic"].startswith("invalid_number:")
    assert audit["sketch"]["points"] == "0,0 25.4,0 25.4,-30 0,-30"
    print(
        f"PASS: {counts} actual transport calls replayed, canonical native history, closed downloaded stock STL, retained sketch/invalid-input observations"
    )


if __name__ == "__main__":
    main()
