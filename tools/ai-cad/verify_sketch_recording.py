"""Replay actual browser point-placement/drag commands and native snapshots."""

import json
from pathlib import Path
import tempfile
from store import ROOT, Store


def main():
    example = ROOT / "examples/ai-cad/sketch-editor"
    recording = json.loads((example / "browser-recording.json").read_text())
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.cad.json"
        store = Store(path)
        commits = 0
        for row in recording["calls"]:
            before = path.read_bytes() if path.exists() else None
            result = {"result": store.execute(row["command"])}
            assert result == row["reply"]
            if row["command"]["action"] == "preview":
                assert (path.read_bytes() if path.exists() else None) == before
            else:
                name = ("create", "widen")[commits]
                commits += 1
                assert json.loads(path.read_text()) == json.loads(
                    (example / f"{name}.cad.json").read_text()
                )
        assert commits == 2
        state = Store(path).execute({"action": "inspect"})
        assert state["bodies"][0]["volume_mm3"] == "43200"
        undo = store.execute(
            {"action": "undo", "expected_revision": 2, "transaction_id": "verify-undo"}
        )
        assert undo["bodies"][0]["volume_mm3"] == "36000"
    print(
        "PASS: four actual browser create/drag commands replay exactly; previews do not write; native snapshots reopen and undo"
    )


if __name__ == "__main__":
    main()
