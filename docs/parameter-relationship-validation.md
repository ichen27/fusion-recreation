# Parameter relationship validation — 2026-10-19

## Delivered behavior

Exact affine rules now drive parameter values before geometry validation. The symmetric-profile fixture declares `tip_x = width / 2`: width 100→120 moves the tip 50→60 mm while thickness remains 12 mm. The same rules and computed values persist through preview/save/reopen/undo, and both browser edits and typed MCP calls use the Rust evaluator.

The [platform delivery plan](platform-delivery-plan.md) records the confirmed full-platform scope. This is one completed bounded capability, not completion of that platform or a general sketch solver.

## Verification

- 36 model/HTTP integration tests pass, including 10 relationship tests. Coverage includes exact signed fractions, 40 seeded affine combinations, dependency chains/diamonds, the full 64-parameter depth, cycle paths, missing references, malformed fields/numbers, zero-coefficient rejection, eight-term limit and intermediate overflow.
- Derived targets reject direct set/adjust operations. Explicit rule replacement works; removal freezes the current computed value and permits subsequent independent edits. Fixed dependent parameters and preserve preconditions reject upstream changes. Fixing after an upstream edit captures the newly computed value without overwriting an existing fixed invariant.
- Stored derived values are checked against their relationships; stale values reject instead of being silently repaired. Failed transactions leave the document unchanged. Replay receipts, previews, persistence, undo and redo are tested with actual compiled geometry.
- Real MCP stdio accepts relationship operations, widens an input, reports both changed parameter IDs, rejects direct dependent edits and restores values through undo. No new natural-language inference run is claimed.
- Browser verification shows the derived field and formula, prevents direct editing, previews/saves width changes with the dependent tip moving, and restores both values through undo/redo. A collapsed profile edit is rejected without changing the saved solid. Screenshot visually inspected; no page errors reported.
- Earlier block/corner conversation and profile extrusion artifacts replay unchanged. All 104 existing Python geometry/document test executions pass. Rust format/Clippy, Python lint/format and JavaScript syntax/format are checked, with CI covering the new replay.

## Initial host performance baseline

Ten sequential samples per operation on the Mac mini (ARM64), using the built release engine and system Python. These are measurements of the complete local host call, including Rust process launch and serialization. They are not cold-start guarantees or GPU measurements.

| Operation | Median ms | p95 ms |
|---|---:|---:|
| evaluate_profile_with_relationship | 4.18 | 4.84 |
| inspect_one_undo_snapshot | 10.58 | 11.51 |
| inspect_64_undo_snapshots | 282.42 | 289.06 |
| preview_64_undo_snapshots | 281.23 | 330.68 |

[Raw measurements and source hashes](../examples/ai-cad/relationships/host-latency.json). The 64-history fixture is built through 64 actual width edits. The host currently revalidates every saved history model; the substantially higher inspect/preview cost identifies a concrete target for caching/incremental validation. This observation does not justify skipping document validation or selecting GPU compute without further measurements. Kernel-only time, peak memory, GPU upload/frame cost and concurrency are not measured here.

## Reproduction and limits

[Example artifacts and commands](../examples/ai-cad/relationships/README.md) include editable snapshots, exact replies and the screenshot. Run standard validation from [the quickstart](../tools/ai-cad/README.md), then `python3 tools/ai-cad/verify_relationship_example.py`. Run `python3 tools/ai-cad/benchmark_workflow.py --samples 10` for a local informational baseline; timing is not a CI pass/fail gate.

Relationships are bounded directed affine rules in millimeters, not nonlinear geometric constraints. Generated face/edge identity, analytic holes, exports and broader platform gates remain unimplemented in this change. Old documents remain compatible; older binaries reject relationship-bearing documents. Restart connected clients after upgrading to load the new MCP schemas. The existing working document and client configuration are preserved.
