"""Replay exact coupled-constraint transport evidence, native history and exported parts."""

import json
from pathlib import Path
import tempfile
import zipfile
from store import ROOT, Store, dispatch
from exports import display
from measurements import dispatch_measure
from intent import dispatch_explain
from test_holes import read_stl, audit_triangles
from verify_coaxial import same_reply

EXAMPLE = ROOT / "examples/ai-cad/linear-constraints"


def main():
    counts = {}
    with tempfile.TemporaryDirectory() as directory:
        for transport in ("browser", "mcp"):
            path = Path(directory) / f"{transport}.cad.json"
            if transport == "browser":
                path.write_bytes((EXAMPLE / "browser-source.cad.json").read_bytes())
            store = Store(path)
            rows = json.loads((EXAMPLE / f"{transport}-recording.json").read_text())[
                "calls"
            ]
            counts[transport] = len(rows)
            jobs = {
                row["reply"]["result"]["job_id"]: row["reply"]["result"]
                for row in rows
                if row.get("url", "").startswith("/api/preview-jobs?")
                and "reply" in row["reply"]["result"]
            }
            rejected = commits = 0
            for row in rows:
                before = path.read_bytes() if path.exists() else None
                command = (
                    row.get("command") if transport == "browser" else row["arguments"]
                )
                name = row.get("url", row.get("tool"))
                if name == "cad_explain":
                    same_reply(dispatch_explain(store, command), row["reply"])
                elif name == "cad_measure":
                    same_reply(dispatch_measure(store, command), row["reply"])
                elif transport == "browser" and name.startswith("/api/preview-jobs"):
                    if command:
                        finished = jobs[row["reply"]["result"]["job_id"]]
                        actual = display(dispatch(store, command))
                        same_reply(actual, finished["reply"])
                        rejected += int("error" in actual)
                else:
                    if transport == "mcp" and name != "cad_history":
                        command = {"action": name.removeprefix("cad_"), **command}
                    actual = dispatch(store, command)
                    if transport == "browser":
                        actual = display(actual)
                    same_reply(actual, row["reply"])
                    rejected += int("error" in actual)
                    if command["action"] in ("commit", "undo") and "result" in actual:
                        if command["action"] == "commit":
                            commits += 1
                            stage = (
                                "created"
                                if transport == "mcp" and commits == 1
                                else "edited"
                            )
                        else:
                            stage = "undo"
                        assert json.loads(path.read_text()) == json.loads(
                            (EXAMPLE / f"{transport}-{stage}.cad.json").read_text()
                        )
                        continue
                assert (path.read_bytes() if path.exists() else None) == before
            assert commits == (2 if transport == "mcp" else 1)
            assert rejected == (2 if transport == "mcp" else 1)
            state = store.execute(dict(action="inspect"))
            assert state["model"]["parameters"]["left"] == "60"
            assert state["model"]["parameters"]["right"] == "30"
            assert state["model"]["parameters"]["offset"] == "70"
            assert state["model"]["relations"]["left"]["terms"] == {
                "gap": "-2/3",
                "span": "2/3",
            }
    assert json.loads(
        (EXAMPLE / "browser-download.cad.json").read_text()
    ) == json.loads((EXAMPLE / "browser-edited.cad.json").read_text())
    with zipfile.ZipFile(EXAMPLE / "browser-edited.zip") as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["revision"] == 2
        for body, expected, x_bounds in zip(
            manifest["bodies"], [16000, 8000], [(0, 80), (90, 130)]
        ):
            triangles = read_stl(archive.read(body["file"]))
            assert abs(audit_triangles(triangles, 0) - expected) < 1e-8
            xs = [point[0] for triangle in triangles for point in triangle]
            assert (min(xs), max(xs)) == x_bounds
    audit = json.loads((EXAMPLE / "browser-audit.json").read_text())
    assert all(row["disabled"] for row in audit["derived"])
    assert {row["id"] for row in audit["derived"]} == {"left", "right", "offset"}
    assert (
        audit["invalid"]["invalidText"] == "5"
        and "dimension_range" in audit["invalid"]["diagnostic"]
    )
    print(
        f"PASS: {counts} actual calls, persistent exact constraints/history, derived controls, invalid edit and two correctly placed outward STL parts"
    )


if __name__ == "__main__":
    main()
