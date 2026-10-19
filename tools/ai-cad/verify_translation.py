"""Replay browser movement/intersection and verify exported world coordinates."""

import json
from pathlib import Path
import tempfile
from store import ROOT, Store, dispatch
from test_holes import audit_triangles, read_stl

EXAMPLE = ROOT / "examples/ai-cad/translation"


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "model.json"
        store = Store(path)
        stages = {3: "moved", 4: "common", 5: "edited", 6: "undo"}
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
            == "7500"
        )
        moved = Store(EXAMPLE / "moved.cad.json").execute({"action": "inspect"})
        assert {b["feature_id"]: b["volume_mm3"] for b in moved["bodies"]} == {
            "stock1": "24000",
            "move1": "24000",
        }
        triangles = read_stl((EXAMPLE / "edited.stl").read_bytes())
        assert abs(audit_triangles(triangles, 0) - 5625) < 1e-6
        points = [p for t in triangles for p in t]
        assert [min(p[i] for p in points) for i in range(3)] == [25, 5, 5]
        assert [max(p[i] for p in points) for i in range(3)] == [40, 30, 20]
    print(
        "PASS: twelve actual browser calls, moved-stock/intersection edits, contact rejection, undo/reopen and world-space STL"
    )


if __name__ == "__main__":
    main()
