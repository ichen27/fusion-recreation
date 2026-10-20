"""Measure transaction rebuilds with isolated CPU/RSS phases and exact baseline replies."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import resource
import statistics
import subprocess
import sys
import time
from engine_transport import NativeWorker
from store import BINARY, ROOT, encode
from test_booleans import cases
from benchmark_curved_runtime import hardware, cpu

EXAMPLE = ROOT / "examples/ai-cad/independent-rebuild"


def model():
    result = dict(parameters={}, features=[], fixed={})
    for i in range(4):
        source = cases()["cavity"][0]
        ids = set(source["parameters"]) | {f["id"] for f in source["features"]}

        def rename(value):
            if isinstance(value, str):
                return f"p{i}.{value}" if value in ids else value
            if isinstance(value, list):
                return [rename(v) for v in value]
            if isinstance(value, dict):
                return {rename(k): rename(v) for k, v in value.items()}
            return value

        part = rename(source)
        result["parameters"].update(part["parameters"])
        result["features"].extend(part["features"])
    return result


def requests():
    base = model()
    result = {}
    for name, parameter in [
        ("first_branch", "p0.a.height"),
        ("last_branch", "p3.a.height"),
        ("first_profile", "p0.a.c1"),
    ]:
        assert parameter in base["parameters"]
        result[name] = dict(
            schema_version=1,
            model=base,
            operations=[dict(op="set_parameter", id=parameter, mm="11")],
            preserve=[],
        )
    linked = json.loads(json.dumps(base))
    linked["relations"] = {
        "p3.a.height": dict(offset_mm="0", terms={"p0.a.height": "1"})
    }
    result["linked_branches"] = dict(
        schema_version=1,
        model=linked,
        operations=[dict(op="set_parameter", id="p0.a.height", mm="11")],
        preserve=[],
    )
    result["constraint_only"] = dict(
        schema_version=1,
        model=base,
        operations=[dict(op="fix_parameter", id="p0.a.height")],
        preserve=[],
    )
    return result


def phase(binary, case, samples):
    request = encode(requests()[case])
    worker = NativeWorker()
    native_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    host_before = resource.getrusage(resource.RUSAGE_SELF)
    walls = []
    expected = None
    try:
        for i in range(samples + 1):
            start = time.perf_counter()
            output = worker.run(binary, None, request)
            elapsed = (time.perf_counter() - start) * 1000
            assert output.returncode == 0, output.stdout
            reply = json.loads(output.stdout)
            if expected is None:
                expected = reply
            else:
                assert reply == expected
                walls.append(elapsed)
    finally:
        worker.close()
    native = resource.getrusage(resource.RUSAGE_CHILDREN)
    host = resource.getrusage(resource.RUSAGE_SELF)
    return dict(
        case=case,
        samples=samples,
        wall_samples_ms=walls,
        wall_median_ms=statistics.median(walls),
        native_batch_cpu_ms=(cpu(native) - cpu(native_before)) * 1000,
        host_batch_cpu_ms=(cpu(host) - cpu(host_before)) * 1000,
        peak_native_rss_bytes=native.ru_maxrss
        * (1 if platform.system() == "Darwin" else 1024),
        native_calls_including_warmup=samples + 1,
        worker_starts=worker.starts,
        request_sha256=hashlib.sha256(request).hexdigest(),
        reply_sha256=hashlib.sha256(encode(expected)).hexdigest(),
    )


def main(args):
    if args.phase:
        print(json.dumps(phase(args.binary, args.case, args.samples)))
        return
    results = []
    for i, (name, request) in enumerate(requests().items()):
        row = {"case": name}
        binaries = [("current", BINARY)] + (
            [("baseline", args.baseline)] if args.baseline else []
        )
        if i % 2:
            binaries.reverse()
        fresh = []
        for label, binary in binaries:
            fresh_reply = subprocess.run(
                [str(binary)], input=encode(request), capture_output=True, check=True
            )
            fresh.append(json.loads(fresh_reply.stdout))
            run = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--phase",
                    "--binary",
                    str(binary),
                    "--case",
                    name,
                    "--samples",
                    str(args.samples),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            row[label] = json.loads(run.stdout)
            assert (
                row[label]["reply_sha256"]
                == hashlib.sha256(encode(fresh[-1])).hexdigest()
            )
            if args.write:
                EXAMPLE.mkdir(parents=True, exist_ok=True)
                (EXAMPLE / f"{name}.request.json").write_text(
                    json.dumps(request, indent=2) + "\n"
                )
        assert all(r == fresh[0] for r in fresh)
        results.append(row)
    report = dict(
        recorded_at=datetime.now(timezone.utc).isoformat(),
        hardware=hardware(),
        scope="Serial transaction requests. Native CPU/RSS includes warmup and worker startup/shutdown; wall samples exclude warmup. Every baseline/current fresh/worker response agrees exactly. No host cache, browser, concurrent workload or GPU measurement.",
        current_binary_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),
        results=results,
    )
    if args.baseline:
        report["baseline_binary_sha256"] = hashlib.sha256(
            args.baseline.read_bytes()
        ).hexdigest()
    if args.write:
        (EXAMPLE / "benchmark.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=7)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--phase", action="store_true")
    parser.add_argument("--binary", type=Path, default=BINARY)
    parser.add_argument("--case", choices=list(requests()))
    args = parser.parse_args()
    if not 1 <= args.samples <= 100:
        parser.error("Use 1..100 samples")
    main(args)
