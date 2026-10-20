# Curved geometry CPU and worker baseline

Seven editable source models exercise evaluation, 128-segment mesh generation, analytic topology and exact measurement. Each fresh-process/worker phase runs in its own driver process; replies must match exactly. This measures native CPU and transport cost, with host caches bypassed.

Recorded on Apple M4 (10 CPU cores, 16 GiB RAM), seven timed calls after one warmup. Baseline engine source: `2763a58af1a77c27d144f22a4e3f035604c9fc13`. These are observations on this machine, not portable performance thresholds.

| Model / evaluate | Fresh median ms | Worker median ms | Worker native CPU ms/call* | Worker peak native MiB |
|---|---:|---:|---:|---:|
| revolution | 2.52 | 0.15 | 0.32 | 3.36 |
| tapered_ring | 2.22 | 0.12 | 0.28 | 3.33 |
| concave_sweep | 8.45 | 5.79 | 5.95 | 4.69 |
| curved_intersection | 2.46 | 0.29 | 0.45 | 3.59 |
| blind_cut | 14.78 | 11.79 | 11.90 | 4.72 |
| stepped_union | 54.61 | 51.37 | 51.46 | 4.97 |
| nested_cut | 49.64 | 46.32 | 46.42 | 5.00 |

*Native CPU includes warmup and startup/shutdown, divided by all eight calls. Wall medians exclude warmup and driver response comparisons. Worker CPU/RSS is collected after the child is reaped. RSS is each isolated phase’s native-process high-water mark, not whole-application memory or allocations per call.

The worker removes most launch overhead on simple analytic geometry. Stepped unions and nested cuts remain dominated by native geometry work; replacing transport alone does not resolve that cost. The current radial Boolean embeds sections as 3D unit prisms and invokes the planar-cell engine. A direct exact 2D section algorithm is the next optimization candidate and must preserve material/topology validation.

| Artifact | Purpose |
|---|---|
| [benchmark.json](benchmark.json) | Raw samples, CPU/RSS counters, hardware, binary and request/reply hashes for all 28 workloads |
| `*-*.request.json` | All 28 exact requests, directly usable with the native executable |
| Source models linked in `benchmark.json` | Editable sources under the adjacent example directories |

After the [quickstart](../../../tools/ai-cad/README.md):

```sh
python3 tools/ai-cad/benchmark_curved_runtime.py --samples 7
```

Use `--write` to replace the recorded report and request artifacts with a new measurement. The script runs serially, alternates phase order across workloads and enforces response equivalence. It does not measure concurrent throughput, GPU computation/rendering, export, AI inference, cold filesystem cache or cross-request geometry caching. Exact geometry remains CPU work; GPU display buffers are separately verified in the [navigation example](../navigation/README.md).
