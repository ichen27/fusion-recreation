"""Replay actual native file import/edit/undo/download and corruption rejection."""

import json
from pathlib import Path
import tempfile
from store import ROOT, Store, dispatch

EXAMPLE = ROOT / "examples/ai-cad/native-project"


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "workspace.cad.json"
        store = Store(path)
        checkpoints = {
            1: "imported",
            2: "edited",
            3: "undo",
            4: "empty",
            5: "downloaded",
        }
        for row in json.loads((EXAMPLE / "browser-recording.json").read_text())[
            "calls"
        ]:
            before = path.read_bytes() if path.exists() else None
            actual = dispatch(store, row["command"])
            assert actual == row["reply"]
            if "error" in actual or row["command"]["action"].startswith("preview"):
                assert (path.read_bytes() if path.exists() else None) == before
            else:
                revision = actual["result"]["revision"]
                assert json.loads(path.read_text()) == json.loads(
                    (EXAMPLE / (checkpoints[revision] + ".cad.json")).read_text()
                )
        assert (
            store.native_snapshot(5) == (EXAMPLE / "downloaded.cad.json").read_bytes()
        )
        imported = json.loads((EXAMPLE / "imported.cad.json").read_text())["state"]
        assert len(imported["receipts"]) == 1 and len(imported["undo"]) == 1
        assert imported["undo"][0]["features"] == []
        # Reopen the downloaded project and redo the dimension edit from its history.
        reopened = Store(Path(directory) / "reopened.cad.json")
        reopened.path.write_bytes((EXAMPLE / "downloaded.cad.json").read_bytes())
        redone = reopened.execute(
            {"action": "redo", "expected_revision": 5, "transaction_id": "reopen-redo"}
        )
        edited = json.loads((EXAMPLE / "edited.cad.json").read_text())["state"]["model"]
        assert redone["model"] == edited
        assert len(redone["bodies"]) == 2
    print(
        "PASS: actual native import/preview/edit/undo/redo/download, reopened history and damaged checksum rejection"
    )


if __name__ == "__main__":
    main()
