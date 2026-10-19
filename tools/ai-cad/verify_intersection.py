"""Replay actual browser solid intersection, upstream editing, export and undo."""

import json
from pathlib import Path
import tempfile
from store import ROOT, Store, dispatch
from test_holes import audit_triangles, read_stl

EXAMPLE = ROOT / "examples/ai-cad/intersection"


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "model.json"
        store = Store(path)
        stages = {2: "inputs", 3: "common", 4: "edited", 5: "undo"}
        for row in json.loads((EXAMPLE / "browser-recording.json").read_text())[
            "calls"
        ]:
            before = path.read_bytes() if path.exists() else None
            reply = dispatch(store, row["command"])
            assert reply == row["reply"]
            if "error" in reply or row["command"]["action"] == "preview":
                assert (path.read_bytes() if path.exists() else None) == before
            elif reply["result"]["revision"] in stages:
                stage = stages[reply["result"]["revision"]]
                assert json.loads(path.read_text()) == json.loads(
                    (EXAMPLE / (stage + ".cad.json")).read_text()
                )
        reopened = Store(path).execute({"action": "inspect"})
        assert len(reopened["bodies"]) == 1
        assert reopened["bodies"][0]["volume_mm3"] == "28000"
        edited = Store(EXAMPLE / "edited.cad.json").execute({"action": "inspect"})
        assert edited["bodies"][0]["volume_mm3"] == "23000"
        downloaded = read_stl((EXAMPLE / "edited.stl").read_bytes())
        assert abs(audit_triangles(downloaded, 0) - 23000) < 1e-6
        for triangle in downloaded:
            for x, y, z in triangle:
                assert -1e-9 <= x <= 40 + 1e-9 and -1e-9 <= y <= 40 + 1e-9
                assert -1e-9 <= z <= 20 + 1e-9 and x + y <= 50 + 1e-9
    print(
        "PASS: ten actual browser calls, intersection/upstream edit/empty rejection, native undo/reopen and downloaded STL"
    )


if __name__ == "__main__":
    main()
