"""Replay browser/MCP explanations and an edit affecting two related parts."""

import json
from pathlib import Path
import tempfile
from store import ROOT, Store, dispatch
from intent import dispatch_explain

EXAMPLE = ROOT / "examples/ai-cad/model-intent"


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "model.json"
        store = Store(path)
        store.execute(json.loads((EXAMPLE / "create.json").read_text()))
        assert json.loads(path.read_text()) == json.loads(
            (EXAMPLE / "initial.cad.json").read_text()
        )
        rows = json.loads((EXAMPLE / "browser-recording.json").read_text())["calls"]
        for row in rows:
            before = path.read_bytes()
            actual = (dispatch_explain if row["path"] == "/api/explain" else dispatch)(
                store, row["command"]
            )
            assert actual == row["reply"]
            if row["path"] == "/api/explain" or row["command"]["action"] == "preview":
                assert path.read_bytes() == before
        assert json.loads(path.read_text()) == json.loads(
            (EXAMPLE / "edited.cad.json").read_text()
        )
        info = rows[0]["reply"]["result"]
        assert [f["id"] for f in info["source_features"]] == ["second", "positioned"]
        assert info["parameters"]["width"]["affected_bodies"] == ["first", "positioned"]
        assert info["parameters"]["half"]["driving_parameters"] == ["width"]
        assert info["parameters"]["height"]["fixed_mm"] == "5"
        state = Store(path).execute({"action": "inspect"})
        assert {b["feature_id"]: b["volume_mm3"] for b in state["bodies"]} == {
            "first": "1600",
            "positioned": "800",
        }
        assert state["model"]["parameters"]["half"] == "20"
        assert state["model"]["parameters"]["height"] == "5"
        before = path.read_bytes()
        for row in json.loads((EXAMPLE / "mcp-recording.json").read_text()):
            assert row["tool"] == "cad_explain"
            assert dispatch_explain(Store(path), row["arguments"]) == row["reply"]
        assert path.read_bytes() == before
    print(
        "PASS: actual browser/MCP explanations, shared-driver edit affects both parts, fixed height retained, native replay/read-only checks"
    )


if __name__ == "__main__":
    main()
