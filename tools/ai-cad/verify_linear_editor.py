"""Replay browser-authored coupled constraints, repair, replacement and exports."""

import json
from pathlib import Path
import tempfile
import zipfile
from store import ROOT, Store, dispatch
from exports import display
from verify_coaxial import same_reply
from test_holes import read_stl, audit_triangles

EXAMPLE = ROOT / "examples/ai-cad/linear-editor"


def main():
    rows = json.loads((EXAMPLE / "browser-recording.json").read_text())["calls"]
    jobs = {
        row["reply"]["result"]["job_id"]: row["reply"]["result"]
        for row in rows
        if row["url"].startswith("/api/preview-jobs?")
        and "reply" in row["reply"]["result"]
    }
    commits = rejected = 0
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.json"
        path.write_bytes((EXAMPLE / "browser-source.cad.json").read_bytes())
        store = Store(path)
        for row in rows:
            before = path.read_bytes()
            command = row["command"]
            if row["url"].startswith("/api/preview-jobs"):
                if command:
                    actual = display(dispatch(store, command))
                    same_reply(actual, jobs[row["reply"]["result"]["job_id"]]["reply"])
                    rejected += int("error" in actual)
            else:
                actual = display(dispatch(store, command))
                same_reply(actual, row["reply"])
                if command["action"] in ("commit", "undo") and "result" in actual:
                    if command["action"] == "commit":
                        stage = ["created", "edited", "replaced"][commits]
                        commits += 1
                    else:
                        stage = "undo"
                    assert json.loads(path.read_text()) == json.loads(
                        (EXAMPLE / f"browser-{stage}.cad.json").read_text()
                    )
                    continue
            assert path.read_bytes() == before
        assert commits == 3 and rejected == 1
        result = store.execute(dict(action="inspect"))
        assert result["revision"] == 5
        assert result["model"]["parameters"]["left"] == "80"
        assert result["model"]["parameters"]["right"] == "40"
        assert result["model"]["parameters"]["offset"] == "90"
        assert result["model"]["relations"]["left"]["terms"] == {
            "gap": "-2/3",
            "span": "2/3",
        }
    replacement = json.loads((EXAMPLE / "browser-replaced.cad.json").read_text())[
        "state"
    ]["model"]
    assert (
        replacement["parameters"]["left"] == replacement["parameters"]["right"] == "60"
    )
    assert replacement["parameters"]["offset"] == "70"
    assert (
        replacement["relations"]["left"]["terms"]
        == replacement["relations"]["right"]["terms"]
        == {"gap": "-1/2", "span": "1/2"}
    )
    assert json.loads(
        (EXAMPLE / "browser-download.cad.json").read_text()
    ) == json.loads((EXAMPLE / "browser-edited.cad.json").read_text())
    with zipfile.ZipFile(EXAMPLE / "browser-edited.zip") as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["revision"] == 3
        for body, volume, bounds in zip(
            manifest["bodies"], [16000, 8000], [(0, 80), (90, 130)]
        ):
            triangles = read_stl(archive.read(body["file"]))
            assert abs(audit_triangles(triangles, 0) - volume) < 1e-8
            xs = [point[0] for triangle in triangles for point in triangle]
            assert (min(xs), max(xs)) == bounds
    audit = json.loads((EXAMPLE / "browser-audit.json").read_text())
    assert audit["dialogOpen"] and "linear_underdetermined" in audit["rankDiagnostic"]
    assert audit["terms"] == ["left", "right", "gap", "span"]
    assert set(audit["targets"]) == {"left", "right"}
    assert all(row["disabled"] for row in audit["derived"])
    print(
        f"PASS: {len(rows)} actual browser calls, retained invalid draft, exact constraint creation/replacement, source edit, undo, native download and correctly placed STL parts"
    )


if __name__ == "__main__":
    main()
