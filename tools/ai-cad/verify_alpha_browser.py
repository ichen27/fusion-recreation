"""Replay the actual alpha browser commands, including the rejected draft."""

import json
from pathlib import Path
import tempfile
from store import ROOT, Store, dispatch
from exports import display
from topology import dispatch_topology
from selection import dispatch_selection
from verify_coaxial import same_reply

EXAMPLE = ROOT / "examples/ai-cad/modelling-alpha"


def browser_numbers(value):
    # JSON.stringify normalizes 43200.0 to 43200; exact native quantities are strings.
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return [browser_numbers(v) for v in value]
    if isinstance(value, dict):
        return {k: browser_numbers(v) for k, v in value.items()}
    return value


def main():
    calls = json.loads((EXAMPLE / "browser-recording.json").read_text())["calls"]
    commits = invalid = 0
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory) / "part.cad.json")
        for row in calls:
            command = row["command"]
            before = store.path.read_bytes() if store.path.exists() else None
            if row["url"] == "/api/topology":
                actual = dispatch_topology(store, command)
            elif row["url"] == "/api/selection":
                actual = dispatch_selection(store, command)
            else:
                actual = display(dispatch(store, command))
            if row["url"] == "/api/preview-jobs":
                # The retained POST acknowledges a job; replay its command synchronously.
                if any(
                    op.get("mm") == "0" and op.get("id") == "sketch1.width"
                    for op in command.get("operations", [])
                ):
                    assert actual["error"]["code"] == "invalid_profile"
                    invalid += 1
                else:
                    assert "result" in actual, actual
            else:
                same_reply(browser_numbers(actual), row["reply"])
            if command.get("action") in ("commit", "import"):
                commits += 1
            else:
                assert (
                    store.path.read_bytes() if store.path.exists() else None
                ) == before
        assert store.load() == Store(EXAMPLE / "browser-final.cad.json").load()
        assert commits == 7 and invalid == 1
    selected = [r["reply"]["result"] for r in calls if r["url"] == "/api/selection"]
    assert selected[-1]["selected_surface"]["support"]["offset"] == "3"
    assert (
        selected[-1]["selected_surface"]["reference"]
        == "feature/part/hole/left/shoulder"
    )
    print(
        f"PASS: {len(calls)} browser commands, {commits} saves/imports, repaired collapsed rectangle and reselected named shoulder at edited depth"
    )


if __name__ == "__main__":
    main()
