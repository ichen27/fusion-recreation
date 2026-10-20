"""Replay saved view selections and audit retained camera/GPU observations."""

import hashlib
import json
from pathlib import Path
import tempfile
from store import ROOT, Store
from selection import dispatch_selection

EXAMPLE = ROOT / "examples/ai-cad/navigation"


def main():
    source = (EXAMPLE / "source.cad.json").read_bytes()
    rows = json.loads((EXAMPLE / "browser-recording.json").read_text())["calls"]
    expected = [
        ["0", "0", "1"],
        ["0", "-1", "0"],
        ["1", "0", "0"],
        ["0", "0", "-1"],
        ["0", "1", "0"],
        ["-1", "0", "0"],
        ["0", "0", "1"],
    ]
    assert len(rows) == len(expected)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.json"
        path.write_bytes(source)
        store = Store(path)
        for row, normal in zip(rows, expected):
            assert row["url"] == "/api/selection"
            assert dispatch_selection(store, row["command"]) == row["reply"]
            assert (
                row["reply"]["result"]["selected_surface"]["support"]["normal"]
                == normal
            )
            assert path.read_bytes() == source
    audit = json.loads((EXAMPLE / "browser-audit.json").read_text())
    assert (
        audit["pan"]["selectionCalls"] == 6 and audit["pan"]["gesture"] == "middle drag"
    )
    assert abs(audit["pan"]["camera"]["pan"][0] - 0.24) < 1e-7
    assert abs(audit["pan"]["camera"]["pan"][1] - 80 / 828) < 1e-7
    assert (
        audit["keyboard"]["preset"] == "custom"
        and audit["keyboard"]["selectionCalls"] == 7
    )
    for key in ["initialCamera", "fit", "wheelBefore", "wheelAfter", "beforeRecovery"]:
        assert audit[key]["uploads"] == 0
    assert audit["fit"]["pan"] == [0, 0]
    assert audit["wheelAfter"]["zoom"] > audit["wheelBefore"]["zoom"]
    assert audit["afterRecovery"]["uploads"] == 1
    for key in ["angles", "pan", "zoom", "aspect"]:
        assert audit["afterRecovery"][key] == audit["beforeRecovery"][key]
    shift = audit["syntheticShiftDrag"]
    assert shift["synthetic"] and shift["selectionCalls"] == 7
    assert shift["after"]["angles"] == shift["before"]["angles"]
    assert abs(shift["after"]["pan"][0] - shift["before"]["pan"][0] - 48 / 750) < 1e-7
    assert abs(shift["after"]["pan"][1] - shift["before"]["pan"][1] + 40 / 828) < 1e-7
    gpu = json.loads((EXAMPLE / "gpu-projection.json").read_text())
    assert gpu["cases"] == 63 and gpu["pointsPerCase"] == 4 and gpu["glError"] == 0
    assert gpu["maximumError"] <= gpu["tolerance"] == 2e-6
    runtime = json.loads((EXAMPLE / "browser-runtime.json").read_text())
    assert (
        runtime["native_sha256_before"]
        == runtime["native_sha256_after"]
        == hashlib.sha256(source).hexdigest()
    )
    print(
        "PASS: seven saved surface picks, unchanged native bytes, retained pan/zoom/keyboard/recovery observations and GPU/CPU projection comparison"
    )


if __name__ == "__main__":
    main()
