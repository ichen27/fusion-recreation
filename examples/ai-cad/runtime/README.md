# Runtime measurements and bounded reuse

Measured on the development Mac mini (Apple M4, arm64, 16 GB unified RAM), 2026-10-19. These are observations on small specified workloads, not guaranteed latency targets.

| Workload | Before median | After median |
|---|---:|---:|
| Inspect profile, 64 undo states | 262.08 ms | 2.01 ms warm |
| Preview width edit, 64 undo states | 261.15 ms | 6.17 ms warm |
| Orbit bracket, 60 frames: mesh uploads | 120 calls / 4,550,400 bytes | 0 calls / 0 bytes |
| Orbit bracket CPU event/draw submission | 0.20 ms | 0.10 ms |
| GPU timer median | 0.508 ms | 0.527 ms |

The GPU timing difference does not establish an improvement or regression. Frame interval medians remained approximately 16.7 ms. The renderer identified itself as **ANGLE Metal Renderer: Apple M4**; GPU timer queries were available and non-disjoint. These are browser query measurements, not physical display latency or hardware utilization counters.

A separate bracket benchmark with 64 history states measured uncached inspection at 236.03 ms wall / 218.61 ms CPU, fresh host cache at 230.68 ms wall / 213.34 ms CPU, warm inspect at 2.00 ms wall / 2.00 ms CPU and warm preview at 5.66 ms wall / 5.36 ms CPU. Full raw samples and whole-run RSS high-water marks are in the files below. Fresh host means a new Store object; OS and Python process caches remain warm.

## Changes behind the measurements

- Per-Store successful no-operation evaluations are retained in a bounded LRU: at most 128 entries / 8 MiB encoded data including keys. Every load still reads the document, verifies its checksum/schema/revision/receipts and checks every history model against validated content or the Rust evaluator. New edits always evaluate through Rust. Unknown or modified history does not inherit trust from a matching revision.
- The cache key includes canonical model content and engine file device/inode/size/mtime/ctime. Replacing, modifying or removing the executable prevents reuse. This is ordinary local file-change detection, not an adversarial executable-integrity mechanism.
- Each HTTP handler has a separate mesh LRU capped at 32 entries / 16 MiB. Entries use full model content, body ID, segment count and engine identity. No cache is written into the native document. Decoding stored JSON gives callers independent objects; mutations cannot poison future hits. Failures and oversized results are not cached. Cache byte limits cover encoded payloads/keys, not Python object overhead.
- The viewer uploads combined triangle/line vertex data only when geometry changes, retaining it for camera movement and resize. Context restoration recreates resources and uploads again. Exact CPU geometry is unchanged. There is no feature-level incremental kernel, cancellation scheduler or GPU geometry compute yet.

## Files and reproduction

| File | Meaning |
|---|---|
| [host-before.json](host-before.json), [host-after.json](host-after.json) | Existing profile workload, 10 samples and source hashes |
| [cpu-memory.json](cpu-memory.json) | Bracket workload, 5 samples, host+child CPU time, cache sizes and RSS |
| [browser-before.json](browser-before.json), [browser-after.json](browser-after.json) | 60 synthetic orbit frames, upload counts, CPU/frame/GPU samples and renderer identity |

From the repository root, after the normal locked release build:

```sh
python3 tools/ai-cad/benchmark_workflow.py --samples 10 --output work/host.json
python3 tools/ai-cad/benchmark_runtime.py --samples 5 --output work/runtime.json
python3 tools/ai-cad/viewer.py --store work/bracket.cad.json
# With agent-browser installed, in another terminal:
agent-browser --session cad-benchmark open http://127.0.0.1:8765
agent-browser --session cad-benchmark --json eval --stdin < tools/ai-cad/benchmark_browser.js
agent-browser --session cad-benchmark close
```

Create the bracket document using the [bracket quickstart](../bracket/README.md). Before measurements use the implementation at PR 9; after measurements use this checkpoint. Do not treat a repeated warm sample as a cold-machine run. `ru_maxrss` reports the host's whole-run high-water RSS and the largest reaped child's high-water RSS, not their simultaneous sum. Browser memory, large assemblies and MacBook-client hardware remain unmeasured.

51 integration tests pass, including cache eviction/mutation isolation, executable replacement, external edits, valid-checksum corrupt history, revision/precondition enforcement and display reuse. MCP and all four native/replay fixtures remain unchanged. Browser context loss/restoration was exercised with `WEBGL_lose_context`, with no console errors. Timing results are informational, not CI pass thresholds.
