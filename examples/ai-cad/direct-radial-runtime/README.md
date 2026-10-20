# Direct exact radial boundaries

Coaxial joins and cuts now construct their boundary directly in radius/height space. Segments split at exact crossings and overlap endpoints; winding and edge direction classify the material on each side. This removes temporary 3D unit prisms and their cell decomposition. No epsilon offsets or mesh approximations enter native geometry.

| Worker evaluation | Before ms | After ms | Before native MiB | After native MiB |
|---|---:|---:|---:|---:|
| revolution | 0.153 | 0.184 | 3.36 | 3.38 |
| tapered_ring | 0.118 | 0.117 | 3.33 | 3.25 |
| concave_sweep | 5.790 | 5.963 | 4.69 | 4.66 |
| curved_intersection | 0.285 | 0.269 | 3.59 | 3.59 |
| blind_cut | 11.788 | 0.306 | 4.72 | 3.59 |
| stepped_union | 51.367 | 0.431 | 4.97 | 3.69 |
| nested_cut | 46.322 | 0.611 | 5.00 | 3.80 |

Both runs used Apple M4, seven warm timed samples per phase and isolated native CPU/RSS accounting. The baseline is retained in [curved-runtime](../curved-runtime/README.md). Small differences in unaffected paths are run-to-run variation; no improvement is claimed there. These single-machine observations are not latency guarantees or concurrent throughput measurements.

Validation includes 135 rational boundary/error comparisons against the independent legacy 3D cell path; coincident, partial overlap, point/edge contact, concavity and 1e-40 gaps; all 28 saved benchmark request/reply hashes unchanged; 254 Python checks; 26 Rust tests; saved browser/native/STL replay; ten fresh typed MCP calls; fourteen independently constructed reference Booleans with28 STEP readbacks, directed residuals and exact moments.

| Artifact | Purpose |
|---|---|
| [benchmark.json](benchmark.json) | New raw timings, CPU/RSS, hardware and request/reply/binary hashes |
| [comparison.json](comparison.json) | All28 before/after measurements and strict hash equivalence |
| `*-*.request.json` | The exact portable requests used by the measurement |
| [Source and exports](../coaxial-booleans/README.md) | Editable feature models, browser/native recordings and reference STEP files |

After the [quickstart](../../../tools/ai-cad/README.md):

```sh
cargo test --release --manifest-path crates/model-engine/Cargo.toml section_boolean
python3 tools/ai-cad/benchmark_curved_runtime.py --samples 7
python3 tools/ai-cad/verify_coaxial_boolean.py
python3 tools/ai-cad/verify_coaxial_boolean_export.py
```

The last command needs the optional STEP comparison environment. To record a separate performance run, pass `--write --output-dir <directory>` to the benchmark. The retained baseline is not overwritten by that option.

Limits remain one connected simple result section, at most32 simplified corners, flat-ended single axis contact, and no enclosed radial contour holes. Intermediate radial coordinates are bounded to1024 bits and4096 atomic segments; 3D construction cell/patch budgets no longer apply. Branching/touching contours reject. The established generated-surface ordering is retained for the recorded corpus, but these names remain revision-only. No general noncoaxial curved Boolean or GPU geometry computation is added.
