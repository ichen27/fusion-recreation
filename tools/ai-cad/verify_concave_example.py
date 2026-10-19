"""Replay the published concave-profile example; --write refreshes its JSON artifacts."""

import argparse
import json
from pathlib import Path
import tempfile

from store import ROOT, Store
from exports import display


EXAMPLE = ROOT / "examples/ai-cad/concave-profile"


def main(write=False):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.cad.json"
        store = Store(path)
        for name in ("create", "widen"):
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
        assert result["result"]["bodies"][0]["volume_mm3"] == "14000 - (90)*pi"
        assert result["result"]["model"]["parameters"]["right_x"] == "90"
        assert result["result"]["changed_parameters"] == [
            "right_x",
            "width",
        ]
    recording = json.loads((EXAMPLE / "browser-recording.json").read_text())
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "browser.json"
        store = Store(path)
        commits = 0
        for row in recording["calls"]:
            before = path.read_bytes() if path.exists() else None
            actual = display({"result": store.execute(row["command"])})
            # This historical recording predates optional triangle provenance.
            # Keep every recorded geometry/state field in the comparison.
            for body in actual["result"]["bodies"]:
                body.get("display_mesh", {}).pop("triangle_surfaces", None)
            assert actual == row["reply"]
            if row["command"]["action"] == "preview":
                assert (path.read_bytes() if path.exists() else None) == before
            else:
                name = ("drawn", "edited")[commits]
                assert json.loads(path.read_text()) == json.loads(
                    (EXAMPLE / f"{name}.cad.json").read_text()
                )
                commits += 1
        assert commits == 2
        assert (
            Store(path).execute({"action": "inspect"})["bodies"][0]["volume_mm3"]
            == "14000"
        )
        assert (
            store.execute(
                {
                    "action": "undo",
                    "expected_revision": 2,
                    "transaction_id": "concave-undo",
                }
            )["bodies"][0]["volume_mm3"]
            == "12000"
        )
    print(
        "PASS: width → dependent holes → rebuilt concave plate; exact results, snapshots and reopen verified"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
