"""Replay the recorded action-menu preview and audit unchanged native bytes."""

import hashlib
import json
from pathlib import Path
import tempfile
from exports import display
from store import ROOT, Store, dispatch

EXAMPLE = ROOT / "examples/ai-cad/feature-actions"


def main():
    source = (EXAMPLE / "source.cad.json").read_bytes()
    rows = json.loads((EXAMPLE / "browser-recording.json").read_text())["calls"]
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.json"
        path.write_bytes(source)
        store = Store(path)
        expected = None
        completed = 0
        for row in rows:
            assert row["url"].startswith("/api/preview-jobs")
            if row["command"]:
                expected = display(dispatch(store, row["command"]))
            elif "reply" in row["reply"]["result"]:
                assert row["reply"]["result"]["reply"] == expected
                completed += 1
            assert path.read_bytes() == source
        assert completed == 1
    audit = json.loads((EXAMPLE / "browser-audit.json").read_text())
    assert audit["initial"]["visibleButtons"] == 8
    assert audit["before"]["visibleButtons"] == 28
    assert audit["initial"]["featureHeight"] < audit["before"]["featureHeight"]
    assert audit["accordion"] == dict(open=["copy"], uploads=0)
    assert audit["keyboardClosed"] and audit["keyboardOpened"]
    assert audit["afterRefresh"]["open"] == ["copy"]
    assert audit["previewControls"] == dict(disabled=True, previewVisible=True)
    assert audit["afterDiscard"] == dict(enabled=True, open=["copy"])
    runtime = json.loads((EXAMPLE / "browser-runtime.json").read_text())
    assert runtime["native_sha256_before"] == runtime["native_sha256_after"]
    assert runtime["native_sha256_after"] == hashlib.sha256(source).hexdigest()
    print(
        "PASS: recorded preview/discard, unchanged native bytes, keyboard/accordion/redraw audit; browser metrics are retained observations"
    )


if __name__ == "__main__":
    main()
