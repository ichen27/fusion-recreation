"""Compare whole-request CPU/wall cost and exact replies of two engine revisions."""

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import resource
import statistics
import subprocess
import time
from store import BINARY, ROOT, encode


def cases():
    cavity = json.loads(
        (ROOT / "examples/ai-cad/planar-booleans/cavity.model.json").read_text()
    )
    late = copy.deepcopy(cavity)
    late["parameters"]["late.height"] = "4"
    late["features"].append(
        dict(kind="block", id="late", width="a.c1", depth="a.c1", height="late.height")
    )
    linked = dict(
        parameters={
            "width": "10",
            "height": "5",
            "zero": "0",
            "step": "20",
            "last": "30",
        },
        fixed={},
        features=[
            dict(kind="block", id="part", width="width", depth="width", height="height")
        ],
    )
    for i in range(31):
        linked["features"].append(
            dict(
                kind="instance",
                id=f"copy{i}",
                source="part" if i == 0 else f"copy{i - 1}",
                offset=["last" if i == 30 else "step", "zero", "zero"],
            )
        )

    def edit(id, mm):
        return [dict(op="set_parameter", id=id, mm=mm)]

    rows = [
        ("cavity_inspect", cavity, []),
        ("cavity_dimension_edit", cavity, edit("a.height", "11")),
        ("late_independent_edit", late, edit("late.height", "6")),
        ("linked_32_inspect", linked, []),
        ("linked_32_last_placement", linked, edit("last", "35")),
        ("linked_32_root_dimension", linked, edit("height", "6")),
    ]
    return {
        name: dict(schema_version=1, model=model, operations=operations, preserve=[])
        for name, model, operations in rows
    }


def run(binary, data):
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu = usage.ru_utime + usage.ru_stime
    start = time.perf_counter()
    process = subprocess.run([str(binary)], input=data, capture_output=True, timeout=20)
    wall = (time.perf_counter() - start) * 1000
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu = (usage.ru_utime + usage.ru_stime - cpu) * 1000
    result = json.loads(process.stdout)
    if process.returncode or "error" in result:
        raise RuntimeError(result)
    return result, wall, cpu


def benchmark(before, after, samples, directory):
    directory.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, request in cases().items():
        (directory / f"{name}.request.json").write_text(
            json.dumps(request, indent=2) + "\n"
        )
        data = encode(request)
        expected, _, _ = run(before, data)
        actual, _, _ = run(after, data)
        assert actual == expected, name
        (directory / f"{name}.response.json").write_text(
            json.dumps(expected, indent=2) + "\n"
        )
        measurements = {"before": [], "after": []}
        for sample in range(samples):
            # Alternate order to reduce systematic warmup/order bias.
            order = [("before", before), ("after", after)]
            if sample % 2:
                order.reverse()
            for label, binary in order:
                result, wall, cpu = run(binary, data)
                assert result == expected, name
                measurements[label].append(dict(wall_ms=wall, cpu_ms=cpu))
        row = dict(
            name=name,
            features=len(request["model"]["features"]),
            exact_reply_sha256=hashlib.sha256(encode(expected)).hexdigest(),
        )
        for label, values in measurements.items():
            row[label] = dict(
                samples=values,
                wall_median_ms=statistics.median(v["wall_ms"] for v in values),
                cpu_median_ms=statistics.median(v["cpu_ms"] for v in values),
            )
        row["wall_speedup"] = (
            row["before"]["wall_median_ms"] / row["after"]["wall_median_ms"]
        )
        rows.append(row)
        print(
            name,
            round(row["before"]["wall_median_ms"], 2),
            "->",
            round(row["after"]["wall_median_ms"], 2),
            "ms",
            flush=True,
        )
    peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    result = dict(
        recorded_at=datetime.now(timezone.utc).isoformat(),
        platform=platform.platform(),
        python=platform.python_version(),
        source_base_commit=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        binaries={
            label: hashlib.sha256(binary.read_bytes()).hexdigest()
            for label, binary in [("before", before), ("after", after)]
        },
        samples_per_case=samples,
        rows=rows,
        largest_child_peak_rss_bytes=peak
        if platform.system() == "Darwin"
        else peak * 1024,
        limits="One machine, fresh CLI subprocess per sample, shared OS caches, sequential alternate-order measurements. CPU includes reaped children; RSS is the largest child high-water mark across the run, not a per-operation or simultaneous total. Exact JSON equality checked for every reply. No timing pass threshold, cross-request feature reuse, GPU compute or general throughput guarantee.",
    )
    (directory / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, default=BINARY)
    parser.add_argument("--samples", type=int, default=7)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 3 <= args.samples <= 30:
        parser.error("Use 3..30 samples")
    benchmark(args.before.resolve(), args.after.resolve(), args.samples, args.output)
