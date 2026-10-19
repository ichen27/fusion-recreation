"""Replay the all-browser empty-document/multi-part workflow and its downloaded ZIP."""

import io
import json
import math
from pathlib import Path
import tempfile
import zipfile
from store import ROOT, Store, dispatch
from exports import export_stl_archive
from test_holes import audit_triangles, read_stl

EXAMPLE = ROOT / "examples/ai-cad/browser-stock"


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.json"
        s = Store(path)
        mutations = 0
        for row in json.loads((EXAMPLE / "browser-recording.json").read_text())[
            "calls"
        ]:
            before = path.read_bytes() if path.exists() else None
            assert dispatch(s, row["command"]) == row["reply"]
            if row["command"]["action"] == "preview":
                assert (path.read_bytes() if path.exists() else None) == before
            else:
                if mutations in {1, 3, 4, 5}:
                    name = {1: "cut", 3: "parts", 4: "undo", 5: "final"}[mutations]
                    assert json.loads(path.read_text()) == json.loads(
                        (EXAMPLE / f"{name}.cad.json").read_text()
                    )
                mutations += 1
        assert mutations == 6
        state = Store(path).execute({"action": "inspect"})
        assert state["revision"] == 6
        assert {b["feature_id"]: b["volume_mm3"] for b in state["bodies"]} == {
            "holes1": "3900*pi",
            "plane1": "18000",
        }
        data, manifest = export_stl_archive(s, 6, 128)
        actual = (EXAMPLE / "parts.zip").read_bytes()
        with (
            zipfile.ZipFile(io.BytesIO(data)) as replayed,
            zipfile.ZipFile(io.BytesIO(actual)) as downloaded,
        ):
            assert downloaded.testzip() is None
            assert downloaded.namelist() == replayed.namelist()
            assert json.loads(downloaded.read("manifest.json")) == manifest
            for row in manifest["bodies"]:
                # Text floats may vary slightly across platforms; compare topology/volume.
                triangles = read_stl(downloaded.read(row["file"]))
                volume = audit_triangles(triangles, 0)
                expected = (
                    18000
                    if row["feature_id"] == "plane1"
                    else 3900 * 128 * math.sin(2 * math.pi / 128) / 2
                )
                assert abs(volume - expected) < 1e-6
                current = audit_triangles(read_stl(replayed.read(row["file"])), 0)
                assert abs(current - volume) < 1e-6
                assert len(triangles) == row["triangles"]
    print(
        "PASS: eleven actual browser calls from empty model, native checkpoints/reopen, downloaded multi-body ZIP topology/volume/manifest"
    )


if __name__ == "__main__":
    main()
