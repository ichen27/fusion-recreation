"""Replay the published round-flange example; --write refreshes its JSON artifacts."""

import argparse
import json
from pathlib import Path
import tempfile

from store import ROOT, Store


EXAMPLE = ROOT / "examples/ai-cad/round-flange"


def main(write=False):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.cad.json"
        store = Store(path)
        for name in ("create", "grow"):
            command = json.loads((EXAMPLE / f"{name}.json").read_text())
            result = {"result": store.execute(command)}
            artifacts = {
                f"{name}.reply.json": result,
                f"{name}.cad.json": json.loads(path.read_text()),
            }
            for filename, value in artifacts.items():
                target = EXAMPLE / filename
                if write:
                    target.write_text(json.dumps(value, indent=2) + "\n")
                else:
                    assert json.loads(target.read_text()) == value, filename
            assert (
                Store(path).execute({"action": "inspect"})["model"]
                == result["result"]["model"]
            )
        assert result["result"]["bodies"][0]["volume_mm3"] == "11910*pi"
        assert result["result"]["model"]["parameters"]["right_x"] == "40"
        assert result["result"]["changed_parameters"] == [
            "left_x",
            "radius",
            "right_x",
        ]
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "browser.json"
        store = Store(path)
        store.execute(json.loads((EXAMPLE / "stock.json").read_text()))
        assert json.loads(path.read_text()) == json.loads(
            (EXAMPLE / "stock.cad.json").read_text()
        )
        recording = json.loads((EXAMPLE / "browser-recording.json").read_text())
        commits = 0
        for row in recording["calls"]:
            before = path.read_bytes()
            assert {"result": store.execute(row["command"])} == row["reply"]
            if row["command"]["action"] == "preview":
                assert path.read_bytes() == before
            else:
                name = ("browser-create", "browser-edit")[commits]
                commits += 1
                assert json.loads(path.read_text()) == json.loads(
                    (EXAMPLE / f"{name}.cad.json").read_text()
                )
        assert commits == 2
        assert (
            Store(path).execute({"action": "inspect"})["bodies"][0]["volume_mm3"]
            == "7190*pi"
        )
        assert (
            store.execute(
                {
                    "action": "undo",
                    "expected_revision": 3,
                    "transaction_id": "round-undo",
                }
            )["bodies"][0]["volume_mm3"]
            == "7410*pi"
        )
    print(
        "PASS: radius → dependent mounting holes → rebuilt round flange; exact results, snapshots and reopen verified"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
