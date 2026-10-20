"""Replay retained density reads and independently verify SI conversions."""

from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import tempfile
from measurements import dispatch_measure
from store import ROOT, Store

EXAMPLE = ROOT / "examples/ai-cad/mass"


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
                reply = dispatch_measure(store, call[key])
                assert reply == call["reply"], (filename, call[key])
                if "result" in reply:
                    result = reply["result"]
                    assert result["volume_mm3"] == "80"
                    assert result["centroid_mm"] == ["5", "2", "1"]
                    if "mass_properties" in result:
                        mass = result["mass_properties"]
                        expected = F(80, 10**9) * F(call[key]["density_kg_per_m3"])
                        assert F(mass["mass_kg"]) == expected
                        sides = [F(10, 1000), F(4, 1000), F(2, 1000)]
                        for i in range(3):
                            for j in range(3):
                                moment = (
                                    expected
                                    * sum(sides[k] ** 2 for k in range(3) if k != i)
                                    / 12
                                    if i == j
                                    else F(0)
                                )
                                assert (
                                    F(mass["centroidal_inertia_kg_m2"][i][j]) == moment
                                )
                assert path.read_bytes() == source
                count += 1
    runtime = json.loads((EXAMPLE / "browser-runtime.json").read_text())
    assert (
        runtime["native_sha256_before"]
        == runtime["native_sha256_after"]
        == hashlib.sha256(source).hexdigest()
    )
    print(
        f"PASS: {count} browser/MCP reads, independent mass/inertia SI conversion and unchanged document"
    )


if __name__ == "__main__":
    main()
