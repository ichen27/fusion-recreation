"""Replay exact sequential plane cuts and actual browser edit/undo recording."""

import json
from pathlib import Path
import tempfile
from store import ROOT, Store, dispatch

EXAMPLE = ROOT / "examples/ai-cad/plane-cuts"


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.json"
        s = Store(path)
        for name in ["create", "resize"]:
            result = dispatch(s, json.loads((EXAMPLE / f"{name}.json").read_text()))
            assert result == json.loads((EXAMPLE / f"{name}.reply.json").read_text())
            assert json.loads(path.read_text()) == json.loads(
                (EXAMPLE / f"{name}.cad.json").read_text()
            )
        assert (
            Store(path).execute({"action": "inspect"})["bodies"][0]["volume_mm3"]
            == "42592/3"
        )
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "browser.json"
        s = Store(path)
        s.execute(json.loads((EXAMPLE / "stock.json").read_text()))
        assert json.loads(path.read_text()) == json.loads(
            (EXAMPLE / "stock.cad.json").read_text()
        )
        mutations = 0
        for row in json.loads((EXAMPLE / "browser-recording.json").read_text())[
            "calls"
        ]:
            before = path.read_bytes()
            assert dispatch(s, row["command"]) == row["reply"]
            if row["command"]["action"] == "preview":
                assert path.read_bytes() == before
            else:
                name = ["first", "second", "resize", "undo"][mutations]
                mutations += 1
                assert json.loads(path.read_text()) == json.loads(
                    (EXAMPLE / f"browser-{name}.cad.json").read_text()
                )
        assert mutations == 4
        assert (
            Store(path).execute({"action": "inspect"})["bodies"][0]["volume_mm3"]
            == "62500/3"
        )
        assert (
            s.execute(
                {
                    "action": "redo",
                    "expected_revision": 5,
                    "transaction_id": "verify-redo",
                }
            )["bodies"][0]["volume_mm3"]
            == "42592/3"
        )
    print(
        "PASS: chained planes, upstream rebuild, empty-solid rejection, native snapshots/reopen/undo/redo"
    )


if __name__ == "__main__":
    main()
