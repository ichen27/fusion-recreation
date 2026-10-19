"""Replay actual directed edge-link creation, edits, unlinking and cycle rejection."""

import json
from pathlib import Path
import tempfile

from store import ROOT, Store, dispatch


def main():
    example = ROOT / "examples/ai-cad/sketch-relationships"
    recording = json.loads((example / "browser-recording.json").read_text())
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.json"
        store = Store(path)
        commits = 0
        failures = 0
        for row in recording["calls"]:
            before = path.read_bytes() if path.exists() else None
            result = dispatch(store, row["command"])
            assert result == row["reply"]
            if "error" in result:
                assert result["error"]["code"] == "relation_cycle"
                failures += 1
            if row["command"]["action"] == "preview" or "error" in result:
                assert (path.read_bytes() if path.exists() else None) == before
            else:
                name = ("create", "resize", "unlink")[commits]
                expected_volume = ("36000", "50400", "46200")[commits]
                commits += 1
                assert json.loads(path.read_text()) == json.loads(
                    (example / f"{name}.cad.json").read_text()
                )
                assert result["result"]["bodies"][0]["volume_mm3"] == expected_volume
        assert (commits, failures) == (3, 1)
        state = Store(path).execute({"action": "inspect"})
        assert "sketch1.v3.x" not in state["model"]["relations"]
        undone = store.execute(
            {"action": "undo", "expected_revision": 3, "transaction_id": "undo-unlink"}
        )
        assert undone["model"]["parameters"]["sketch1.v3.x"] == "120"
        assert len(undone["model"]["relations"]) == 4
        assert undone["bodies"][0]["volume_mm3"] == "50400"
    print(
        "PASS: seven browser link/edit/unlink/cycle calls, native snapshots, preview immutability, reopen and undo"
    )


if __name__ == "__main__":
    main()
