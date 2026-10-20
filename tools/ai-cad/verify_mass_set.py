"""Replay read-only mass selection evidence with independent block formulas."""

from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import tempfile
from store import ROOT, Store
from mass_properties import dispatch_mass_set
from test_mass_set import independent

EXAMPLE = ROOT / "examples/ai-cad/combined-mass"


def main():
    source = (EXAMPLE / "source.cad.json").read_bytes()
    count = 0
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.cad.json"
        path.write_bytes(source)
        store = Store(path)
        for filename, key in [
            ("browser-recording.json", "command"),
            ("mcp-recording.json", "arguments"),
        ]:
            for call in json.loads((EXAMPLE / filename).read_text())["calls"]:
                command = call[key]
                reply = dispatch_mass_set(store, command)
                assert reply == call["reply"], (filename, command)
                if "result" in reply:
                    result = reply["result"]
                    selected = command["parts"]
                    masses = [
                        F(80, 10**9) * F(p["density_kg_per_m3"]) for p in selected
                    ]
                    centers = [
                        [F(5), F(2), F(1)]
                        if p["feature_id"] == "box"
                        else [F(25), F(32), F(41)]
                        for p in selected
                    ]
                    lengths = [F(10, 1000), F(4, 1000), F(2, 1000)]
                    own = [
                        [
                            [
                                m
                                * sum(lengths[k] ** 2 for k in range(3) if k != i)
                                / 12
                                if i == j
                                else F(0)
                                for j in range(3)
                            ]
                            for i in range(3)
                        ]
                        for m in masses
                    ]
                    mass, center, tensor = independent(masses, centers, own)
                    assert F(result["mass_kg"]) == mass
                    assert list(map(F, result["center_of_mass_mm"])) == center
                    assert [
                        [F(v) for v in row]
                        for row in result["centroidal_inertia_kg_m2"]
                    ] == tensor
                    assert result["overlap_policy"] == "count_each_selected_occurrence"
                assert path.read_bytes() == source
                count += 1
    runtime = json.loads((EXAMPLE / "browser-runtime.json").read_text())
    assert (
        runtime["native_sha256_before"]
        == runtime["native_sha256_after"]
        == hashlib.sha256(source).hexdigest()
    )
    print(
        f"PASS: {count} recorded browser/MCP reads, independent mixed-density center/tensor and unchanged native bytes"
    )


if __name__ == "__main__":
    main()
