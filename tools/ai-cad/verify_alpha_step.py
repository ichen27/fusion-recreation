"""Round-trip the alpha's retained models through the explicit STEP adapter."""

import argparse
import json
import math
from pathlib import Path
import tempfile
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from step_export import export_step, measure
from store import ROOT, Store

EXAMPLE = ROOT / "examples/ai-cad/modelling-alpha"


def main(write=False):
    rows = []
    for name, expected in [
        ("rectangular-plate", 43200),
        ("counterbored-mount", 36000 - 204 * math.pi),
        ("turned-spacer", 1365 * math.pi),
    ]:
        with tempfile.TemporaryDirectory() as directory:
            body = Store(EXAMPLE / name / "edited.cad.json").execute(
                dict(action="inspect")
            )["bodies"][0]
            path = Path(directory) / "part.step"
            result = export_step(body, path)
            assert result["solid_count"] == 1
            reader = STEPControl_Reader()
            assert (
                reader.ReadFile(str(path)) == IFSelect_RetDone
                and reader.TransferRoots()
            )
            shape = reader.OneShape()
            assert BRepCheck_Analyzer(shape).IsValid()
            actual = measure(shape)
            assert abs(actual - expected) < 1e-6
            if write:
                (EXAMPLE / name / "edited.step").write_bytes(path.read_bytes())
            rows.append(
                dict(
                    part=name,
                    valid=True,
                    solids=1,
                    expected_volume_mm3=expected,
                    step_volume_mm3=actual,
                )
            )
    if write:
        (EXAMPLE / "step-verification.json").write_text(
            json.dumps(rows, indent=2) + "\n"
        )
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    main(parser.parse_args().write)
