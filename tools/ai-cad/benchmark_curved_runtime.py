"""Isolated CPU/RSS and fresh-process versus worker latency for integrated geometry."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import statistics
import subprocess
import sys
import time
from engine_transport import NativeWorker
from store import BINARY, ROOT, encode

EXAMPLE = ROOT / "examples/ai-cad/curved-runtime"
CASES = {
    "revolution": "revolution/stepped.model.json",
    "tapered_ring": "revolution/tapered_ring.model.json",
    "concave_sweep": "straight-sweep/concave.model.json",
    "curved_intersection": "coaxial-intersection/conical_ring.model.json",
    "blind_cut": "coaxial-booleans/blind_cut.model.json",
    "stepped_union": "coaxial-booleans/stepped_union.model.json",
    "nested_cut": "coaxial-booleans/nested.model.json",
}
MODES = {
    "evaluate": None,
    "mesh": "--mesh",
    "topology": "--topology",
    "measure": "--measure",
}


def request(case, operation):
    model = json.loads((ROOT / "examples/ai-cad" / CASES[case]).read_text())
    if operation == "evaluate":
        return dict(schema_version=1, model=model, operations=[], preserve=[])
    result = dict(model=model, feature_id=model["features"][-1]["id"])
    if operation == "mesh":
        result.update(segments=128, include_surfaces=True)
    return result


def cpu(usage):
    return usage.ru_utime + usage.ru_stime


def phase(case, operation, transport, samples):
    # A separate driver process for each phase prevents other cases' child RSS
    # high-water marks and CPU counters from contaminating this measurement.
    data = encode(request(case, operation))
    mode = MODES[operation]
    command = [str(BINARY)] + ([mode] if mode else [])
    worker = NativeWorker()
    host_before = resource.getrusage(resource.RUSAGE_SELF)
    native_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    expected = None
    wall = []
    try:
        for i in range(samples + 1):
            started = time.perf_counter()
            reply = (
                worker.run(BINARY, mode, data)
                if transport == "worker"
                else subprocess.run(
                    command, input=data, capture_output=True, check=True
                )
            )
            elapsed = (time.perf_counter() - started) * 1000
            assert reply.returncode == 0, reply.stdout
            decoded = json.loads(reply.stdout)
            assert "error" not in decoded, decoded
            if expected is None:
                expected = decoded
            else:
                assert decoded == expected, (case, operation, transport)
                wall.append(elapsed)
            # First call warms the transport/filesystem; CPU/RSS still include it.
            assert len(wall) == i
    finally:
        # RUSAGE_CHILDREN accounts for a worker only after it has been waited for.
        worker.close()
    native = resource.getrusage(resource.RUSAGE_CHILDREN)
    host = resource.getrusage(resource.RUSAGE_SELF)
    assert len(wall) == samples
    assert worker.starts == (1 if transport == "worker" else 0)
    calls = samples + 1
    native_ms = (cpu(native) - cpu(native_before)) * 1000
    return dict(
        case=case,
        operation=operation,
        transport=transport,
        native_calls_including_warmup=calls,
        native_processes=worker.starts if transport == "worker" else calls,
        wall_samples_ms=wall,
        wall_median_ms=statistics.median(wall),
        wall_min_ms=min(wall),
        wall_max_ms=max(wall),
        native_batch_cpu_ms=native_ms,
        native_cpu_ms_per_call_including_warmup=native_ms / calls,
        host_batch_cpu_ms=(cpu(host) - cpu(host_before)) * 1000,
        peak_native_rss_bytes=native.ru_maxrss
        * (1 if platform.system() == "Darwin" else 1024),
        reply_sha256=hashlib.sha256(encode(expected)).hexdigest(),
        request_sha256=hashlib.sha256(data).hexdigest(),
        response_bytes=len(reply.stdout),
    )


def hardware():
    result = dict(
        system=platform.system(),
        release=platform.release(),
        architecture=platform.machine(),
        python=platform.python_version(),
        logical_cpus=os.cpu_count(),
    )
    if platform.system() == "Darwin":

        def value(name):
            return subprocess.check_output(["sysctl", "-n", name], text=True).strip()

        result.update(
            cpu=value("machdep.cpu.brand_string"),
            physical_cpus=int(value("hw.physicalcpu")),
            memory_bytes=int(value("hw.memsize")),
        )
    return result


def benchmark(samples, write, output_dir):
    rows = []
    for index, (case, operation) in enumerate((c, o) for c in CASES for o in MODES):
        pair = {}
        # Alternate phase order across workloads; retain every measured sample.
        phases = ["fresh", "worker"] if index % 2 == 0 else ["worker", "fresh"]
        for transport in phases:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--phase",
                    transport,
                    "--case",
                    case,
                    "--operation",
                    operation,
                    "--samples",
                    str(samples),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            pair[transport] = json.loads(completed.stdout)
        assert pair["fresh"]["reply_sha256"] == pair["worker"]["reply_sha256"], (
            case,
            operation,
        )
        assert pair["fresh"]["request_sha256"] == pair["worker"]["request_sha256"]
        rows.append(
            dict(
                case=case,
                operation=operation,
                exact_replies_equal=True,
                transports=pair,
            )
        )
        print(
            f"{case}/{operation}: fresh {pair['fresh']['wall_median_ms']:.2f} ms; worker {pair['worker']['wall_median_ms']:.2f} ms",
            flush=True,
        )
    report = dict(
        recorded_at=datetime.now(timezone.utc).isoformat(),
        hardware=hardware(),
        binary_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),
        samples_per_phase=samples,
        models=CASES,
        results=rows,
        scope="Single serial native request at a time. Warm wall samples include process/pipe/JSON transport, excluding the driver's response comparison. Native batch CPU includes one warmup plus timed calls and process startup/shutdown; host batch CPU includes comparisons. Child RSS is the maximum native-process high-water mark for that isolated phase, not total host memory or a per-call allocation. No cross-request geometry cache, GPU compute, rendering, export, model inference, concurrency or timing pass threshold.",
    )
    if write:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "benchmark.json").write_text(json.dumps(report, indent=2) + "\n")
        for case in CASES:
            for operation in MODES:
                (output_dir / f"{case}-{operation}.request.json").write_text(
                    json.dumps(request(case, operation), indent=2) + "\n"
                )
    print(f"PASS: {len(rows)} workloads, isolated phases, exact fresh/worker replies")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=7, choices=range(1, 101))
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=EXAMPLE)
    parser.add_argument("--phase", choices=["fresh", "worker"])
    parser.add_argument("--case", choices=list(CASES))
    parser.add_argument("--operation", choices=list(MODES))
    args = parser.parse_args()
    if args.phase:
        if not args.case or not args.operation:
            parser.error("--phase requires --case and --operation")
        print(json.dumps(phase(args.case, args.operation, args.phase, args.samples)))
    else:
        benchmark(args.samples, args.write, args.output_dir)
