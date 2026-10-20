"""Replay coaxial-intersection transport evidence and check native history/exports."""

import argparse
import json
from pathlib import Path
import tempfile
import math
from store import ROOT, Store, dispatch
from exports import display
from measurements import dispatch_measure
from selection import dispatch_selection
from topology import dispatch_topology
from test_holes import read_stl, audit_triangles

EXAMPLE = ROOT / "examples/ai-cad/coaxial-intersection"


def same_reply(actual, recorded):
    # JSON round trips and libm vary by a few ulps only in disposable display data.
    # Exact native coordinates, measures, topology IDs and command state stay strict.
    def compare(a, b, approximate=False):
        if approximate and type(a) in (int, float) and type(b) in (int, float):
            assert math.isclose(a, b, rel_tol=1e-13, abs_tol=1e-13), (a, b)
            return
        assert type(a) is type(b), (type(a), type(b))
        if isinstance(a, dict):
            assert a.keys() == b.keys()
            for key in a:
                compare(a[key], b[key], approximate or key == "display_mesh")
        elif isinstance(a, list):
            assert len(a) == len(b)
            for x, y in zip(a, b):
                compare(x, y, approximate)
        else:
            assert a == b, (a, b)

    compare(actual, recorded)


def main(concave=False):
    example = ROOT / "examples/ai-cad/concave-coaxial" if concave else EXAMPLE
    before_volume = "572*pi" if concave else "150*pi"
    edited_coefficient = 657 if concave else 216
    counts = {}
    with tempfile.TemporaryDirectory() as directory:
        for transport in ("browser", "mcp"):
            path = Path(directory) / (transport + ".json")
            if transport == "browser":
                path.write_bytes((example / "browser-source.cad.json").read_bytes())
            store = Store(path)
            commits = 0
            rejected = 0
            rows = json.loads((example / (transport + "-recording.json")).read_text())[
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
                        same_reply(reply, job["reply"])
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
                    same_reply(reply, row["reply"])
                    rejected += int("error" in reply)
                    if command["action"] in ("commit", "undo") and "result" in reply:
                        if command["action"] == "commit":
                            commits += 1
                            stage = ["created", "edited"][commits - 1]
                        else:
                            stage = "undo"
                        assert json.loads(path.read_text()) == json.loads(
                            (
                                example / (transport + "-" + stage + ".cad.json")
                            ).read_text()
                        )
                        continue
                assert (path.read_bytes() if path.exists() else None) == before
            assert commits == 2 and rejected >= 1
            state = store.execute(dict(action="inspect"))
            assert state["bodies"][0]["volume_mm3"] == before_volume

    downloaded = json.loads((example / "browser-download.cad.json").read_text())
    assert downloaded == json.loads((example / "browser-edited.cad.json").read_text())
    triangles = read_stl((example / "browser-edited.stl").read_bytes())
    volume = audit_triangles(triangles, 0)
    expected = edited_coefficient * 128 * math.sin(math.tau / 128) / 2
    assert abs(volume - expected) < 1e-7
    audit = json.loads((example / "browser-audit.json").read_text())
    assert audit["invalid"]["invalidText"] == "20"
    assert "empty_solid" in audit["invalid"]["diagnostic"]
    print(
        f"PASS: {counts} actual transport calls replayed, canonical native history, closed outward intersection STL, retained invalid-input observation"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concave", action="store_true")
    main(parser.parse_args().concave)
