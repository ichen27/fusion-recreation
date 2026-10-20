"""Compare fresh CLI processes with a reused stateless worker and exact replies."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import platform
import statistics
import subprocess
import time
from benchmark_rebuild import cases
from engine_transport import NativeWorker
from store import BINARY, ROOT, encode
from test_countersinks import countersunk
from test_planar_loft import loft

EXAMPLE = ROOT / "examples/ai-cad/native-worker"


def benchmark(samples=15, write=False):
    scenarios = [(name, None, request) for name, request in cases().items()]
    for mode in ("--mesh", "--explain", "--measure", "--topology"):
        model = countersunk() if mode == "--mesh" else loft()
        request = dict(model=model, feature_id="part")
        if mode == "--mesh":
            request.update(segments=128, include_surfaces=True)
        scenarios.append((mode[2:], mode, request))
    worker = NativeWorker()
    rows = []
    try:
        for name, mode, request in scenarios:
            data = encode(request)
            command = [str(BINARY)] + ([mode] if mode else [])
            expected = subprocess.run(
                command, input=data, capture_output=True, check=True
            ).stdout
            assert json.loads(worker.run(BINARY, mode, data).stdout) == json.loads(
                expected
            )
            times = {"fresh_ms": [], "worker_ms": []}
            for sample in range(samples):
                order = list(times)
                if sample % 2:
                    order.reverse()
                for label in order:
                    started = time.perf_counter()
                    result = (
                        subprocess.run(
                            command, input=data, capture_output=True, check=True
                        )
                        if label == "fresh_ms"
                        else worker.run(BINARY, mode, data)
                    )
                    times[label].append((time.perf_counter() - started) * 1000)
                    assert json.loads(result.stdout) == json.loads(expected), name
            rows.append(
                dict(
                    case=name,
                    mode=mode,
                    median_ms={k: statistics.median(v) for k, v in times.items()},
                    samples=times,
                    reply_sha256=hashlib.sha256(expected).hexdigest(),
                    exact_replies_equal=True,
                )
            )
            if write:
                EXAMPLE.mkdir(parents=True, exist_ok=True)
                (EXAMPLE / (name + ".request.json")).write_text(
                    json.dumps(request, indent=2) + "\n"
                )
        assert worker.starts == 1
        result = dict(
            recorded_at=datetime.now(timezone.utc).isoformat(),
            platform=dict(
                system=platform.system(),
                release=platform.release(),
                architecture=platform.machine(),
                python=platform.python_version(),
            ),
            binary_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),
            samples_per_case=samples,
            worker_starts=worker.starts,
            worker_requests=worker.requests,
            results=rows,
            scope="Wall latency only; includes host framing/JSON validation. Warm worker, alternating order. No cross-request geometry cache, parallel geometry or GPU compute.",
        )
        if write:
            (EXAMPLE / "benchmark.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({row["case"]: row["median_ms"] for row in rows}, indent=2))
        print(
            f"PASS: {len(rows)} workloads, exact replies, {worker.requests} worker calls in one process"
        )
    finally:
        worker.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=15, choices=range(1, 101))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    benchmark(args.samples, args.write)
