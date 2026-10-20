"""Replay native material history and real browser preview/save/clear/undo."""

import hashlib
import json
from pathlib import Path
import tempfile
from store import ROOT, Store, dispatch
from materials import dispatch_material_mass
from exports import display
from verify_coaxial import same_reply as compare_reply

EXAMPLE = ROOT / "examples/ai-cad/materials"


def same_reply(actual, recorded):
    # Browser JSON turns integral floating-point display volumes into integers.
    # Canonical native volume strings and all material/history values stay strict.
    for reply in (actual, recorded):
        for body in reply.get("result", {}).get("bodies", []):
            if "volume_approx_mm3" in body:
                body["volume_approx_mm3"] = float(body["volume_approx_mm3"])
    compare_reply(actual, recorded)


def main():
    mcp = json.loads((EXAMPLE / "mcp-recording.json").read_text())["calls"]
    browser = json.loads((EXAMPLE / "browser-recording.json").read_text())["calls"]
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory) / "part.cad.json")
        for index, call in enumerate(mcp):
            args = call["arguments"]
            before = store.path.read_bytes() if store.path.exists() else None
            if call["tool"] == "cad_material_mass":
                actual = dispatch_material_mass(store, args)
                assert store.path.read_bytes() == before
            else:
                action = {"cad_commit": "commit", "cad_preview": "preview"}.get(
                    call["tool"]
                )
                actual = dispatch(store, {**args, "action": action} if action else args)
            assert actual == call["reply"]
            if index in (0, 3, 5, 7, 9):
                name = {
                    0: "source",
                    3: "override",
                    5: "edited",
                    7: "inherited",
                    9: "undo",
                }[index]
                assert store.load() == Store(EXAMPLE / f"{name}.cad.json").load()
        store.path.write_bytes((EXAMPLE / "browser-source.cad.json").read_bytes())
        jobs = {
            r["reply"]["result"]["job_id"]: r["reply"]["result"]
            for r in browser
            if r["url"].startswith("/api/preview-jobs?")
            and "reply" in r["reply"]["result"]
        }
        commits = 0
        for row in browser:
            before = store.path.read_bytes()
            command = row["command"]
            if row["url"] == "/api/material-mass":
                assert dispatch_material_mass(store, command) == row["reply"]
            elif row["url"].startswith("/api/preview-jobs"):
                if command:
                    same_reply(
                        display(dispatch(store, command)),
                        jobs[row["reply"]["result"]["job_id"]]["reply"],
                    )
            else:
                same_reply(display(dispatch(store, command)), row["reply"])
                if command["action"] in ("commit", "undo"):
                    if command["action"] == "commit":
                        stage = ["override", "inherited"][commits]
                        commits += 1
                    else:
                        stage = "undo"
                    assert (
                        store.load()
                        == Store(EXAMPLE / f"browser-{stage}.cad.json").load()
                    )
                    continue
            assert store.path.read_bytes() == before
        assert commits == 2
        assert json.loads(store.path.read_text()) == json.loads(
            (EXAMPLE / "browser-download.cad.json").read_text()
        )
    for name in ["source", "override", "edited", "inherited", "undo"]:
        state = Store(EXAMPLE / f"{name}.cad.json").load()
        assert (
            state["model"]["parameters"]
            == Store(EXAMPLE / "source.cad.json").load()["model"]["parameters"]
        )
    base_features = Store(EXAMPLE / "source.cad.json").load()["model"]["features"]
    for name in ["override", "edited", "inherited", "undo"]:
        assert (
            Store(EXAMPLE / f"{name}.cad.json").load()["model"]["features"]
            == base_features
        )
    runtime = json.loads((EXAMPLE / "browser-runtime.json").read_text())
    assert (
        runtime["native_sha256_before"]
        == hashlib.sha256(
            (EXAMPLE / "browser-source.cad.json").read_bytes()
        ).hexdigest()
    )
    assert (
        runtime["native_sha256_after"]
        == hashlib.sha256((EXAMPLE / "browser-undo.cad.json").read_bytes()).hexdigest()
    )
    audit = json.loads((EXAMPLE / "browser-audit.json").read_text())
    assert audit["customDensityDisplay"] == "none" and "3/12500" in audit["text"]
    print(
        f"PASS: {len(mcp)} MCP/{len(browser)} browser calls, native material stages, exact mass, unchanged geometry, clear/inheritance, undo and native download"
    )


if __name__ == "__main__":
    main()
