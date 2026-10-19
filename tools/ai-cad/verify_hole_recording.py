"""Replay actual browser hole commands, native snapshots, display mesh and undo."""

import copy
from fractions import Fraction
import json
import math
from pathlib import Path
import tempfile

from store import ROOT, Store
from test_holes import audit_triangles, read_stl


def main():
    example = ROOT / "examples/ai-cad/hole-editor"
    recording = json.loads((example / "browser-recording.json").read_text())
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.cad.json"
        path.write_bytes((example / "base.cad.json").read_bytes())
        store = Store(path)
        commits = 0
        for row in recording["calls"]:
            before = path.read_bytes()
            result = {"result": store.execute(row["command"])}
            recorded = copy.deepcopy(row["reply"])
            for body in recorded["result"]["bodies"]:
                mesh = body.pop("display_mesh")
                approximate = body.pop("volume_approx_mm3")
                v = body["analytic"]["volume"]
                constant, coefficient = (
                    float(Fraction(v[k])) for k in ("constant_mm3", "pi_subtract_mm3")
                )
                assert abs(approximate - (constant - coefficient * math.pi)) < 1e-8
                actual = audit_triangles(
                    [
                        [tuple(mesh["vertices"][i]) for i in t]
                        for t in mesh["triangles"]
                    ],
                    2,
                )
                assert (
                    abs(
                        actual
                        - (constant - coefficient * 64 * math.sin(2 * math.pi / 64) / 2)
                    )
                    < 1e-6
                )
            # Exact semantic output is portable; libm display vertices may differ.
            assert result == recorded
            if row["command"]["action"] == "preview":
                assert path.read_bytes() == before
            else:
                name = ("create", "edit")[commits]
                commits += 1
                assert json.loads(path.read_text()) == json.loads(
                    (example / f"{name}.cad.json").read_text()
                )
        assert commits == 2
        state = Store(path).execute({"action": "inspect"})
        assert state["bodies"][0]["volume_mm3"] == "12000 - (125)*pi"
        undo = store.execute(
            {
                "action": "undo",
                "expected_revision": 3,
                "transaction_id": "verify-hole-undo",
            }
        )
        assert undo["bodies"][0]["volume_mm3"] == "12000 - (90)*pi"
        assert undo["model"]["features"] == state["model"]["features"]
    archived = read_stl((example / "plate.stl").read_bytes())
    assert (
        abs(
            audit_triangles(archived, 2)
            - (12000 - 125 * 128 * math.sin(2 * math.pi / 128) / 2)
        )
        < 1e-6
    )
    print(
        "PASS: four actual browser hole commands, exact native state, display topology/volume, reopen and undo"
    )


if __name__ == "__main__":
    main()
