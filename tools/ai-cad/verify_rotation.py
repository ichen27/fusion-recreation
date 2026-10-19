"""Replay browser quarter-turn/intersection and verify exported world coordinates."""

import json
from pathlib import Path
import tempfile
from store import ROOT, Store, dispatch
from test_holes import audit_triangles, read_stl

EXAMPLE = ROOT / "examples/ai-cad/quarter-turn"


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "model.json"
        store = Store(path)
        stages = {3: "turned", 4: "common", 5: "edited", 6: "undo"}
        for row in json.loads((EXAMPLE / "browser-recording.json").read_text())[
            "calls"
        ]:
            before = path.read_bytes() if path.exists() else None
            actual = dispatch(store, row["command"])
            assert actual == row["reply"]
            if "error" in actual or row["command"]["action"] == "preview":
                assert (path.read_bytes() if path.exists() else None) == before
            elif actual["result"]["revision"] in stages:
                name = stages[actual["result"]["revision"]]
                assert json.loads(path.read_text()) == json.loads(
                    (EXAMPLE / (name + ".cad.json")).read_text()
                )
        assert (
            Store(path).execute({"action": "inspect"})["bodies"][0]["volume_mm3"]
            == "4000"
        )
        moved = Store(EXAMPLE / "turned.cad.json").execute({"action": "inspect"})
        assert {b["feature_id"]: b["volume_mm3"] for b in moved["bodies"]} == {
            "stock1": "8000",
            "turn1": "8000",
        }
        triangles = read_stl((EXAMPLE / "edited.stl").read_bytes())
        assert abs(audit_triangles(triangles, 0) - 8000) < 1e-6
        points = [p for t in triangles for p in t]
        assert [min(p[i] for p in points) for i in range(3)] == [0, 0, 0]
        assert [max(p[i] for p in points) for i in range(3)] == [40, 20, 10]
    print(
        "PASS: twelve actual browser calls, quarter-turn/intersection edits, disjoint rejection, undo/reopen and world-space STL"
    )


if __name__ == "__main__":
    main()
