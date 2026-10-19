"""Replay browser topology changes and explicit cleanup; preserve native history."""

import argparse
import json
from pathlib import Path
import tempfile

from store import ROOT, Store

EXAMPLE = ROOT / "examples/ai-cad/feature-edits"


def main(write=False):
    recording = json.loads((EXAMPLE / "browser-recording.json").read_text())
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.json"
        path.write_bytes((EXAMPLE / "base.cad.json").read_bytes())
        store = Store(path)
        commits = 0
        for row in recording["calls"]:
            before = path.read_bytes()
            result = {"result": store.execute(row["command"])}
            assert result == row["reply"]
            if row["command"]["action"] == "preview":
                assert path.read_bytes() == before
            else:
                name = ("add", "remove", "clear")[commits]
                commits += 1
                assert json.loads(path.read_text()) == json.loads(
                    (EXAMPLE / f"{name}.cad.json").read_text()
                )
                expected = ("12000 - (170)*pi", "12000 - (125)*pi", "12000")[
                    commits - 1
                ]
                assert result["result"]["bodies"][0]["volume_mm3"] == expected
        assert commits == 3
        cleanup = json.loads((EXAMPLE / "cleanup.json").read_text())
        state = store.execute(cleanup)
        assert len(state["changed_parameters"]) == 9
        assert not any(k.startswith("holes1.") for k in state["model"]["parameters"])
        for name, value in [
            ("cleanup.reply.json", {"result": state}),
            ("cleanup.cad.json", json.loads(path.read_text())),
        ]:
            if write:
                (EXAMPLE / name).write_text(json.dumps(value, indent=2) + "\n")
            else:
                assert value == json.loads((EXAMPLE / name).read_text())
        assert Store(path).execute({"action": "inspect"})["model"] == state["model"]
        store.execute(
            {"action": "undo", "expected_revision": 7, "transaction_id": "undo-cleanup"}
        )
        undo = store.execute(
            {"action": "undo", "expected_revision": 8, "transaction_id": "undo-clear"}
        )
        assert [h["id"] for h in undo["bodies"][0]["analytic"]["holes"]] == ["h2", "h3"]
        assert undo["bodies"][0]["volume_mm3"] == "12000 - (125)*pi"
    print(
        "PASS: six browser structural edits, explicit parameter cleanup, native snapshots, reopen and undo"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
