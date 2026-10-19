# Reuse validated geometry within a request

The Rust evaluator validates the original document before applying an edit. Previously it then rebuilt all geometry again, even for inspection or an edit confined to the last feature. It now transfers the unchanged feature prefix from that first evaluation and rebuilds only the suffix beginning at the first changed feature or referenced parameter value.

Feature definitions must match exactly, including order, kind, inputs, plane normals, vertex/hole IDs and placements. The existing exhaustive feature-reference table identifies direct parameters. Affine relationships are refreshed before comparing their resolved values. Prefix validity follows declaration order: every feature input must refer to an earlier validated feature. Rebuilding the whole suffix is deliberately conservative; an independent feature after the first change is rebuilt too.

Intermediate profiles, analytic solids and exact planar cells move into the new evaluation without cloning complete geometry. Consumption checkpoints restore the terminal-body set at the retained boundary: removing a Boolean restores its inputs, while adding a second consumer still rejects. Global parameter, relationship, fixed-value, model-size and preserve checks remain active. Invalid starting documents reject before edits, even if an edit would repair them.

No geometry cache is accepted from a client or loaded from disk. Reuse lasts for one engine request; the process still exits afterward. Existing cancellation, time limits, document locking, revision checks and host result-cache invalidation apply. The 32-feature model cap bounds retained intermediates; at most 33 small consumption checkpoints contain at most 32 feature IDs each.

## Measured CPU effect

[Full report](comparison.json) retains seven samples per case, alternating old/new subprocess order, exact-result hashes, executable hashes and platform details. These are whole CLI wall times, including startup and serialization, on one Mac mini. The baseline executable came from source `a8cd18815baf214a57a98126860530edc810a5b2`; the comparison runs the prefix-reuse implementation. Every sampled result is identical to the baseline JSON.

| Workload | Before median | After median | Input / output |
|---|---:|---:|---|
| Cavity inspection | 44.54 ms | 23.29 ms | [request](cavity_inspect.request.json) / [reply](cavity_inspect.response.json) |
| Cavity root-height edit | 44.04 ms | 44.35 ms | [request](cavity_dimension_edit.request.json) / [reply](cavity_dimension_edit.response.json) |
| Independent block edit after cavity | 45.02 ms | 24.07 ms | [request](late_independent_edit.request.json) / [reply](late_independent_edit.response.json) |
| 32-feature linked-part inspection | 41.43 ms | 22.15 ms | [request](linked_32_inspect.request.json) / [reply](linked_32_inspect.response.json) |
| Last linked placement edit | 41.46 ms | 22.83 ms | [request](linked_32_last_placement.request.json) / [reply](linked_32_last_placement.response.json) |
| Shared root-dimension edit | 41.52 ms | 41.41 ms | [request](linked_32_root_dimension.request.json) / [reply](linked_32_root_dimension.response.json) |

Root edits show no meaningful gain because the suffix includes essentially all geometry. Inspections and late edits improve by roughly 1.8–1.9× in these fixtures. This is not a browser frame-rate, GPU-compute or large-assembly throughput claim. The largest child-process RSS high-water mark observed across the run was 5,193,728 bytes; it is not simultaneous total memory or a per-operation allocation measurement. Shared OS caches and other machine activity can affect timing. CI checks exact replies without imposing a timing threshold.

## Verification and reproduction

Ten Rust tests include differential comparison with a full-rebuild path across all 63 checked-in `.model.json` fixtures, inspection and four parameter edits per fixture. Focused tests cover prefix boundaries, topology consumption, feature removal/reordering, shared relations, cycles, fixed/preserve conflicts and invalid starting models. The 160 Python tests, actual MCP transport and retained browser cancellation/edit/measurement replay also pass.

After the [normal build/setup](../../../tools/ai-cad/README.md):

```sh
cargo +1.85.1 test --release --locked --manifest-path crates/model-engine/Cargo.toml
python3 tools/ai-cad/verify_rebuild.py
```

To reproduce comparative timing, build the baseline revision above in a separate checkout and provide its executable:

```sh
python3 tools/ai-cad/benchmark_rebuild.py --before /path/to/baseline/model-engine --output work/rebuild-comparison
```

The output includes requests, complete replies and a fresh timing report. This stage reduces duplicate work inside one transaction. Reuse across requests, dependency-based reuse after an early unrelated change, persistent workers and broader scheduling remain open.
