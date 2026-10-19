"""Replay actual read-only browser/MCP measurements against retained native input."""

import json
from pathlib import Path
import tempfile
from measurements import dispatch_measure
from store import ROOT, Store

EXAMPLE = ROOT / "examples/ai-cad/measurements"


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.json"
        path.write_bytes((EXAMPLE / "input.cad.json").read_bytes())
        before = path.read_bytes()
        store = Store(path)
        for filename, count, key in [
            ("browser-recording.json", 2, "command"),
            ("mcp-recording.json", 4, "arguments"),
        ]:
            rows = json.loads((EXAMPLE / filename).read_text())["calls"]
            assert len(rows) == count
            for row in rows:
                assert dispatch_measure(store, row[key]) == row["reply"]
                assert path.read_bytes() == before
    print(
        "PASS: two browser/four MCP measurements replay with exact linked-part centroids and unchanged native history"
    )


if __name__ == "__main__":
    main()
