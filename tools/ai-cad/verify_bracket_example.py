"""Replay the published bracket example; --write refreshes its JSON artifacts."""

import argparse
import json
from pathlib import Path
import tempfile

from store import ROOT, Store


EXAMPLE = ROOT / "examples/ai-cad/bracket"


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
        assert result["result"]["bodies"][0]["volume_mm3"] == "43200 - (162)*pi"
        assert result["result"]["model"]["parameters"]["center_x"] == "60"
        assert result["result"]["changed_parameters"] == [
            "center_x",
            "right_x",
            "width",
        ]
    print(
        "PASS: width → dependent mounting holes → rebuilt bracket; exact results, snapshots and reopen verified"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
