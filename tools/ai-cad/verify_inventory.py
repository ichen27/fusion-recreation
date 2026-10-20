"""Replay retained MCP and browser inventory evidence against native documents."""

import json
from pathlib import Path
import tempfile
from inventory import dispatch_inventory
from store import ROOT, Store, dispatch

EXAMPLE = ROOT / "examples/ai-cad/inventory"


def main():
    calls = json.loads((EXAMPLE / "mcp-recording.json").read_text())["calls"]
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory) / "part.cad.json")
        for row in calls:
            args = row["arguments"]
            before = store.path.read_bytes() if store.path.exists() else None
            if row["tool"] == "cad_inventory":
                actual = dispatch_inventory(store, args)
                assert store.path.read_bytes() == before
            else:
                action = {"cad_commit": "commit", "cad_preview": "preview"}.get(
                    row["tool"]
                )
                actual = dispatch(store, {**args, "action": action} if action else args)
            assert actual == row["reply"]
        assert store.load() == Store(EXAMPLE / "undo.cad.json").load()
        browser = json.loads((EXAMPLE / "browser-recording.json").read_text())["calls"]
        assert len(browser) == 7
        for index, row in enumerate(browser):
            source = "source" if index < 3 else "edited"
            store.path.write_bytes((EXAMPLE / f"{source}.cad.json").read_bytes())
            before = store.path.read_bytes()
            assert dispatch_inventory(store, row["command"]) == row["reply"]
            assert store.path.read_bytes() == before
        assert browser[3]["reply"]["error"]["code"] == "revision_conflict"
    for stage in ("source", "edited"):
        result = dispatch_inventory(
            Store(EXAMPLE / f"{stage}.cad.json"),
            dict(expected_revision=1 if stage == "source" else 2),
        )["result"]
        assert result["csv"].encode() == (EXAMPLE / f"{stage}.csv").read_bytes()
        expected = {k: v for k, v in result.items() if k != "csv"}
        assert expected == json.loads((EXAMPLE / f"{stage}.json").read_text())
        assert expected == json.loads((EXAMPLE / f"browser-{stage}.json").read_text())
    assert (EXAMPLE / "source.csv").read_bytes() == (
        EXAMPLE / "browser-source.csv"
    ).read_bytes()
    audit = json.loads((EXAMPLE / "browser-audit.json").read_text())
    assert audit["staleDisabled"] and audit["staleStatus"].startswith(
        "revision_conflict:"
    )
    assert audit["documents_unchanged_by_reads"]
    print(
        f"PASS: {len(calls)} recorded MCP / {len(browser)} browser calls; exact CSV/JSON exports, stale rejection and native history"
    )


if __name__ == "__main__":
    main()
