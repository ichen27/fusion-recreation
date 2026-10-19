"""Replay actual viewport-selected native references and audit retained mesh provenance."""

import json
from pathlib import Path
import tempfile
from store import ROOT, Store
from selection import dispatch_selection
from topology import topology_model
from exports import tessellate

EXAMPLE = ROOT / "examples/ai-cad/surface-picking"


def main():
    rows = json.loads((EXAMPLE / "browser-recording.json").read_text())["calls"]
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.json"
        path.write_bytes((EXAMPLE / "input.cad.json").read_bytes())
        before = path.read_bytes()
        store = Store(path)
        for row in rows:
            assert row["url"] == "/api/selection"
            assert row["command"]["action"] == "select_surface"
            assert dispatch_selection(store, row["command"]) == row["reply"]
            assert path.read_bytes() == before
        assert [r["command"]["surface_id"] for r in rows] == [
            "feature/solid/cap/top",
            "feature/part/hole/left/upper",
            "feature/part/hole/left/shoulder",
        ]
        model = store.load()["model"]
        mesh = tessellate(model, "part", include_surfaces=True)
        assert mesh == json.loads((EXAMPLE / "tagged-mesh.json").read_text())
        topology = topology_model(model, "part")
        assert set(mesh["triangle_surfaces"]) == set(topology["surfaces"])
        assert len(mesh["triangle_surfaces"]) == len(mesh["triangles"])
    metrics = json.loads((EXAMPLE / "orbit-metrics.json").read_text())
    assert metrics["uploads"] == 0
    selected = [d for d in metrics["draws"] if d["mode"] == 4 and d["selected"] == 1]
    count = 3 * mesh["triangle_surfaces"].count("feature/part/hole/left/shoulder")
    assert selected and all(d["count"] == count for d in selected)
    print(
        "PASS: three actual viewport picks, exact native surface context, retained triangle provenance and zero-upload shoulder highlighting/orbit"
    )


if __name__ == "__main__":
    main()
