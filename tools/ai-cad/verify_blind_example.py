"""Replay exact blind-hole edits and actual browser recording/native snapshots."""

import json
from pathlib import Path
import tempfile
from store import ROOT, Store, dispatch

EXAMPLE = ROOT / "examples/ai-cad/blind-holes"


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.json"
        store = Store(path)
        for name in ["create", "deeper"]:
            result = dispatch(store, json.loads((EXAMPLE / f"{name}.json").read_text()))
            assert result == json.loads((EXAMPLE / f"{name}.reply.json").read_text())
            assert json.loads(path.read_text()) == json.loads(
                (EXAMPLE / f"{name}.cad.json").read_text()
            )
        assert (
            Store(path).execute({"action": "inspect"})["bodies"][0]["volume_mm3"]
            == "7528*pi"
        )
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "browser.json"
        store = Store(path)
        store.execute(
            json.loads((ROOT / "examples/ai-cad/round-flange/stock.json").read_text())
        )
        mutations = 0
        for row in json.loads((EXAMPLE / "browser-recording.json").read_text())[
            "calls"
        ]:
            before = path.read_bytes()
            result = dispatch(store, row["command"])
            assert result == row["reply"]
            if row["command"]["action"] == "preview":
                assert path.read_bytes() == before
            else:
                name = ["browser-create", "browser-deeper", "browser-undo"][mutations]
                mutations += 1
                assert json.loads(path.read_text()) == json.loads(
                    (EXAMPLE / f"{name}.cad.json").read_text()
                )
        assert mutations == 3
        assert (
            Store(path).execute({"action": "inspect"})["bodies"][0]["volume_mm3"]
            == "7764*pi"
        )
        assert (
            store.execute(
                {
                    "action": "redo",
                    "expected_revision": 4,
                    "transaction_id": "verify-redo",
                }
            )["bodies"][0]["volume_mm3"]
            == "7528*pi"
        )
    print(
        "PASS: blind depth edits, exact snapshots, actual rejected preview/undo, reopen and redo"
    )


if __name__ == "__main__":
    main()
