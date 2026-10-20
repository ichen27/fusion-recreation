"""Replay actual browser overlap/contact inspection with unchanged native bytes."""

import hashlib
import json
from pathlib import Path
import tempfile
from store import ROOT, Store
from interference import dispatch_interference
from selection import dispatch_selection

EXAMPLE = ROOT / "examples/ai-cad/interference"


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
                    "/api/interference": dispatch_interference,
                }[call["url"]]
                assert fn(store, call["command"]) == call["reply"]
                assert path.read_bytes() == source
                if call["url"] == "/api/interference":
                    values.append(call["reply"]["result"]["overlap_volume_mm3"])
    assert values == ["40", "0"]
    print(
        "PASS: four actual browser reads across overlapping/contact documents, unchanged native history"
    )


if __name__ == "__main__":
    main()
