"""Replay the actual Codex-generated tool calls; this does not invoke inference."""

import json
from pathlib import Path
import tempfile
from store import ROOT, Store


def summarize(result):
    fields = (
        "revision",
        "model",
        "changed_parameters",
        "can_undo",
        "can_redo",
        "preview",
        "committed_revision",
        "replayed",
    )
    return {key: result[key] for key in fields if key in result} | {
        "bodies": [
            {"feature_id": body["feature_id"], "volume_mm3": body["volume_mm3"]}
            for body in result["bodies"]
        ]
    }


def replay(directory):
    record = json.loads((directory / "recording.json").read_text())
    assert record["schema_version"] == 1 and len(record["turns"]) == 2
    with tempfile.TemporaryDirectory() as temporary:
        store = Store(Path(temporary) / "replayed.cad.json")
        snapshots = []
        for turn in record["turns"]:
            assert [call["tool"] for call in turn["calls"]] == [
                "cad_inspect",
                "cad_preview",
                "cad_commit",
            ]
            for call in turn["calls"]:
                action = {
                    "cad_inspect": "inspect",
                    "cad_preview": "preview",
                    "cad_commit": "commit",
                }[call["tool"]]
                result = store.execute({**call["arguments"], "action": action})
                assert summarize(result) == call["observed"], call["tool"]
            snapshots.append(store.execute({"action": "inspect"}))
        first, second = snapshots
        assert first["revision"] == 1 and second["revision"] == 2
        assert first["bodies"][0]["volume_mm3"] == "71400"
        assert second["bodies"][0]["volume_mm3"] == "85800"
        assert first["model"]["features"] == second["model"]["features"]
        assert first["model"]["fixed"] == second["model"]["fixed"]
        before, after = first["model"]["parameters"], second["model"]["parameters"]
        assert before == {
            "width": "100",
            "depth": "60",
            "thickness": "12",
            "corner_size": "10",
        }
        assert after == {**before, "width": "120"}
        for name, expected in [
            ("created.cad.json", first),
            ("widened.cad.json", second),
        ]:
            # Copy before opening so the fixture directory never gets a .lock file.
            path = Path(temporary) / name
            path.write_bytes((directory / name).read_bytes())
            assert Store(path).execute({"action": "inspect"}) == expected
        final_reply = json.loads((directory / "final.reply.json").read_text())
        assert final_reply["result"] == second
        # The recorded model remains editable/reversible after reopening.
        undo = store.execute(
            {
                "action": "undo",
                "expected_revision": 2,
                "transaction_id": "verify-recording-undo",
            }
        )
        assert undo["model"] == first["model"]
    return record


if __name__ == "__main__":
    replay(ROOT / "examples/ai-cad/live-codex")
    print(
        "PASS: six recorded Codex calls replay exactly; snapshots reopen; width-only edit and undo verified"
    )
