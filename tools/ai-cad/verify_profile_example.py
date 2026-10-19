"""Replay the published profile example; --write refreshes its JSON artifacts."""

import argparse
import json
from pathlib import Path
import tempfile

from store import ROOT, Store


EXAMPLE = ROOT / "examples/ai-cad/profile-extrusion"


def main(write=False):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.cad.json"
        store = Store(path)
        for name in ("profile", "extrude", "widen"):
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
        assert result["result"]["bodies"][0]["volume_mm3"] == "68400"
    print(
        "PASS: profile → extrusion → width edit; exact results, snapshots and reopen verified"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
