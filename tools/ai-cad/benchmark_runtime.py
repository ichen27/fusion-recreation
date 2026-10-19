"""Host CPU/wall latency and process RSS high-water marks; no timing pass threshold."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import resource
import statistics
import subprocess
import tempfile
import time
from exports import display
from result_cache import ResultCache
from store import ROOT, Store


def cpu_seconds():
    values = [
        resource.getrusage(kind)
        for kind in (resource.RUSAGE_SELF, resource.RUSAGE_CHILDREN)
    ]
    return sum(v.ru_utime + v.ru_stime for v in values)


def peak_rss_bytes(kind):
    value = resource.getrusage(kind).ru_maxrss
    return value if platform.system() == "Darwin" else value * 1024


def measure(name, action, samples):
    wall = []
    cpu = []
    for _ in range(samples):
        c = cpu_seconds()
        t = time.perf_counter()
        action()
        wall.append((time.perf_counter() - t) * 1000)
        cpu.append((cpu_seconds() - c) * 1000)
    return {
        "name": name,
        "wall_samples_ms": wall,
        "cpu_samples_ms": cpu,
        "wall_median_ms": statistics.median(wall),
        "cpu_median_ms": statistics.median(cpu),
    }


def main(samples):
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.json"
        store = Store(path)
        store.execute(
            json.loads((ROOT / "examples/ai-cad/bracket/create.json").read_text())
        )
        for rev in range(1, 65):
            store.execute(
                {
                    "action": "commit",
                    "expected_revision": rev,
                    "transaction_id": f"width-{rev}",
                    "operations": [
                        {"op": "adjust_parameter", "id": "width", "delta_mm": "1"}
                    ],
                    "preserve": ["thickness", "radius", "margin", "depth"],
                }
            )
        uncached = Store(path)
        uncached.evaluations = ResultCache(max_entries=0)
        inspect = {"action": "inspect"}
        preview = {
            "action": "preview",
            "expected_revision": 65,
            "operations": [{"op": "adjust_parameter", "id": "width", "delta_mm": "1"}],
            "preserve": ["thickness", "radius", "margin", "depth"],
        }
        rows.append(
            measure(
                "uncached_inspect_64_history",
                lambda: uncached.execute(inspect),
                samples,
            )
        )
        rows.append(
            measure(
                "fresh_host_inspect_64_history",
                lambda: Store(path).execute(inspect),
                samples,
            )
        )
        store.execute(inspect)
        rows.append(
            measure(
                "warm_host_inspect_64_history", lambda: store.execute(inspect), samples
            )
        )
        rows.append(
            measure(
                "warm_host_preview_64_history", lambda: store.execute(preview), samples
            )
        )
        meshes = ResultCache(max_entries=32, max_bytes=16 * 1024 * 1024)
        rows.append(
            measure(
                "uncached_display_bracket",
                lambda: display({"result": store.execute(inspect)}),
                samples,
            )
        )
        display({"result": store.execute(inspect)}, meshes)
        rows.append(
            measure(
                "warm_display_bracket",
                lambda: display({"result": store.execute(inspect)}, meshes),
                samples,
            )
        )
        caches = {
            "evaluation_bytes": store.evaluations.bytes,
            "evaluation_entries": len(store.evaluations.entries),
            "evaluation_hits": store.evaluations.hits,
            "evaluation_misses": store.evaluations.misses,
            "mesh_bytes": meshes.bytes,
            "mesh_entries": len(meshes.entries),
        }
    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "base_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "rows": rows,
        "caches": caches,
        "host_peak_rss_bytes": peak_rss_bytes(resource.RUSAGE_SELF),
        "largest_child_peak_rss_bytes": peak_rss_bytes(resource.RUSAGE_CHILDREN),
        "limits": "Sequential measurements on one machine with shared OS caches. Fresh host means a new Store/cache, not cold OS or a new Python process. CPU time sums host and reaped child user/system CPU; RSS values are whole-run high-water marks, not simultaneous aggregate memory or per-operation allocations. No geometry algorithm speedup, feature-level incremental evaluation, GPU compute or generalized throughput guarantee is claimed.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 3 <= args.samples <= 30:
        parser.error("Use 3..30 samples")
    result = main(args.samples)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    for row in result["rows"]:
        print(
            row["name"],
            round(row["wall_median_ms"], 2),
            "ms wall",
            round(row["cpu_median_ms"], 2),
            "ms CPU",
        )
