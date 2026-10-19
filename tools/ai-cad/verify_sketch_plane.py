"""Replay the actual browser sketch/cut/edit/export workflow."""

import json
from pathlib import Path
import tempfile
from store import ROOT, Store, dispatch
from test_holes import audit_triangles, read_stl

EXAMPLE = ROOT / "examples/ai-cad/sketch-plane"


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "model.json"
        store = Store(path)
        stages = {1: "sketch", 2: "cut", 3: "edited", 4: "undo"}
        volumes = {1: "120000", 2: "108000", 3: "104000", 4: "108000"}
        for row in json.loads((EXAMPLE / "browser-recording.json").read_text())[
            "calls"
        ]:
            before = path.read_bytes() if path.exists() else None
            reply = dispatch(store, row["command"])
            assert reply == row["reply"]
            if "error" in reply or row["command"]["action"] == "preview":
                assert (path.read_bytes() if path.exists() else None) == before
            else:
                revision = reply["result"]["revision"]
                assert reply["result"]["bodies"][0]["volume_mm3"] == volumes[revision]
                assert json.loads(path.read_text()) == json.loads(
                    (EXAMPLE / (stages[revision] + ".cad.json")).read_text()
                )
        reopened = Store(path).execute({"action": "inspect"})
        assert reopened["bodies"][0]["volume_mm3"] == "108000"
        assert reopened["model"]["features"][0]["kind"] == "planar_profile"
        downloaded = read_stl((EXAMPLE / "edited.stl").read_bytes())
        assert abs(audit_triangles(downloaded, 0) - 104000) < 1e-6
        for triangle in downloaded:
            for x, y, z in triangle:
                assert x + z <= 100 + 1e-8
                assert 3 * x + y <= 300 + 1e-8
    print(
        "PASS: eight actual sketch/plane browser calls, native edit/undo/reopen, rejected concavity and downloaded STL"
    )


if __name__ == "__main__":
    main()
