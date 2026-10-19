"""Measure host operation latency, including Rust launch and full history validation.

This is an informational baseline, not a GPU benchmark or a CI timing gate.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time

from store import BINARY, ROOT, Store, evaluate


def measure(name, action, samples):
    durations = []
    for _ in range(samples):
        start = time.perf_counter_ns()
        action()
        durations.append((time.perf_counter_ns() - start) / 1_000_000)
    ordered = sorted(durations)
    return {
        "name": name,
        "samples_ms": durations,
        "first_sample_ms": durations[0],
        "median_ms": statistics.median(durations),
        "p95_ms": ordered[math.ceil(0.95 * len(ordered)) - 1],
    }


def main(samples):
    fixture = ROOT / "examples/ai-cad/relationships"
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory) / "part.cad.json")
        result = store.execute(json.loads((fixture / "create.json").read_text()))
        model = result["model"]
        rows.append(
            measure(
                "evaluate_profile_with_relationship", lambda: evaluate(model), samples
            )
        )
        rows.append(
            measure(
                "inspect_one_undo_snapshot",
                lambda: store.execute({"action": "inspect"}),
                samples,
            )
        )
        for revision in range(1, 65):
            store.execute(
                {
                    "action": "commit",
                    "expected_revision": revision,
                    "transaction_id": f"width-{revision}",
                    "operations": [
                        {"op": "adjust_parameter", "id": "width", "delta_mm": "1"}
                    ],
                    "preserve": ["depth", "shoulder", "thickness", "zero"],
                }
            )
        assert len(store.load()["undo"]) == 64
        rows.append(
            measure(
                "inspect_64_undo_snapshots",
                lambda: store.execute({"action": "inspect"}),
                samples,
            )
        )
        command = {
            "action": "preview",
            "expected_revision": 65,
            "operations": [{"op": "adjust_parameter", "id": "width", "delta_mm": "1"}],
            "preserve": ["depth", "shoulder", "thickness", "zero"],
        }
        rows.append(
            measure(
                "preview_64_undo_snapshots", lambda: store.execute(command), samples
            )
        )
    sources = [
        *sorted((ROOT / "crates/model-engine/src").glob("*.rs")),
        ROOT / "experiments/2026-10-15-rust-boundary/src/lib.rs",
        Path(__file__),
        ROOT / "tools/ai-cad/store.py",
    ]
    return {
        "schema_version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "base_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "working_tree_dirty": bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=ROOT, text=True
            )
        ),
        "platform": platform.system(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "binary_sha256": hashlib.sha256(BINARY.read_bytes()).hexdigest(),
        "source_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sources
        },
        "rows": rows,
        "limits": "Wall-clock host latency on the current machine, including JSON/process overhead and repeated CPU validation. Sequential samples share OS caches; first sample is not a certified cold start. No isolated kernel timing, GPU timing, memory measurement or general performance guarantee. History workload contains 64 actual accepted edits of a small part.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 3 <= args.samples <= 100:
        parser.error("samples must be between 3 and 100")
    report = main(args.samples)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    else:
        print(json.dumps(report, indent=2))
    for row in report["rows"]:
        print(
            f"{row['name']}: median {row['median_ms']:.2f} ms, p95 {row['p95_ms']:.2f} ms",
            file=sys.stderr,
        )
