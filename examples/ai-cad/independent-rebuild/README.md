# Independent feature rebuilds

The original engine now reuses unchanged geometry later in a transaction's history, even when an earlier independent feature changed. It still validates the complete starting model. No geometry is cached between requests.

A feature must retain its history position, definition and referenced parameter values. Every input ancestor must also qualify. Before restoring cached geometry, its consumed-input set must match the original checkpoint exactly; otherwise the feature is evaluated normally. This prevents reuse from hiding a newly invalid second consumer. Global constraints and feature IDs are always validated.

## Retained artifacts

- [source.cad.json](source.cad.json), [edited.cad.json](edited.cad.json), [undo.cad.json](undo.cad.json): editable four-cavity workload and history snapshots. Parts intentionally occupy the same coordinates to repeat the same geometry cost across independent feature branches; this is not a physical assembly layout.
- [mcp-recording.json](mcp-recording.json): five actual stdio MCP calls creating the model, previewing/saving a first-branch edit, rejecting zero height and undoing.
- `*.request.json`: five portable native requests for first/last/profile edits, linked drivers and a constraint-only transaction.
- [benchmark.json](benchmark.json): raw wall samples, isolated CPU/RSS phases, machine/runtime details and request/reply/executable hashes.

## Measured results

Apple M4, 10 physical/logical CPUs and 16 GiB memory. Nine measured worker calls follow one warmup in each separately launched phase. All five baseline/current and fresh/worker responses agree exactly. Baseline source is `ccc63c5a1332b5c24d73b762aabf6602601a27cc`.

| Transaction | Prefix baseline median | Dependency reuse median |
|---|---:|---:|
| Edit first cavity height | 165.19 ms | 101.57 ms |
| Edit last cavity height | 103.14 ms | 102.45 ms |
| Edit first outline | 165.89 ms | 102.87 ms |
| Edit two linked branches | 164.88 ms | 123.29 ms |
| Add fixed constraint | 83.34 ms | 82.80 ms |

Native peak RSS was about 5.9–6.1 MB across these phases. CPU/RSS includes worker startup, warmup and shutdown; wall samples exclude warmup. Baseline/current phase order alternates by workload. The retained run followed completion of this task's tests. These are workload observations, not latency or memory guarantees. No concurrent workload, host-cache hit, GPU activity or browser frame timing is measured.

## Reproduce

Build the release engine following the [quickstart](../../../tools/ai-cad/README.md):

```sh
python tools/ai-cad/verify_independent_rebuild.py
python tools/ai-cad/benchmark_independent_rebuild.py --samples 9
# Optionally compare a separately built prefix-baseline executable:
python tools/ai-cad/benchmark_independent_rebuild.py --samples 9 --baseline /path/to/baseline/model-engine
# With MCP dependencies installed:
python tools/ai-cad/verify_independent_rebuild_mcp.py
```

The replay verifies current canonical reply hashes against both retained versions and replays native/MCP history. Rust tests compare reuse and full rebuilding across the existing model corpus, positive/zero parameter edits, removed consumers, structural edits, fixed/derived constraints and invalid starting models. A targeted test checks reused independent geometry, changed ancestry and conflicting consumption.

Reordering conservatively invalidates reuse. A changed ancestor invalidates dependent features even if the final geometry might happen to be equivalent. Original and rebuilt geometry may coexist within bounded transaction memory. Cross-request caches, arbitrary dependency reorder reuse and parallel geometry execution remain separate work.
