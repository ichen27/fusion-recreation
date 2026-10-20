"""Replay actual browser separation/contact/overlap inspection with unchanged native bytes."""

import hashlib
import json
from pathlib import Path
import tempfile
from store import ROOT, Store
from clearance import dispatch_clearance
from selection import dispatch_selection

EXAMPLE = ROOT / "examples/ai-cad/clearance"


def main():
    stages = json.loads((EXAMPLE / "browser-recording.json").read_text())["stages"]
    values = []
    for stage in stages:
        source = (EXAMPLE / stage["native"]).read_bytes()
        runtime = json.loads((EXAMPLE / stage["runtime"]).read_text())
        assert (
            runtime["native_sha256_before"]
            == runtime["native_sha256_after"]
            == hashlib.sha256(source).hexdigest()
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.json"
            path.write_bytes(source)
            store = Store(path)
            for call in stage["calls"]:
                fn = {
                    "/api/selection": dispatch_selection,
                    "/api/clearance": dispatch_clearance,
                }[call["url"]]
                assert fn(store, call["command"]) == call["reply"]
                assert path.read_bytes() == source
                if call["url"] == "/api/clearance":
                    values.append(call["reply"]["result"]["relation"])
    assert values == ["separated", "touching", "overlapping"]
    print(
        "PASS: six actual browser reads across separated/touching/overlapping documents, unchanged native history"
    )


if __name__ == "__main__":
    main()
